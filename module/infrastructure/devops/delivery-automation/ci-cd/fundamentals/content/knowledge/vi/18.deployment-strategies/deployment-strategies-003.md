# Hiểu blue-green và thời điểm chuyển lưu lượng

Blue-green deployment là chiến lược triển khai duy trì hai môi trường chạy song song: **blue** đang phục vụ người dùng và **green** chứa phiên bản mới đang được chuẩn bị. Khi green đã được triển khai, kiểm tra và đáp ứng các điều kiện phát hành, hệ thống chuyển lưu lượng từ blue sang green. Nếu phiên bản mới gặp vấn đề, nhóm có thể chuyển lưu lượng trở lại blue trong thời gian ngắn, miễn là dữ liệu và các phụ thuộc vẫn tương thích.

Điểm quyết định của blue-green không chỉ là có hai bản chạy cùng lúc. Điều quan trọng là **chọn đúng thời điểm chuyển lưu lượng (traffic cutover)**: green phải đủ sẵn sàng, các kiểm tra phải có ý nghĩa, rủi ro dữ liệu phải được kiểm soát và nhóm phải biết điều kiện nào sẽ khiến họ rollback.

Đây là một phần của năng lực **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, quality gate, phát hành có truy vết, xác minh sau triển khai và khả năng quay lui.

## 1. Blue-green deployment là gì?

Blue và green là hai phiên bản môi trường có khả năng chạy ứng dụng độc lập. Tên màu chỉ là quy ước; có thể gọi là stable/candidate, current/next hoặc v1/v2.

- **Blue:** phiên bản hiện tại đang nhận traffic production.
- **Green:** phiên bản mới đã được triển khai nhưng chưa nhận traffic production chính.
- **Traffic router:** thành phần quyết định request đi đến blue hay green, ví dụ load balancer, ingress, reverse proxy, service mesh hoặc DNS.

Luồng tổng quát:

~~~mermaid
flowchart TD
    U["Người dùng"] --> R["Load balancer / traffic router"]
    R --> B["Blue: phiên bản hiện tại"]
    R -. "Sau cutover" .-> G["Green: phiên bản mới"]
    B --> DB[("Database dùng chung")]
    G --> DB
    G --> V["Readiness, smoke test và xác minh"]
    V --> D{"Đủ điều kiện chuyển traffic?"}
    D -- "Chưa" --> G
    D -- "Đạt" --> R
~~~

Trước cutover, blue tiếp tục phục vụ người dùng trong khi green được tạo và kiểm tra. Sau cutover, green nhận request mới. Blue thường được giữ lại trong một khoảng thời gian để có thể rollback nhanh, sau đó mới được gỡ bỏ hoặc tái sử dụng cho lần triển khai tiếp theo.

Blue-green có thể dùng hai cụm máy ảo, hai nhóm container, hai Kubernetes Deployment, hai App Service slot hoặc hai nhóm target phía sau load balancer. Cách triển khai cụ thể thay đổi theo nền tảng, nhưng nguyên tắc về readiness, routing, dữ liệu và rollback vẫn giống nhau.

## 2. Blue-green giải quyết vấn đề gì?

Triển khai trực tiếp lên môi trường đang phục vụ có thể tạo ra khoảng thời gian mà người dùng gặp phiên bản chưa ổn định, một phần instance cũ và mới xử lý request khác nhau hoặc rollback cần thay đổi lại từng máy.

Blue-green giúp:

- Chuẩn bị và kiểm tra phiên bản mới trước khi người dùng chính thức nhận traffic.
- Chuyển traffic qua một điểm điều khiển tập trung.
- Giảm thời gian gián đoạn khi cutover được thiết kế tốt.
- Giữ phiên bản cũ sẵn sàng để quay lui nhanh.
- Kiểm thử phiên bản mới trong môi trường production-like trước khi chuyển.
- Tách quá trình triển khai binary khỏi thời điểm thay đổi người dùng nhận phiên bản đó.

Blue-green không tự bảo đảm zero downtime. Kết nối đang mở, session, cache, schema database, background worker và các hệ thống phụ trợ có thể khiến chuyển đổi phức tạp. Nếu hai phiên bản không tương thích với dữ liệu dùng chung, chuyển traffic hoặc rollback có thể gây lỗi dù routing hoạt động đúng.

## 3. So sánh blue-green với rolling và canary

Ba chiến lược đều giảm rủi ro phát hành nhưng kiểm soát traffic theo cách khác nhau:

| Chiến lược | Cách thay phiên bản | Cách traffic thay đổi | Điểm mạnh | Giới hạn chính |
| --- | --- | --- | --- | --- |
| Blue-green | Chuẩn bị đầy đủ môi trường mới song song với môi trường hiện tại | Chuyển một phần lớn hoặc toàn bộ traffic tại router | Cutover và rollback nhanh nếu hệ thống tương thích | Cần tài nguyên cho hai môi trường và kiểm soát dữ liệu dùng chung |
| Rolling | Thay instance cũ từng nhóm bằng instance mới | Traffic dần đi qua cả instance cũ và mới trong thời gian rollout | Không cần duy trì hai môi trường đầy đủ | Hai phiên bản cùng phục vụ một thời gian; rollback có thể lâu hơn |
| Canary | Triển khai phiên bản mới cho một nhóm nhỏ | Tăng tỷ lệ traffic đến phiên bản mới theo từng bước | Đo hành vi trên traffic thực với blast radius nhỏ | Cần routing/metrics tốt và có thể kéo dài thời gian hai phiên bản cùng tồn tại |

Blue-green có thể kết hợp canary: green được dựng đầy đủ, sau đó router gửi một tỷ lệ nhỏ traffic đến green trước khi chuyển hoàn toàn. Khi người ta nói blue-green, không nhất thiết phải chuyển 100% traffic trong một thao tác duy nhất; điều đó phụ thuộc khả năng của router và chính sách phát hành.

Chọn chiến lược dựa trên kiến trúc, khả năng quan sát, chi phí tài nguyên, mức độ rủi ro và yêu cầu phục hồi. Nếu hệ thống không thể chạy hai phiên bản đồng thời vì giới hạn license, dữ liệu hoặc tài nguyên, blue-green có thể không phù hợp.

## 4. Những điều kiện cần chuẩn bị trước khi tạo green

Blue-green cần được thiết kế từ pipeline và kiến trúc ứng dụng, không chỉ thêm một bước đổi route ở cuối.

### 4.1. Artifact phải bất biến và có thể truy vết

Build artifact một lần từ commit đã xác định, chạy test và quality gate, sau đó triển khai đúng artifact đó lên green. Không build lại một phiên bản khác trong lúc triển khai production chỉ vì cần thay cấu hình.

Ghi lại:

- Commit SHA và repository nguồn.
- Artifact version và digest.
- Build run ID và build provenance nếu có.
- Cấu hình triển khai và phiên bản manifest.
- Image digest hoặc package checksum.
- Kết quả test, scan và quality gate.

Khi green được xác minh và traffic được chuyển, blue-green phải biết chính xác phiên bản nào đang chạy ở mỗi màu. Nếu rollback, nhóm cần biết blue đang trỏ tới artifact nào và artifact đó còn tồn tại trong registry hay không.

### 4.2. Môi trường blue và green phải tương đương ở những điểm quan trọng

Hai môi trường cần có cấu hình tương đương về:

- Runtime, hệ điều hành, CPU architecture và tài nguyên.
- Network policy, DNS, firewall và outbound access.
- Secret, certificate và quyền truy cập dịch vụ.
- Feature flag và cấu hình ứng dụng.
- Kết nối database, cache, message broker và object storage.
- Observability: log, metrics, tracing và alert.

Không nhất thiết mọi giá trị cấu hình phải giống nhau, nhưng khác biệt phải được khai báo và có lý do. Nếu green dùng cấu hình database hoặc quyền truy cập khác blue, smoke test phải kiểm tra đúng cấu hình sẽ dùng sau cutover.

### 4.3. Tài nguyên và capacity

Trong giai đoạn chuẩn bị, blue và green cùng tồn tại nên nhu cầu CPU, memory, connection pool, node và quota có thể tăng gần gấp đôi đối với phần được nhân bản. Cần tính cả tài nguyên phụ trợ như database connection, broker consumer, cache namespace và license.

Nếu green được scale lên đầy đủ trước cutover nhưng database không đủ connection, chính quá trình chuẩn bị có thể làm blue chậm đi. Hãy kiểm tra giới hạn và đặt quota phù hợp trước khi chạy hai môi trường đồng thời.

## 5. Các trạng thái trong một lần blue-green release

Một lần phát hành có thể được mô hình hóa bằng các trạng thái:

| Trạng thái | Blue | Green | Traffic |
| --- | --- | --- | --- |
| Stable | Đang phục vụ | Chưa có hoặc đang dừng | 100% đến blue |
| Provisioning | Đang phục vụ | Đang tạo | 100% đến blue |
| Validating | Đang phục vụ | Đã chạy, đang kiểm tra | Production vẫn đến blue; test riêng đến green |
| Ready | Đang phục vụ | Đã đạt kiểm tra | Chưa cutover hoặc đang nhận canary traffic |
| Switching | Đang phục vụ | Đủ điều kiện | Router đang chuyển theo kế hoạch |
| Green active | Giữ lại để rollback | Đang phục vụ | Traffic mới đến green |
| Rollback | Được kích hoạt lại | Được cô lập hoặc điều tra | Traffic mới quay về blue |
| Retired | Được gỡ hoặc tái sử dụng | Trở thành phiên bản cũ ở lần sau | Chỉ một môi trường active |

Không nên coi trạng thái container Running là trạng thái Ready. Cần có điều kiện chuyển trạng thái rõ ràng và lưu kết quả để người vận hành biết pipeline đang ở bước nào.

## 6. Triển khai green trước khi chuyển traffic

Một trình tự triển khai green thường gồm:

1. Xác định artifact digest và cấu hình release.
2. Kiểm tra quality gate, provenance, chữ ký và scan theo policy.
3. Tạo tài nguyên green từ manifest hoặc infrastructure-as-code đã review.
4. Cấp secret, network rule và quyền truy cập đúng môi trường.
5. Chạy migration tương thích nếu cần.
6. Khởi động application instance và chờ readiness.
7. Chạy smoke test trực tiếp vào green qua endpoint nội bộ.
8. Xác minh log, metrics, tracing và dependency.
9. Đánh giá capacity và tiêu chí cutover.

Trong giai đoạn này, blue vẫn nhận traffic production. Không để green tự động gửi email, thanh toán, phát event hoặc chạy scheduled job trùng với blue chỉ vì green đã khởi động. Các tác vụ có side effect cần cơ chế leader, feature flag hoặc tắt worker trên môi trường chưa active.

### 6.1. Readiness, liveness và smoke test

Ba loại kiểm tra có mục đích khác nhau:

- **Liveness:** tiến trình còn hoạt động và không bị kẹt đến mức cần restart.
- **Readiness:** instance có thể nhận request production; dependency bắt buộc đã sẵn sàng.
- **Smoke test:** một tập thao tác nhỏ xác minh các luồng quan trọng thực sự hoạt động.

Một endpoint health chỉ trả HTTP 200 có thể chưa đủ. Green có thể trả health success nhưng không ghi được database, không lấy được secret, không kết nối broker hoặc không tải được model/config cần thiết.

Smoke test nên kiểm tra những hành vi có ý nghĩa, ví dụ:

- Endpoint đọc dữ liệu trả đúng cấu trúc.
- Một thao tác ghi thử trong vùng dữ liệu test được lưu và đọc lại.
- Ứng dụng xác thực được với dependency.
- Một luồng quan trọng hoàn tất trong thời gian cho phép.
- Không có lỗi nghiêm trọng trong log khởi động.

Tránh chạy smoke test tạo giao dịch thật, gửi email thật hoặc phát sự kiện có side effect không thể hoàn tác. Dùng test account, dữ liệu riêng hoặc chế độ dry-run nếu có.

## 7. Khi nào nên chuyển traffic?

Không chuyển traffic chỉ vì deployment job đã hoàn tất hoặc container đã Running. Green chỉ nên được xem là đủ điều kiện khi các điều kiện đã định trước đều đạt.

Một quyết định cutover nên kiểm tra:

### 7.1. Green đã sẵn sàng về kỹ thuật

- Tất cả instance cần thiết đã Ready.
- Cấu hình và secret được nạp đúng.
- Database migration và dependency initialization đã hoàn tất.
- Smoke test trên green đạt.
- Không có lỗi khởi động hoặc crash loop.
- Log và metrics được gửi về hệ thống quan sát.

### 7.2. Rủi ro thay đổi đã được đánh giá

- Artifact digest khớp với bản đã kiểm thử và phê duyệt.
- Quality gate, vulnerability policy và provenance đạt yêu cầu.
- Database schema tương thích với cả blue và green trong thời gian chuyển.
- Feature flag và side effect được kiểm soát.
- Có kế hoạch rollback đã được kiểm tra hoặc diễn tập phù hợp.

### 7.3. Có khả năng quan sát sau cutover

Trước khi chuyển, dashboard và alert phải sẵn sàng để theo dõi:

- Tỷ lệ request thành công và lỗi theo phiên bản.
- Latency p50/p95/p99.
- Tỷ lệ timeout và connection error.
- CPU, memory, thread, connection pool và saturation.
- Database query latency, lock và connection count.
- Queue lag, consumer error và retry.
- Business metrics như tạo đơn, thanh toán thành công hoặc hoàn tất giao dịch.

Đặc biệt, cần có cách phân biệt traffic đến blue và green. Nếu metrics chỉ tổng hợp toàn hệ thống, lỗi ở green có thể bị che khuất bởi lượng request blue vẫn xử lý tốt.

### 7.4. Xác định trước ngưỡng quyết định

Đặt ngưỡng trước cutover dựa trên SLO, baseline và mức độ quan trọng của dịch vụ. Ví dụ, nhóm có thể quy định:

- Error rate không vượt ngưỡng đã phê duyệt trong cửa sổ quan sát.
- Latency không vượt giới hạn SLO hoặc baseline có điều chỉnh.
- Không xuất hiện lỗi nghiệp vụ nghiêm trọng.
- Không có crash loop hoặc saturation kéo dài.
- Queue lag và database connection nằm trong giới hạn.

Không dùng một con số chung cho mọi hệ thống. Một API thanh toán, một trang nội dung và một worker xử lý batch có đặc điểm tải khác nhau. Ngưỡng phải phản ánh mức độ rủi ro mà tổ chức chấp nhận.

**Thời điểm cutover phù hợp** là khi green đã vượt qua các kiểm tra kỹ thuật và nghiệp vụ, dữ liệu tương thích, router có thể chuyển có kiểm soát, đội vận hành có đủ tín hiệu để phát hiện lỗi và quyết định rollback.

### 7.5. Chọn cửa sổ vận hành

Sau khi green đạt điều kiện kỹ thuật, chọn thời điểm thực hiện cutover dựa trên lịch tải và khả năng hỗ trợ vận hành:

- Ưu tiên khoảng thời gian có đủ người trực để theo dõi và ra quyết định.
- Tránh trùng với batch lớn, chốt sổ, đợt thanh toán hoặc sự kiện nghiệp vụ có lưu lượng bất thường nếu các hoạt động đó làm tăng rủi ro.
- Xác nhận các hệ thống phụ trợ và đội liên quan đang ở trạng thái ổn định.
- Thông báo cho người trực và các nhóm phụ thuộc về thời điểm chuyển, tiêu chí dừng và người có quyền rollback.
- Dành đủ thời gian cho cửa sổ quan sát sau cutover trước khi bắt đầu một thay đổi lớn khác.

Chọn giờ ít traffic có thể giảm số người dùng bị ảnh hưởng nếu phải rollback, nhưng không thay thế readiness, smoke test, capacity check hoặc giám sát. Với dịch vụ hoạt động liên tục, có thể chuyển vào bất kỳ thời điểm nào nếu hệ thống đã sẵn sàng và đội vận hành có khả năng phản ứng.

## 8. Chuyển traffic bằng cách nào?

Traffic router là điểm điều khiển chính của blue-green. Các cách phổ biến:

| Cơ chế | Cách chuyển | Lưu ý |
| --- | --- | --- |
| Load balancer target group | Thay target group hoặc đổi weight từ blue sang green | Có thể hỗ trợ connection draining và health check |
| Kubernetes Service selector | Thay label selector để Service chọn pod green | Cần readiness probe và lưu ý thời gian cập nhật endpoint |
| Ingress/reverse proxy | Cập nhật upstream hoặc backend service | Có thể cần reload và thời gian propagation |
| Service mesh | Cập nhật routing rule/virtual service | Có thể hỗ trợ weight và canary trước cutover |
| DNS | Đổi record từ blue sang green | Cache DNS và TTL khiến chuyển đổi không tức thời |
| Platform slot | Swap slot hoặc đổi backend theo cơ chế của nền tảng | Phụ thuộc hành vi session, storage và cấu hình slot |

Với load balancer hoặc service mesh, có thể bắt đầu bằng một tỷ lệ traffic nhỏ đến green, sau đó tăng dần. Với DNS, không nên giả định đổi record đồng nghĩa mọi client chuyển ngay; resolver và client có thể cache địa chỉ lâu hơn TTL.

### 8.1. Ví dụ Kubernetes Service selector

Giả sử hai Deployment tạo pod cùng mang label app=orders-api, nhưng khác label track:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api-blue
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
      track: blue
  template:
    metadata:
      labels:
        app: orders-api
        track: blue
    spec:
      containers:
        - name: api
          image: registry.example.com/orders-api@sha256:BLUE_IMAGE_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
~~~

Deployment green có cùng cấu trúc nhưng tên là orders-api-green, label track là green và image digest của phiên bản mới. Service ban đầu chọn blue:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
    track: blue
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

Sau khi green đạt readiness và smoke test, có thể đổi selector:

~~~bash
kubectl patch service orders-api \
  --type merge \
  -p '{"spec":{"selector":{"app":"orders-api","track":"green"}}}'
~~~

Service sẽ cập nhật EndpointSlice để chọn pod green phù hợp. Việc cập nhật endpoint và kết nối hiện hữu có độ trễ; không nên coi patch trả về thành công là bằng chứng toàn bộ traffic đã chuyển. Cần quan sát request thực tế và xác minh routing qua metrics/log.

Các chuỗi BLUE_IMAGE_DIGEST và GREEN_IMAGE_DIGEST là chỗ giữ chỗ; trong manifest thật phải thay bằng digest hợp lệ. Ví dụ chỉ minh họa cơ chế selector, không bao gồm namespace, resource quota, network policy, autoscaling hoặc cấu hình production đầy đủ.

Nếu muốn rollback, đổi selector về track blue sau khi xác nhận blue vẫn còn Ready và tương thích với trạng thái dữ liệu hiện tại.

## 9. Connection draining, session và traffic đang xử lý

Khi router chuyển request mới sang green, các request đang chạy trên blue có thể vẫn chưa kết thúc. Cần xác định cách xử lý:

- **Connection draining:** ngừng gửi kết nối mới đến blue nhưng cho request hiện tại hoàn tất trong một khoảng thời gian.
- **Graceful shutdown:** ứng dụng ngừng nhận request mới, hoàn tất công việc đang xử lý rồi thoát.
- **Timeout:** đặt giới hạn cho request dài để tránh blue bị giữ vô thời hạn.
- **WebSocket/streaming:** có thể cần giữ kết nối đến blue hoặc yêu cầu client reconnect.
- **Sticky session:** session gắn với instance có thể khiến người dùng tiếp tục quay lại blue sau cutover.

Nếu session lưu trong memory của instance, người dùng có thể mất đăng nhập khi chuyển môi trường. Nên dùng session store dùng chung hoặc cơ chế token stateless nếu phù hợp. Nếu hai phiên bản dùng format session khác nhau, cần bảo đảm chúng tương thích trong thời gian chuyển và rollback.

Đối với worker và consumer, chuyển HTTP traffic không tự chuyển quyền xử lý message. Nếu cả blue và green cùng consume một queue, có thể xử lý trùng, cạnh tranh hoặc tạo side effect hai lần. Cần thiết kế idempotency, consumer group, leader election hoặc quy trình dừng worker blue đúng thời điểm.

## 10. Database và dữ liệu dùng chung là rủi ro lớn nhất

Blue và green thường kết nối cùng database. Điều đó giúp dữ liệu nhất quán giữa hai môi trường, nhưng cũng có nghĩa hai phiên bản có thể đọc/ghi cùng schema trong thời gian triển khai và rollback.

Không nên triển khai migration phá hủy trước cutover nếu blue còn cần schema cũ. Một chiến lược phổ biến là **expand-contract**:

1. **Expand:** thêm cột, bảng, index hoặc API mới theo cách vẫn tương thích với phiên bản cũ.
2. **Deploy compatible version:** triển khai green có thể làm việc với schema mới và cũ trong giai đoạn chuyển tiếp.
3. **Cutover:** chuyển traffic sang green sau khi xác minh.
4. **Observe:** giữ blue trong thời gian rollback, bảo đảm blue vẫn chạy được với schema hiện tại.
5. **Contract:** chỉ xóa cột, bảng hoặc đường tương thích cũ sau khi phiên bản cũ không còn cần và kế hoạch rollback không còn phụ thuộc chúng.

Ví dụ, nếu green cần cột customer_status mới, migration có thể thêm cột nullable trước. Green ghi cả trường cũ và mới trong giai đoạn chuyển tiếp nếu cần. Sau khi blue đã bị loại bỏ và dữ liệu được backfill/kiểm tra, nhóm mới cân nhắc xóa cột cũ ở một release sau.

Một số thay đổi dữ liệu không thể rollback bằng cách đổi traffic. Nếu green ghi dữ liệu theo format mà blue không đọc được, quay lại blue có thể gây lỗi hoặc mất dữ liệu. Hãy kiểm tra tương thích đọc/ghi trước khi cutover và có chiến lược phục hồi dữ liệu riêng cho migration không đảo ngược.

## 11. Cache, message và side effect

Hai môi trường cùng tồn tại có thể chia sẻ hoặc tách riêng cache, broker và các hệ thống ngoài. Mỗi lựa chọn có hệ quả:

- Cache dùng chung giúp blue và green nhìn thấy cùng dữ liệu, nhưng key format phải tương thích.
- Cache riêng giúp cô lập, nhưng green có thể cold cache và tạo tải đột biến lên database.
- Queue dùng chung cần kiểm soát consumer để tránh xử lý song song ngoài ý muốn.
- Topic hoặc queue riêng giúp kiểm thử green, nhưng phải tránh phát sự kiện test sang hệ thống thật.
- Email, payment, webhook và notification cần idempotency hoặc bị tắt trong quá trình validation.
- Scheduled job chỉ nên có một phiên bản active nếu tác vụ không được thiết kế chạy song song.

Nếu green cần warm-up cache, hãy thực hiện trước cutover và theo dõi tải lên dependency. Không chạy warm-up với thao tác tạo side effect nghiệp vụ. Nếu phải gửi event, dùng event test hoặc môi trường giả lập.

## 12. Theo dõi sau cutover và quyết định giữ hay rollback

Sau khi chuyển traffic, công việc chưa kết thúc. Đây là giai đoạn xác minh green trên traffic thật.

Theo dõi ít nhất:

- Tỷ lệ request thành công và lỗi, tách theo version.
- Latency và timeout.
- Log lỗi ứng dụng, exception và crash.
- Saturation của CPU, memory, thread và connection pool.
- Database latency, lock và số connection.
- Queue lag, retry và dead-letter.
- Business metrics: giao dịch thành công, đơn hàng tạo được, thanh toán hoàn tất.
- Alert từ hệ thống dependency và hạ tầng.

Thời gian quan sát cần dựa trên đặc tính tải. Một API có traffic liên tục có thể có tín hiệu sớm trong vài phút; một batch chạy theo giờ hoặc nghiệp vụ chỉ phát sinh vào thời điểm nhất định cần cửa sổ dài hơn để có đủ bằng chứng.

### 12.1. Điều kiện tiếp tục giữ green

Giữ green làm phiên bản active khi:

- Error rate và latency nằm trong ngưỡng đã định.
- Không có lỗi nghiệp vụ nghiêm trọng.
- Dependency và database hoạt động ổn định.
- Không có dấu hiệu tăng retry, queue lag hoặc resource saturation bất thường.
- Các luồng quan trọng đã có đủ traffic để xác minh.
- Không có alert mới liên quan đến bản phát hành.

### 12.2. Điều kiện rollback

Quay về blue khi xuất hiện điều kiện đã định trước, chẳng hạn:

- Tỷ lệ lỗi vượt ngưỡng trong cửa sổ quan sát.
- Latency tăng vượt SLO và ảnh hưởng người dùng.
- Giao dịch quan trọng thất bại hoặc dữ liệu sai.
- Green crash loop, mất readiness hoặc không truy cập được dependency.
- Queue lag hoặc retry tăng đến mức đe dọa SLA.
- Có dấu hiệu bảo mật hoặc hành vi không mong muốn.

Không chờ hết cửa sổ quan sát nếu phát hiện sự cố nghiêm trọng. Ngược lại, không rollback chỉ vì một cảnh báo nhiễu nếu chưa kiểm tra tác động và ngưỡng đã định. Người vận hành cần phân biệt tín hiệu thực với lỗi giám sát.

## 13. Rollback blue-green như thế nào?

Nếu blue vẫn còn hoạt động và dữ liệu tương thích, rollback có thể chỉ là đổi router về blue:

1. Xác nhận blue còn Ready và có đủ capacity.
2. Dừng hoặc giảm traffic đến green.
3. Chuyển request mới về blue.
4. Drain kết nối green đang xử lý nếu có thể.
5. Xác minh traffic và business metrics đã ổn định trên blue.
6. Cô lập green để điều tra; không xóa log hoặc artifact.
7. Ghi lại release ID, digest, thời điểm và lý do rollback.

Rollback traffic không tự đảo ngược database migration, message đã phát, email đã gửi hoặc giao dịch đã hoàn tất. Cần xác định những side effect nào đã xảy ra và có kế hoạch xử lý riêng.

Giữ blue trong thời gian quan sát đã định. Xóa blue quá sớm làm mất khả năng quay lui nhanh; giữ quá lâu làm tăng chi phí và có thể để lại một môi trường cũ dễ bị bỏ quên. Thời điểm dọn blue nên dựa trên rủi ro rollback, trạng thái dữ liệu và chính sách lưu giữ artifact.

### 13.1. Rollback không phải lúc nào cũng an toàn

Không thể rollback chỉ bằng route nếu:

- Green đã thay đổi schema theo cách blue không đọc được.
- Green đã ghi dữ liệu theo format mới không tương thích.
- Một message đã được xử lý theo logic mới và không thể lặp lại an toàn.
- Blue thiếu capacity vì đã scale down.
- Secret, certificate hoặc endpoint của blue đã bị thu hồi.
- External side effect đã được thực hiện và không thể hoàn tác.

Vì vậy, rollback phải được thiết kế cùng lúc với migration, worker, session, cache và tích hợp bên ngoài. Nếu dữ liệu đã tiến tới trạng thái không thể quay lại, phương án có thể là forward-fix hoặc triển khai bản sửa tiếp theo thay vì quay về binary cũ.

## 14. Các lỗi thường gặp khi dùng blue-green

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chuyển traffic ngay khi container Running | Green chưa sẵn sàng về nghiệp vụ | Dùng readiness, smoke test và dependency checks |
| Blue và green không tương thích schema | Rollback làm ứng dụng cũ lỗi | Dùng expand-contract và kiểm thử tương thích |
| Cả hai môi trường cùng chạy worker | Xử lý message/job trùng | Điều khiển worker active, idempotency và leader election |
| Không drain kết nối cũ | Request dài bị ngắt hoặc treo | Connection draining và graceful shutdown |
| Session lưu trong memory | Người dùng mất session sau cutover | Shared session store hoặc cơ chế stateless |
| Chỉ nhìn metrics tổng | Lỗi green bị blue che khuất | Tách metrics theo version/color |
| Dùng DNS và giả định chuyển tức thời | Client vẫn gọi blue do cache DNS | Tính đến TTL và resolver; ưu tiên router có cutover rõ |
| Không tính capacity hai môi trường | Thiếu tài nguyên hoặc tăng tải database | Load test và tính quota/connection trước release |
| Xóa blue ngay sau cutover | Rollback chậm hoặc không thể thực hiện | Giữ blue trong cửa sổ quan sát |
| Coi đổi traffic là rollback hoàn chỉnh | Side effect và dữ liệu mới vẫn tồn tại | Có kế hoạch dữ liệu, message và external side effect |
| Build artifact riêng cho từng màu | Blue/green có thể chạy binary khác ngoài dự kiến | Promote cùng artifact digest đã xác minh |

## 15. Ví dụ một lần blue-green release cho dịch vụ đặt hàng

Giả sử orders-api phiên bản 1.8.0 đang chạy trên blue. Nhóm muốn phát hành 1.9.0 có thêm trạng thái đơn hàng mới.

**Trước release**

- Build 1.9.0 từ commit đã review, chạy unit/integration test và quality gate.
- Lưu artifact digest và provenance.
- Kiểm tra migration chỉ thêm cột mới, chưa xóa trường mà 1.8.0 cần.
- Xác định smoke test và ngưỡng error rate/latency.
- Xác minh blue đủ capacity để tiếp tục phục vụ trong khi green được tạo.

**Chuẩn bị green**

- Tạo Deployment green bằng đúng image digest 1.9.0.
- Cấp secret và network policy.
- Chạy migration mở rộng và chờ hoàn tất.
- Chờ tất cả pod green Ready.
- Gọi endpoint health và smoke test tạo/đọc đơn hàng bằng test account.
- Xác minh log, database latency, queue và cache.
- Giữ worker side effect ở trạng thái chỉ blue active cho đến khi cutover.

**Cutover**

- Router chuyển một tỷ lệ nhỏ request đến green nếu nền tảng hỗ trợ.
- Theo dõi error rate, latency và business metrics riêng của green.
- Nếu đạt ngưỡng trong cửa sổ quan sát, tăng tỷ lệ traffic đến green.
- Khi toàn bộ traffic mới đã đến green và hệ thống ổn định, đánh dấu green là active.
- Drain kết nối blue và giữ blue sẵn sàng rollback.

**Sau release**

- Theo dõi giao dịch, queue và database trong khoảng thời gian phù hợp.
- Nếu green gặp lỗi nghiêm trọng, chuyển traffic về blue sau khi xác minh schema vẫn tương thích.
- Nếu ổn định, chờ hết cửa sổ rollback rồi mới gỡ blue.
- Chỉ ở một release sau, khi không còn phiên bản cũ cần trường cũ, mới thực hiện contract migration.

Ví dụ này cho thấy thời điểm chuyển traffic phụ thuộc cả vào trạng thái ứng dụng lẫn dữ liệu, worker và khả năng quan sát. Không thể chỉ dựa vào kết quả của lệnh deploy.

## 16. Checklist trước, trong và sau cutover

**Trước khi tạo green**

- [ ] Artifact đã được build, test, scan và định danh bằng digest.
- [ ] Có provenance và release record theo policy.
- [ ] Blue/green có cấu hình, network, secret và quyền phù hợp.
- [ ] Đã tính capacity, quota và database connection cho hai môi trường.
- [ ] Migration tương thích với phiên bản cũ và mới.
- [ ] Worker, scheduler và side effect có cơ chế kiểm soát.
- [ ] Có dashboard, alert và tiêu chí cutover/rollback.

**Trước khi chuyển traffic**

- [ ] Green có đủ replica và tất cả instance Ready.
- [ ] Smoke test trên green đạt.
- [ ] Dependency, database, cache và broker hoạt động.
- [ ] Artifact digest đúng với bản đã phê duyệt.
- [ ] Không có lỗi nghiêm trọng trong log.
- [ ] Blue vẫn khỏe và có thể nhận lại traffic.
- [ ] Router có phương án chuyển và connection draining phù hợp.
- [ ] Người vận hành biết ai quyết định cutover và ai kích hoạt rollback.

**Sau khi chuyển traffic**

- [ ] Request mới thực sự đến green theo metrics/log.
- [ ] Error rate, latency và business metrics nằm trong ngưỡng.
- [ ] Database, queue, cache và dependency ổn định.
- [ ] Blue được giữ trong cửa sổ rollback đã định.
- [ ] Release/deployment record ghi đúng digest, thời điểm và kết quả.
- [ ] Chỉ gỡ blue khi đã hết nhu cầu rollback và dữ liệu tương thích.
- [ ] Contract migration được thực hiện ở thời điểm riêng, có kiểm soát.

## Kết luận

Blue-green deployment tách việc chuẩn bị phiên bản mới khỏi thời điểm người dùng bắt đầu nhận phiên bản đó. Blue tiếp tục phục vụ trong khi green được triển khai và kiểm tra; traffic chỉ được chuyển khi green đã Ready, smoke test đạt, dependency và dữ liệu tương thích, capacity đủ và hệ thống quan sát sẵn sàng.

Sau cutover, cần theo dõi metrics theo phiên bản, xử lý connection draining, session, worker và side effect. Giữ blue trong cửa sổ rollback giúp quay lại nhanh, nhưng chỉ an toàn khi schema và dữ liệu vẫn tương thích. Khi thiết kế đầy đủ các điều kiện này, blue-green giúp CI/CD phát hành có kiểm soát, truy vết được và phục hồi nhanh hơn khi phiên bản mới gặp sự cố.
