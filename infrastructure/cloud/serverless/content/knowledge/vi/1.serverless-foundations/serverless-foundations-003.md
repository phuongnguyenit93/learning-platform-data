# So sánh serverless với máy ảo, container và Kubernetes

Khi triển khai một ứng dụng Java, nhóm phát triển có thể chạy ứng dụng trên máy ảo (VM), đóng gói ứng dụng thành container, điều phối container bằng Kubernetes hoặc triển khai các hàm serverless. Những lựa chọn này đều giúp đưa mã nguồn lên môi trường chạy thật, nhưng chúng đặt trách nhiệm vận hành ở những nơi khác nhau.

Trong module **CLOUD_SERVERLESS**, trọng tâm là mô hình serverless, đặc biệt là Function as a Service (FaaS): một hàm Java được gọi bởi HTTP request, thông điệp hoặc sự kiện. Để quyết định khi nào FaaS phù hợp, cần hiểu nó khác gì với VM, container và Kubernetes về đơn vị triển khai, quyền kiểm soát, khả năng mở rộng, trạng thái, độ trễ và chi phí.

## 1. Bốn khái niệm giải quyết những lớp vấn đề khác nhau

### Máy ảo (Virtual Machine)

Máy ảo mô phỏng một máy tính hoàn chỉnh trên hạ tầng vật lý hoặc nền tảng ảo hóa. Mỗi VM thường có hệ điều hành khách, CPU và bộ nhớ được cấp phát, đĩa lưu trữ và mạng riêng. Nhóm vận hành có quyền kiểm soát lớn đối với hệ điều hành, tiến trình, thư viện hệ thống, cổng mạng và cách ứng dụng chạy.

Đổi lại, nhóm phải quản lý nhiều việc: tạo và cấu hình VM, cập nhật hệ điều hành, vá lỗ hổng, cài JDK, giám sát tài nguyên, cấu hình cân bằng tải, mở rộng số máy và xử lý máy bị lỗi. Một ứng dụng Spring Boot có thể chạy như một tiến trình thường trực trên VM và tiếp tục phục vụ request kể cả khi không có lưu lượng.

### Container

Container đóng gói ứng dụng cùng các thư viện và cấu hình cần thiết thành một image có thể triển khai nhất quán ở nhiều môi trường. Container thường chia sẻ kernel của hệ điều hành máy chủ, vì vậy nhẹ hơn VM và khởi chạy nhanh hơn trong nhiều tình huống. Với Java, image có thể chứa JAR, JRE phù hợp và lệnh khởi chạy ứng dụng.

Container giải quyết tốt vấn đề đóng gói và tính nhất quán, nhưng tự nó không giải quyết toàn bộ việc vận hành. Vẫn cần một môi trường để chạy container, cấp CPU và bộ nhớ, quản lý mạng, thay thế instance lỗi, mở rộng số bản sao, lưu log và triển khai phiên bản mới. Môi trường đó có thể là một máy chủ đơn, một dịch vụ container được quản lý hoặc Kubernetes.

### Kubernetes

Kubernetes là nền tảng điều phối container. Người vận hành khai báo trạng thái mong muốn, chẳng hạn ứng dụng cần ba bản sao, mỗi bản sao có giới hạn tài nguyên cụ thể và phải được truy cập qua một Service. Kubernetes liên tục đối chiếu trạng thái thực tế với trạng thái mong muốn: lập lịch Pod lên node, khởi động lại container bị lỗi, thay thế Pod, hỗ trợ rolling update và mở rộng theo cấu hình.

Kubernetes không phải một định dạng đóng gói thay cho container. Trong cách triển khai phổ biến, container là đơn vị chạy, còn Kubernetes quản lý vòng đời và kết nối các đơn vị đó. Dù dùng dịch vụ Kubernetes được quản lý, nhóm vẫn cần hiểu và vận hành workload, cấu hình tài nguyên, quyền truy cập, mạng, lưu trữ, autoscaling, quan sát hệ thống và chi phí của cụm.

### Serverless và Function as a Service (FaaS)

Serverless là mô hình cung cấp dịch vụ trong đó nhà cung cấp cloud đảm nhận phần lớn việc cấp phát và vận hành hạ tầng nền. “Serverless” không có nghĩa là ứng dụng không chạy trên máy chủ; nó có nghĩa là người phát triển không trực tiếp quản lý máy chủ cho từng workload.

Với FaaS, đơn vị triển khai thường là một hàm hoặc một gói hàm. Hàm được kích hoạt bởi một trigger như HTTP request, thông điệp trong queue, thay đổi dữ liệu hoặc sự kiện theo lịch. Nền tảng tạo hoặc tái sử dụng môi trường thực thi, gọi hàm, quản lý số lượng phiên thực thi đồng thời và có thể giảm về không khi không có việc. Chi phí thường gắn với số lần gọi, thời gian thực thi và tài nguyên được cấp, tùy cách tính của nhà cung cấp.

FaaS giảm đáng kể công việc quản lý máy chủ, nhưng ứng dụng phải thích nghi với vòng đời thực thi của hàm. Một lần gọi có thể chạy trong môi trường mới hoặc môi trường đã được tái sử dụng; bộ nhớ và đĩa cục bộ không nên được xem là nơi lưu trạng thái lâu dài. Thời gian chạy, bộ nhớ, số lần gọi đồng thời, kích thước gói triển khai và thời lượng thực thi cũng có giới hạn theo từng nền tảng.

## 2. So sánh nhanh

| Tiêu chí | Máy ảo (VM) | Container | Kubernetes | Serverless FaaS |
|---|---|---|---|---|
| Đơn vị triển khai | Máy và hệ điều hành khách, sau đó là ứng dụng | Image chứa ứng dụng và phụ thuộc | Workload container, thường khai báo bằng Deployment/Job | Hàm hoặc gói hàm cùng cấu hình trigger |
| Ai quản lý máy chủ? | Nhóm vận hành hoặc nhà cung cấp VM ở lớp hạ tầng | Nhóm vận hành hoặc dịch vụ container quản lý máy chạy | Nhóm vận hành hoặc nhà cung cấp quản lý control plane/node | Nhà cung cấp cloud quản lý hạ tầng thực thi |
| Quyền kiểm soát môi trường | Rất cao | Cao ở cấp image; phụ thuộc môi trường chạy | Cao đối với workload và cấu hình cụm | Hạn chế hơn; chạy trong runtime và giới hạn của nền tảng |
| Vòng đời ứng dụng | Thường là tiến trình chạy liên tục | Container thường chạy liên tục hoặc theo tác vụ | Pod được duy trì theo trạng thái khai báo | Hàm chạy khi có trigger; môi trường có thể được tái sử dụng |
| Mở rộng | Thường cấu hình VM, autoscaling group và cân bằng tải | Tăng số container bằng công cụ hoặc dịch vụ chạy container | Có cơ chế điều phối và autoscaling | Nền tảng tự điều chỉnh số phiên thực thi theo tải trong giới hạn quota |
| Khi không có tải | VM vẫn thường được cấp phát | Container hoặc máy chạy có thể vẫn tồn tại | Node và workload thường vẫn tiêu thụ tài nguyên | Có thể scale về zero nếu cấu hình và loại dịch vụ hỗ trợ |
| Trạng thái | Có thể dùng đĩa và tiến trình lâu dài, nhưng cần thiết kế HA/backup | Thường nên để trạng thái bên ngoài container | Có thể dùng volume, database hoặc dịch vụ ngoài cụm | Nên lưu trạng thái ở database, object storage hoặc dịch vụ bền vững bên ngoài |
| Công việc vận hành | OS, vá lỗi, mạng, triển khai, mở rộng, giám sát | Image, runtime, host, mạng, triển khai và mở rộng | Cụm, node, workload, policy, mạng, lưu trữ và quan sát | Trigger, quyền, cấu hình hàm, giới hạn, retry, log và dịch vụ phụ trợ |
| Cách tính chi phí thường gặp | Tài nguyên VM theo thời gian cấp phát, cộng lưu trữ và mạng | Máy chạy hoặc tài nguyên container theo thời gian, cộng lưu trữ và mạng | Node/cụm và dịch vụ đi kèm theo thời gian, cộng tài nguyên workload | Số lần gọi, thời lượng, tài nguyên và các dịch vụ liên quan |

Bảng trên mô tả xu hướng phổ biến. Dịch vụ managed có thể thay đổi trách nhiệm vận hành và cách tính phí; ví dụ một dịch vụ container có thể tự scale về zero, còn một dịch vụ FaaS có thể cho phép cấu hình số instance tối thiểu để giảm độ trễ.

## 3. Khác biệt quan trọng trong kiến trúc và vận hành

### Đơn vị triển khai và quyền kiểm soát

Với VM, nhóm thường triển khai một ứng dụng hoặc nhiều tiến trình lên một máy đã cài hệ điều hành và runtime. Nhóm có thể thay đổi cấu hình hệ thống sâu, nhưng phải chịu trách nhiệm cho nhiều lớp hơn.

Với container, nhóm chuyển trọng tâm sang image: image cần chứa đúng JRE, ứng dụng và phụ thuộc. Cùng một image có thể chạy trên laptop, máy chủ, dịch vụ container hoặc Kubernetes nếu môi trường tương thích. Tuy vậy, ai cấp máy chạy và xử lý container lỗi vẫn là câu hỏi riêng.

Với Kubernetes, nhóm mô tả cách workload phải hoạt động: số replica, tài nguyên, health check, cấu hình triển khai, Service và chính sách mở rộng. Nền tảng điều phối việc thực hiện các khai báo đó. Khả năng kiểm soát lớn đi cùng số lượng khái niệm và thành phần cần hiểu lớn hơn.

Với FaaS, nhóm tập trung vào mã hàm, cấu hình runtime, trigger, quyền truy cập và các dịch vụ mà hàm gọi đến. Nhà cung cấp quyết định cách bố trí môi trường thực thi. Điều này giảm công việc hạ tầng nhưng cũng giới hạn quyền tùy biến hệ điều hành, tiến trình nền và thời gian chạy.

### Mở rộng và xử lý tải đột biến

Một ứng dụng chạy trên VM thường mở rộng bằng cách tăng cấu hình máy hoặc thêm VM, sau đó phân phối request qua load balancer. Quá trình tạo máy mới và khởi động ứng dụng có thể mất thời gian; vì vậy cần dự báo tải hoặc duy trì dung lượng dự phòng.

Container cho phép tăng số bản sao của ứng dụng độc lập với image. Nếu dùng Kubernetes, Deployment và Horizontal Pod Autoscaler có thể điều chỉnh replica theo CPU, bộ nhớ hoặc metric tùy chỉnh. Tuy nhiên, Pod mới vẫn cần node có đủ tài nguyên; nếu cụm hết chỗ, cần cơ chế mở rộng node hoặc chuẩn bị dung lượng trước.

FaaS có thể tăng số phiên thực thi để xử lý nhiều trigger đồng thời mà người phát triển không phải tự tạo từng máy. Cơ chế này thuận tiện với tải không đều và các tác vụ độc lập. Khả năng mở rộng không vô hạn: quota concurrency, tốc độ nhận thông điệp, giới hạn downstream và giới hạn của dịch vụ đích đều có thể trở thành nút thắt. Nếu hàng nghìn lần gọi đồng thời cùng truy cập một database có connection limit nhỏ, việc FaaS scale nhanh có thể làm database quá tải.

Vì vậy, autoscaling cần đi cùng kiểm soát tải. Với xử lý message, có thể giới hạn concurrency, điều chỉnh batch size và tốc độ tiêu thụ queue. Với HTTP, cần đặt timeout, giới hạn request và bảo vệ dịch vụ phụ trợ. Không nên đánh đồng “tự mở rộng” với “không cần thiết kế năng lực hệ thống”.

### Vòng đời, trạng thái và độ bền dữ liệu

VM và container có thể chạy tiến trình trong thời gian dài. Ứng dụng có thể giữ cache hoặc connection pool trong bộ nhớ của tiến trình, nhưng dữ liệu quan trọng vẫn cần cơ chế lưu trữ bền vững và phục hồi khi máy hoặc container bị thay thế.

Pod Kubernetes cũng có thể bị tạo lại hoặc chuyển node. Bộ nhớ trong container không phải kho dữ liệu bền vững. Nếu cần lưu file, nhóm phải chọn volume phù hợp hoặc dịch vụ lưu trữ ngoài cụm và hiểu rõ chính sách backup, phục hồi, tính sẵn sàng.

Hàm FaaS thường có vòng đời ngắn và môi trường thực thi có thể bị đóng bất cứ lúc nào sau khi xử lý. Một môi trường có thể được tái sử dụng cho nhiều lần gọi, nên biến toàn cục có thể giúp tái sử dụng đối tượng hoặc connection pool trong một số trường hợp. Tuy nhiên, không được dựa vào việc môi trường sẽ còn tồn tại, cũng không được dùng bộ nhớ toàn cục hay file tạm làm nguồn dữ liệu chuẩn. Hãy lưu trạng thái nghiệp vụ vào database, object storage, cache hoặc dịch vụ bền vững thích hợp.

### Retry, lỗi trùng lặp và tính idempotent

Trong hệ thống chạy liên tục, nhóm thường tự quyết định retry ở tầng ứng dụng, queue hoặc client. Với FaaS, nền tảng có thể tự retry một số loại sự kiện bất đồng bộ theo chính sách của dịch vụ. Hành vi khác nhau giữa trigger và nhà cung cấp: HTTP đồng bộ, queue và event bus có thể có quy tắc timeout, retry, visibility timeout và dead-letter queue khác nhau.

Một thông điệp có thể được giao lại khi hàm timeout, môi trường lỗi hoặc xác nhận xử lý không hoàn tất. Do đó, hàm xử lý sự kiện nên idempotent: xử lý cùng một sự kiện nhiều lần vẫn tạo ra kết quả nghiệp vụ đúng một lần về mặt hiệu ứng. Có thể dùng event ID làm khóa chống trùng, unique constraint, bảng ghi nhận đã xử lý hoặc thao tác cập nhật có điều kiện. Với batch message, cần hiểu cơ chế báo lỗi từng phần để tránh xử lý lại toàn bộ batch khi chỉ một phần tử thất bại.

Retry cần có giới hạn và backoff phù hợp. Lỗi dữ liệu không hợp lệ thường không tự hết khi retry; cần đưa thông điệp sang dead-letter queue hoặc luồng xử lý lỗi để điều tra. Nếu retry quá nhanh hoặc quá nhiều, một lỗi ở dịch vụ phụ trợ có thể tạo thành đợt tải lớn hơn.

### Khởi động lạnh và độ trễ

VM và container chạy thường trực có thể trả lời request sau khi tiến trình đã khởi động. VM mới hoặc container mới vẫn có thời gian khởi tạo, nhưng nhóm thường kiểm soát thời điểm khởi động và có thể duy trì số bản sao tối thiểu.

Với FaaS, khi nền tảng cần tạo môi trường thực thi mới, request có thể phải chờ tải runtime, nạp lớp Java, khởi tạo thư viện và chạy mã khởi tạo. Khoảng trễ bổ sung này thường được gọi là cold start. Java có thể chịu ảnh hưởng bởi kích thước gói triển khai, số lượng dependency, công việc trong static initializer và framework được nạp.

Không phải mọi lần gọi đều cold start; nền tảng có thể tái sử dụng môi trường đã khởi tạo. Dù vậy, không nên giả định môi trường luôn nóng. Có thể giảm ảnh hưởng bằng cách giữ gói triển khai gọn, tránh khởi tạo nặng không cần thiết, đo thời gian thực tế và dùng tính năng như provisioned concurrency hoặc snapshot runtime nếu nhà cung cấp hỗ trợ và ngân sách cho phép. Cần cân nhắc cold start với yêu cầu độ trễ của người dùng thay vì tối ưu trước khi đo.

## 4. Ví dụ cùng một nghiệp vụ Java trên bốn mô hình

Giả sử hệ thống cần nhận sự kiện `OrderPaid` và cập nhật trạng thái đơn hàng.

| Mô hình | Cách triển khai có thể dùng |
|---|---|
| VM | Chạy một ứng dụng Java thường trực trên VM. Ứng dụng nhận HTTP request hoặc tự tiêu thụ queue, giữ các thành phần dùng chung trong tiến trình và được nhóm vận hành cập nhật, giám sát. |
| Container | Đóng gói ứng dụng Java thành image. Chạy một hoặc nhiều container trên máy chủ hoặc dịch vụ container; cấu hình restart, health check và số bản sao ở nền tảng chạy. |
| Kubernetes | Đưa image vào Deployment hoặc một workload phù hợp. Khai báo replica, tài nguyên, probe, Service và autoscaling; dùng queue consumer chạy trong Pod hoặc API nhận sự kiện. |
| Serverless FaaS | Triển khai hàm Java được kích hoạt khi queue nhận `OrderPaid`. Nền tảng gọi hàm theo thông điệp, điều chỉnh concurrency và áp dụng chính sách retry được cấu hình. |

Phần xử lý nghiệp vụ nên được giữ trong lớp Java có thể kiểm thử độc lập. Adapter của từng mô hình chịu trách nhiệm chuyển HTTP request hoặc message thành lời gọi nghiệp vụ. Ví dụ minh họa phần lõi:

```java
public final class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public void markPaid(String orderId, String eventId) {
        // Repository thực hiện cập nhật có điều kiện hoặc ghi nhận eventId
        // để cùng một sự kiện được giao lại không tạo hiệu ứng lặp.
        orders.markPaidIfNotProcessed(orderId, eventId);
    }
}
```

Trên VM hoặc container, một HTTP controller hay queue consumer thường gọi `OrderService` trong tiến trình thường trực. Trên Kubernetes, cùng ứng dụng có thể chạy trong Pod và được điều phối theo cấu hình workload. Trên FaaS, handler nhận payload do nền tảng chuyển vào, xác thực dữ liệu, gọi `OrderService` rồi trả kết quả hoặc báo lỗi để trigger áp dụng chính sách tương ứng.

Ví dụ khung handler dưới đây chỉ thể hiện ranh giới giữa adapter và nghiệp vụ; kiểu sự kiện, chữ ký handler và API context cụ thể phụ thuộc nhà cung cấp FaaS:

```java
public final class OrderPaidFunction {
    private final OrderService orderService;

    public OrderPaidFunction(OrderService orderService) {
        this.orderService = orderService;
    }

    public void handle(OrderPaid event, FunctionContext context) {
        validate(event);
        orderService.markPaid(event.orderId(), event.eventId());
    }

    private void validate(OrderPaid event) {
        if (event == null || event.orderId() == null || event.eventId() == null) {
            throw new IllegalArgumentException("Invalid OrderPaid event");
        }
    }
}
```

Đoạn mã không phải handler có thể biên dịch trực tiếp cho mọi cloud provider. Khi triển khai thật, cần dùng interface và thư viện adapter đúng nền tảng, cấu hình trigger, timeout, memory/CPU, quyền gọi database và queue, cách trả lỗi, cùng cơ chế idempotency phù hợp.

Ví dụ cũng cho thấy một điểm quan trọng: chuyển từ container sang FaaS không tự động làm thay đổi nghiệp vụ. Thay đổi lớn nằm ở cách ứng dụng được kích hoạt, vòng đời tiến trình, quản lý cấu hình và kết nối, xử lý lỗi, giới hạn tài nguyên và quan sát vận hành.

## 5. So sánh chi phí đúng cách

Không thể kết luận FaaS luôn rẻ hơn VM hoặc Kubernetes chỉ vì chỉ tính phí khi hàm chạy. Cần tính tổng chi phí của workload và cách workload được sử dụng.

- **VM:** thường trả tiền cho CPU, RAM và dung lượng máy trong thời gian VM được cấp phát, kể cả khi tải thấp. Chi phí có thể dễ dự báo với tải ổn định; nhóm phải tính thêm lưu trữ, backup, truyền dữ liệu, cân bằng tải và công sức vận hành.
- **Container:** chi phí phụ thuộc nơi chạy. Nếu tự quản lý máy chủ, chi phí gần với VM; nếu dùng dịch vụ container theo task hoặc tài nguyên, hóa đơn dựa trên cấu hình và thời gian chạy. Image registry, logging, networking và dịch vụ phụ trợ cũng góp phần vào tổng chi phí.
- **Kubernetes:** ngoài tài nguyên CPU/RAM của workload, cần tính node, control plane nếu tính phí, lưu trữ, load balancer, log/metric, add-on và thời gian của đội ngũ vận hành. Cụm có thể dùng chung cho nhiều workload, nhưng chi phí quản trị và dung lượng dự phòng vẫn tồn tại.
- **FaaS:** thường tính theo số invocation, thời lượng và cấu hình bộ nhớ hoặc CPU; có thể có phí cho concurrency được cấp trước, log, truyền dữ liệu, API gateway, queue, database và các dịch vụ tích hợp. Scale-to-zero giúp giảm chi phí khi nhàn rỗi, nhưng tải lớn và liên tục có thể khiến chi phí mỗi đơn vị công việc cao hơn một dịch vụ chạy ổn định.

Khi ước tính, hãy dùng số liệu thực tế hoặc kịch bản tải: số request/sự kiện mỗi tháng, thời lượng xử lý trung bình và ở phân vị cao, bộ nhớ/CPU, tỷ lệ lỗi và retry, thời gian nhàn rỗi, lưu lượng mạng, dung lượng lưu trữ và mức độ dự phòng cần thiết. So sánh cùng một mức độ sẵn sàng và cùng yêu cầu hiệu năng. Đồng thời tính cả chi phí phát triển, trực vận hành, nâng cấp và xử lý sự cố.

## 6. Khi nào nên chọn từng mô hình?

| Tình huống | Lựa chọn thường phù hợp | Lý do và điều cần cân nhắc |
|---|---|---|
| Ứng dụng cũ cần hệ điều hành tùy chỉnh, agent riêng hoặc tiến trình dài hạn | VM | Có quyền kiểm soát môi trường cao; đổi lại nhóm chịu trách nhiệm vá lỗi và vận hành máy. |
| Muốn đóng gói ứng dụng nhất quán giữa máy phát triển, kiểm thử và production | Container | Image làm rõ runtime và dependency; vẫn cần chọn nơi chạy và cơ chế điều phối. |
| Có nhiều dịch vụ container, cần triển khai đồng bộ, service discovery, policy và autoscaling tùy chỉnh | Kubernetes | Có hệ sinh thái điều phối mạnh; cần năng lực vận hành cụm và kiểm soát độ phức tạp. |
| Tác vụ ngắn, độc lập, được kích hoạt bởi HTTP, queue hoặc sự kiện và tải biến động | Serverless FaaS | Giảm quản lý máy chủ và có thể scale-to-zero; phải thiết kế cho giới hạn runtime, retry, idempotency và cold start. |
| Công việc nền chạy liên tục, cần giữ kết nối lâu dài hoặc xử lý luồng kéo dài | Container, Kubernetes hoặc VM | Mô hình tiến trình thường trực có thể phù hợp hơn; một số nền tảng serverless hỗ trợ tác vụ dài nhưng cần kiểm tra giới hạn cụ thể. |
| Tải ổn định, cao trong phần lớn thời gian và cần hiệu năng dự đoán được | VM, container hoặc Kubernetes | Dung lượng chạy thường trực có thể kinh tế và dễ kiểm soát hơn; cần so sánh bằng benchmark và hóa đơn thực tế. |

Các lựa chọn không loại trừ nhau. Một hệ thống có thể chạy API chính trên Kubernetes, dùng FaaS cho xử lý ảnh sau khi upload, lưu dữ liệu trong database managed và gửi thông điệp qua queue. Cũng có thể dùng VM cho thành phần cần quyền kiểm soát hệ điều hành và FaaS cho các tác vụ theo sự kiện. Ranh giới nên dựa trên đặc tính từng workload.

## 7. Những hiểu lầm cần tránh

1. **“Serverless không có server.”** Mã vẫn chạy trên hạ tầng máy chủ; nhà cung cấp chịu trách nhiệm quản lý phần lớn hạ tầng đó.
2. **“Container đồng nghĩa với Kubernetes.”** Container là cách đóng gói và cô lập tiến trình; Kubernetes là một nền tảng điều phối container. Có thể chạy container mà không cần Kubernetes.
3. **“Kubernetes và serverless là hai công nghệ cùng một lớp.”** Kubernetes chủ yếu giải quyết điều phối workload; FaaS cung cấp mô hình thực thi theo lần gọi hoặc sự kiện. Có nền tảng serverless được xây dựng trên container hoặc Kubernetes ở phía sau.
4. **“FaaS tự động xử lý mọi lỗi.”** Nền tảng có thể retry theo chính sách, nhưng ứng dụng vẫn cần idempotency, timeout, dead-letter queue, quan sát và cách xử lý dữ liệu lỗi.
5. **“Scale-to-zero luôn tối ưu.”** Nó tiết kiệm tài nguyên nhàn rỗi nhưng có thể tạo cold start. Với tải liên tục hoặc yêu cầu độ trễ chặt, giữ instance sẵn sàng hoặc dùng mô hình chạy thường trực có thể hợp lý hơn.
6. **“Hàm chạy lại sẽ luôn nhận đúng một thông điệp.”** Nhiều cơ chế sự kiện cung cấp ngữ nghĩa giao ít nhất một lần hoặc có khả năng giao lại. Hãy thiết kế để xử lý trùng an toàn và kiểm tra ngữ nghĩa của trigger cụ thể.
7. **“Không quản lý máy chủ nghĩa là không cần vận hành.”** Vẫn phải quản lý quyền IAM, secrets, cấu hình, quota, concurrency, log, metric, cảnh báo, retry và chi phí.

## 8. Quy trình ra quyết định

Khi chọn mô hình triển khai cho một dịch vụ Java, có thể đi qua các câu hỏi sau:

1. **Workload được kích hoạt như thế nào?** Nếu chủ yếu là HTTP request hoặc sự kiện rời rạc từ queue/event bus, FaaS là ứng viên đáng xem xét. Nếu cần tiến trình luôn chạy, kết nối dài hoặc tác vụ kéo dài, hãy xem container, Kubernetes hoặc VM.
2. **Thời gian xử lý và tài nguyên có nằm trong giới hạn nền tảng không?** Đối chiếu timeout, bộ nhớ, CPU, kích thước artifact, concurrency và quota với giới hạn của nhà cung cấp.
3. **Có thể tách trạng thái khỏi tiến trình không?** Nếu cần giữ session hoặc dữ liệu bền vững trong bộ nhớ/đĩa cục bộ, hãy thiết kế lại với kho lưu trữ ngoài hoặc cân nhắc workload thường trực.
4. **Hệ thống chịu được retry và giao trùng không?** Xác định ngữ nghĩa giao nhận, timeout và dead-letter handling; bổ sung idempotency trước khi tăng concurrency.
5. **Độ trễ khởi động có chấp nhận được không?** Đo cold start và latency ở phân vị cao, đặc biệt với Java và framework có thời gian khởi tạo lớn.
6. **Dịch vụ phụ trợ chịu được tải đồng thời không?** Kiểm tra connection limit, throughput và quota của database, API bên ngoài và queue; đặt giới hạn concurrency hoặc backpressure khi cần.
7. **Tổng chi phí và năng lực đội ngũ có phù hợp không?** So sánh chi phí hạ tầng lẫn vận hành ở cùng yêu cầu tải, độ sẵn sàng và bảo mật.

Nếu câu trả lời cho thấy workload ngắn, độc lập, được kích hoạt theo sự kiện, ít phụ thuộc vào trạng thái trong tiến trình và có thể xử lý retry an toàn, FaaS thường là lựa chọn tốt. Nếu workload cần quyền kiểm soát hệ điều hành, tiến trình thường trực, tài nguyên chuyên biệt hoặc hiệu năng ổn định ở tải cao, VM hay container có thể phù hợp hơn. Kubernetes đáng cân nhắc khi tổ chức cần điều phối nhiều workload container và có khả năng vận hành nền tảng đó.

## 9. Kết luận

VM trao quyền kiểm soát máy tính ảo; container chuẩn hóa cách đóng gói ứng dụng; Kubernetes điều phối vòng đời của container; serverless FaaS cung cấp cách chạy hàm theo trigger mà không cần nhóm tự quản lý máy chủ thực thi. Mỗi mô hình có điểm mạnh và chi phí riêng.

Đối với ứng dụng Java, quyết định nên bắt đầu từ đặc tính workload: trigger, thời lượng xử lý, trạng thái, yêu cầu độ trễ, khả năng retry, mức tải và giới hạn của dịch vụ phụ trợ. Khi các yếu tố đó phù hợp với thực thi theo sự kiện, FaaS giúp giảm gánh nặng hạ tầng. Khi cần tiến trình dài hạn hoặc quyền kiểm soát sâu, VM, container hay Kubernetes có thể là lựa chọn phù hợp hơn.
