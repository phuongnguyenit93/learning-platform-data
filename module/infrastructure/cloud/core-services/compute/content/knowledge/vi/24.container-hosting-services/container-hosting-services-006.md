# Co giãn container theo yêu cầu, mức đồng thời hoặc hàng đợi

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vì sao số lượng container cần thay đổi theo tải thay vì cố định quanh năm.
- Chọn tín hiệu co giãn phù hợp: CPU, bộ nhớ, số yêu cầu đang xử lý hoặc độ dài hàng đợi.
- Ước lượng số bản sao cần chạy và thiết lập giới hạn co giãn an toàn.
- Cấu hình co giãn cho workload HTTP và worker xử lý hàng đợi.
- Kiểm chứng quá trình scale out, scale in, khả năng phục hồi và ảnh hưởng đến chi phí.

## 1. Vì sao cần co giãn container?

Một dịch vụ container thường có tải thay đổi theo giờ, ngày hoặc sự kiện. API bán hàng có thể nhận lượng truy cập cao trong đợt khuyến mãi; dịch vụ gửi email có thể nhận hàng nghìn công việc sau khi một chiến dịch kết thúc; hệ thống xử lý ảnh có thể chỉ bận vào một số khung giờ.

Nếu luôn chạy số lượng container đủ cho giờ cao điểm, phần lớn tài nguyên sẽ nhàn rỗi khi tải thấp. Nếu chỉ chạy đủ cho mức tải trung bình, hệ thống có thể phản hồi chậm hoặc từ chối yêu cầu khi tải tăng đột ngột.

Co giãn tự động điều chỉnh số bản sao container theo nhu cầu quan sát được. Bộ điều khiển thu thập số liệu, so sánh với mục tiêu và thay đổi số bản sao trong giới hạn đã cấu hình. Khi tải tăng, hệ thống thực hiện **scale out**; khi tải giảm ổn định, hệ thống **scale in**.

Ví dụ, một API có thể chạy tối thiểu 2 bản sao để duy trì khả năng phục vụ và tăng lên tối đa 30 bản sao khi lượng yêu cầu tăng. Một worker xử lý đơn hàng có thể tăng từ 1 lên 20 bản sao khi hàng đợi có nhiều thông điệp chưa xử lý.

Co giãn theo chiều ngang thay đổi số lượng bản sao. Đây là cách phổ biến với container vì ứng dụng có thể phân phối tải giữa nhiều instance. Co giãn theo chiều dọc thay đổi CPU hoặc bộ nhớ của một instance; cách này hữu ích trong một số trường hợp nhưng thường cần cân nhắc thời gian khởi động lại, giới hạn tài nguyên của node và khả năng mở rộng của ứng dụng.

## 2. Chọn tín hiệu co giãn phù hợp

Tín hiệu co giãn phải phản ánh nguyên nhân làm dịch vụ quá tải. Chọn một chỉ số dễ đo nhưng không liên quan trực tiếp đến nút thắt có thể khiến hệ thống tăng container mà độ trễ vẫn không giảm.

| Tín hiệu | Phù hợp với | Ưu điểm | Hạn chế cần lưu ý |
|---|---|---|---|
| CPU sử dụng | API hoặc worker có tác vụ tính toán nặng | Dễ thu thập, được hỗ trợ rộng rãi | Không phản ánh đầy đủ tình trạng chờ I/O, khóa hoặc phụ thuộc bên ngoài |
| Bộ nhớ | Dịch vụ có mức dùng bộ nhớ tăng theo số phiên hoặc dữ liệu đang xử lý | Giúp tránh thiếu bộ nhớ và bị OOM kill | Bộ nhớ có thể không giảm ngay sau khi tải giảm; scale in dựa riêng vào bộ nhớ có thể chậm |
| Số yêu cầu đồng thời | API, dịch vụ HTTP hoặc RPC | Gần với lượng công việc đang giữ tài nguyên | Một yêu cầu nhẹ và một yêu cầu nặng có thể có chi phí rất khác nhau |
| Độ dài hàng đợi | Worker xử lý bất đồng bộ | Đo trực tiếp lượng công việc đang chờ | Cần tính đến tốc độ xử lý, thời gian chờ cho phép và kích thước thông điệp |
| Tuổi thông điệp lâu nhất | Hàng đợi cần đáp ứng SLA thời gian | Phát hiện backlog bị tồn đọng dù số lượng chưa quá lớn | Phụ thuộc vào metric và độ trễ cập nhật của hệ thống hàng đợi |
| Tốc độ đến và tốc độ xử lý | Pipeline có lưu lượng biến động mạnh | Giúp dự báo năng lực cần thiết | Cần số liệu ổn định và mô hình đo chính xác |

### 2.1. Co giãn theo CPU hoặc bộ nhớ

CPU phù hợp khi lượng công việc tăng làm thời gian tính toán trên mỗi container tăng. Ví dụ, API tạo báo cáo hoặc worker mã hóa video thường sử dụng CPU đáng kể.

Bộ nhớ phù hợp khi số phiên, dữ liệu đệm hoặc tác vụ đang hoạt động làm bộ nhớ tăng theo tải. Tuy nhiên, cần phân biệt bộ nhớ thực sự cần cho tải hiện tại với bộ nhớ mà runtime giữ lại để tái sử dụng. Một container có thể tiếp tục giữ vùng nhớ đã cấp phát dù số yêu cầu giảm.

Trong Kubernetes, Horizontal Pod Autoscaler (HPA) có thể lấy metric tài nguyên từ Metrics Server. Với metric CPU dạng phần trăm, container cần khai báo CPU request để HPA có cơ sở tính mức sử dụng. Nếu request không được khai báo, metric CPU utilization có thể không được tính đúng cho container đó.

### 2.2. Co giãn theo số yêu cầu đồng thời

Đồng thời (concurrency) là số yêu cầu hoặc tác vụ đang được một instance xử lý tại cùng thời điểm. Chỉ số này hữu ích khi một instance có giới hạn thực tế về số kết nối, luồng xử lý hoặc bộ nhớ cho mỗi yêu cầu.

Giả sử một API có mục tiêu 40 yêu cầu đồng thời trên mỗi container. Nếu đang có khoảng 240 yêu cầu đồng thời và các container phân phối tải tương đối đều, ước lượng ban đầu là:

    Số bản sao cần thiết = ceil(240 / 40) = 6

Đây là ước lượng năng lực, không phải cam kết rằng hệ thống luôn có đúng 6 container. Bộ điều khiển còn xét số bản sao hiện tại, metric trong các chu kỳ đo, thời gian khởi động và giới hạn min/max. Cần kiểm tra độ trễ và tỷ lệ lỗi để xác nhận mục tiêu concurrency phù hợp.

Dịch vụ quản lý container như Google Cloud Run cho phép cấu hình concurrency tối đa trên mỗi instance cùng số instance tối thiểu và tối đa. Khi chọn concurrency quá cao, mỗi instance có thể nhận nhiều yêu cầu hơn khả năng xử lý, gây tăng độ trễ hoặc cạn kết nối đến cơ sở dữ liệu. Khi chọn quá thấp, hệ thống có thể tạo nhiều instance hơn cần thiết và tăng chi phí khởi động.

### 2.3. Co giãn theo độ dài hàng đợi

Worker thường không nhận yêu cầu trực tiếp từ người dùng. Producer ghi công việc vào hàng đợi; worker lấy thông điệp, xử lý và xác nhận hoàn tất. Độ dài hàng đợi cho biết lượng công việc đang chờ, vì vậy phù hợp để điều chỉnh số worker.

Giả sử chính sách đặt mục tiêu không quá 30 thông điệp đang chờ cho mỗi worker. Khi hàng đợi có 900 thông điệp, số worker ước lượng là:

    Số worker cần thiết = ceil(900 / 30) = 30

Nếu cấu hình tối đa chỉ cho phép 20 worker, hệ thống sẽ dừng ở 20 và backlog tiếp tục được xử lý dần. Điều này cho thấy giới hạn co giãn phải được chọn cùng với SLA xử lý và năng lực của các dịch vụ phụ thuộc.

Độ dài hàng đợi không phải lúc nào cũng đủ. Nếu thông điệp có thời gian xử lý rất khác nhau, 100 thông điệp đơn giản có thể được xử lý nhanh hơn 10 thông điệp cần tính toán nặng. Nên theo dõi thêm tuổi thông điệp lâu nhất, tốc độ đến, tốc độ hoàn tất và tỷ lệ lỗi.

Có thể ước lượng năng lực worker theo thông lượng. Gọi:

- λ là tốc độ công việc đến, tính bằng công việc mỗi phút.
- μ là tốc độ một worker xử lý, tính bằng công việc mỗi phút.
- ρ là mức sử dụng mục tiêu, nhỏ hơn 1 để giữ khoảng dự phòng.

Số worker tối thiểu để theo kịp tải ổn định có thể ước lượng bằng:

    N = ceil(λ / (μ × ρ))

Ví dụ, hàng đợi nhận 120 công việc mỗi phút; mỗi worker xử lý trung bình 10 công việc mỗi phút; mục tiêu sử dụng là 70%:

    N = ceil(120 / (10 × 0,7)) = 18 worker

Phép tính này giả định tốc độ xử lý tương đối ổn định. Khi có backlog tồn đọng, cần bổ sung năng lực để vừa xử lý công việc mới vừa giảm backlog trong thời gian yêu cầu.

## 3. Cơ chế điều khiển và các tham số quan trọng

Một vòng co giãn thường gồm bốn bước:

1. Thu thập metric từ nền tảng container, bộ cân bằng tải, hệ thống giám sát hoặc message broker.
2. Bộ điều khiển so sánh giá trị hiện tại với mục tiêu đã cấu hình.
3. Nền tảng tăng hoặc giảm số bản sao trong phạm vi cho phép.
4. Bộ điều khiển đo lại sau một khoảng thời gian và tiếp tục điều chỉnh.

Các tham số sau ảnh hưởng trực tiếp đến độ ổn định:

- **Số bản sao tối thiểu (min replicas/instances):** giữ sẵn năng lực cơ bản. Giá trị 0 có thể tiết kiệm chi phí khi không có tải, nhưng yêu cầu đầu tiên có thể phải chờ khởi động.
- **Số bản sao tối đa (max replicas/instances):** giới hạn chi phí và mức tiêu thụ tài nguyên. Cần đặt theo quota, ngân sách, năng lực node và giới hạn của hệ thống phụ thuộc.
- **Mục tiêu metric:** ví dụ CPU trung bình 65%, tối đa 40 yêu cầu đồng thời trên một instance hoặc 30 thông điệp chờ trên một worker.
- **Chu kỳ lấy mẫu và polling:** metric được cập nhật theo chu kỳ. Chu kỳ quá dài khiến phản ứng chậm; quá ngắn có thể làm hệ thống phản ứng với dao động ngắn.
- **Thời gian ổn định (stabilization window):** trì hoãn scale in để tránh giảm bản sao ngay sau một nhịp tải thấp ngắn.
- **Cooldown:** khoảng chờ sau một lần điều chỉnh, thường hữu ích với scaler dựa trên sự kiện.
- **Tốc độ scale:** giới hạn số bản sao được thêm hoặc loại bỏ trong một khoảng thời gian.
- **Readiness và startup:** container mới chỉ nên nhận tải sau khi ứng dụng sẵn sàng. Nếu thời gian khởi động dài, cần tính đến độ trễ từ lúc có tín hiệu đến lúc có năng lực phục vụ.

Nên dùng chính sách tăng nhanh khi tải tăng và giảm từ từ khi tải giảm. Scale out chậm có thể làm backlog hoặc độ trễ tăng mạnh. Scale in quá nhanh có thể ngắt yêu cầu đang xử lý, làm worker bỏ dở công việc hoặc khiến hệ thống liên tục bật tắt container.

## 4. Ví dụ thực hành: Kubernetes HPA cho API

Giả sử dịch vụ checkout chạy bằng Deployment tên checkout-api. Mỗi Pod khai báo CPU request 500 millicore và memory request 512 MiB. HPA sẽ giữ tối thiểu 2 Pod, tăng tối đa 30 Pod và hướng đến CPU trung bình 65% so với CPU request.

Phần khai báo tài nguyên trong container có thể như sau:

    resources:
      requests:
        cpu: 500m
        memory: 512Mi
      limits:
        cpu: "1"
        memory: 1Gi

Ví dụ HPA dùng API autoscaling/v2:

    apiVersion: autoscaling/v2
    kind: HorizontalPodAutoscaler
    metadata:
      name: checkout-api
    spec:
      scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: checkout-api
      minReplicas: 2
      maxReplicas: 30
      behavior:
        scaleUp:
          stabilizationWindowSeconds: 0
          policies:
            - type: Percent
              value: 100
              periodSeconds: 60
        scaleDown:
          stabilizationWindowSeconds: 300
          policies:
            - type: Percent
              value: 25
              periodSeconds: 60
      metrics:
        - type: Resource
          resource:
            name: cpu
            target:
              type: Utilization
              averageUtilization: 65

Trong ví dụ này, HPA có thể tăng số Pod nhanh khi CPU vượt mục tiêu. Khi tải giảm, HPA chờ cửa sổ ổn định 300 giây và giới hạn tốc độ giảm còn tối đa 25% mỗi 60 giây. Các giá trị chỉ là điểm bắt đầu; cần hiệu chỉnh bằng thử tải và số liệu vận hành.

Trước khi áp dụng, xác minh các điều kiện:

- Metrics Server hoạt động và API tài nguyên trả về được số liệu.
- Deployment có CPU request cho container cần đo.
- Ứng dụng có readiness probe phản ánh đúng khả năng nhận yêu cầu.
- Cluster còn đủ node và quota để tạo Pod mới.
- Service và Ingress phân phối lưu lượng đến các Pod đã sẵn sàng.

Có thể kiểm tra bằng các lệnh:

    kubectl apply -f checkout-hpa.yaml
    kubectl get hpa checkout-api
    kubectl describe hpa checkout-api
    kubectl get pods -l app=checkout-api -w
    kubectl top pods -l app=checkout-api

Nếu HPA hiển thị metric là unknown, kiểm tra Metrics Server, CPU request và sự kiện trong kết quả describe. Nếu số Pod không tăng dù CPU cao, kiểm tra maxReplicas, quota, trạng thái scheduling và tài nguyên còn trống trong cluster.

HPA cũng hỗ trợ metric tùy chỉnh và metric bên ngoài khi cluster được tích hợp adapter tương ứng. Có thể dùng số yêu cầu đang chờ hoặc số yêu cầu trên mỗi Pod làm tín hiệu. Việc cung cấp metric, đơn vị và cách tổng hợp phải nhất quán; HPA không tự hiểu một metric ứng dụng nếu chưa có thành phần đưa metric đó vào Kubernetes Metrics API.

## 5. Ví dụ thực hành: KEDA co giãn worker theo hàng đợi RabbitMQ

Giả sử một hệ thống thương mại điện tử ghi tác vụ gửi hóa đơn vào queue orders. Deployment order-worker đọc queue và xử lý từng thông điệp. Khi queue tăng, KEDA có thể dùng độ dài queue để điều chỉnh số Pod.

Ví dụ ScaledObject:

    apiVersion: keda.sh/v1alpha1
    kind: ScaledObject
    metadata:
      name: order-worker-scaler
    spec:
      scaleTargetRef:
        name: order-worker
      minReplicaCount: 0
      maxReplicaCount: 20
      pollingInterval: 15
      cooldownPeriod: 120
      advanced:
        horizontalPodAutoscalerConfig:
          behavior:
            scaleDown:
              stabilizationWindowSeconds: 300
      triggers:
        - type: rabbitmq
          metadata:
            protocol: amqp
            queueName: orders
            mode: QueueLength
            value: "30"
            hostFromEnv: RABBITMQ_HOST

Biến môi trường RABBITMQ_HOST trong Deployment nên lấy từ Kubernetes Secret:

    env:
      - name: RABBITMQ_HOST
        valueFrom:
          secretKeyRef:
            name: rabbitmq-connection
            key: host

Secret rabbitmq-connection cần được tạo và phân quyền truy cập phù hợp. Không ghi chuỗi kết nối có thông tin xác thực trực tiếp vào manifest được commit lên kho mã. Tên biến môi trường trong Deployment phải khớp với hostFromEnv.

Với cấu hình trên, KEDA kiểm tra queue theo chu kỳ polling 15 giây, dùng mục tiêu 30 thông điệp trên mỗi worker và điều chỉnh số bản sao trong khoảng 0 đến 20. HPA quản lý việc giảm số worker từ nhiều Pod xuống 1 Pod với cửa sổ ổn định 300 giây; cooldown 120 giây của KEDA trì hoãn bước scale từ 1 về 0 khi queue không còn công việc. Nếu cần luôn có worker sẵn sàng, đặt minReplicaCount thành 1 và vẫn cấu hình cửa sổ ổn định cho HPA. Giá trị thực tế cần dựa vào thời gian xử lý thông điệp và SLA của queue.

Trình tự triển khai và kiểm tra:

    kubectl apply -f order-worker.yaml
    kubectl apply -f order-worker-scaledobject.yaml
    kubectl get scaledobject
    kubectl describe scaledobject order-worker-scaler
    kubectl get hpa
    kubectl get pods -l app=order-worker -w

Sau đó đưa một lượng thông điệp thử nghiệm vào queue orders trong môi trường kiểm thử. Quan sát số thông điệp chờ, số worker, tốc độ hoàn tất và tuổi thông điệp lâu nhất. Khi queue giảm, xác nhận HPA giảm dần số worker theo cửa sổ ổn định; nếu cho phép scale to zero, quan sát bước giảm từ 1 về 0 sau cooldown.

Nếu KEDA không tạo được scaler hoặc metric, kiểm tra trạng thái ScaledObject, sự kiện, log của KEDA operator, quyền truy cập Secret và kết nối đến RabbitMQ. Nếu số worker chạm maxReplicaCount nhưng backlog vẫn tăng, cần xem lại giới hạn tối đa, tốc độ xử lý mỗi worker và năng lực của hệ thống phụ thuộc.

Worker phải xác nhận thông điệp sau khi xử lý thành công. Nếu container bị dừng trong lúc xử lý, broker cần có cơ chế đưa thông điệp chưa được xác nhận trở lại queue. Thiết kế xử lý idempotent để việc nhận lại thông điệp không tạo hóa đơn trùng hoặc gây tác dụng phụ lặp lại.

## 6. Ví dụ dịch vụ quản lý: co giãn API theo concurrency

Với nền tảng quản lý container như Google Cloud Run, nhóm vận hành có thể cấu hình số yêu cầu đồng thời tối đa trên mỗi instance, số instance tối thiểu và tối đa. Ví dụ, API tra cứu đơn hàng đặt giới hạn concurrency là 40 yêu cầu trên mỗi instance, tối thiểu 2 instance và tối đa 30 instance.

Khi lượng yêu cầu tăng, nền tảng có thể bổ sung instance theo tải và các tín hiệu nội bộ. Khi tải giảm, nền tảng giảm số instance theo chính sách của dịch vụ. Cấu hình concurrency là giới hạn quan trọng: một instance nhận quá nhiều yêu cầu có thể làm tăng độ trễ, tranh chấp CPU hoặc cạn connection pool.

Khi thử nghiệm, nên thay đổi giới hạn concurrency từng bước, ví dụ 10, 20 rồi 40 yêu cầu đồng thời trên mỗi instance. Với mỗi mức, đo p95/p99 latency, tỷ lệ lỗi, CPU, bộ nhớ và số kết nối đến cơ sở dữ liệu. Chọn giá trị đáp ứng SLA và giới hạn của downstream; không chọn chỉ dựa trên số request tối đa mà nền tảng cho phép.

Các nền tảng như Amazon ECS cũng hỗ trợ điều chỉnh số task của service dựa trên target tracking, chẳng hạn CPU, bộ nhớ hoặc số yêu cầu trên mỗi target của Application Load Balancer. Với worker, có thể dùng metric hàng đợi từ dịch vụ như Amazon SQS thông qua cơ chế metric và chính sách scaling thích hợp. Dù dùng nền tảng nào, nguyên tắc vẫn là chọn metric gắn với năng lực thực tế, đặt min/max và kiểm chứng hành vi khi tải tăng giảm.

## 7. Trade-off vận hành và cách tránh sự cố

### 7.1. Tốc độ phản ứng và chi phí

Scale out nhanh giúp hấp thụ đột biến nhưng có thể tạo nhiều container cùng lúc, làm tăng tải lên registry, mạng, node và dịch vụ phụ thuộc. Scale out chậm tiết kiệm tài nguyên hơn nhưng có thể khiến yêu cầu chờ lâu.

Đặt min replicas cao hơn giúp giảm thời gian khởi động khi có tải đột ngột, đổi lại phải trả chi phí cho năng lực nhàn rỗi. Scale to zero phù hợp với tác vụ ít dùng hoặc chấp nhận cold start; không phù hợp nếu mọi yêu cầu đều cần phản hồi tức thời.

### 7.2. Giới hạn dịch vụ phụ thuộc

Tăng số API Pod có thể đồng thời tăng số kết nối đến cơ sở dữ liệu. Nếu mỗi Pod mở connection pool 20 kết nối và hệ thống cho phép 30 Pod, số kết nối tiềm năng có thể lên đến 600. Nếu cơ sở dữ liệu chỉ chịu được 200 kết nối, scale out có thể chuyển nút thắt từ API sang database.

Cần đặt giới hạn connection pool, giới hạn concurrency, rate limit hoặc hàng đợi bảo vệ downstream. Max replicas nên được xác định từ năng lực của toàn bộ chuỗi xử lý, không chỉ từ tài nguyên container.

### 7.3. Khởi động và readiness

Container mới cần tải image, khởi tạo runtime, kết nối dịch vụ và làm nóng cache. Trong thời gian đó, Pod chưa sẵn sàng không nên nhận lưu lượng. Readiness probe phải phản ánh đúng trạng thái phục vụ; liveness probe không nên thất bại chỉ vì một phụ thuộc tạm thời chậm, nếu điều đó khiến container liên tục khởi động lại.

Với ứng dụng khởi động lâu, cân nhắc giữ một số bản sao tối thiểu, dùng image gọn, tối ưu bước khởi động và kiểm tra giới hạn tốc độ scale out của nền tảng.

### 7.4. Scale in an toàn

Khi giảm số bản sao, nền tảng có thể gửi tín hiệu kết thúc container. Ứng dụng cần dừng nhận yêu cầu mới, hoàn tất hoặc từ chối có kiểm soát các yêu cầu đang xử lý, rồi thoát trong thời hạn termination grace period.

Worker cần xử lý tín hiệu dừng, ngừng nhận thông điệp mới và hoàn tất hoặc để broker phát lại thông điệp chưa xác nhận. Thời gian visibility timeout hoặc ack timeout phải phù hợp với thời gian xử lý. Không xác nhận thông điệp trước khi kết quả được ghi bền vững.

### 7.5. Dao động số bản sao

Nếu metric liên tục vượt và xuống dưới ngưỡng, số bản sao có thể tăng giảm liên tục. Hiện tượng này làm chi phí và độ trễ không ổn định. Có thể giảm dao động bằng cửa sổ ổn định, cooldown, giới hạn tốc độ scale in, mục tiêu metric có khoảng dự phòng và metric được làm mượt.

Không nên đặt mục tiêu sát 100% năng lực. Hệ thống cần khoảng dự phòng để xử lý biến động, thời gian lấy mẫu và độ trễ khởi động container.

### 7.6. Quan sát đúng kết quả

Theo dõi đồng thời ba nhóm số liệu:

- **Năng lực:** số bản sao mong muốn và thực tế, CPU, bộ nhớ, số yêu cầu đồng thời, số worker sẵn sàng.
- **Chất lượng dịch vụ:** throughput, p95/p99 latency, tỷ lệ lỗi, timeout, số lần retry.
- **Hàng đợi:** queue depth, tuổi thông điệp lâu nhất, tốc độ đến, tốc độ hoàn tất, số thông điệp lỗi hoặc chuyển vào dead-letter queue.

Chỉ nhìn số container tăng lên chưa đủ để kết luận co giãn thành công. Nếu số Pod tăng nhưng độ trễ không giảm, có thể nút thắt nằm ở database, API bên ngoài, khóa dùng chung hoặc giới hạn mạng.

## 8. Quy trình kiểm chứng co giãn

Thực hiện trong môi trường kiểm thử hoặc staging với tải có kiểm soát:

1. **Ghi nhận đường cơ sở:** đo số bản sao, CPU, bộ nhớ, throughput, p95 latency và trạng thái hàng đợi khi tải thấp.
2. **Tăng tải từ từ:** tăng số người dùng hoặc tốc độ tạo thông điệp theo từng bước. Ghi lại thời điểm metric vượt mục tiêu.
3. **Kiểm tra scale out:** xác nhận số bản sao mong muốn tăng, container mới được schedule, readiness thành công và lưu lượng được phân phối.
4. **Kiểm tra chất lượng:** xác nhận p95/p99 latency, tỷ lệ lỗi và thời gian chờ hàng đợi nằm trong mục tiêu khi tải ổn định.
5. **Thử giới hạn tối đa:** tăng tải đến khi chạm max replicas. Xác nhận hệ thống bảo vệ downstream và cảnh báo backlog hoặc độ trễ tăng.
6. **Giảm tải:** ngừng tạo tải và quan sát scale in. Xác nhận cửa sổ ổn định/cooldown có tác dụng và số bản sao giảm từ từ.
7. **Thử dừng container:** chủ động kết thúc một Pod đang nhận tải hoặc xử lý thông điệp. Xác nhận yêu cầu được xử lý có kiểm soát và thông điệp không bị mất.
8. **Đối chiếu chi phí:** so sánh thời gian chạy, số instance trung bình và tài nguyên tiêu thụ với mục tiêu ngân sách.

Một lần kiểm thử nên bao gồm cả tải tăng nhanh và tải tăng chậm. Tải tăng nhanh kiểm tra khả năng phản ứng; tải tăng chậm giúp phát hiện mục tiêu metric hoặc ngưỡng scale chưa phù hợp. Với worker, nên thử thông điệp có thời gian xử lý khác nhau và trường hợp xử lý lỗi để đánh giá retry, idempotency và dead-letter queue.

## 9. Xử lý một số tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| CPU cao nhưng HPA không tăng Pod | Thiếu CPU request, metric không có, HPA chạm max | Kiểm tra describe HPA, Metrics Server, request và maxReplicas |
| Pod tăng nhưng latency không giảm | Nút thắt ở database, API ngoài, khóa hoặc network | Đối chiếu latency theo dependency, connection pool và throughput |
| Queue tăng nhưng worker không tăng | Scaler không đọc được queue hoặc metric | Kiểm tra ScaledObject, KEDA operator, Secret và quyền truy cập broker |
| Worker tăng nhưng queue vẫn tồn đọng | Năng lực mỗi worker thấp, max replicas quá thấp hoặc message lỗi lặp lại | Đo tốc độ xử lý, tuổi message, retry và dead-letter queue |
| Số Pod tăng giảm liên tục | Metric nhiễu, ngưỡng quá sát hoặc scale in quá nhanh | Tăng stabilization window/cooldown và giới hạn tốc độ scale in |
| Pod mới ở trạng thái Pending | Thiếu CPU/memory trên node, quota hoặc giới hạn scheduling | Kiểm tra events, node capacity, quota và autoscaler của cluster |
| Yêu cầu lỗi khi scale in | Ứng dụng không drain hoặc thời gian kết thúc quá ngắn | Kiểm tra graceful shutdown, readiness và termination grace period |

## 10. Checklist trước khi đưa vào production

- [ ] Chọn metric phản ánh đúng nút thắt: CPU, bộ nhớ, concurrency hoặc queue.
- [ ] Xác định min/max replicas từ SLA, quota, ngân sách và năng lực downstream.
- [ ] Khai báo resource requests/limits và readiness probe phù hợp.
- [ ] Cấu hình stabilization window, cooldown và tốc độ scale in/out.
- [ ] Bảo vệ thông tin kết nối broker bằng Secret hoặc kho bí mật của nền tảng.
- [ ] Giới hạn connection pool và concurrency để không làm quá tải dịch vụ phụ thuộc.
- [ ] Đảm bảo graceful shutdown, xử lý retry và idempotency cho worker.
- [ ] Theo dõi số bản sao, latency, lỗi, queue depth và tuổi thông điệp.
- [ ] Thử tải tăng, tải giảm, chạm max replicas và dừng container.
- [ ] Thiết lập cảnh báo khi metric không có, scaler lỗi hoặc backlog vượt SLA.

## Kết luận

Co giãn container hiệu quả bắt đầu từ việc chọn đúng tín hiệu. CPU phù hợp với workload thiên về tính toán; concurrency phù hợp với dịch vụ xử lý yêu cầu đồng thời; queue depth và tuổi thông điệp phù hợp với worker bất đồng bộ. Min/max, thời gian ổn định, readiness và khả năng drain quyết định hệ thống phản ứng có ổn định hay không. Hãy kiểm chứng bằng tải thực tế và theo dõi cả chất lượng dịch vụ lẫn năng lực của các thành phần phụ thuộc trước khi áp dụng chính sách vào production.
