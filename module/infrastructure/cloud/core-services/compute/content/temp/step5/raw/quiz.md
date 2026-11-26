Câu 1. Khi tự động cấu hình máy ảo mới để chạy cùng một ứng dụng, đặc tính nào quan trọng nhất của script khởi tạo?
A. Lưu toàn bộ cấu hình trực tiếp trong snapshot của máy ảo.
B. Gắn bước cài đặt với tên máy cố định của từng instance.
C. Yêu cầu vận hành viên xác nhận trước mỗi lần tự khởi động.
D. Thiết kế các bước cài đặt có thể thực thi lặp an toàn.
Đáp án đúng: D

Câu 2. Tác vụ xử lý video mất vài phút và không cần trả kết quả ngay. Cách triển khai nào phù hợp?
A. Xử lý đồng bộ trong API và tăng timeout của request.
B. Đưa công việc vào hàng đợi và xử lý qua worker nền.
C. Đẩy tác vụ qua cron và chạy theo lịch mỗi giờ cố định.
D. Gửi lại request đến API liên tục cho đến khi xong.
Đáp án đúng: B

Câu 3. Trong kế hoạch khôi phục thảm họa, RPO mô tả điều gì?
A. Thời gian tối đa hệ thống được phép ngừng phục vụ.
B. Thời gian trung bình để phát hiện một lỗi nghiêm trọng.
C. Khoảng thời gian dữ liệu được phép mất khi xảy ra sự cố.
D. Khoảng thời gian tối đa được giữ lại các bản sao lưu.
Đáp án đúng: C

Câu 4. Khi đánh giá thiết kế compute, bằng chứng nào mạnh nhất cho khả năng chịu lỗi mất một availability zone?
A. Sơ đồ có hai máy ảo đặt trong cùng một zone.
B. Kết quả diễn tập mất một zone và đo thời gian phục hồi.
C. Bảng cấu hình máy ảo với RAM và CPU còn dư trong từng zone.
D. Nhật ký deploy thành công nhiều lần trên một máy.
Đáp án đúng: B

Câu 5. Với máy ảo IaaS, khách hàng thường trực tiếp chịu trách nhiệm cho công việc nào?
A. Cập nhật hypervisor trên máy chủ vật lý của nhà cung cấp.
B. Cập nhật hệ điều hành khách và vá các gói phần mềm.
C. Thay phần cứng lưu trữ khi linh kiện máy chủ bị hỏng.
D. Bảo trì switch và đường truyền trong trung tâm dữ liệu.
Đáp án đúng: B

Câu 6. Workload có tải nền ổn định suốt năm. Cách nào thường giúp giảm chi phí compute?
A. Áp dụng cam kết sử dụng cho phần tải nền ổn định.
B. Chuyển mọi workload sang máy có bộ tăng tốc chuyên dụng.
C. Giữ toàn bộ máy chạy liên tục với cấu hình lớn nhất.
D. Dùng toàn bộ máy interruptible cho cơ sở dữ liệu chính.
Đáp án đúng: A

Câu 7. Ứng dụng web cần mở rộng nhiều replica mà vẫn giữ được phiên đăng nhập. Thiết kế nào phù hợp?
A. Giữ tầng web stateless và chuyển phiên sang kho dùng chung.
B. Gắn mỗi phiên vào ổ đĩa cục bộ trên web server đang phục vụ.
C. Giữ mọi phiên trong RAM của máy nhận request đầu.
D. Tăng số CPU của máy web duy nhất để phục vụ.
Đáp án đúng: A

Câu 8. Cơ chế nào là một ví dụ điển hình của load balancing ở tầng ứng dụng L7?
A. Dựa vào IP nguồn để chọn tuyến mạng mặc định.
B. Dựa vào địa chỉ MAC để chuyển frame giữa cổng.
C. Dựa vào đường dẫn HTTP để chọn backend phù hợp.
D. Dựa vào cổng TCP để phân phối các kết nối mạng.
Đáp án đúng: C

Câu 9. Nhóm hạ tầng cần giới hạn số VM mà từng dự án có thể tạo. Cơ chế nào phù hợp?
A. Đặt quota theo dự án để giới hạn lượng instance tạo mới.
B. Bật tự động tăng giới hạn mỗi khi đội dự án yêu cầu.
C. Dùng nhãn tài nguyên để ngăn mọi thao tác tạo máy mới.
D. Đặt alarm CPU để từ chối các lệnh tạo VM.
Đáp án đúng: A

Câu 10. Dữ liệu database phải tiếp tục tồn tại khi thay máy ảo chạy ứng dụng. Phương án lưu trữ nào phù hợp?
A. Gắn volume block bền vững và quản lý hệ thống tập tin.
B. Gắn ephemeral disk và lưu trạng thái vào RAM khi chạy.
C. Đặt toàn bộ dữ liệu sản xuất trong lớp cache ngắn hạn.
D. Đóng gói dữ liệu thường xuyên thay đổi vào image bất biến.
Đáp án đúng: A

Câu 11. Một dịch vụ tăng độ trễ và CPU VM đạt 95%. Bước điều tra ưu tiên nào hợp lý?
A. Tăng số máy trước khi xem số liệu tải thực tế.
B. Tắt log ứng dụng để giảm lưu lượng khi CPU cao.
C. Thay load balancer trước khi xác định điểm nghẽn dịch vụ.
D. Đối chiếu CPU, request rate và độ trễ theo cùng mốc thời gian.
Đáp án đúng: D

Câu 12. Khi cấu hình inbound firewall cho một dịch vụ, quy tắc nào thể hiện nguyên tắc ít quyền nhất?
A. Chỉ mở cổng cần thiết từ đúng nhóm nguồn truy cập.
B. Cho phép mọi cổng từ Internet trong suốt giai đoạn kiểm thử.
C. Mở toàn bộ dải cổng nội bộ giữa tất cả workload.
D. Chỉ lọc lưu lượng đi ra và bỏ qua hướng vào.
Đáp án đúng: A

Câu 13. Khi deploy cùng một image container nhiều lần, cách tham chiếu nào khóa chính xác bản build?
A. Dùng tag latest để luôn chọn bản phát hành mới nhất.
B. Dùng tên repository không có tag và kéo image khi chạy.
C. Dùng tag theo môi trường rồi đổi đích mỗi lần phát hành.
D. Dùng image digest để khóa chính xác nội dung triển khai.
Đáp án đúng: D

Câu 14. Đội muốn chạy container mà không quản trị node Kubernetes. Phương án nào phù hợp nhất?
A. Tự vận hành cluster Kubernetes trên các VM riêng biệt.
B. Cài container runtime thủ công lên từng máy ảo trong cụm.
C. Dùng dịch vụ container được quản lý ở mức workload.
D. Dùng nhóm VM tự quản cùng script khởi chạy container ở mỗi node.
Đáp án đúng: C

Câu 15. Một service liên tục bị OOM dù CPU trung bình thấp. Thay đổi sizing nào nên thử trước?
A. Chọn instance có xung CPU cao hơn nhưng RAM cũ trong cùng họ máy.
B. Tăng số core và giữ nguyên mức RAM hiện tại.
C. Chọn instance có GPU mạnh hơn nhưng RAM tương đương.
D. Tăng RAM khả dụng và đo lại peak bộ nhớ thực tế.
Đáp án đúng: D

Câu 16. Khi so sánh chi phí VM giữa hai cloud, cách nào cho kết quả công bằng hơn?
A. So sánh giá niêm yết của hai instance cùng tên gọi.
B. Chuẩn hóa hiệu năng, vùng triển khai và chi phí mạng đi kèm.
C. So sánh số vCPU mà bỏ qua thế hệ CPU sử dụng.
D. So sánh phí giờ chạy mà bỏ qua lưu lượng mạng.
Đáp án đúng: B

Câu 17. Ngay sau deploy ứng dụng mới, bước nào xác nhận tối thiểu đường đi phục vụ hoạt động?
A. Chỉ dựa vào pipeline thành công mà không kiểm tra endpoint.
B. Gọi smoke test qua tuyến truy cập thật và kiểm tra phản hồi.
C. Kiểm tra số lượng tệp trong image vừa tải lên registry.
D. Đọc cấu hình IaC và so với nhánh mã nguồn phát hành.
Đáp án đúng: B

Câu 18. Khi chọn GPU để suy luận mô hình lớn, thông số nào ảnh hưởng trực tiếp đến khả năng chứa mô hình?
A. Tốc độ ghi tối đa của ổ đĩa tạm máy chủ.
B. Số lượng cổng mạng vật lý trên máy chủ chứa GPU.
C. Dung lượng VRAM so với kích thước mô hình và batch.
D. Số luồng CPU logic được khai báo trong hệ điều hành.
Đáp án đúng: C

Câu 19. Muốn tầng web stateless chịu được mất một availability zone, cách triển khai nào trực tiếp nhất?
A. Chạy nhiều replica trong một zone và gắn cùng volume cho mọi node.
B. Dùng máy ảo cấu hình lớn tại một zone duy nhất.
C. Phân bố replica sang nhiều zone và cân bằng tải giữa chúng.
D. Tăng tần suất snapshot cho replica trong một zone.
Đáp án đúng: C

Câu 20. Một cụm MPI trao đổi thông điệp thường xuyên giữa các node. Yếu tố nào quan trọng nhất?
A. Dung lượng object storage cao để lưu nhiều bản checkpoint.
B. Đường Internet băng thông lớn cho người dùng cuối.
C. Số lượng endpoint HTTP công khai của hệ thống điều phối.
D. Độ trễ liên node thấp và băng thông mạng ổn định.
Đáp án đúng: D

Câu 21. Thiết bị IoT cần phản hồi tức thời ngay cả khi kết nối cloud gián đoạn. Thiết kế nào phù hợp?
A. Đẩy mọi dữ liệu thô lên cloud rồi chờ kết quả.
B. Xử lý tại edge và đồng bộ kết quả khi có mạng.
C. Tăng số lần gửi request tới cloud khi mạng yếu.
D. Chuyển dữ liệu lên kho lưu trữ để xử lý cuối ngày.
Đáp án đúng: B

Câu 22. Autoscaling theo mức CPU mục tiêu thường phản ứng thế nào khi tải tăng bền vững?
A. Giảm replica để giữ CPU cao và tiết kiệm chi phí.
B. Tăng cấu hình RAM của mọi instance đang hoạt động.
C. Dừng các node ít tải để cân lại CPU trung bình.
D. Tăng số replica theo chính sách đến khi chỉ số ổn định.
Đáp án đúng: D

Câu 23. Công việc nào phù hợp nhất với VM interruptible có thể bị thu hồi bất ngờ?
A. Batch job có checkpoint và có thể chạy lại an toàn.
B. Database chính chỉ có một node ghi duy nhất trong vùng triển khai.
C. Phiên giao dịch trực tuyến không có chuyển đổi dự phòng.
D. Tác vụ điều khiển thời gian thực với deadline cứng.
Đáp án đúng: A

Câu 24. Kubernetes scheduler thường dựa vào thông số nào để xếp Pod lên node còn đủ tài nguyên?
A. Giá trị limits khai báo cho mọi container trong cluster.
B. Tổng requests của container trong Pod so với node khả dụng.
C. CPU usage đo được của Pod trong phút gần nhất theo toàn bộ node.
D. Số replica mục tiêu khai báo trong Deployment của Pod.
Đáp án đúng: B

Câu 25. Ứng dụng cloud cần đọc object storage mà không lưu khóa truy cập dài hạn. Lựa chọn nào thích hợp?
A. Đóng gói API key dùng chung cùng image triển khai.
B. Gán workload identity với quyền đọc bucket cần thiết.
C. Chép khóa truy cập quản trị viên vào ổ boot VM.
D. Dùng tài khoản root rồi thay mật khẩu theo mỗi bản phát hành.
Đáp án đúng: B

Câu 26. Để tạo VM nhất quán và giảm sai lệch giữa môi trường, nên quản lý image nền thế nào?
A. Cập nhật thủ công image đang dùng trên từng máy riêng.
B. Dùng snapshot mỗi máy làm template cho lần deploy kế.
C. Cài package khác nhau tùy kỹ sư vận hành từng ca.
D. Build image có phiên bản, kiểm thử rồi đưa vào sử dụng.
Đáp án đúng: D

Câu 27. Chỉ số nào giúp theo dõi độ trễ ở nhóm request chậm của một API?
A. Độ trễ p95 của request theo endpoint và khoảng thời gian.
B. Độ trễ trung bình của request theo endpoint và khoảng thời gian.
C. Số request mỗi giây theo endpoint và khoảng thời gian.
D. Tỷ lệ request lỗi theo endpoint và khoảng thời gian.
Đáp án đúng: A

Câu 28. Khi cập nhật kernel cho cụm VM phục vụ web, cách nào giảm gián đoạn dịch vụ?
A. Patch lần lượt từng node, drain lưu lượng và kiểm tra health.
B. Patch tất cả node đồng thời vào thời điểm ít người dùng.
C. Tắt health check trong lúc reboot mọi node cùng lúc.
D. Gỡ load balancer và truy cập trực tiếp từng node đang patch qua IP public.
Đáp án đúng: A

Câu 29. Trường hợp nào thể hiện đặc trưng của serverless functions rõ nhất?
A. Ứng dụng giữ tiến trình nền trên VM chạy cả ngày.
B. Một container được chạy thủ công qua SSH trên máy chủ.
C. Hàm được gọi theo event và tự mở rộng lượt thực thi.
D. Ứng dụng được cài như service hệ thống trên máy ảo.
Đáp án đúng: C

Câu 30. Khi thử tải, median latency gần như giữ nguyên nhưng p95 tăng mạnh. Diễn giải nào phù hợp?
A. Mọi request đều đã chậm hơn cùng một mức độ.
B. Tốc độ xử lý trung bình tăng đều ở mọi mức tải.
C. Hệ thống chắc chắn không có giới hạn kết nối mạng.
D. Nhóm request chậm chịu tác động lớn hơn khi tải cao.
Đáp án đúng: D

Câu 31. Một VM được quản lý bằng IaC bị sửa cấu hình thủ công. Cách xử lý bền vững nào phù hợp?
A. Giữ thay đổi trên máy và bỏ qua lần apply tiếp theo của pipeline.
B. Đối chiếu drift rồi đưa trạng thái mong muốn vào mã cấu hình.
C. Tạo bản sao máy vừa sửa để thay thế toàn bộ cluster.
D. Tắt công cụ IaC để tránh cập nhật ngoài ý muốn.
Đáp án đúng: B

Câu 32. Muốn tạo thumbnail sau khi ảnh được tải lên object storage, trigger nào thích hợp?
A. Gọi hàm theo lịch cố định dù không có ảnh mới.
B. Chạy hàm khi có login mới vào hệ thống quản trị.
C. Gọi hàm theo sự kiện tạo object trong bucket nguồn.
D. Khởi động hàm khi thay đổi cấu hình mạng của VPC.
Đáp án đúng: C

Câu 33. Một function có thời gian khởi động lạnh đáng kể. Cách nào thường giúp giảm cold start?
A. Tăng số lần ghi log đồng bộ khi hàm vừa khởi động.
B. Tải tất cả thư viện tùy chọn trước khi xử lý request.
C. Tạo kết nối mạng mới cho mỗi request ở mọi lượt gọi.
D. Giảm phụ thuộc khởi tạo và dùng concurrency được giữ sẵn.
Đáp án đúng: D

Câu 34. Điều gì xảy ra khi terminate VM, khác với stop thông thường?
A. Instance ngừng chạy nhưng vẫn có thể start lại bằng cùng ID.
B. Instance ngừng chạy và được giữ để chạy lại theo lịch.
C. Instance kết thúc vòng đời và đĩa tạm có thể bị mất.
D. Instance tạm ngừng và chi phí lưu trữ có thể còn phát sinh.
Đáp án đúng: C

Câu 35. Dịch vụ nhận request tăng đột biến nhưng worker xử lý chậm. Thiết kế nào chống nghẽn tại đầu vào?
A. Tăng timeout HTTP để frontend giữ kết nối lâu hơn.
B. Cho API gọi trực tiếp worker bằng RPC đồng bộ.
C. Ghi job vào RAM cục bộ của một instance web.
D. Đệm yêu cầu trong hàng đợi bền vững và scale worker.
Đáp án đúng: D

Câu 36. VM chỉ có IP private cần tải bản vá từ Internet mà không nhận kết nối vào. Cấu hình nào phù hợp?
A. Định tuyến lưu lượng đi ra qua NAT gateway trong mạng.
B. Gán địa chỉ IP công khai trực tiếp cho mọi máy.
C. Mở cổng SSH inbound từ Internet tới mọi instance.
D. Dùng Internet gateway trực tiếp mà không có NAT hoặc proxy.
Đáp án đúng: A

Câu 37. Service stateless chạm giới hạn CPU trên một VM. Muốn tăng cả khả dụng lẫn throughput, nên làm gì?
A. Tăng xung CPU trên máy hiện tại mà vẫn giữ một replica duy nhất.
B. Tăng kích thước RAM trên máy duy nhất đang chạy.
C. Tăng số replica sau load balancer với phân phối request.
D. Tăng dung lượng đĩa tạm trên một instance duy nhất.
Đáp án đúng: C

Câu 38. SLO availability là 99,9% theo tháng. Error budget biểu thị điều gì?
A. Thời gian khôi phục tối đa dành cho mỗi sự cố của dịch vụ.
B. Mức dữ liệu tối đa có thể mất sau một đợt phục hồi.
C. Khoảng thời gian trung bình giữa hai lần hệ thống gặp lỗi.
D. Mức không đạt SLO còn cho phép trong kỳ đo.
Đáp án đúng: D

Câu 39. Load balancer tiếp tục chuyển request vào replica lỗi. Kiểm tra nào nên ưu tiên?
A. Cấu hình idle timeout của các kết nối từ client.
B. Quy tắc sticky session và thuật toán chọn backend.
C. Cấu hình health check, ngưỡng lỗi và trạng thái target.
D. Mức retry và timeout của request tới backend.
Đáp án đúng: C

Câu 40. Database bị ghi nhầm lúc 14:05. Điều kiện nào giúp khôi phục dữ liệu gần thời điểm 14:04?
A. Chỉ có một snapshot được chụp vào đầu mỗi tháng.
B. Có backup nền và nhật ký thay đổi liên tục để replay.
C. Chỉ tăng số replica đọc mà không lưu nhật ký giao dịch.
D. Chỉ có snapshot máy ảo khi bắt đầu phát hành ứng dụng.
Đáp án đúng: B

Câu 41. Cần xoay vòng khóa truy cập cho nhiều worker mà không build lại image. Thiết kế nào phù hợp?
A. Lưu secret trong dịch vụ quản lý bí mật và cấp quyền theo workload.
B. Chèn secret vào image mới và redeploy toàn bộ worker.
C. Ghi secret vào file cấu hình rồi commit cùng mã nguồn.
D. Đặt secret vào biến môi trường trong Dockerfile dùng chung.
Đáp án đúng: A

Câu 42. Frontend được gọi API nội bộ nhưng không được truy cập database trực tiếp. Cấu hình nào phù hợp?
A. Cho toàn bộ subnet giao tiếp lẫn nhau trên mọi port.
B. Chỉ cho frontend tới API và API tới DB đúng cổng.
C. Mở tất cả kết nối nội bộ rồi giới hạn ở load balancer.
D. Cấp IP công khai cho DB và dùng firewall ở client.
Đáp án đúng: B

Câu 43. Kubernetes HPA báo không thể tính CPU utilization. Cần kiểm tra điều kiện nào?
A. CPU limits đang đặt thấp hơn mức sử dụng đỉnh.
B. HPA đã cấu hình cooldown cho các đợt tăng replica.
C. Metrics khả dụng và requests CPU được khai báo trên container.
D. Deployment đang có đủ số replica theo mức đặt ban đầu.
Đáp án đúng: C

Câu 44. Phát biểu nào đúng về mức cô lập giữa container và VM?
A. Container luôn có nhân hệ điều hành riêng biệt cho từng bản.
B. VM chia sẻ trực tiếp kernel guest với tất cả VM khác.
C. Container thường chia sẻ kernel host, VM có guest OS riêng.
D. VM không cần hypervisor còn container luôn cần hypervisor.
Đáp án đúng: C

Câu 45. Function chạm giới hạn số lượt thực thi đồng thời. Request tiếp theo có thể gặp điều gì?
A. Hàm tự kéo dài timeout mặc định để xử lý thêm yêu cầu.
B. CPU mỗi lượt thực thi tự nhân đôi khi queue tăng lên.
C. Thời gian thực thi mọi request tự giảm một nửa.
D. Lượt gọi vượt ngưỡng có thể bị throttling hoặc chờ.
Đáp án đúng: D

Câu 46. Consumer nhận lại cùng một message do cơ chế at-least-once. Thiết kế nào tránh ghi trùng?
A. Tăng timeout nhận message để giảm khả năng worker chạy lại khi mạng có lỗi.
B. Dùng mã định danh giao dịch và kiểm tra trùng trước khi ghi.
C. Đặt nhiều replica consumer cùng ghi vào bảng không có khóa.
D. Tắt retry trên consumer sau lần thất bại đầu tiên.
Đáp án đúng: B

Câu 47. Để tiết kiệm chi phí batch bằng VM spot, ứng dụng cần đặc tính nào?
A. Worker tự checkpoint, nhận tín hiệu thu hồi và chạy lại được.
B. Mọi tác vụ chỉ được phép chạy trên một máy duy nhất.
C. Toàn bộ dữ liệu tạm phải lưu ở RAM không đồng bộ.
D. Job phải giữ kết nối khách hàng liên tục trong nhiều giờ.
Đáp án đúng: A

Câu 48. RTO 30 phút của dịch vụ có ý nghĩa gì khi xảy ra sự cố?
A. Thời gian khôi phục dịch vụ mục tiêu tối đa là 30 phút.
B. Dữ liệu mất tối đa được phép là đúng 30 phút.
C. Khoảng cách giữa hai lần snapshot phải là 30 phút cho mọi dữ liệu.
D. Tổng thời gian giữ backup bắt buộc là 30 phút.
Đáp án đúng: A
