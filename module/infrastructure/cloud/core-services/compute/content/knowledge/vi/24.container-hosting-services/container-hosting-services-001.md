# Chọn container trên VM hoặc dịch vụ container có quản lý

Đóng gói ứng dụng thành container giúp ứng dụng mang theo thư viện và cấu hình chạy cần thiết. Tuy nhiên, image container vẫn cần một môi trường để khởi chạy, cấp CPU và bộ nhớ, kết nối mạng, lưu log, phục hồi khi lỗi và mở rộng khi tải tăng. Có hai hướng triển khai phổ biến: tự vận hành container trên máy ảo (VM) hoặc sử dụng dịch vụ container có quản lý của nhà cung cấp cloud.

Quyết định này ảnh hưởng trực tiếp đến phần việc đội ngũ phải vận hành, mức độ kiểm soát hạ tầng, cách mở rộng, tính sẵn sàng và tổng chi phí. Không có lựa chọn tốt nhất cho mọi ứng dụng; cần chọn theo đặc điểm tải, yêu cầu kỹ thuật và năng lực vận hành của nhóm.

Sau bài học, bạn có thể:

- Giải thích phần trách nhiệm của đội ngũ khi chạy container trên VM và khi dùng dịch vụ có quản lý.
- So sánh hai mô hình theo khả năng kiểm soát, mở rộng, tính sẵn sàng, bảo mật và chi phí.
- Chọn mô hình phù hợp cho một workload và nêu được lý do.
- Kiểm tra một triển khai container trước khi đưa vào môi trường production.

## 1. Container chạy trên máy ảo

Ở mô hình này, đội ngũ tạo VM trong mạng cloud, quản lý hệ điều hành và cài container runtime như Docker Engine hoặc containerd. Sau đó, ứng dụng được khởi chạy bằng lệnh, Docker Compose hoặc một cơ chế quản lý tiến trình như systemd. VM cung cấp CPU, bộ nhớ, đĩa và giao diện mạng; container chia sẻ kernel của hệ điều hành máy chủ.

Ví dụ, một API nội bộ có lưu lượng tương đối ổn định có thể chạy trên một VM Linux. Reverse proxy trên VM nhận HTTPS, chuyển tiếp yêu cầu đến cổng ứng dụng chỉ mở trên loopback:

```bash
docker run -d \
  --name orders-api \
  --restart unless-stopped \
  --cpus=1 \
  --memory=768m \
  --publish 127.0.0.1:8080:8080 \
  --env-file /etc/orders-api.env \
  registry.example.com/orders-api:1.4.2
```

Trong ví dụ, giới hạn CPU và bộ nhớ giúp một container không dễ chiếm hết tài nguyên của VM. Chính sách restart hỗ trợ khởi chạy lại container sau khi tiến trình dừng hoặc Docker khởi động lại. Cổng `8080` chỉ được bind trên loopback để reverse proxy cùng VM có thể truy cập; người dùng bên ngoài đi qua điểm vào HTTPS đã được bảo vệ. File môi trường cần có quyền đọc hạn chế. Với production, nên lấy bí mật từ secret manager và dùng image đã quét, được định danh bằng digest thay vì phụ thuộc vào một tag có thể bị thay đổi.

Đội ngũ chịu trách nhiệm cho toàn bộ lớp máy chủ: cập nhật và gia cố hệ điều hành, vá kernel, cập nhật container runtime, cấu hình firewall, quản lý SSH và quyền truy cập, giám sát dung lượng đĩa, xoay vòng log, sao lưu dữ liệu, cập nhật image và xử lý sự cố của VM. Nếu cần triển khai nhiều bản sao để chịu lỗi, đội ngũ còn phải thiết kế load balancer, health check, phân bố VM qua các vùng sẵn sàng và cơ chế thay thế VM hỏng.

Chạy container trên VM đem lại quyền kiểm soát lớn đối với hệ điều hành, mạng, agent giám sát và cách bố trí tiến trình. Mô hình này phù hợp khi workload cần phần mềm hoặc cấu hình cấp máy chủ đặc thù, cần chạy lâu dài với mức tải ổn định, hoặc tổ chức đã có quy trình quản trị VM tốt. Đổi lại, việc mở rộng và duy trì tính sẵn sàng thường đòi hỏi nhiều công việc tự động hóa hơn.

Một VM duy nhất vẫn là điểm lỗi đơn. `--restart` chỉ khởi động lại container trên máy đó; nó không phục hồi được khi VM, đĩa hoặc vùng sẵn sàng gặp sự cố. Muốn có tính sẵn sàng cao, cần nhiều VM ở các vùng phù hợp, cân bằng tải và kiểm tra khả năng chuyển lưu lượng khi một bản sao không khỏe.

## 2. Dịch vụ container có quản lý

Dịch vụ container có quản lý cung cấp một lớp điều phối hoặc môi trường chạy container do nhà cung cấp vận hành. Người dùng thường khai báo image, CPU, bộ nhớ, số bản sao, cấu hình mạng, quyền truy cập và chính sách mở rộng. Nền tảng chịu trách nhiệm cho một phần công việc như lập lịch container, theo dõi tiến trình, thay thế bản sao lỗi hoặc quản lý hạ tầng chạy bên dưới.

Tên gọi “có quản lý” không có nghĩa mọi trách nhiệm đều được chuyển cho nhà cung cấp. Phạm vi quản lý phụ thuộc vào sản phẩm và chế độ triển khai:

- **AWS ECS với AWS Fargate:** khai báo task và service; Fargate cấp môi trường chạy task mà đội ngũ không phải quản lý trực tiếp các VM worker. Đội ngũ vẫn cấu hình task, IAM task role, mạng, lưu trữ, log và chính sách mở rộng.
- **Amazon EKS, Google Kubernetes Engine (GKE) và Azure Kubernetes Service (AKS):** cung cấp Kubernetes control plane được quản lý. Việc quản lý node vẫn phụ thuộc chế độ sử dụng; một số chế độ tự động hóa nhiều hơn, nhưng đội ngũ vẫn cần hiểu workload, cấu hình cluster, quyền, mạng và vận hành Kubernetes.
- **Google Cloud Run và Azure Container Apps:** cung cấp môi trường chạy container cấp cao hơn, có thể tự động điều chỉnh số instance theo yêu cầu hoặc sự kiện. Một số cấu hình có thể scale về 0; khi đó cần tính đến thời gian khởi động lạnh và yêu cầu của ứng dụng.

Ví dụ, một API bán hàng có lưu lượng tăng mạnh vào giờ cao điểm có thể được đóng gói thành image và triển khai thành service trên Cloud Run hoặc Azure Container Apps. Với AWS, cùng image có thể được khai báo thành task definition và chạy bằng ECS Fargate. Nhóm cấu hình CPU, bộ nhớ, cổng, biến cấu hình, secret reference, health check, quyền gọi các dịch vụ khác và giới hạn số instance. Nền tảng khởi chạy các bản sao theo cấu hình và có thể tăng hoặc giảm số bản sao theo chính sách đã chọn.

Dịch vụ có quản lý giảm đáng kể công việc chăm sóc máy chủ hoặc control plane, giúp triển khai nhiều bản sao và tự động phục hồi dễ hơn. Tuy vậy, đội ngũ vẫn phải chịu trách nhiệm về chất lượng image, lỗ hổng trong thư viện ứng dụng, thiết kế API, dữ liệu, quyền ứng dụng, cấu hình ingress/egress, bí mật, cảnh báo và cách xử lý sự cố ở cấp ứng dụng. Nền tảng có thể khởi động lại container nhưng không thể tự sửa một lỗi logic khiến mọi bản sao đều trả về lỗi.

## 3. So sánh hai mô hình

| Tiêu chí | Container trên VM | Dịch vụ container có quản lý |
|---|---|---|
| Kiểm soát | Kiểm soát VM, hệ điều hành, runtime và cách chạy container | Kiểm soát cấu hình workload; quyền với máy chủ hoặc control plane thấp hơn tùy dịch vụ |
| Công việc vận hành | Tự vá OS/runtime, quản lý dung lượng, runtime, tiến trình và năng lực VM | Nhà cung cấp quản lý một phần hạ tầng; đội ngũ quản lý image, cấu hình service, quyền, mạng và ứng dụng |
| Mở rộng | Tự thêm VM/container hoặc ghép với autoscaling group, load balancer và công cụ điều phối | Thường có cơ chế scale theo CPU, bộ nhớ, số yêu cầu hoặc sự kiện; cần đặt ngưỡng và giới hạn |
| Phục hồi | Tự cấu hình restart, health check, thay VM và phân bố qua vùng | Nền tảng thường có thể thay bản sao lỗi; cần cấu hình số bản sao, phân bố vùng và kiểm tra sức khỏe phù hợp |
| Chi phí | Thường trả cho năng lực VM đã cấp, kể cả khi rảnh; có thể hiệu quả khi sử dụng ổn định | Có thể tính theo tài nguyên/instance/thời gian/yêu cầu; tiện cho tải biến động nhưng có thêm phí nền tảng, mạng và quan sát |
| Tính linh hoạt | Dễ tùy chỉnh OS, agent, thiết bị và cấu hình cấp máy chủ | Bị giới hạn bởi tính năng, runtime, quota và mô hình mạng của dịch vụ |
| Dữ liệu lâu dài | Có thể gắn đĩa VM, nhưng cần quản lý backup và vòng đời đĩa | Thường dùng filesystem tạm thời; nên đặt dữ liệu lâu dài ở database, object storage hoặc volume được hỗ trợ |
| Tính di động | Image OCI tương đối dễ chuyển; script và cấu hình VM có thể phụ thuộc môi trường | Image vẫn có thể chuyển; cấu hình IAM, mạng, autoscaling và triển khai thường gắn với nhà cung cấp |

### Khác biệt về mở rộng và tính sẵn sàng

Với VM, tăng tải có thể cần tăng số container trên máy còn dư tài nguyên, hoặc cấp thêm VM. Nếu mở rộng qua nhiều VM, cần có cơ chế phân phối image, cấu hình đồng nhất, đăng ký instance vào load balancer và loại bỏ máy không khỏe. Autoscaling VM thường phản ứng theo metric của máy chủ; nó không tự hiểu mọi đặc điểm của ứng dụng.

Với dịch vụ có quản lý, nền tảng có thể tạo thêm bản sao theo CPU, bộ nhớ, số yêu cầu đồng thời hoặc hàng đợi. Tuy nhiên, autoscaling không phải là không giới hạn: quota tài khoản, giới hạn kết nối database, thời gian khởi động, giới hạn concurrency và khả năng mở rộng của dịch vụ phụ thuộc phía sau đều có thể trở thành nút thắt. Cần đặt ngưỡng tối đa và thử tải trước khi production.

Tương tự, dịch vụ có quản lý không tự động bảo đảm ứng dụng luôn sẵn sàng. Hãy cấu hình số bản sao tối thiểu phù hợp, health check đúng, phân bố qua vùng sẵn sàng nếu sản phẩm hỗ trợ và bảo đảm các dependency cũng có khả năng chịu lỗi. Một service có một bản sao hoặc phụ thuộc vào một database đơn lẻ vẫn có thể gián đoạn.

### Khác biệt về chi phí

Không nên so sánh chỉ bằng giá CPU và bộ nhớ. Tổng chi phí vận hành có thể gồm:

`Tổng chi phí = compute + storage + network + load balancer + registry + logs/metrics + license + công sức vận hành`

VM có thể tiết kiệm khi workload chạy liên tục, sử dụng ổn định và VM được khai thác tốt. Nhưng VM nhàn rỗi vẫn phát sinh chi phí, đồng thời cần tính thời gian của người vận hành để vá lỗi, trực sự cố và duy trì tính sẵn sàng. Dịch vụ quản lý có thể giảm thời gian vận hành và phù hợp với tải thay đổi, nhưng chi phí có thể tăng do số instance tối thiểu, thời gian chạy, request, lưu lượng ra ngoài, NAT, load balancer hoặc log dung lượng lớn. Với dịch vụ có scale-to-zero, hãy cân nhắc cả cold start và yêu cầu độ trễ.

## 4. Cách chọn mô hình theo workload

Ưu tiên container trên VM khi có một hoặc nhiều điều kiện sau:

- Tải ổn định, chạy liên tục và có thể tận dụng tốt một nhóm VM đã được cấp.
- Ứng dụng cần agent, thư viện hệ thống, cấu hình mạng hoặc quyền kiểm soát máy chủ đặc thù.
- Tổ chức đã có đội ngũ và quy trình quản trị VM, vá lỗi, giám sát và khôi phục đáng tin cậy.
- Workload nhỏ, nội bộ hoặc ở môi trường edge nơi mô hình triển khai đơn giản và quyền kiểm soát máy chủ là cần thiết.

Ưu tiên dịch vụ container có quản lý khi:

- Lưu lượng biến động theo giờ, theo mùa hoặc theo sự kiện và cần tự động tăng giảm bản sao.
- Nhóm muốn tập trung vào ứng dụng, giảm việc quản lý node hoặc control plane.
- Cần quy trình triển khai nhiều bản sao, health check, thay thế instance lỗi và rollback có sẵn.
- Workload phù hợp với giới hạn runtime, mạng, lưu trữ và quota của nền tảng.

Có thể dùng kết hợp. Ví dụ, một hệ thống cũ có agent đặc thù tiếp tục chạy trên VM, trong khi API mới chạy trên dịch vụ quản lý. Dù chọn mô hình nào, nên giữ image theo chuẩn OCI, cấu hình ứng dụng bên ngoài image và tự động hóa quá trình build, scan, phát hành để giảm khác biệt giữa các môi trường.

Trước khi quyết định, hãy trả lời các câu hỏi sau:

1. Tải nền và tải đỉnh là bao nhiêu? Tải có biến động đủ lớn để autoscaling tạo ra giá trị không?
2. Ứng dụng có cần truy cập cấp máy chủ, thiết bị đặc biệt, filesystem lâu dài hoặc giao thức mạng không được nền tảng hỗ trợ không?
3. Nhóm có thể trực và vá VM/cluster không? Thời gian vận hành đó có đáng so với phí dịch vụ quản lý không?
4. Ứng dụng cần bao nhiêu bản sao, mức sẵn sàng nào và các dependency có đáp ứng được không?
5. Chi phí mạng, log, lưu trữ, số instance tối thiểu và cold start ảnh hưởng thế nào đến tổng chi phí và trải nghiệm?

## 5. Ví dụ triển khai cùng một image trên hai mô hình

Giả sử nhóm phát triển dịch vụ `orders-api`. Image được build và đẩy lên registry dùng chung:

```bash
docker build -t registry.example.com/orders-api:1.4.2 .
docker push registry.example.com/orders-api:1.4.2
```

**Phương án A — chạy trên VM:** tạo VM Linux trong subnet phù hợp, chỉ cho phép truy cập quản trị từ nguồn tin cậy, cài runtime đã được phê duyệt, cấu hình reverse proxy và khởi chạy container với giới hạn tài nguyên. Với production, nên quản lý cấu hình bằng công cụ tự động hóa, dùng secret manager, gửi log và metric về hệ thống tập trung, đồng thời chuẩn bị quy trình thay VM. Nếu cần HA, triển khai nhiều VM ở các vùng sẵn sàng và đặt sau load balancer.

**Phương án B — chạy trên dịch vụ quản lý:** tạo service từ cùng image, chọn CPU và bộ nhớ, đặt số bản sao tối thiểu/tối đa hoặc chính sách scale, cấu hình health check, ingress, quyền truy cập dịch vụ, secret reference và nơi gửi log. Chẳng hạn, ECS Fargate chạy task theo task definition; Cloud Run hoặc Azure Container Apps triển khai image thành service và điều chỉnh instance theo cấu hình. Cần kiểm tra giới hạn concurrency, timeout, thời gian khởi động và cách nền tảng xử lý filesystem tạm thời.

Hai phương án dùng cùng image nhưng khác cách cấp năng lực và vận hành. Nếu API có tải nền cao, ổn định, phương án VM có thể dễ dự toán và tận dụng tài nguyên. Nếu tải thay đổi mạnh, phương án quản lý có thể giảm công việc tăng giảm máy và phục hồi instance. Quyết định cuối cùng nên dựa trên thử nghiệm tải và ước tính tổng chi phí, không chỉ dựa trên một mức giá compute.

## 6. Kiểm tra trước khi đưa vào production

Thực hiện các bước kiểm tra sau cho cả hai mô hình:

1. **Image:** xác nhận đúng phiên bản hoặc digest, quét lỗ hổng, loại bỏ secret khỏi image và chạy ứng dụng bằng user không phải root khi có thể.
2. **Sức khỏe ứng dụng:** có endpoint readiness/health phù hợp; kiểm tra ứng dụng chỉ nhận traffic khi đã sẵn sàng và bị loại khỏi load balancer khi không khỏe.
3. **Tài nguyên:** đặt giới hạn CPU/bộ nhớ hợp lý, chạy thử tải và quan sát CPU throttling, bộ nhớ tăng bất thường hoặc lỗi OOM.
4. **Mạng và quyền:** chỉ mở ingress cần thiết, mã hóa kết nối, giới hạn egress, dùng danh tính dịch vụ với quyền tối thiểu và truy cập database qua mạng riêng khi phù hợp.
5. **Bí mật và dữ liệu:** lấy secret từ nơi quản lý bí mật; không lưu dữ liệu quan trọng trong writable layer hoặc filesystem tạm của container. Dùng database, object storage hoặc volume bền vững được nền tảng hỗ trợ.
6. **Mở rộng và chịu lỗi:** thử tăng tải, chạm ngưỡng scale tối đa, dừng một bản sao và xác nhận lưu lượng được phục vụ bởi các bản sao còn lại. Kiểm tra quota và khả năng chịu tải của dependency.
7. **Quan sát và khôi phục:** xác nhận log, metric, trace và cảnh báo có ích; thử triển khai phiên bản mới, rollback và khôi phục dữ liệu theo quy trình.

Trên VM Linux, có thể kiểm tra nhanh trạng thái và tài nguyên bằng:

```bash
docker ps --filter name=orders-api
docker logs --tail=100 orders-api
docker stats --no-stream orders-api
curl -fsS http://127.0.0.1:8080/health
```

Lệnh `curl` cần được chạy từ VM hoặc môi trường có đường mạng đến endpoint kiểm tra. Với dịch vụ quản lý, kiểm tra trạng thái deployment/revision, số bản sao mong muốn và đang chạy, sự kiện khởi chạy, log ứng dụng, metric CPU/bộ nhớ, số yêu cầu và kết quả health check. Sau đó gọi endpoint công khai hoặc nội bộ bằng một yêu cầu thử để xác nhận đường đi mạng và phản hồi thực tế.

## Checklist lựa chọn và vận hành

- [ ] Đã mô tả tải nền, tải đỉnh, yêu cầu độ trễ và mức sẵn sàng.
- [ ] Đã xác định ứng dụng có cần quyền kiểm soát VM, agent hoặc cấu hình cấp máy chủ không.
- [ ] Đã so sánh tổng chi phí compute, mạng, lưu trữ, log và công sức vận hành.
- [ ] Đã xác nhận nền tảng hỗ trợ cổng, giao thức, volume, thời gian chạy và quota cần thiết.
- [ ] Đã cấu hình image an toàn, quyền tối thiểu, secret và giới hạn tài nguyên.
- [ ] Đã kiểm tra health check, mở rộng, phục hồi khi một bản sao lỗi và rollback.
- [ ] Đã xác nhận log, metric, cảnh báo và dữ liệu quan trọng được lưu ngoài vòng đời container.

Hãy chọn mô hình mà nhóm có thể vận hành ổn định trong giới hạn chi phí và kỹ năng hiện có. VM phù hợp khi cần quyền kiểm soát máy chủ và có năng lực tự quản trị; dịch vụ có quản lý phù hợp khi muốn giảm phần việc hạ tầng và tận dụng điều phối, phục hồi hoặc mở rộng do nền tảng cung cấp.
