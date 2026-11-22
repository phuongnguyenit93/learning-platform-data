# Theo dõi sai lệch cấu hình và sự cố hạ tầng

Môi trường kiểm thử chỉ cung cấp bằng chứng đáng tin khi cấu hình, tài nguyên và dịch vụ phụ thuộc được kiểm soát. Một thay đổi ngoài kế hoạch về biến môi trường, quyền truy cập, phiên bản runtime, DNS, chứng chỉ, database hoặc giới hạn tài nguyên có thể khiến test thất bại dù mã nguồn không đổi. Ngược lại, một lỗi hạ tầng có thể bị hiểu nhầm là lỗi sản phẩm nếu nhóm không có đủ thông tin để phân biệt nguyên nhân.

Theo dõi sai lệch cấu hình và sự cố hạ tầng là hoạt động liên tục nhằm phát hiện khác biệt giữa trạng thái mong muốn và trạng thái thực tế, xác định ảnh hưởng đến kiểm thử, xử lý sự cố và giữ lại bằng chứng về môi trường đã chạy. Mục tiêu là giúp nhóm biết môi trường nào đang đáng tin, kết quả nào cần chạy lại và thay đổi nào cần được phê duyệt.

## 1. Phân biệt sai lệch cấu hình, thay đổi hợp lệ và sự cố hạ tầng

Trước khi xử lý, cần phân loại đúng hiện tượng. Không phải mọi khác biệt đều là sai lệch cần sửa và không phải mọi lần test thất bại đều do hạ tầng.

- **Cấu hình mong muốn (desired configuration):** trạng thái được định nghĩa trong nguồn chuẩn đã được phê duyệt, chẳng hạn Infrastructure as Code, manifest, cấu hình pipeline hoặc baseline môi trường.
- **Cấu hình thực tế (observed configuration):** trạng thái đang có trên máy chủ, container, cluster, dịch vụ cloud, database, mạng hoặc công cụ kiểm thử.
- **Sai lệch cấu hình (configuration drift):** khác biệt giữa trạng thái thực tế và trạng thái mong muốn mà không có quyết định hoặc ngoại lệ hợp lệ tương ứng.
- **Thay đổi có chủ đích:** khác biệt đã được phê duyệt, có lý do, phạm vi và thời hạn. Nó cần được phản ánh vào nguồn chuẩn nếu tiếp tục tồn tại.
- **Sai lệch tạm thời:** khác biệt phát sinh trong quá trình triển khai, autoscaling, failover hoặc thao tác kiểm tra và được dự kiến sẽ tự hết hoặc được dọn sau đó.
- **Sự cố hạ tầng (infrastructure incident):** tình trạng làm suy giảm hoặc mất khả năng cung cấp một thành phần hạ tầng cần thiết, ví dụ database không sẵn sàng, DNS lỗi, runner hết dung lượng hoặc mạng bị gián đoạn.
- **Lỗi môi trường kiểm thử:** môi trường không đáp ứng điều kiện đã thống nhất khiến kết quả kiểm thử không còn đại diện hoặc không thể tái hiện.

Một sai lệch cấu hình có thể chưa gây sự cố ngay, nhưng vẫn làm tăng rủi ro. Ví dụ, staging đang dùng phiên bản TLS cũ hơn baseline nhưng các test chức năng vẫn pass. Đây vẫn là sai lệch cần xử lý trước khi dùng staging để xác minh yêu cầu bảo mật hoặc khả năng tương thích.

Ngược lại, autoscaler tăng số lượng pod trong giới hạn chính sách có thể làm trạng thái quan sát khác với cấu hình tĩnh mà không phải drift. Cần so sánh với quy tắc và trạng thái mong muốn có tính đến những thay đổi động được phép.

## 2. Vì sao phải theo dõi cấu hình và hạ tầng trong chiến lược kiểm thử?

Kết quả kiểm thử phụ thuộc vào cả ứng dụng lẫn môi trường. Khi môi trường thay đổi mà không được ghi nhận, nhóm có thể đưa ra kết luận sai về chất lượng sản phẩm.

Các hậu quả thường gặp:

- Test pass trên một môi trường nhưng fail trên môi trường khác do phiên bản runtime hoặc dependency khác nhau.
- Lỗi chỉ xuất hiện khi database có cấu hình connection pool hoặc isolation khác baseline.
- Kiểm thử hiệu năng cho kết quả không thể so sánh vì CPU, memory, autoscaling hoặc dữ liệu đã thay đổi.
- Kiểm thử bảo mật bỏ sót vấn đề vì firewall, IAM hoặc TLS được cấu hình khác với môi trường mục tiêu.
- CI thất bại ngẫu nhiên do runner thiếu tài nguyên, DNS chập chờn hoặc dịch vụ phụ thuộc không sẵn sàng.
- Nhóm sửa mã nguồn để xử lý một lỗi thực chất do môi trường, tạo thêm thay đổi không cần thiết.
- Báo cáo kiểm thử không thể tái lập vì không biết cấu hình nào đã được dùng.
- Một thay đổi khẩn cấp trên staging tồn tại lâu dài nhưng không được đưa vào nguồn cấu hình chuẩn.

Vì vậy, mỗi kết quả kiểm thử quan trọng nên liên kết với phiên bản ứng dụng, phiên bản cấu hình, môi trường, thời điểm và trạng thái hạ tầng liên quan. Khi phát hiện sự cố, nhóm có thể xác định những kết quả nào bị ảnh hưởng và cần chạy lại.

## 3. Thiết lập baseline và nguồn cấu hình chuẩn

Theo dõi drift cần một trạng thái mong muốn rõ ràng. Nếu baseline không có chủ sở hữu hoặc đã lỗi thời, công cụ có thể báo quá nhiều khác biệt không có ý nghĩa hoặc bỏ qua thay đổi thực sự quan trọng.

Nguồn chuẩn có thể gồm:

- Repository Infrastructure as Code cho mạng, compute, storage và dịch vụ cloud.
- Manifest hoặc Helm chart cho Kubernetes và nền tảng container.
- File cấu hình ứng dụng theo môi trường.
- Quy tắc bảo mật, IAM, firewall và network policy.
- Cấu hình database, cache, queue và reverse proxy.
- Định nghĩa runner, image build và pipeline CI.
- Danh mục phiên bản runtime, hệ điều hành và dependency.
- Runbook, sơ đồ phụ thuộc và hồ sơ thay đổi đã phê duyệt.

Baseline nên có phiên bản, người sở hữu và quy trình thay đổi. Mỗi môi trường cần có định nghĩa rõ phần nào giống nhau và phần nào được phép khác nhau. Ví dụ, staging có thể dùng ít instance hơn production, nhưng vẫn cần giữ cùng phiên bản database, chính sách TLS và cấu hình logic ảnh hưởng đến kết quả kiểm thử.

Không nên sao chép toàn bộ cấu hình production sang staging một cách máy móc. Hãy xác định những thuộc tính phải tương đương, những thuộc tính được phép giảm quy mô và những khác biệt phải ghi nhận. Với mỗi khác biệt, mô tả tác động đến loại kiểm thử có thể chạy.

## 4. Lập danh mục thành phần và thuộc tính cần giám sát

Không thể theo dõi mọi tham số với cùng mức chi tiết. Hãy lập danh mục các thành phần có ảnh hưởng đến độ tin cậy của môi trường và kết quả kiểm thử.

| Nhóm | Thuộc tính cần theo dõi | Ví dụ sai lệch hoặc sự cố |
|---|---|---|
| Hệ điều hành và runtime | Phiên bản, patch, timezone, locale, kernel | Runner dùng JDK hoặc Node runtime khác baseline |
| Container và image | Image digest, tag, resource limit, security context | Tag thay đổi nhưng không có bản dựng mới được phê duyệt |
| Cluster và compute | Node pool, replica, CPU, memory, autoscaling | Pod bị giới hạn CPU thấp hơn cấu hình |
| Mạng | DNS, route, firewall, ingress, proxy, TLS | Staging không kết nối được dịch vụ phụ |
| IAM và secret | Role, policy, service account, quyền, thời hạn secret | Pipeline được cấp quyền ghi rộng hơn cần thiết |
| Database | Engine version, schema, parameter, connection pool, storage | Parameter hoặc schema lệch baseline |
| Cache và queue | Phiên bản, TTL, retention, partition, retry, capacity | Queue đầy hoặc retention ngắn hơn yêu cầu |
| Storage | Bucket policy, encryption, quota, lifecycle | Object không được mã hóa theo chính sách |
| Dịch vụ phụ thuộc | Endpoint, sandbox, quota, health, timeout | Nhà cung cấp sandbox ngừng phản hồi |
| Công cụ kiểm thử | Runner image, browser, driver, test agent | Browser tự cập nhật làm thay đổi kết quả |

Mỗi mục nên có chủ sở hữu, mức quan trọng, cách thu thập trạng thái, tần suất kiểm tra, ngưỡng cảnh báo và cách khắc phục. Không cần cảnh báo mọi thay đổi nhỏ; ưu tiên thuộc tính ảnh hưởng đến bảo mật, tính đúng đắn, khả năng tái lập và hiệu năng.

## 5. Phát hiện drift bằng kiểm tra chủ động và giám sát liên tục

Có thể kết hợp kiểm tra theo lịch, kiểm tra khi có thay đổi và quan sát liên tục.

### 5.1. So sánh với nguồn chuẩn

Công cụ quản lý cấu hình hoặc Infrastructure as Code có thể so sánh trạng thái thực tế với khai báo mong muốn. Kết quả cần cho biết tài nguyên nào khác, thuộc tính nào thay đổi và nguồn nào được dùng làm baseline.

Một số cách tiếp cận:

- Chạy lệnh plan hoặc diff trước khi áp dụng thay đổi hạ tầng.
- Kiểm tra manifest đang chạy so với cấu hình trong repository.
- Quét policy để phát hiện cấu hình vi phạm chuẩn.
- Kiểm tra phiên bản package, runtime, image và dependency.
- Đối chiếu cấu hình IAM, firewall, TLS và quyền truy cập.
- Kiểm tra định kỳ database parameter và schema migration.

Cần phân biệt diff dự kiến trong một pull request với drift đã xảy ra trên môi trường. Báo cáo phải chỉ rõ trạng thái được so sánh, thời điểm thu thập và commit hoặc phiên bản baseline.

### 5.2. Kiểm tra khi triển khai và sau thay đổi

Một số drift xuất hiện ngay sau release, thay đổi cấu hình hoặc thao tác vận hành. Nên có kiểm tra trước và sau các mốc quan trọng:

- Trước khi cấp môi trường mới.
- Sau khi triển khai ứng dụng hoặc hạ tầng.
- Sau khi thay đổi quyền, secret, network policy hoặc chứng chỉ.
- Trước khi chạy kiểm thử hiệu năng hoặc bảo mật.
- Trước mốc nghiệm thu hoặc release candidate.
- Sau khi phục hồi hoặc failover.

Kiểm tra trước khi test giúp phát hiện môi trường chưa sẵn sàng. Kiểm tra sau khi test giúp xác nhận thử nghiệm không để lại cấu hình, dữ liệu hoặc tài nguyên bất thường.

### 5.3. Theo dõi tín hiệu vận hành

Metrics, logs, traces và health checks giúp phát hiện sự cố hạ tầng mà diff cấu hình không thể nhận ra. Ví dụ, cấu hình database không thay đổi nhưng kết nối bị từ chối vì hết connection; cluster vẫn có đủ node nhưng storage latency tăng; DNS record đúng nhưng resolver không hoạt động.

Theo dõi các tín hiệu như:

- Availability và health của dịch vụ.
- Tỷ lệ lỗi kết nối, timeout và retry.
- CPU, memory, disk, I/O và network saturation.
- Queue depth, consumer lag và thời gian xử lý.
- Database connection, lock, replication lag và storage.
- Runner queue time, disk space và process termination.
- Chứng chỉ sắp hết hạn và lỗi xác thực.
- Thời gian phản hồi của dịch vụ phụ thuộc.

Cần thiết kế ngưỡng cảnh báo dựa trên mức ảnh hưởng và hành vi bình thường. Cảnh báo quá nhạy có thể làm nhóm bỏ qua tín hiệu; cảnh báo quá rộng có thể không phát hiện sự cố trước khi ảnh hưởng đến test.

## 6. Phân loại sai lệch và xác định mức độ ảnh hưởng

Sau khi phát hiện, không nên tự động áp dụng baseline hoặc đóng cảnh báo. Trước tiên hãy xác định khác biệt có được phép không và ảnh hưởng đến kiểm thử ra sao.

Có thể phân loại như sau:

- **Đã phê duyệt:** thay đổi có ticket, chủ sở hữu, lý do và thời hạn rõ.
- **Ngoài kế hoạch:** thay đổi không có quyết định tương ứng hoặc không được phản ánh trong nguồn chuẩn.
- **Tạm thời:** khác biệt có thời hạn do autoscaling, failover, triển khai hoặc kiểm tra.
- **Không còn cần thiết:** tài nguyên hoặc cấu hình cũ còn sót sau khi một hoạt động kết thúc.
- **Chưa xác định:** chưa đủ thông tin để biết khác biệt có hợp lệ không.
- **Sự cố đang diễn ra:** khác biệt đi kèm suy giảm hoặc mất dịch vụ.

Đánh giá mức độ ảnh hưởng theo:

1. Thành phần và môi trường bị tác động.
2. Loại kiểm thử phụ thuộc vào thành phần đó.
3. Phạm vi người dùng, nhóm hoặc pipeline bị ảnh hưởng.
4. Tác động đến bảo mật, dữ liệu, tính đúng đắn và hiệu năng.
5. Khả năng tái hiện và mức độ kéo dài.
6. Có phương án thay thế hoặc môi trường khác không.
7. Kết quả kiểm thử nào có thể đã bị làm sai lệch.

Ví dụ, sai lệch timezone có thể ảnh hưởng test ngày hết hạn, lịch và báo cáo; sai lệch TLS có thể ảnh hưởng kiểm thử bảo mật và tích hợp; thiếu dung lượng runner có thể chỉ ảnh hưởng một số pipeline. Severity nên phản ánh hậu quả, còn priority phản ánh thứ tự cần xử lý.

## 7. Xây dựng quy trình triage và ghi nhận drift

Mỗi phát hiện cần được lưu trong nguồn quản lý thống nhất để có thể theo dõi từ lúc phát hiện đến khi xử lý.

Một bản ghi nên có:

| Trường | Nội dung |
|---|---|
| Mã phát hiện | ID duy nhất |
| Môi trường | Local, CI, integration, staging hoặc môi trường khác |
| Thành phần | Cluster, node, database, service, runner hoặc tài nguyên |
| Thuộc tính | Cấu hình hoặc tín hiệu bị sai lệch |
| Baseline | Phiên bản hoặc nguồn chuẩn được so sánh |
| Trạng thái thực tế | Giá trị quan sát, thời điểm và nguồn thu thập |
| Thời điểm bắt đầu | Lần đầu phát hiện hoặc khoảng thời gian ước tính |
| Phân loại | Đã duyệt, ngoài kế hoạch, tạm thời, chưa xác định hoặc incident |
| Ảnh hưởng | Test, nhóm, release và rủi ro liên quan |
| Chủ sở hữu | Người hoặc nhóm xử lý |
| Hành động | Điều tra, sửa, rollback, chấp nhận hoặc theo dõi |
| Bằng chứng đóng | Kết quả diff, health check và kiểm thử lại |

Quy trình triage:

1. Xác minh cảnh báo có đúng môi trường và tài nguyên không.
2. So sánh với baseline đúng phiên bản.
3. Kiểm tra change record, pipeline và thao tác gần thời điểm phát hiện.
4. Xác định drift có chủ đích, tạm thời hay không được phép.
5. Đánh giá ảnh hưởng và phạm vi test cần tạm dừng.
6. Gán chủ sở hữu và thời hạn.
7. Chọn cách xử lý và tiêu chí xác minh.
8. Lưu quyết định, bằng chứng và trạng thái.

Nếu chưa biết nguyên nhân, để trạng thái điều tra với người phụ trách và mốc cập nhật. Không đóng phát hiện chỉ vì cảnh báo biến mất trong lần quét tiếp theo; cần xác định nguyên nhân biến mất và bảo đảm trạng thái mong muốn đã được khôi phục.

## 8. Phân biệt lỗi sản phẩm với lỗi hạ tầng trong quá trình kiểm thử

Khi test fail, nhóm cần tránh kết luận vội. Một lỗi có thể do mã nguồn, cấu hình, dữ liệu, dịch vụ phụ thuộc, runner hoặc chính test.

Hãy thu thập:

- Build, commit và phiên bản test.
- Môi trường, cấu hình hiệu lực và thời điểm chạy.
- Log, metric, trace và mã tương quan.
- Trạng thái dịch vụ phụ thuộc.
- Kết quả chạy cùng test trên môi trường khác nếu phù hợp.
- Lịch sử thay đổi hạ tầng và cấu hình.
- Tình trạng runner, mạng, database và tài nguyên.
- Khả năng tái hiện bằng dữ liệu và điều kiện ban đầu.

Một cách phân tích hữu ích là kiểm tra giả thuyết theo từng lớp:

- Nếu cùng build và dữ liệu chạy ổn trên môi trường tương đương khác, điều tra sai lệch môi trường.
- Nếu nhiều test không liên quan cùng fail tại một thời điểm, xem xét hạ tầng hoặc dịch vụ dùng chung.
- Nếu chỉ một luồng fail và có dấu vết logic sai, điều tra sản phẩm.
- Nếu test fail ngẫu nhiên và không có bằng chứng sản phẩm thay đổi, xem xét race condition, dữ liệu dùng chung hoặc flaky test.
- Nếu lỗi chỉ xuất hiện khi cấu hình thay đổi, kiểm tra tác động của thuộc tính drift.

Đây là hướng điều tra, không phải quy tắc kết luận tự động. Một lỗi sản phẩm có thể chỉ xuất hiện trên một cấu hình cụ thể; một sự cố hạ tầng cũng có thể chỉ ảnh hưởng một luồng. Cần xác minh bằng bằng chứng.

Khi môi trường không đáp ứng điều kiện, đánh dấu kết quả là bị ảnh hưởng hoặc không hợp lệ theo quy trình. Không tính một lần chạy thất bại do runner mất kết nối như lỗi chức năng của sản phẩm.

## 9. Theo dõi sự cố hạ tầng và phối hợp ứng phó

Sự cố hạ tầng có thể làm gián đoạn pipeline, khiến môi trường không sẵn sàng hoặc làm sai lệch kết quả kiểm thử. Cần có quy trình incident rõ ràng.

### 9.1. Phát hiện và xác nhận

Nguồn phát hiện có thể là alert, health check, người dùng nội bộ, pipeline thất bại hoặc dashboard. Người nhận cần xác nhận:

- Thành phần nào đang lỗi?
- Môi trường và nhóm nào bị ảnh hưởng?
- Sự cố bắt đầu khi nào?
- Có thay đổi nào gần thời điểm đó?
- Có ảnh hưởng đến dữ liệu hoặc tính toàn vẹn không?
- Có giải pháp thay thế an toàn không?

### 9.2. Phân mức và thông báo

Dùng mức độ sự cố theo chính sách tổ chức. Một ví dụ:

| Mức | Tác động | Cách ứng phó |
|---|---|---|
| Critical | Mất môi trường trọng yếu, ảnh hưởng nhiều nhóm hoặc có nguy cơ dữ liệu/bảo mật | Kích hoạt quy trình incident, chỉ định incident lead và cập nhật thường xuyên |
| High | Một luồng hoặc nhóm kiểm thử quan trọng bị chặn, không có phương án thay thế | Ưu tiên khôi phục, thông báo các nhóm liên quan và đánh giá lịch release |
| Medium | Một phần chức năng môi trường suy giảm nhưng có workaround | Giao chủ sở hữu, theo dõi và lên kế hoạch sửa |
| Low | Ảnh hưởng nhỏ, không chặn hoạt động chính | Ghi nhận và xử lý theo backlog hoặc lịch bảo trì |

Tên mức, thời gian phản hồi và kênh thông báo cần tuân theo chính sách nội bộ. Không nên tự tạo SLA nếu tổ chức đã có quy định.

### 9.3. Khôi phục dịch vụ và xác nhận

Sau khi xử lý, không chỉ kiểm tra rằng máy chủ hoặc pod đã chạy. Cần xác minh chức năng phụ thuộc, dữ liệu, quyền và luồng kiểm thử liên quan hoạt động đúng. Nếu sự cố có thể làm hỏng dữ liệu test, cần tạo lại hoặc phục hồi dataset trước khi chạy lại.

Giữ timeline sự cố, quyết định, thay đổi đã thực hiện và bằng chứng phục hồi. Sau incident, tổ chức post-incident review để tìm nguyên nhân gốc và biện pháp ngăn tái diễn.

## 10. Xử lý drift an toàn: sửa, rollback hay chấp nhận có thời hạn

Khi đã xác nhận drift, có ba hướng xử lý thường gặp.

**Khôi phục baseline:** dùng khi thay đổi không được phép hoặc không có lý do hợp lệ. Cần xác minh nguồn chuẩn trước khi áp dụng để tránh ghi đè một thay đổi đúng nhưng chưa được cập nhật.

**Cập nhật baseline:** dùng khi thay đổi được phê duyệt và cần trở thành trạng thái mong muốn mới. Phải cập nhật mã cấu hình, review, kiểm tra diff và triển khai theo quy trình.

**Chấp nhận ngoại lệ có thời hạn:** dùng khi chưa thể sửa ngay nhưng có lý do rõ và rủi ro được người có thẩm quyền chấp nhận. Ngoại lệ cần có phạm vi, biện pháp giảm thiểu, người phê duyệt và ngày xem xét lại.

Không nên chạy lệnh tự động áp dụng toàn bộ baseline ngay khi phát hiện drift. Trước tiên cần xem diff, hiểu nguyên nhân và xác định tác động. Một thao tác tự động có thể xóa tài nguyên cần thiết, đảo ngược thay đổi khẩn cấp hoặc làm gián đoạn môi trường đang phục vụ kiểm thử.

Khi drift liên quan đến bảo mật, quyền truy cập rộng hoặc secret bị lộ, ưu tiên kiểm soát nguy cơ theo quy trình incident/security. Có thể cần thu hồi credential, giới hạn mạng hoặc cô lập môi trường trước khi hoàn tất điều tra.

## 11. Kiểm tra lại môi trường sau khi khắc phục

Sau khi sửa cấu hình hoặc khôi phục hạ tầng, cần chứng minh môi trường đã trở lại trạng thái phù hợp.

Một chuỗi xác minh có thể gồm:

1. Chạy lại kiểm tra diff với baseline đã được phê duyệt.
2. Xác minh phiên bản, cấu hình, quyền và trạng thái tài nguyên.
3. Chạy health check cho các thành phần và phụ thuộc quan trọng.
4. Kiểm tra dữ liệu, queue, cache và trạng thái còn sót nếu có ảnh hưởng.
5. Chạy smoke test để xác nhận luồng cơ bản.
6. Chạy lại những test bị ảnh hưởng bởi sự cố hoặc drift.
7. So sánh kết quả và ghi nhận giới hạn còn lại.
8. Cập nhật issue, change record và báo cáo môi trường.

Không cần chạy lại toàn bộ suite nếu phân tích tác động chứng minh chỉ một phạm vi bị ảnh hưởng và chính sách cho phép. Tuy nhiên, với thay đổi rộng như runtime, database, network hoặc IAM, có thể cần kiểm tra hồi quy rộng hơn.

Nếu không thể tái tạo chính xác trạng thái trước sự cố, ghi rõ khác biệt và đánh giá liệu kết quả mới có đủ đại diện. Đừng đánh dấu môi trường sẵn sàng chỉ dựa trên một health endpoint đơn lẻ.

## 12. Liên kết drift và incident với kết quả kiểm thử

Một môi trường có thể thay đổi trong khi nhiều pipeline đang chạy. Cần có khả năng xác định test run nào bị ảnh hưởng.

Mỗi lần chạy nên lưu:

- Environment ID và phiên bản baseline.
- Build hoặc commit của ứng dụng.
- Phiên bản image, runtime và dependency.
- Thời điểm bắt đầu/kết thúc.
- Cấu hình quan trọng hoặc fingerprint không chứa secret.
- Trạng thái health và incident đang mở.
- Run ID, correlation ID và người kích hoạt.

Khi có drift hoặc incident, dùng khoảng thời gian và thành phần bị ảnh hưởng để tìm các test run liên quan. Đánh dấu các kết quả có thể bị nhiễu, sau đó quyết định chạy lại, loại khỏi báo cáo hoặc giữ với chú thích.

Một fingerprint cấu hình có thể giúp so sánh môi trường mà không lưu bí mật. Fingerprint nên bỏ qua hoặc băm các giá trị nhạy cảm, đồng thời giữ tên thuộc tính, phiên bản và metadata cần thiết để xác định khác biệt.

## 13. Bảo vệ tính toàn vẹn và an toàn của dữ liệu cấu hình

Cấu hình môi trường có thể chứa secret, endpoint nội bộ, thông tin mạng và dữ liệu nhạy cảm. Báo cáo drift và incident phải đủ chi tiết để điều tra nhưng không tạo thêm rủi ro.

Thực hành cần áp dụng:

- Không ghi token, mật khẩu, private key hoặc secret thô vào log và ticket.
- Dùng secret manager và quyền tối thiểu cho pipeline.
- Che hoặc loại bỏ giá trị nhạy cảm khỏi diff và fingerprint.
- Kiểm soát ai được đọc baseline, trạng thái thực tế và báo cáo sự cố.
- Ghi lại người thay đổi, thời điểm, lý do và phê duyệt.
- Bảo vệ state file và artifact của công cụ Infrastructure as Code.
- Tách quyền phát hiện, quyền áp dụng cấu hình và quyền phê duyệt ngoại lệ khi cần.
- Thu hồi quyền tạm thời sau khi điều tra hoặc diễn tập kết thúc.

Không nên gửi toàn bộ cấu hình hệ thống vào kênh chat hoặc issue công khai. Chỉ chia sẻ phần cần thiết, dùng kho lưu có quyền truy cập phù hợp và liên kết đến bằng chứng được bảo vệ.

## 14. Đo lường chất lượng quản lý môi trường

Chỉ số giúp biết quy trình có phát hiện và xử lý vấn đề đủ sớm hay không. Có thể theo dõi:

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Số drift chưa được phê duyệt | Mức độ khác biệt ngoài kiểm soát | Tìm nhóm tài nguyên hoặc quy trình hay tạo thay đổi thủ công |
| Thời gian phát hiện drift | Khoảng từ lúc drift xuất hiện đến lúc được nhận diện | Đánh giá độ phủ của kiểm tra chủ động |
| Thời gian khôi phục baseline | Thời gian từ xác nhận đến khi trạng thái phù hợp | Tìm điểm nghẽn về quyền, chủ sở hữu hoặc triển khai |
| Số incident theo thành phần | Thành phần gây gián đoạn thường xuyên | Ưu tiên cải thiện độ tin cậy |
| Thời gian môi trường không sẵn sàng | Mức gián đoạn hoạt động kiểm thử | Đánh giá ảnh hưởng đến tiến độ và pipeline |
| Tỷ lệ test run bị ảnh hưởng | Mức độ kết quả kiểm thử bị nhiễu bởi hạ tầng | Xác định phạm vi và chi phí chạy lại |
| Tỷ lệ drift tái diễn | Hiệu quả của biện pháp ngăn ngừa | Tìm nguyên nhân gốc chưa được giải quyết |
| Ngoại lệ quá hạn | Rủi ro được chấp nhận nhưng chưa được xem lại | Theo dõi trách nhiệm và thời hạn |
| Tỷ lệ môi trường có baseline cập nhật | Mức độ bao phủ quản lý cấu hình | Tìm môi trường chưa được quản trị |

Không nên chỉ tối ưu số lượng drift bằng cách giảm độ nhạy hoặc loại bỏ tài nguyên khỏi phạm vi quét. Cần đọc chỉ số cùng thay đổi hệ thống, số lần triển khai và mức độ quan trọng của môi trường. Một môi trường có ít cảnh báo nhưng không được giám sát có thể kém tin cậy hơn môi trường phát hiện nhiều drift nhỏ và xử lý đúng.

## 15. Ví dụ: staging sai lệch cấu hình làm kiểm thử thanh toán thất bại

Giả sử một pipeline chạy smoke test thanh toán trên staging và nhận lỗi timeout. Cùng thời điểm, một số test tích hợp khác cũng thất bại khi gọi dịch vụ thanh toán sandbox.

Nhóm điều tra:

1. Xác nhận build ứng dụng và test không thay đổi so với lần chạy thành công gần nhất.
2. Kiểm tra trace để thấy request dừng ở ingress trước khi đến dịch vụ thanh toán.
3. So sánh cấu hình ingress và phát hiện timeout đã bị thay đổi thủ công.
4. Kiểm tra change record nhưng không tìm thấy phê duyệt tương ứng.
5. Xác định đây là drift ngoài kế hoạch, ảnh hưởng các test phụ thuộc ingress và thanh toán.
6. Tạm dừng các pipeline cần kết quả tin cậy trên staging, thông báo chủ sở hữu môi trường.
7. Rà soát baseline, xác nhận giá trị đúng và khôi phục qua quy trình thay đổi.
8. Chạy lại diff, health check, smoke test và các test thanh toán bị ảnh hưởng.
9. Ghi nhận nguyên nhân, người xử lý, thời điểm và bằng chứng.

Sau khi khôi phục, nhóm phát hiện thay đổi thủ công có thể lặp lại vì một quy trình hỗ trợ khẩn cấp không ghi thay đổi vào repository. Hành động phòng ngừa là yêu cầu mọi thay đổi staging đi qua change record, giới hạn quyền chỉnh sửa trực tiếp và chạy drift scan sau thao tác vận hành.

Nếu nguyên nhân thực tế là sandbox thanh toán ngừng hoạt động, nhóm sẽ ghi nhận incident của dịch vụ phụ thuộc thay vì khôi phục cấu hình ingress. Hai giả thuyết có thể tạo cùng biểu hiện timeout nhưng cần bằng chứng khác nhau và cách xử lý khác nhau.

## 16. Quy trình theo dõi drift và ứng phó incident

Có thể áp dụng quy trình tổng quát:

1. **Định nghĩa baseline:** xác định nguồn chuẩn, phiên bản, chủ sở hữu và khác biệt được phép theo môi trường.
2. **Lập danh mục:** chọn tài nguyên, thuộc tính và tín hiệu cần giám sát theo rủi ro.
3. **Thu thập trạng thái:** chạy diff, policy scan, health check và giám sát vận hành.
4. **Xác minh phát hiện:** kiểm tra thời điểm, nguồn, change record và tính đúng của cảnh báo.
5. **Phân loại:** drift đã duyệt, drift ngoài kế hoạch, drift tạm thời hoặc incident.
6. **Đánh giá tác động:** xác định môi trường, test run, dữ liệu và release bị ảnh hưởng.
7. **Giao trách nhiệm:** chỉ định chủ sở hữu, mức ưu tiên, thời hạn và kênh cập nhật.
8. **Xử lý:** khôi phục baseline, cập nhật nguồn chuẩn, cô lập hoặc chấp nhận ngoại lệ có thời hạn.
9. **Xác minh:** kiểm tra diff, health, smoke test và chạy lại test bị ảnh hưởng.
10. **Học hỏi:** phân tích nguyên nhân gốc, cập nhật kiểm soát và theo dõi drift tái diễn.

~~~mermaid
flowchart TD
    A["Baseline và danh mục môi trường"] --> B["Quét drift và theo dõi health"]
    B --> C["Phát hiện khác biệt hoặc sự cố"]
    C --> D["Xác minh nguồn, thời điểm và change record"]
    D --> E{"Thay đổi đã được phê duyệt?"}
    E -->|Có| F["Ghi nhận khác biệt hợp lệ và thời hạn"]
    E -->|Không / chưa rõ| G["Triage và đánh giá tác động"]
    G --> H{"Có incident đang diễn ra?"}
    H -->|Có| I["Kích hoạt ứng phó và khôi phục dịch vụ"]
    H -->|Không| J["Khôi phục baseline hoặc cập nhật nguồn chuẩn"]
    I --> K["Xác minh cấu hình và health"]
    J --> K
    K --> L["Chạy lại test bị ảnh hưởng"]
    L --> M["Lưu bằng chứng và phân tích nguyên nhân"]
    F --> N["Theo dõi và rà soát định kỳ"]
    M --> N
    N --> B
~~~

## 17. Checklist theo dõi sai lệch và sự cố hạ tầng

Trước khi dùng môi trường cho một đợt kiểm thử quan trọng, hãy kiểm tra:

- Baseline có nguồn chuẩn, phiên bản và chủ sở hữu rõ ràng không?
- Các khác biệt hợp lệ giữa môi trường đã được mô tả chưa?
- Thành phần quan trọng và thuộc tính cần theo dõi đã được lập danh mục chưa?
- Drift scan và health monitoring có lịch hoặc trigger phù hợp không?
- Báo cáo diff có ghi thời điểm, nguồn và giá trị nhưng không lộ secret không?
- Thay đổi thủ công có change record, người phê duyệt và thời hạn không?
- Có thể liên kết incident với build, môi trường và test run bị ảnh hưởng không?
- Quy trình triage phân biệt lỗi sản phẩm, lỗi test và lỗi hạ tầng chưa?
- Có chủ sở hữu, mức ưu tiên và hành động cho mỗi phát hiện không?
- Cách khôi phục baseline có được review trước khi áp dụng không?
- Ngoại lệ có biện pháp giảm thiểu và ngày xem xét lại không?
- Sau khắc phục có chạy diff, health check và test phù hợp không?
- Có cơ chế đánh dấu kết quả kiểm thử bị nhiễu và chạy lại không?
- Chỉ số drift, incident, thời gian phục hồi và ngoại lệ quá hạn có được xem xét định kỳ không?

Theo dõi sai lệch cấu hình và sự cố hạ tầng giúp nhóm phân biệt trạng thái môi trường với chất lượng của chính sản phẩm. Khi baseline có chủ sở hữu, thay đổi được truy vết, tín hiệu vận hành được giám sát và kết quả kiểm thử gắn với cấu hình thực tế, nhóm có thể phát hiện nguyên nhân sớm, tránh kết luận sai và khôi phục môi trường một cách có kiểm soát. Đây là điều kiện cần để các phép kiểm thử trên local, CI, staging và pre-production tạo ra bằng chứng đáng tin cậy.

