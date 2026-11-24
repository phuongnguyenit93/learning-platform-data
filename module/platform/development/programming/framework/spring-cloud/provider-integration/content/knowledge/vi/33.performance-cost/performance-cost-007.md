# Ước lượng chi phí theo thao tác, dung lượng và truyền dữ liệu

Khi một ứng dụng Spring Boot sử dụng dịch vụ managed của AWS, Azure hoặc Google Cloud, hóa đơn thường được hình thành từ nhiều đơn vị tính khác nhau. Một object storage có thể tính phí dung lượng lưu theo GB-tháng, số lần PUT/GET/LIST, truy xuất dữ liệu ở tầng lưu trữ lạnh và truyền dữ liệu ra ngoài. Một message broker có thể tính theo request, số lượng message hoặc dung lượng payload. Database có thể tính theo giờ compute, dung lượng, I/O hoặc đơn vị request/capacity. Vì vậy, chỉ lấy giá của một instance hoặc một GB lưu trữ sẽ không phản ánh đầy đủ chi phí của workload.

Bài học này hướng dẫn chuyển một luồng nghiệp vụ thành các đơn vị có thể đo và dự toán: số thao tác, dung lượng dữ liệu được giữ, byte được truyền và tài nguyên chạy liên tục. Bạn sẽ xây dựng mô hình chi phí theo tháng, phân biệt cách tính của các nhóm dịch vụ, đo hoạt động ở tầng Spring Boot và đối chiếu kết quả với dữ liệu billing của nhà cung cấp. Các mức giá cụ thể thay đổi theo dịch vụ, region, tier, loại request, bậc sử dụng và thời điểm; bài học tập trung vào phương pháp tính để có thể thay số bằng bảng giá hiện hành.

## Mục tiêu

Sau bài học, bạn có thể:

- Chuyển một thao tác nghiệp vụ thành các request hoặc đơn vị tính phí của dịch vụ managed.
- Ước lượng số lần gọi, dung lượng lưu trung bình, tăng trưởng dữ liệu và byte truyền theo tháng.
- Tính riêng chi phí thao tác, lưu trữ, truy xuất, truyền dữ liệu, compute và các thành phần phụ trợ.
- Nhận diện các yếu tố làm tăng số đơn vị tính phí như retry, pagination, fan-out, replication và versioning.
- Đối chiếu mô hình chi phí giữa AWS, Azure và Google Cloud mà không giả định các dịch vụ có cùng cách tính.
- Dùng metric trong Spring Boot để đo workload và phân bổ chi phí theo dịch vụ hoặc tính năng.
- Xây dựng kịch bản cơ sở, tăng trưởng và tải đỉnh để ra quyết định tối ưu có thể kiểm chứng.

## 1. Đọc mô hình giá trước khi tính

Nhà cung cấp cloud công bố giá theo từng dịch vụ và đơn vị đo. Cùng một dịch vụ có thể có nhiều thành phần giá: dung lượng, thao tác, thời gian chạy, throughput được cấp trước, request vượt ngưỡng, bản sao dữ liệu, truy xuất hoặc truyền dữ liệu. Trước khi đưa số vào bảng tính, hãy đọc phần mô tả đơn vị tính phí và điều kiện áp dụng.

### 1.1. Các nhóm đơn vị tính phí thường gặp

| Nhóm | Đơn vị thường gặp | Ví dụ dịch vụ hoặc thành phần |
|---|---|---|
| Compute | vCPU-hour, GB RAM-hour, instance-hour, request hoặc thời gian thực thi | VM, container, serverless function, managed application platform |
| Dung lượng | GB-month, GiB-month, GB-hour, số bản sao hoặc dung lượng dự phòng | Object storage, block storage, database, backup |
| Thao tác | Số request, số transaction, số operation hoặc nhóm request theo loại | PUT/GET/LIST, database read/write, queue send/receive, secret access |
| Message và event | Số message, kích thước payload, số lần giao nhận hoặc throughput | SQS, SNS, Azure Service Bus, Google Pub/Sub |
| Truyền dữ liệu | Byte/GB theo nguồn, đích, chiều truyền và tuyến mạng | Internet egress, cross-region, cross-zone, inter-cloud |
| Tài nguyên mạng | Giờ hoạt động, số endpoint, byte xử lý hoặc số kết nối | NAT gateway, load balancer, private endpoint, transit gateway |
| Quan sát | Byte log ingest, metric sample, trace span, thời gian lưu giữ | Logging, monitoring, tracing và audit |

Đơn vị có thể khác nhau giữa dịch vụ và nhà cung cấp. Một request PUT có thể là một operation, trong khi một lần gọi API batch có thể chứa nhiều item nhưng được tính theo số item, số request hoặc cả hai. Một message lớn có thể được chia thành nhiều đơn vị tính phí. Không dùng tên API làm bằng chứng duy nhất cho cách tính phí.

### 1.2. Công thức tổng quát

Có thể mô hình hóa chi phí tháng như sau:

```text
C_tháng = C_compute
        + C_operations
        + C_storage
        + C_retrieval
        + C_data_transfer
        + C_network
        + C_backup_replication
        + C_observability
        + C_other
```

Trong đó:

- `C_operations` là chi phí của các request, transaction, message hoặc operation được tính phí.
- `C_storage` là chi phí giữ dữ liệu trong các tier và bản sao.
- `C_retrieval` là phí đọc hoặc khôi phục dữ liệu nếu tier lưu trữ có tính phí truy xuất.
- `C_data_transfer` là phí truyền byte theo tuyến và chiều truyền.
- `C_network` gồm NAT, load balancer, peering, private endpoint hoặc thành phần mạng khác.
- `C_backup_replication` gồm dung lượng và thao tác tạo, sao chép, khôi phục bản sao.
- `C_observability` gồm ingest và lưu log, metric, trace.

Đây là khung kiểm kê, không phải mọi dịch vụ đều có đủ các khoản trên. Một khoản đã được gộp trong giá dịch vụ không được cộng lại lần thứ hai. Thuế, hỗ trợ doanh nghiệp, chiết khấu cam kết và credit có thể được tính ở cấp tài khoản hoặc hợp đồng; hãy thể hiện riêng để phân biệt chi phí kỹ thuật với số tiền thanh toán cuối cùng.

## 2. Chuyển luồng nghiệp vụ thành số thao tác

Điểm bắt đầu của dự toán là hành vi người dùng và các bước xử lý phía sau. Đếm số request HTTP ở cổng API thường chưa đủ vì một request có thể gọi nhiều dịch vụ managed.

### 2.1. Lập bản đồ một thao tác nghiệp vụ

Ví dụ, một yêu cầu tải tài liệu có thể thực hiện:

1. Xác thực người dùng và kiểm tra quyền.
2. Đọc metadata tài liệu từ database.
3. Gọi object storage để tạo URL tải xuống hoặc đọc nội dung.
4. Ghi audit event.
5. Gửi metric và log.

Một thao tác nghiệp vụ vì vậy có thể tạo một hoặc nhiều thao tác tính phí ở từng dịch vụ. Hãy ghi lại số lần gọi trên mỗi luồng thành công và trên mỗi luồng lỗi.

| Luồng nghiệp vụ | Dịch vụ | Thao tác cần đếm |
|---|---|---|
| Tải tài liệu | Database | Số lần đọc metadata, số query hoặc read unit |
| Tải tài liệu | Object storage | GET, HEAD hoặc thao tác metadata thực sự gọi tới storage; signed URL thường được ký ở ứng dụng và không phải object GET |
| Tải tài liệu | Audit/logging | Số event và byte log được ingest |
| Tạo đơn hàng | Database | Read, write, transaction hoặc capacity unit |
| Tạo đơn hàng | Message broker | Send, receive, delivery, dead-letter và retry |
| Xử lý nền | Object storage | GET/PUT, multipart request và byte được đọc/ghi |

Không phải thao tác nào trong bảng cũng luôn bị tính phí riêng. Bảng giúp xác định thứ cần đo; sau đó phải đối chiếu với mô hình giá của dịch vụ thực tế.

### 2.2. Tính số lần gọi thực tế

Với một loại thao tác `i`, có thể bắt đầu bằng:

```text
N_i = N_business
      × calls_per_business_operation_i
      + N_background_i
      + N_retry_i
```

Trong đó `N_business` là số lần nghiệp vụ xảy ra trong tháng; `calls_per_business_operation_i` là số lần thao tác dịch vụ được gọi cho mỗi nghiệp vụ; `N_background_i` là số lần gọi do lịch nền, đồng bộ hoặc tác vụ quản trị; `N_retry_i` là số lần thử lại thực tế.

Ví dụ, 500.000 lượt tải tài liệu, mỗi lượt đọc một metadata record và một object, tạo tối thiểu 500.000 database read và 500.000 object GET. Nếu mỗi lượt đọc metadata có trung bình 1,2 query do pagination hoặc lookup phụ, database có thể nhận 600.000 query. Nếu 1% object GET phải retry một lần, số GET tăng thêm 5.000.

Không nên mặc định một tỷ lệ retry cố định cho mọi dịch vụ. Lấy số lần thử lại từ metric hoặc trace. SDK có thể tự retry bên trong một lần gọi method; bộ đếm ở tầng service wrapper có thể chỉ đếm một lần gọi logic, không đếm đủ số HTTP request tới nhà cung cấp.

### 2.3. Các yếu tố làm tăng số thao tác

- **Fan-out:** một request gọi nhiều dịch vụ hoặc nhiều partition. Đếm số lần gọi thực tế tới từng phụ thuộc.
- **Pagination:** một lần đọc danh sách có thể tạo nhiều request nếu kết quả được chia thành nhiều trang.
- **Retry:** timeout, throttling và lỗi tạm thời có thể tạo thêm request hoặc message delivery.
- **Batching:** một API batch có thể gom nhiều item; cần xác định nhà cung cấp tính theo request hay theo item.
- **Long polling:** một lần chờ có thể kéo dài nhưng vẫn tạo request hoặc đơn vị polling theo mô hình của dịch vụ.
- **Visibility timeout và redelivery:** message không được xác nhận đúng hạn có thể được giao lại và xử lý lại.
- **Multipart upload:** một file lớn có thể tạo request khởi tạo, upload nhiều part, complete và abort.
- **Health check và đồng bộ nền:** các request không gắn với hành vi người dùng vẫn tiêu thụ quota và có thể phát sinh chi phí.

### 2.4. Bảng kiểm kê request

| Dịch vụ | Operation | Số lần/tháng | Đơn vị billing | Số đơn vị tính phí dự kiến |
|---|---|---:|---|---:|
| Object storage | PUT | `N_put` | Request hoặc nhóm request | Theo bảng giá dịch vụ |
| Object storage | GET | `N_get` | Request hoặc nhóm request | Theo bảng giá dịch vụ |
| Object storage | LIST | `N_list` | Request hoặc nhóm request | Theo bảng giá dịch vụ |
| Database | Read | `N_read` | Query, RU, read unit hoặc capacity | Theo chế độ provisioned/on-demand |
| Database | Write | `N_write` | Query, RU, write unit hoặc capacity | Theo chế độ provisioned/on-demand |
| Messaging | Send/Publish | `N_send` | Request, operation hoặc message-size unit | Theo tier và payload |
| Messaging | Receive/Deliver | `N_receive` | Request, operation hoặc delivery | Theo mô hình broker |

Các ký hiệu là biến đầu vào của mô hình. Khi dịch vụ tính theo block payload, throughput hoặc capacity được cấp trước, cần thêm cột thể hiện số block, đơn vị capacity hoặc thời gian duy trì cấu hình.

## 3. Ước lượng chi phí thao tác

Với một nhóm thao tác có đơn giá theo đơn vị, công thức khái quát là:

```text
C_operation_i = billable_units_i × price_per_unit_i
```

`billable_units_i` phải được tính đúng theo quy tắc làm tròn, bậc miễn phí, ngưỡng và đơn vị của dịch vụ. Nếu giá được công bố theo 1.000 request, có thể quy đổi số request sang đơn vị 1.000 theo cách tính của bảng giá. Một số dịch vụ tổng hợp sản lượng trước khi áp dụng bậc; một số dịch vụ có mức tối thiểu hoặc làm tròn riêng. Không tự áp dụng `ceil` cho từng request nếu bảng giá không quy định như vậy.

### 3.1. Object storage

Các thao tác thường cần phân biệt gồm PUT, POST, COPY, LIST, GET, SELECT, multipart upload, abort multipart và replication. Giá có thể khác nhau theo nhóm request và storage class. Một ứng dụng tải ảnh có thể có nhiều GET nhưng ít PUT; hệ thống ingest dữ liệu có thể có nhiều PUT và LIST; tác vụ backup có thể tạo COPY hoặc replication.

Khi lập dự toán, ghi số lượng request theo từng loại. Đặc biệt kiểm tra:

- LIST có thể phát sinh nhiều trang nếu ứng dụng liệt kê nhiều object.
- Multipart upload tạo nhiều request theo số part, ngoài request khởi tạo và hoàn tất.
- Retry upload có thể gửi lại part hoặc toàn bộ thao tác tùy SDK và giao thức.
- Lifecycle transition, replication và restore có thể phát sinh request riêng.
- Đọc dữ liệu từ tier lạnh có thể có phí retrieval ngoài phí GET.

### 3.2. Database managed

Database có nhiều mô hình giá. Một số dịch vụ tính theo instance-hour và dung lượng; một số tính theo read/write request hoặc request unit; một số cung cấp capacity provisioned, serverless hoặc autoscaling. Hai query có cùng số lượng nhưng khác kích thước item, index, consistency hoặc execution plan có thể tiêu thụ đơn vị tính phí khác nhau.

Với database tính theo request unit, cần đo hoặc ước lượng đơn vị tiêu thụ trên mỗi loại query bằng công cụ của dịch vụ. Với database provisioned, chi phí có thể phát sinh theo capacity được cấp ngay cả khi tải thực tế thấp. Với serverless, theo dõi số request, thời gian xử lý, dung lượng và mức tối thiểu nếu có.

Đối với database quan hệ, ngoài compute và storage, cần kiểm tra backup, I/O, read replica, transaction log, snapshot và truyền dữ liệu. Đọc từ replica ở region khác có thể tăng phí mạng và độ trễ.

### 3.3. Messaging và event

Đếm riêng send/publish, receive/delivery, acknowledge/delete, subscription, filter, retry và dead-letter. Một message được publish một lần nhưng có nhiều subscription có thể tạo nhiều lượt giao nhận. Consumer lỗi và message được redeliver có thể làm tăng delivery và compute.

Kích thước payload quan trọng: dịch vụ có thể tính theo request, theo số block dung lượng hoặc theo GB được xử lý. Batching có thể giảm số request nhưng không nhất thiết giảm số byte hoặc số đơn vị message. Nếu dùng message lớn, kiểm tra giới hạn payload, chi phí lưu giữ và chi phí truyền giữa producer với consumer.

### 3.4. Secrets, identity và các dịch vụ phụ trợ

Secret manager có thể tính theo số secret được lưu, số lần truy cập API, số phiên bản hoặc thời gian lưu. Identity provider có thể có quota hoặc giá theo người dùng/ứng dụng/tính năng. Các lần đọc secret lặp lại trong mỗi request có thể tăng chi phí và độ trễ; cache an toàn theo TTL có thể giảm lượt truy cập nhưng phải có kế hoạch xoay vòng và thu hồi secret.

Logging và tracing cũng là workload có thể đo: số event, số byte ingest, số span, thời gian lưu giữ và số truy vấn. Không bỏ qua chi phí telemetry khi ứng dụng tăng traffic.

## 4. Ước lượng dung lượng lưu trữ

Giá dung lượng thường dựa trên lượng dữ liệu được lưu theo thời gian, chẳng hạn GB-month hoặc GiB-month. Số byte được upload trong tháng không đồng nghĩa với dung lượng trung bình phải trả trong tháng đó. Hãy tính tăng trưởng, retention, xóa dữ liệu, versioning, bản sao và thay đổi storage class.

### 4.1. Dung lượng tăng theo tháng

Với dữ liệu mới được tạo đều trong tháng:

```text
Dung lượng tăng mỗi tháng
  = số object mới mỗi tháng × kích thước trung bình mỗi object

Dung lượng cuối kỳ
  = dung lượng đầu kỳ + dữ liệu mới - dữ liệu đã xóa
```

Nếu workload giữ dữ liệu trong `R` tháng rồi xóa và lượng dữ liệu mới ổn định ở `G` GB mỗi tháng, dung lượng ổn định xấp xỉ `G × R` GB. Đây là ước lượng đơn giản; cần điều chỉnh cho object được cập nhật, retention theo ngày, phiên bản, metadata, nén và bản sao.

### 4.2. Dung lượng trung bình theo thời gian

Nếu dữ liệu tăng đều từ `S_start` lên `S_end` trong tháng và không có biến động khác, có thể ước lượng dung lượng trung bình:

```text
S_average ≈ (S_start + S_end) / 2
C_storage ≈ S_average_GB-month × price_per_GB-month
```

Khi billing dùng GB-hour hoặc GiB-hour, hãy tích phân dung lượng theo thời gian hoặc dùng dữ liệu usage do nhà cung cấp báo cáo. Không lấy dung lượng cuối tháng nhân giá GB-month nếu dung lượng đã tăng dần trong cả tháng.

### 4.3. Retention, versioning và bản sao

Các yếu tố thường làm dung lượng lớn hơn dự kiến:

- **Retention:** dữ liệu giữ 90 ngày sẽ chiếm nhiều dung lượng hơn dữ liệu giữ 30 ngày nếu tốc độ tạo dữ liệu không đổi.
- **Versioning:** ghi đè object có thể giữ lại nhiều phiên bản cũ cho tới khi lifecycle xóa chúng.
- **Replication:** bản sao ở region hoặc tài khoản khác có thể được tính dung lượng riêng.
- **Backup và snapshot:** bản sao lưu có thể có mô hình incremental nhưng vẫn cần dự toán theo dữ liệu thay đổi và thời gian giữ.
- **Soft delete và recycle retention:** dữ liệu đã xóa logic có thể vẫn được tính dung lượng trong thời gian khôi phục.
- **Metadata và index:** database index, metadata, log và cấu trúc phụ trợ có thể làm dung lượng thực tế cao hơn payload nghiệp vụ.

### 4.4. Storage tier và phí truy xuất

Storage tier nóng thường tối ưu cho truy cập thường xuyên; tier lạnh hoặc archive có thể giảm giá lưu trữ nhưng tăng phí truy xuất, độ trễ khôi phục hoặc thời gian lưu tối thiểu. Khi chuyển tier, tính cả:

- Phí transition hoặc request lifecycle nếu có.
- Phí đọc/retrieval theo GB hoặc theo request.
- Phí xóa sớm khi dữ liệu bị xóa trước thời gian lưu tối thiểu.
- Thời gian restore và chi phí tạm thời khi khôi phục dữ liệu.
- Tác động tới SLA và trải nghiệm người dùng.

Không chọn tier chỉ dựa trên đơn giá lưu trữ. Với workload đọc thường xuyên, tổng chi phí GET và retrieval có thể làm tier lạnh đắt hơn tier nóng.

## 5. Ước lượng truyền dữ liệu

Chi phí truyền dữ liệu phụ thuộc vào byte thực tế, chiều truyền, nguồn, đích và tuyến mạng. Hãy lập bản đồ luồng dữ liệu trước khi áp giá.

### 5.1. Phân loại tuyến truyền

| Tuyến | Ví dụ | Điều cần xác minh |
|---|---|---|
| Internet ingress | Người dùng upload file vào cloud | Quy tắc tính phí inbound của dịch vụ và thành phần mạng đi kèm |
| Internet egress | Người dùng tải file từ ứng dụng hoặc object storage | Bậc miễn phí, đơn giá theo vùng đích và tổng GB outbound |
| Cùng region | App gọi database hoặc storage trong cùng region | Dịch vụ có tính phí request, endpoint hoặc xử lý riêng hay không |
| Cross-zone | Workload ở zone A gọi tài nguyên ở zone B | Quy tắc transfer giữa zone và topology thực tế |
| Cross-region | App ở region A đọc database ở region B | Đơn giá theo cặp region, chiều truyền và dịch vụ nguồn |
| Inter-cloud | AWS gửi dữ liệu tới Azure hoặc Google Cloud | Egress của cloud nguồn, ingress của đích và phí kết nối trung gian |
| Private network | NAT, peering, VPN, transit hoặc private endpoint | Phí theo giờ, endpoint, GB xử lý, cổng hoặc tuyến |

Không mặc định mọi lưu lượng cùng cloud hoặc cùng region đều miễn phí. Cũng không mặc định mọi inbound đều miễn phí. Đọc quy tắc của đúng dịch vụ và đường mạng, vì một request có thể đi qua nhiều thành phần có cách tính riêng.

### 5.2. Công thức byte truyền

Với một luồng dữ liệu ổn định:

```text
GB_truyền_tháng
  = số lượt truyền mỗi ngày
  × số ngày trong tháng
  × byte trung bình mỗi lượt
  / số byte trong một GB theo đơn vị billing
```

Khi dùng đơn vị thập phân, 1 GB = 1.000.000.000 byte. Một số công cụ hiển thị GiB với 1 GiB = 1.073.741.824 byte. Hãy giữ cùng đơn vị từ số đo đến bảng giá để tránh sai lệch.

Với stream hoặc kết nối liên tục, ước lượng theo throughput:

```text
GB_truyền_tháng
  = throughput_byte_per_second
  × số giây hoạt động trong tháng
  / số byte trong một GB theo đơn vị billing
```

### 5.3. Những luồng dễ bị bỏ sót

- Object replication và database replication giữa region.
- Message được gửi qua broker hoặc consumer ở region khác.
- Backup, snapshot export và restore sang region khác.
- Log, trace, metric và audit event được gửi tới workspace tập trung.
- NAT gateway hoặc network appliance xử lý byte trước khi ra Internet.
- Tải lại do retry, đồng bộ định kỳ, polling và job backfill.
- CDN cache miss, origin fetch và nội dung bị invalidation thường xuyên.

### 5.4. Tránh tính trùng byte

Vẽ tuyến dữ liệu theo từng chặng và ghi ai trả phí ở mỗi chặng. Ví dụ, khi Spring Boot đọc object từ bucket cùng region rồi stream file ra Internet, có thể có phí GET, phí xử lý mạng và phí egress từ workload. Nếu client tải trực tiếp qua signed URL, đường truyền egress có thể được tính ở object storage. Không cộng đồng thời hai kịch bản như thể cùng một byte đi qua cả hai đường.

Đối với replication, phân biệt byte gốc được ghi vào storage với byte sao chép sang region đích. Dung lượng bản sao làm tăng storage capacity; luồng sao chép có thể làm tăng data transfer và request. Đó là các khoản khác nhau, nhưng phải kiểm tra xem bảng giá của dịch vụ đã gộp khoản nào.

## 6. Ví dụ dự toán cho dịch vụ tài liệu

Giả sử một ứng dụng Spring Boot lưu tài liệu trong object storage. Mỗi tháng hệ thống tạo 400.000 object, kích thước trung bình 250 KB. Người dùng tải 1.200.000 object mỗi tháng. Hệ thống giữ tài liệu 90 ngày, sao chép object mới sang một region dự phòng và cho phép tải trực tiếp từ object storage.

### 6.1. Ước lượng request

Giả sử mỗi object được tạo bằng một PUT đơn giản, mỗi lần tải là một GET và hệ thống phát sinh 40.000 LIST request mỗi tháng:

| Operation | Số lần cơ sở/tháng | Ghi chú |
|---|---:|---|
| PUT | 400.000 | Một request cho mỗi object trong giả định đơn giản |
| GET | 1.200.000 | Một request cho mỗi lượt tải |
| LIST | 40.000 | Đã ước lượng số trang, không chỉ số lần người dùng mở màn hình |

Nếu số lần retry trung bình tương đương 2% số request cơ sở, lượng request dự kiến để lập kịch bản là:

```text
PUT ≈ 400.000 × 1,02 = 408.000
GET ≈ 1.200.000 × 1,02 = 1.224.000
LIST ≈ 40.000 × 1,02 = 40.800
```

Đây là giả định lập kế hoạch. Trong production, hãy thay bằng số request thực đo theo từng operation và xác minh retry có được tính như một request mới hay không.

### 6.2. Ước lượng dung lượng

```text
Dữ liệu mới mỗi tháng
  = 400.000 × 250 KB
  = 100.000.000 KB
  ≈ 100 GB (đơn vị thập phân)

Dung lượng ổn định với retention 90 ngày
  ≈ 100 GB/tháng × 3 tháng
  ≈ 300 GB
```

Ước lượng 300 GB giả định dữ liệu được tạo đều, không có phiên bản cũ, không có object tồn tại quá retention, không tính metadata và không có bản sao trong cùng region. Nếu bản sao ở region dự phòng giữ đủ 90 ngày, dung lượng lưu trữ của bản sao cần được dự toán thêm theo location và tier ở region đó. Nếu bật versioning, hãy tính cả các phiên bản chưa hết hạn.

### 6.3. Ước lượng truyền dữ liệu

```text
Upload mới mỗi tháng        ≈ 100 GB
Replication sang region B   ≈ 100 GB
Download ra Internet        = 1.200.000 × 250 KB
                            ≈ 300 GB
```

Trong giả định client tải trực tiếp từ object storage, 300 GB là dữ liệu egress tới Internet. 100 GB replication là một luồng cross-region riêng. Upload ingress khoảng 100 GB cần được ghi nhận để đối chiếu, nhưng quy tắc tính phí ingress phải được kiểm tra theo dịch vụ. Nếu ứng dụng proxy nội dung, cần vẽ lại tuyến từ bucket tới app và từ app tới người dùng để xác định thành phần egress và network processing.

### 6.4. Lập bảng chi phí

| Thành phần | Sản lượng dùng để tính | Đơn giá cần tra |
|---|---:|---|
| PUT request | Khoảng 408.000 request | Giá nhóm ghi của storage class |
| GET request | Khoảng 1.224.000 request | Giá nhóm đọc của storage class |
| LIST request | Khoảng 40.800 request | Giá nhóm list hoặc request tương ứng |
| Storage region A | Khoảng 300 GB-month ở trạng thái ổn định | Giá GB-month của tier và region A |
| Storage region B | Khoảng 300 GB-month nếu replica giữ đủ dữ liệu | Giá GB-month của tier và region B |
| Internet egress | Khoảng 300 GB/tháng | Giá outbound theo region nguồn và đích |
| Cross-region replication | Khoảng 100 GB/tháng | Giá transfer, request replication và các khoản liên quan |
| Retrieval / transition | Theo số lần và số GB thực tế | Giá tier, retrieval và lifecycle |

Không điền một đơn giá giả định vào ví dụ này vì giá khác nhau theo region, storage class, bậc sử dụng và hợp đồng. Sau khi lấy giá hiện hành, tính từng dòng rồi cộng thành tổng tháng. Thực hiện thêm kịch bản tải tăng 30%, retention dài hơn và tải đột biến để biết độ nhạy của hóa đơn.

## 7. Khác biệt về cách tính giữa AWS, Azure và Google Cloud

Các khái niệm dung lượng, thao tác và truyền dữ liệu có ở cả ba nền tảng, nhưng tên đơn vị, nhóm request, cách áp bậc và các tùy chọn dự phòng không hoàn toàn tương đương.

### 7.1. AWS

- **Amazon S3:** phân biệt storage class, dung lượng, request theo nhóm API, retrieval, lifecycle transition, replication và data transfer. Multipart upload và các thao tác quản trị có thể tạo request riêng.
- **Amazon SQS/SNS:** kiểm tra request, payload-size unit, batch, publish, delivery và các lần nhận lại message. Với SNS fan-out tới nhiều subscription, tính riêng lưu lượng và xử lý ở từng đích.
- **Amazon DynamoDB:** phân biệt on-demand request units với provisioned read/write capacity, dung lượng bảng, index, backup và restore. Cùng một số query có thể tiêu thụ capacity khác nhau tùy kích thước item và cách đọc.
- **Amazon RDS:** tính instance, storage, backup vượt ngưỡng, I/O theo loại storage, read replica và transfer. Giá compute không đại diện cho tổng chi phí database.
- **CloudWatch và dịch vụ mạng:** tính log ingestion/retention, metric, alarm, trace, NAT Gateway, load balancer và data transfer theo tuyến.

Với ứng dụng Spring Boot dùng Spring Cloud AWS, có thể gắn metric vào các thao tác S3, SQS, SNS hoặc DynamoDB ở lớp adapter. Metric ở ứng dụng hỗ trợ phân tích workload; số liệu billing và usage của AWS vẫn là căn cứ xác nhận số đơn vị được tính phí.

### 7.2. Microsoft Azure

- **Azure Blob Storage:** phân biệt dung lượng theo access tier và redundancy, transaction theo loại operation, data retrieval, early deletion, replication và bandwidth. Hot, cool, cold hoặc archive có điều kiện truy cập và giá khác nhau.
- **Azure Service Bus:** kiểm tra số operation, tier, message size, số lần delivery, duplicate detection, transaction và lưu giữ dead-letter. Batching có thể thay đổi số operation nhưng không làm mất giới hạn payload.
- **Azure Cosmos DB:** xác định request unit (RU) theo loại thao tác, kích thước dữ liệu, index và consistency; tính cả throughput provisioned hoặc serverless, storage, backup và replication đa region.
- **Azure SQL:** tính compute hoặc vCore/DTU theo mô hình đã chọn, storage, backup, geo-replication và network egress.
- **Azure Monitor và mạng:** tính log ingestion, retention, query, Private Link, NAT Gateway, load balancing và bandwidth.

Với Spring Cloud Azure, hãy instrument adapter gọi Blob Storage, Service Bus hoặc database. Không dùng số lần gọi method làm đại diện trực tiếp cho RU hoặc transaction nếu SDK/service có thể chia request hoặc tiêu thụ đơn vị khác theo payload.

### 7.3. Google Cloud

- **Cloud Storage:** tính dung lượng theo location và storage class, operation theo nhóm A/B hoặc phân loại tương ứng hiện hành, retrieval, replication và network egress.
- **Pub/Sub:** kiểm tra dung lượng message được publish/consume, số lần giao nhận, subscription, retention, retry và transfer giữa các location.
- **Firestore:** phân biệt document read/write/delete, storage, index, backup và network. Query có thể đọc nhiều document hơn số bản ghi trả về.
- **Cloud SQL:** tính vCPU/RAM hoặc machine tier, storage, backup, network egress và read replica.
- **Cloud Logging/Monitoring và mạng:** tính log volume, metric, trace, retention, Cloud NAT, load balancing và network egress.

Với Spring Cloud GCP, đo số thao tác và byte ở adapter của Storage, Pub/Sub hoặc database. Đối chiếu với Cloud Billing export để kiểm tra sản lượng tính phí thực tế.

### 7.4. Bảng so sánh cách tiếp cận

| Nhóm | AWS | Azure | Google Cloud |
|---|---|---|---|
| Object storage | S3 storage class, request class, retrieval và transfer | Blob tier, transaction, redundancy, retrieval và bandwidth | Cloud Storage class/location, operation, retrieval và egress |
| Messaging | SQS request/payload unit; SNS publish/delivery | Service Bus operation, tier, message và delivery | Pub/Sub data volume, delivery, retention và location |
| NoSQL | DynamoDB read/write capacity hoặc request unit | Cosmos DB RU và throughput | Firestore document operation và storage |
| Quan sát | CloudWatch ingestion/retention và metric | Azure Monitor ingestion/retention | Cloud Logging ingestion/retention và Monitoring |
| Xác minh | Cost and Usage Report / billing data | Cost Management exports | Cloud Billing export |

Các tên nhóm giá và cách đo có thể thay đổi. Khi làm dự toán thật, tra đúng trang giá của sản phẩm, region, tier, loại request và thời điểm áp dụng; không quy đổi một đơn vị của nhà cung cấp này thành đơn vị của nhà cung cấp khác chỉ dựa trên tên gọi.

## 8. Đo workload trong Spring Boot

Để mô hình chi phí hữu ích, cần thu thập số lượng thao tác và kích thước dữ liệu. Có thể dùng Micrometer để tạo metric tại lớp adapter gọi dịch vụ managed. Metric nên thể hiện service, operation, outcome và region với số lượng giá trị hữu hạn.

### 8.1. Đếm thao tác và thời gian

Ví dụ dưới đây minh họa wrapper ghi số lần gọi và thời gian của một thao tác. `Supplier` đại diện cho lời gọi dịch vụ; trong code thật, adapter có thể bọc SDK call, repository hoặc client tương ứng.

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

@Component
public class CloudOperationMetrics {
    private final MeterRegistry registry;

    public CloudOperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T record(String service, String operation, Supplier<T> action) {
        long startedAt = System.nanoTime();
        try {
            T result = action.get();
            registry.counter("cloud.operation.calls",
                    "service", service,
                    "operation", operation,
                    "outcome", "success").increment();
            return result;
        } catch (RuntimeException ex) {
            registry.counter("cloud.operation.calls",
                    "service", service,
                    "operation", operation,
                    "outcome", "error").increment();
            throw ex;
        } finally {
            Timer.builder("cloud.operation.duration")
                    .tag("service", service)
                    .tag("operation", operation)
                    .register(registry)
                    .record(System.nanoTime() - startedAt, TimeUnit.NANOSECONDS);
        }
    }
}
```

Ví dụ sử dụng:

```java
public DocumentMetadata loadMetadata(String documentId) {
    return metrics.record("document-database", "metadata-read",
            () -> repository.findById(documentId)
                    .orElseThrow(DocumentNotFoundException::new));
}
```

Wrapper đếm lần gọi logic ở ứng dụng. Nếu SDK tự retry, một lần gọi `action.get()` có thể tạo nhiều request mạng. Để đếm billable request chính xác hơn, bổ sung SDK interceptor, client instrumentation hoặc số liệu usage từ dịch vụ. Với database tính RU hoặc capacity, lấy metric tiêu thụ do database cung cấp thay vì suy ra chỉ từ số lần gọi repository.

### 8.2. Đo kích thước dữ liệu

Có thể ghi nhận byte đọc/ghi ở lớp ứng dụng khi đã biết kích thước payload:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class CloudPayloadMetrics {
    private final MeterRegistry registry;

    public CloudPayloadMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordBytes(String service, String direction, long bytes) {
        DistributionSummary.builder("cloud.payload.bytes")
                .baseUnit("bytes")
                .tag("service", service)
                .tag("direction", direction)
                .register(registry)
                .record(bytes);
    }
}
```

Đối với stream, nên đếm byte thực sự được đọc hoặc ghi trong quá trình truyền thay vì chỉ dùng Content-Length nếu request có thể bị nén, bị hủy hoặc truyền theo từng phần. Phân biệt byte payload với byte mạng: TLS, protocol header, retry và replication có thể làm lượng byte trên đường truyền lớn hơn.

### 8.3. Quy tắc đặt tag và bảo vệ telemetry

- Dùng tag có cardinality thấp như `service`, `operation`, `region`, `outcome` và `tier`.
- Không gắn user ID, email, object key, message ID hoặc request ID vào tag metric.
- Không đưa nội dung message, secret, access token hoặc dữ liệu cá nhân vào metric hay log.
- Ghi rõ đơn vị byte và thời gian; thống nhất GB hay GiB trong pipeline báo cáo.
- Tách metric theo môi trường và workload để không cộng lẫn test traffic với production.
- Giữ trace sampling phù hợp; trace đầy đủ cho mọi request có thể làm chi phí quan sát tăng đáng kể.

## 9. Từ metric đến dự toán và phân bổ chi phí

Metric ứng dụng cho biết workload đã làm gì; billing export cho biết nhà cung cấp đã tính phí theo sản lượng và quy tắc nào. Hai nguồn cần được đối chiếu.

### 9.1. Quy trình đối chiếu

1. Thu thập metric số thao tác, byte đọc/ghi, thời gian chạy và retry theo service/operation.
2. Lấy usage và cost export từ AWS, Azure hoặc Google Cloud theo cùng khoảng thời gian.
3. Chuẩn hóa region, project/account/subscription, service, SKU, đơn vị và currency.
4. So sánh sản lượng ứng dụng với usage của nhà cung cấp; tìm phần chênh do retry SDK, request phụ, replication, lifecycle hoặc hệ thống khác.
5. Phân bổ chi phí theo team, ứng dụng, tenant hoặc tính năng dựa trên tag và nhãn tài nguyên.
6. Ghi lại giả định và điều chỉnh mô hình khi có thay đổi về giá, traffic hoặc kiến trúc.

### 9.2. Gắn chi phí vào tính năng

Ví dụ, nếu tính năng tải tài liệu chiếm 70% GET request, 40% dung lượng lưu và 80% egress, không nên phân bổ toàn bộ hóa đơn theo một tỷ lệ duy nhất. Hãy chọn driver phù hợp cho từng dòng:

| Khoản chi | Driver phân bổ phù hợp |
|---|---|
| GET/PUT/LIST | Số operation theo tính năng |
| Storage | GB-month theo bucket, prefix hoặc dataset nếu có thể đo |
| Egress | Byte truyền theo tính năng hoặc tuyến |
| Compute | CPU time, memory time hoặc request share |
| Messaging | Message count, payload bytes và delivery count |
| Logging | Byte ingest hoặc log volume theo ứng dụng |

Nếu dịch vụ dùng chung không cung cấp số liệu chi tiết theo tenant, có thể dùng hệ số phân bổ đã thống nhất. Ghi rõ đây là ước lượng phân bổ để tránh nhầm với số tiền billing chính xác.

### 9.3. Kịch bản và độ nhạy

Không chỉ tính một con số duy nhất. Tối thiểu tạo ba kịch bản:

- **Cơ sở:** traffic trung bình dự kiến, retention hiện tại và tỷ lệ lỗi quan sát được.
- **Tăng trưởng:** số người dùng, request, dung lượng và byte truyền tăng theo kế hoạch.
- **Đỉnh hoặc bất lợi:** tải cao, retry tăng, cache miss, replication backlog hoặc retention dài hơn.

Thử thay đổi từng giả định để xác định yếu tố chi phối chi phí. Ví dụ, tăng retention từ 30 lên 90 ngày có thể làm storage tăng gần ba lần khi tốc độ tạo dữ liệu ổn định; tăng tỷ lệ cache hit có thể giảm GET và egress; tăng batch size có thể giảm số request nhưng không nhất thiết giảm payload hoặc đơn vị message.

## 10. Tối ưu chi phí theo nguyên nhân

Chỉ tối ưu sau khi biết khoản chi nào chiếm tỷ trọng lớn và vì sao nó phát sinh.

### 10.1. Giảm số thao tác không cần thiết

- Cache metadata hoặc kết quả đọc có thể tái sử dụng, với TTL và invalidation phù hợp.
- Dùng batch khi dịch vụ hỗ trợ và khi batch không làm tăng latency hoặc retry quá mức.
- Tránh polling quá thường xuyên; cân nhắc event-driven hoặc long polling theo semantics và chi phí dịch vụ.
- Giảm pagination thừa bằng filter, page size hợp lý và query có giới hạn.
- Thiết kế retry có backoff, jitter, giới hạn số lần và phân loại lỗi retryable.
- Tránh ghi cùng một dữ liệu nhiều lần; gom cập nhật nếu nghiệp vụ cho phép.

### 10.2. Tối ưu dung lượng

- Đặt retention rõ ràng và tự động xóa dữ liệu hết hạn.
- Dùng lifecycle chuyển tier theo tuổi và mẫu truy cập.
- Nén dữ liệu phù hợp trước khi lưu hoặc truyền.
- Xóa multipart upload dở dang và phiên bản cũ theo chính sách.
- Chọn redundancy theo RPO/RTO thay vì bật bản sao không có nhu cầu.
- Theo dõi tăng trưởng storage và đặt ngưỡng cảnh báo theo tốc độ tăng.

### 10.3. Giảm truyền dữ liệu

- Đặt workload gần database, broker và storage được gọi thường xuyên khi ràng buộc cho phép.
- Dùng CDN hoặc cache cho nội dung có thể cache an toàn.
- Tránh kéo dữ liệu lớn qua region chỉ để xử lý một phép biến đổi đơn giản; cân nhắc đưa xử lý tới nơi dữ liệu đang ở.
- Nén payload và chỉ truyền trường cần thiết.
- Chọn vị trí log, trace và backup phù hợp với chính sách dữ liệu và nhu cầu vận hành.
- Kiểm tra NAT, peering, load balancer và private endpoint để hiểu phí xử lý byte.

### 10.4. Kiểm soát compute và quan sát

- So sánh provisioned capacity với serverless dựa trên tải nền, tải đỉnh và độ ổn định.
- Scale theo metric có liên hệ với workload như queue depth, concurrency hoặc request rate.
- Tắt môi trường không dùng và đặt lịch cho tài nguyên thử nghiệm.
- Dùng sampling cho trace và đặt retention cho log theo nhu cầu điều tra.
- Theo dõi chi phí theo deployment và môi trường để tránh test workload làm sai dự toán production.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ đếm request HTTP của người dùng | Bỏ sót fan-out, query, message, retry và job nền | Lập bản đồ từng lời gọi tới dịch vụ managed |
| Lấy số method call làm số billable request | Không thấy retry hoặc request phụ do SDK tạo | Đối chiếu interceptor, telemetry dịch vụ và billing export |
| Dùng dung lượng cuối tháng cho cả tháng | Dự toán sai khi dữ liệu tăng dần | Tính GB-month hoặc GB-hour trung bình theo thời gian |
| Bỏ qua versioning và backup | Thiếu dung lượng bản sao và retention | Đưa mọi bản sao và phiên bản vào mô hình |
| Chỉ nhìn giá storage | Bỏ qua PUT/GET, retrieval, replication và egress | Tách riêng operation, storage, retrieval và transfer |
| Coi inbound và outbound giống nhau | Áp sai đơn giá theo chiều truyền | Phân loại nguồn, đích và chiều của từng luồng |
| Cộng trùng cùng một luồng byte | Tổng chi phí bị phóng đại | Vẽ tuyến và gắn từng khoản phí với từng chặng |
| Chuyển dữ liệu sang tier lạnh chỉ vì giá thấp | Retrieval và early deletion có thể làm tổng phí tăng | Dựa trên mẫu truy cập và tổng chi phí vòng đời |
| Không đối chiếu billing thực tế | Mô hình không phản ánh request ẩn hoặc quy tắc làm tròn | So sánh định kỳ với usage export |

## 12. Checklist trước khi duyệt dự toán

- [ ] Đã mô tả luồng nghiệp vụ và các dịch vụ managed được gọi.
- [ ] Đã đếm request theo operation, bao gồm pagination, batch, retry và tác vụ nền.
- [ ] Đã xác định đơn vị tính phí, ngưỡng, bậc, mức tối thiểu và điều kiện miễn phí.
- [ ] Đã tính dung lượng trung bình theo thời gian, retention, versioning và bản sao.
- [ ] Đã tính retrieval, lifecycle transition và phí xóa sớm nếu có.
- [ ] Đã lập bản đồ luồng byte theo nguồn, đích, region, zone và chiều truyền.
- [ ] Đã phân biệt Internet egress, cross-region, cross-zone, inter-cloud và phí xử lý mạng.
- [ ] Đã tách compute, operation, storage, transfer, backup và observability.
- [ ] Đã lập kịch bản cơ sở, tăng trưởng và bất lợi.
- [ ] Đã xác định nguồn billing export và cách đối chiếu sau triển khai.
- [ ] Đã ghi ngày tra giá, currency, region, tier và các giả định của mô hình.

## Kết luận

Dự toán cloud có ý nghĩa khi bắt đầu từ workload thực tế và chuyển mỗi luồng nghiệp vụ thành các đơn vị có thể đo: request, message, GB-month, byte truyền và thời gian tài nguyên chạy. Hãy tính riêng thao tác, dung lượng, retrieval, truyền dữ liệu, compute và quan sát; sau đó đối chiếu với billing export của AWS, Azure hoặc Google Cloud. Metric trong Spring Boot giúp hiểu cách ứng dụng sử dụng dịch vụ, còn số liệu usage của nhà cung cấp xác nhận cách tính phí. Khi hai nguồn được đối chiếu thường xuyên, nhóm có thể dự báo chi phí, phân bổ theo tính năng và chọn tối ưu dựa trên nguyên nhân thực tế.
