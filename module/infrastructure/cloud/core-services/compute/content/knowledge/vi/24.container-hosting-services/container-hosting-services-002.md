# Task, service, revision và đơn vị triển khai container

Trong các nền tảng chạy container trên đám mây, một ứng dụng thường được mô tả bằng nhiều lớp đối tượng. **Task** biểu diễn một lần thực thi container; **service** quản lý một ứng dụng chạy liên tục và duy trì trạng thái mong muốn; **revision** ghi lại một phiên bản cấu hình triển khai; còn **đơn vị triển khai** xác định phần hệ thống được phát hành, thay thế, mở rộng hoặc rollback cùng nhau.

Phân biệt đúng các khái niệm này giúp thiết kế cách chạy ứng dụng, chọn chiến lược cập nhật và xử lý sự cố. Đây là một phần quan trọng khi học các mô hình năng lực tính toán trên đám mây: ngoài việc chọn CPU, bộ nhớ và mạng, người vận hành cần biết nền tảng đang quản lý đối tượng nào và chịu trách nhiệm khôi phục đối tượng đó ra sao.

## 1. Mô hình khái niệm

Có thể hình dung quan hệ giữa các đối tượng như sau:

~~~mermaid
flowchart TD
    A["Image container<br/>được đóng gói và định danh"] --> B["Task definition / cấu hình chạy"]
    B --> C["Revision 17"]
    C --> D["Service"]
    D --> E["Task 1"]
    D --> F["Task 2"]
    D --> G["Task 3"]
    E --> H["Container"]
    F --> I["Container"]
    G --> J["Container"]
    K["Revision 18"] --> D
    D -. "triển khai và thay thế dần" .-> L["Các task theo revision mới"]
~~~

Sơ đồ minh họa một mô hình phổ biến: cấu hình chạy tạo ra revision; service sử dụng revision đó để tạo và duy trì các task. Khi có revision mới, service điều phối quá trình thay thế các task cũ. Tên gọi và ranh giới đối tượng cụ thể thay đổi theo nhà cung cấp, vì vậy cần đối chiếu với mô hình của nền tảng đang dùng.

## 2. Task: một đơn vị thực thi

Task là một lần thực thi được nền tảng khởi chạy từ cấu hình container. Tùy nền tảng, task có thể gồm một container hoặc một nhóm container cần chạy cùng nhau. Ví dụ, một task có thể chứa ứng dụng chính và một sidecar thu thập log hoặc proxy.

Task thường có các thuộc tính vận hành sau:

- **Image:** image và phiên bản image sẽ chạy. Trong môi trường production nên định danh bằng digest, chẳng hạn `registry.example.com/checkout-api@sha256:...`, để bảo đảm cùng một cấu hình luôn lấy đúng image.
- **Tài nguyên:** số vCPU, giới hạn hoặc yêu cầu bộ nhớ, dung lượng tạm và cấu hình tăng tốc nếu có.
- **Mạng:** cổng lắng nghe, chế độ mạng, subnet, security group hoặc chính sách mạng tương ứng.
- **Danh tính và quyền:** service account hoặc task role với quyền tối thiểu cần thiết.
- **Cấu hình ứng dụng:** biến môi trường, tham chiếu đến secret, tham số khởi động và cấu hình logging.
- **Kiểm tra sức khỏe:** lệnh health check hoặc endpoint để nền tảng biết container đã sẵn sàng phục vụ hay chưa.

Một task có vòng đời riêng: được tạo, chuyển sang trạng thái đang chạy, có thể trở nên không khỏe, dừng hoặc kết thúc. Task chạy một lần thường phù hợp với công việc hữu hạn như chạy migration, xử lý một lô dữ liệu hoặc thực hiện tác vụ bảo trì. Khi task kết thúc, nền tảng không nhất thiết khởi chạy lại nó.

Trong Amazon ECS, một **task** là một lần chạy của task definition. Một task definition revision mô tả các container, image, CPU, bộ nhớ, mạng, quyền và logging. Có thể chạy task trực tiếp cho công việc một lần hoặc để ECS service quản lý nhiều task cho ứng dụng dài hạn.

Không nên đồng nhất task với container. Một task có thể chứa nhiều container có vòng đời và cấu hình phối hợp với nhau. Ngược lại, một container riêng lẻ không tự quyết định số bản sao của toàn bộ ứng dụng hay cách cân bằng tải giữa các bản sao.

## 3. Service: quản lý ứng dụng chạy liên tục

Service là đối tượng logic đại diện cho một ứng dụng hoặc workload cần được duy trì. Service thường khai báo trạng thái mong muốn và giao cho bộ lập lịch của nền tảng liên tục điều chỉnh trạng thái thực tế.

Ví dụ, service `checkout-api` có thể yêu cầu ba task luôn sẵn sàng. Nếu một task dừng bất thường, bộ điều khiển phát hiện số task khỏe thấp hơn mong muốn và tạo task thay thế. Nếu tải tăng, autoscaling có thể nâng số lượng task; khi tải giảm, service có thể thu nhỏ số lượng bản sao theo chính sách đã cấu hình.

Service thường đảm nhiệm hoặc tích hợp các chức năng:

- Duy trì số lượng bản sao mong muốn và thay thế task lỗi.
- Phân phối lưu lượng qua load balancer hoặc service discovery.
- Kiểm tra sức khỏe và chỉ đưa bản sao đủ điều kiện vào phục vụ.
- Điều phối cập nhật theo rolling, blue-green hoặc chiến lược triển khai được nền tảng hỗ trợ.
- Tích hợp autoscaling, chính sách mạng, vùng sẵn sàng và giám sát.

Service không đồng nghĩa với một tiến trình hay một task. Một service có thể quản lý nhiều task cùng lúc. Tính sẵn sàng còn phụ thuộc vào cách phân bố task qua các vùng sẵn sàng, sức khỏe của dependency, cấu hình cân bằng tải và khả năng xử lý khi một vùng gặp sự cố.

Cần phân biệt hai tình huống:

| Cách chạy | Hành vi điển hình | Ví dụ phù hợp |
|---|---|---|
| Chạy task độc lập | Người vận hành hoặc lịch chạy khởi tạo một lần; task có thể kết thúc sau khi hoàn thành | Migration cơ sở dữ liệu, tác vụ batch, xử lý file |
| Chạy qua service | Nền tảng duy trì số lượng bản sao, thay thế task lỗi và quản lý endpoint | API, web backend, worker liên tục |

Với worker xử lý hàng đợi, service có thể không cần load balancer HTTP nhưng vẫn cần duy trì số lượng worker, cấp quyền đọc queue, xuất metric và mở rộng theo độ dài hàng đợi.

## 4. Revision: phiên bản cấu hình triển khai

Revision là một bản ghi phiên bản của cấu hình triển khai. Revision thường gắn với image, tài nguyên, biến môi trường, secret được tham chiếu, cổng, lệnh khởi động và các thiết lập runtime. Khi tạo revision mới, nền tảng giữ lại revision cũ để có thể kiểm tra lịch sử hoặc chuyển lưu lượng quay lại nếu mô hình triển khai hỗ trợ.

Một revision nên được xem như một bản chụp cấu hình có thể nhận diện và tái lập. Ví dụ:

- Revision 17 chạy image `checkout-api` với digest A, 0,5 vCPU và 1 GiB bộ nhớ.
- Revision 18 chạy digest B, tăng bộ nhớ lên 2 GiB và cập nhật một biến cấu hình.
- Service bắt đầu triển khai revision 18, tạo các task mới, kiểm tra sức khỏe rồi giảm dần task theo revision 17.

Trong Amazon ECS, revision thuộc về **task definition**. Khi đăng ký task definition mới, ECS tạo một revision mới; service có thể được cập nhật để sử dụng revision đó. Task đang chạy không tự biến đổi cấu hình tại chỗ: service triển khai task mới từ revision mới rồi thay thế task cũ theo cấu hình deployment.

Trong Google Cloud Run, revision là phiên bản bất biến của cấu hình service hoặc job tương ứng. Với Cloud Run service, nhiều revision có thể cùng tồn tại và nhận các tỷ lệ lưu lượng khác nhau. Điều này hỗ trợ triển khai canary hoặc chuyển toàn bộ lưu lượng về revision trước đó. Khái niệm task trong Cloud Run thường gắn với lần thực thi job; với HTTP service, nên dùng đúng thuật ngữ instance và revision của Cloud Run.

Không nên dựa vào tag image có thể thay đổi như `latest` để nhận diện chính xác một revision. Nếu tag được đẩy lại với nội dung khác, cùng một chuỗi cấu hình có thể chạy image khác nhau ở các thời điểm khác nhau. Dùng digest bất biến, lưu metadata build và giữ liên kết giữa revision với commit hoặc bản phát hành giúp truy vết và rollback đáng tin cậy hơn.

Revision cũng không bảo đảm toàn bộ hệ thống có thể rollback an toàn. Nếu phiên bản mới đã thay đổi schema cơ sở dữ liệu theo cách phiên bản cũ không đọc được, chuyển lưu lượng về revision cũ có thể vẫn gây lỗi. Thay đổi dữ liệu cần có chiến lược tương thích ngược, migration theo nhiều bước và kế hoạch khôi phục riêng.

## 5. Đơn vị triển khai container

Đơn vị triển khai là phạm vi mà một lần phát hành tác động đến. Khi xác định đơn vị này, cần trả lời: đối tượng nào được tạo phiên bản mới, đối tượng nào được thay thế, lưu lượng được chuyển ở đâu và rollback sẽ đưa phần nào trở về phiên bản trước?

Không có một định nghĩa duy nhất áp dụng cho mọi nền tảng:

| Nền tảng | Đối tượng thực thi | Đối tượng quản lý hoặc định tuyến | Đơn vị thường dùng khi triển khai |
|---|---|---|---|
| Amazon ECS | Task chạy từ task definition | ECS service duy trì số task và có thể tích hợp load balancer | Deployment của service, gồm các task thuộc task set hoặc revision cấu hình được triển khai |
| Google Cloud Run | Instance phục vụ request; task trong Cloud Run Jobs | Cloud Run service cung cấp endpoint và quản lý phân phối lưu lượng | Revision; có thể chuyển lưu lượng giữa nhiều revision |
| Kubernetes | Pod chứa một hoặc nhiều container | Service cung cấp endpoint mạng ổn định; Deployment quản lý ReplicaSet và rollout | Deployment/ReplicaSet rollout; Pod là bản thực thi được thay thế |

Trong một ứng dụng đơn giản, một service có thể tương ứng với một đơn vị triển khai. Trong hệ thống nhiều thành phần, API, worker và scheduler có thể là các service riêng với nhịp phát hành khác nhau. Nếu gộp nhiều thành phần không cần cập nhật cùng nhau vào một đơn vị, một thay đổi nhỏ có thể buộc triển khai lại toàn bộ nhóm, làm tăng phạm vi ảnh hưởng và thời gian phát hành.

Ngược lại, chia quá nhỏ làm tăng số cấu hình, endpoint, quyền truy cập, pipeline và cảnh báo phải vận hành. Nên tách đơn vị triển khai theo ranh giới trách nhiệm, yêu cầu mở rộng, yêu cầu bảo mật và mức độ độc lập khi phát hành.

Một task gồm ứng dụng chính và sidecar thường được triển khai cùng nhau vì chúng cần phối hợp trong cùng một lần thực thi. Nhưng API và worker đọc cùng một queue có thể nên là hai service riêng: API mở rộng theo lưu lượng HTTP, còn worker mở rộng theo lượng công việc chờ xử lý.

## 6. Ví dụ thực tế: triển khai checkout API trên ECS Fargate

Giả sử nhóm phát triển vận hành API thanh toán có tên `checkout-api`. Ứng dụng cần ba bản sao, lắng nghe cổng 8080 và được truy cập qua Application Load Balancer.

### 6.1. Khai báo cấu hình task

Cấu hình minh họa dưới đây mô tả các thuộc tính chính của task definition; đây là YAML rút gọn để học mô hình, không phải file task definition JSON hoàn chỉnh của ECS.

~~~yaml
family: checkout-api
revision: 17
runtime: FARGATE
networkMode: awsvpc
cpu: 512
memory: 1024
containers:
  - name: api
    image: registry.example.com/checkout-api@sha256:IMAGE_DIGEST_A
    port: 8080
    environment:
      APP_ENV: production
    secrets:
      DATABASE_URL: secret-reference
    healthCheck:
      command: ["CMD-SHELL", "curl -f http://localhost:8080/health/ready"]
    logging:
      driver: awslogs
taskRole: checkout-api-runtime-role
~~~

Task role chỉ nên có quyền mà ứng dụng thực sự cần, ví dụ đọc một secret hoặc ghi vào một bucket cụ thể. Không đưa mật khẩu hoặc token trực tiếp vào image hay file cấu hình được lưu trong mã nguồn.

### 6.2. Tạo service và duy trì số bản sao

Service `checkout-api` sử dụng task definition revision 17 và đặt desired count bằng 3. Service chạy task trong các subnet đã chọn, gắn với target group của load balancer và bật kiểm tra sức khỏe.

Desired count bằng 3 là trạng thái mong muốn, không phải cam kết rằng luôn có đúng ba task khỏe trong mọi thời điểm. Khi triển khai hoặc một vùng gặp lỗi, số task sẵn sàng có thể tạm thời thay đổi theo giới hạn triển khai, năng lực cụm và thời gian khởi động.

Để tăng khả năng sẵn sàng, nên phân bố task trên nhiều Availability Zone, cấu hình health check phù hợp và dành đủ năng lực để tạo task mới trong khi task cũ vẫn phục vụ. Nếu cấu hình triển khai yêu cầu quá nhiều task mới cùng lúc, tài nguyên có thể không đủ; nếu cho phép quá ít task hoạt động, dịch vụ có thể thiếu năng lực trong lúc thay thế.

### 6.3. Phát hành revision mới

Nhóm phát hành image mới với digest B, sau đó đăng ký task definition revision 18. Revision 18 có thể thay đổi image, tăng bộ nhớ lên 2 GiB và cập nhật một cấu hình tương thích. Service được cập nhật để dùng revision 18.

Quy trình rolling deployment điển hình:

1. Nền tảng tạo một hoặc nhiều task mới từ revision 18.
2. Task mới khởi động, tải cấu hình và secret, sau đó vượt qua health check.
3. Load balancer đưa task mới vào nhóm phục vụ khi target đủ khỏe.
4. Nền tảng ngừng nhận request mới trên task cũ, chờ kết nối đang xử lý kết thúc theo thời gian drain.
5. Task thuộc revision 17 được dừng dần cho đến khi service đạt trạng thái mong muốn bằng revision 18.

Với API có request kéo dài, cần đặt thời gian graceful shutdown và deregistration delay phù hợp. Nếu task bị dừng ngay khi đang xử lý request, người dùng có thể gặp lỗi dù rollout được báo thành công.

### 6.4. Kiểm tra sau triển khai

Có thể dùng AWS CLI để kiểm tra revision, trạng thái service và các task đang chạy:

~~~bash
aws ecs describe-task-definition \
  --task-definition checkout-api:18

aws ecs describe-services \
  --cluster prod \
  --services checkout-api

aws ecs list-tasks \
  --cluster prod \
  --service-name checkout-api \
  --desired-status RUNNING
~~~

Sau khi lấy ARN của các task, dùng `describe-tasks` để kiểm tra trạng thái từng task, task definition ARN, lý do dừng và container health. Đồng thời kiểm tra target health của load balancer, log khởi động, metric lỗi và độ trễ. Một service có số task đang chạy đúng vẫn có thể không phục vụ được request nếu target chưa khỏe, ứng dụng không bind đúng cổng hoặc dependency bị lỗi.

Chỉ kết thúc phát hành khi đã xác nhận:

- Service ổn định và các task mới dùng đúng revision 18.
- Số task khỏe đạt mức mong muốn, phân bố đúng vùng sẵn sàng.
- Target group báo healthy và request thử nghiệm qua endpoint thành công.
- Tỷ lệ lỗi, độ trễ, CPU, bộ nhớ và log không có dấu hiệu bất thường.
- Các luồng nghiệp vụ quan trọng, chẳng hạn tạo đơn hoặc xác nhận thanh toán, hoạt động đúng.

Nếu kiểm tra thất bại, dừng việc tăng lưu lượng và triển khai lại revision trước theo quy trình rollback của nền tảng. Sau rollback, vẫn cần kiểm tra task, target health và request thực tế; trạng thái rollout hoàn tất không thay thế việc xác minh chức năng.

## 7. Chiến lược phát hành và đánh đổi vận hành

**Rolling deployment** thay task hoặc instance theo từng nhóm. Cách này tận dụng tài nguyên hiện có và thường phù hợp với dịch vụ stateless. Tuy nhiên, trong một khoảng thời gian có thể đồng thời tồn tại hai revision; ứng dụng và schema dữ liệu phải tương thích giữa các phiên bản.

**Blue-green deployment** chuẩn bị môi trường hoặc nhóm task mới song song với nhóm cũ, sau đó chuyển lưu lượng. Cách này giúp chuyển đổi nhanh và có điểm quay lại rõ ràng, nhưng cần thêm năng lực chạy song song và phải quản lý kết nối, session, dữ liệu trong lúc chuyển đổi.

**Canary deployment** đưa một tỷ lệ nhỏ lưu lượng đến revision mới, theo dõi lỗi và độ trễ rồi tăng dần. Cách này giảm phạm vi ảnh hưởng ban đầu nhưng cần metric đáng tin cậy, tiêu chí dừng rõ ràng và khả năng định tuyến lưu lượng theo revision.

Khi chọn chiến lược, cần cân nhắc các yếu tố sau:

| Yếu tố | Cần quyết định | Rủi ro nếu cấu hình không phù hợp |
|---|---|---|
| Số task và năng lực dự phòng | Có đủ CPU, bộ nhớ, quota và IP để chạy task mới cùng task cũ không? | Deployment bị kẹt hoặc thiếu bản sao phục vụ |
| Health check | Kiểm tra tiến trình, readiness hay khả năng truy cập dependency nào? | Task chưa sẵn sàng nhận request hoặc task tốt bị thay liên tục |
| Thời gian dừng | Ứng dụng cần bao lâu để từ chối request mới và hoàn tất request đang chạy? | Mất request, lỗi kết nối hoặc dừng kéo dài |
| Autoscaling | Mở rộng theo CPU, request, concurrency hay độ dài queue? | Thiếu năng lực khi tải tăng hoặc chi phí cao khi tải giảm |
| Cấu hình và secret | Revision tham chiếu cấu hình nào; secret được cấp quyền và xoay vòng ra sao? | Revision khó tái lập hoặc lộ thông tin nhạy cảm |
| Dữ liệu và rollback | Phiên bản cũ có tương thích với schema và dữ liệu do phiên bản mới tạo ra không? | Rollback ứng dụng thành công nhưng nghiệp vụ vẫn lỗi |

Với workload stateless, task có thể được thay thế bất cứ lúc nào nếu dữ liệu và session được lưu ở hệ thống bên ngoài. Với workload stateful, cần thiết kế volume, cơ chế đồng bộ và quy trình khôi phục riêng; không nên giả định rằng thay task đồng nghĩa dữ liệu của task sẽ được bảo toàn.

Tăng số task cũng không tự động làm ứng dụng nhanh hơn. Cần kiểm tra giới hạn kết nối cơ sở dữ liệu, throughput của queue, quota mạng và khả năng xử lý của dependency. Nếu mỗi task mở quá nhiều kết nối, scale out có thể làm hệ thống phía sau quá tải.

## 8. Đối chiếu nhanh giữa các nền tảng

Khi làm việc với tài liệu hoặc giao diện của nhà cung cấp, hãy tìm đúng đối tượng tương ứng thay vì áp dụng máy móc tên gọi từ nền tảng khác:

- **Amazon ECS:** task definition mô tả cấu hình; task là lần chạy; service duy trì số task; mỗi lần đăng ký task definition tạo revision mới.
- **Google Cloud Run:** service cung cấp endpoint; revision lưu phiên bản cấu hình và có thể nhận tỷ lệ traffic riêng; job execution sử dụng task cho công việc hữu hạn.
- **Kubernetes:** Pod là đơn vị thực thi container; Deployment quản lý rollout thông qua ReplicaSet; Service cung cấp endpoint mạng ổn định. Kubernetes không có đối tượng Task tương đương hoàn toàn với ECS Task.

Khi đọc một nền tảng mới, hãy xác định bốn điểm: cấu hình nào tạo ra bản chạy, controller nào duy trì số lượng bản chạy, phiên bản nào được lưu lại và đối tượng nào nhận lưu lượng khi triển khai.

## 9. Các bước xác minh theo vòng đời

Có thể áp dụng quy trình sau cho mỗi lần phát hành container:

1. **Trước phát hành:** xác nhận image digest, revision dự kiến, CPU/bộ nhớ, cổng, quyền runtime, secret và health check.
2. **Khi bắt đầu:** xác nhận service đang dùng revision cũ và có đủ năng lực để chạy song song theo chiến lược triển khai.
3. **Trong rollout:** quan sát số task theo từng revision, trạng thái khởi động, health check, event của service và target health.
4. **Sau rollout:** kiểm tra revision đang nhận traffic, gọi thử endpoint và chạy smoke test nghiệp vụ; đối chiếu error rate, latency, CPU và memory.
5. **Nếu có lỗi:** dừng tăng traffic, thu thập event/log, rollback về revision tương thích và xác minh lại chức năng sau rollback.

Với Cloud Run, có thể kiểm tra service và danh sách revision bằng các lệnh sau; thay tên revision và region theo môi trường thực tế:

~~~bash
gcloud run services describe checkout-api --region asia-southeast1
gcloud run revisions list --service checkout-api --region asia-southeast1
~~~

Với Kubernetes, trạng thái rollout và lịch sử Deployment có thể được kiểm tra bằng:

~~~bash
kubectl rollout status deployment/checkout-api -n production
kubectl rollout history deployment/checkout-api -n production
~~~

Các lệnh chỉ cung cấp trạng thái của đối tượng nền tảng. Vẫn cần kiểm tra request thực tế, log và metric của ứng dụng để xác nhận người dùng có thể sử dụng dịch vụ.

## 10. Checklist thiết kế và phát hành

- [ ] Đã xác định task là công việc chạy một lần hay bản chạy do service duy trì.
- [ ] Đã xác định container nào cần nằm chung trong một task và lý do phối hợp của chúng.
- [ ] Image được ghim bằng digest; revision có thể truy vết về build hoặc commit.
- [ ] CPU, bộ nhớ, cổng, mạng, quyền runtime, secret và logging đã được khai báo.
- [ ] Service có desired count, health check, phân bố vùng và chính sách autoscaling phù hợp.
- [ ] Đã chọn đơn vị triển khai và chiến lược rolling, blue-green hoặc canary phù hợp với yêu cầu sẵn sàng.
- [ ] Ứng dụng xử lý graceful shutdown và tương thích với các revision cùng tồn tại trong rollout.
- [ ] Đã có tiêu chí xác nhận thành công, điều kiện dừng và phương án rollback.
- [ ] Sau phát hành đã kiểm tra revision, task khỏe, target health, request, log và metric.
- [ ] Đã xem xét ảnh hưởng của thay đổi schema, session và dữ liệu khi rollback.

Khi nắm rõ task, service, revision và đơn vị triển khai, người vận hành có thể đọc đúng trạng thái của nền tảng, dự đoán tác động của mỗi lần phát hành và chọn cách mở rộng hoặc khôi phục phù hợp. Đây là nền tảng để vận hành workload container ổn định, an toàn và kiểm soát được chi phí trên đám mây.
