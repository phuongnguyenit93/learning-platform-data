# Theo dõi hiệu năng Bigtable bằng Key Visualizer

Một nền tảng học trực tuyến ghi hàng triệu sự kiện tiến độ học tập vào **Bigtable**. Dashboard Google Cloud cho thấy CPU trung bình của cluster chưa quá cao, nhưng độ trễ ghi p99 tăng mạnh vào giờ cao điểm. Nguyên nhân có thể không phải thiếu tổng tài nguyên: các row key dạng `2026-11-19#event-id` đang đẩy phần lớn lần ghi mới vào **một vùng khóa liên tiếp**. Thêm node có thể không xử lý dứt điểm điểm nóng đó.

**Key Visualizer** là công cụ quan sát của Bigtable giúp nhìn mức hoạt động, độ trễ và cảnh báo **theo các khoảng row key qua thời gian**. Bài học nằm trong chương **Bigtable và Memorystore** của module **CLOUD_PROVIDERS_GCP**: nối kiến thức về VPC, Compute Engine/GKE/Cloud Run, lưu trữ, giám sát độ tin cậy và chi phí vào quy trình tìm nguyên nhân làm chậm một Bigtable table. Chủ đề ở đây là **Bigtable Key Visualizer**, không phải bộ theo dõi Redis của Memorystore.

Sau bài này, bạn có thể:

1. Đọc heatmap theo trục thời gian và key range, hiểu `key bucket`, màu sắc và giới hạn dữ liệu.
2. Chọn đúng chỉ số `Ops`, `Read/Write pressure index`, `Latency`, `Large rows` khi điều tra.
3. Phân biệt hot row/range, truy cập theo chu kỳ, quét tuần tự và sự cố ảnh hưởng toàn bảng.
4. Ghép Key Visualizer với Monitoring, hot tablets và client metrics để tránh chẩn đoán sai.
5. Đề xuất sửa row-key schema, cache, filter, batching/deduplication và kiểm chứng bằng tải đại diện.
6. Thực hiện một lab **chỉ đọc** và giải các tình huống về hotspot, khả dụng và chi phí.

## 1. Vì sao Bigtable có thể nóng ở một phần keyspace?

Bigtable lưu dữ liệu dạng bảng **row key → column family/qualifier → cells**; row keys được sắp thứ tự **theo bytes, lexicographic**. Các row liên tiếp được quản lý trong các vùng lưu trữ gọi là **tablets**; hạ tầng phân phối/move/split tablets trên nhiều node. Điều này làm các range scans theo prefix rất hiệu quả nhưng đồng thời tạo nguy cơ **lượt truy cập tập trung vào một ít hàng/range**.

~~~mermaid
flowchart TB
    A["Ứng dụng Cloud Run / GKE<br/>đọc ghi Bigtable"] --> B["Row keys được sắp<br/>theo byte tăng dần"]
    B --> T1["Tablet: A–F"]
    B --> T2["Tablet: G–N"]
    B --> T3["Tablet: O–Z"]
    T1 --> N1["Node 1"]
    T2 --> N2["Node 2"]
    T3 --> N3["Node 3"]
    KV["Key Visualizer"] -. "Quan sát usage<br/>theo key buckets" .-> B
    MON["Cloud Monitoring"] -. "Quan sát CPU, latency,<br/>cluster/tablet" .-> N2
~~~

Đây là **sơ đồ khái niệm**. `Tablet` là đơn vị phục vụ/lưu trữ của Bigtable; `key bucket` là đơn vị **hiển thị/thu thập thống kê** của Key Visualizer. **Không đồng nhất** một bucket trên heatmap với một tablet hoặc một node.

### 1.1. Ba loại nghẽn thường bị nhầm

| Hiện tượng | Biểu hiện | Công cụ bổ sung |
| --- | --- | --- |
| **Toàn cluster quá tải** | CPU nhiều node cao, read/write latency tăng diện rộng | Cloud Monitoring cluster CPU, node count, request latency |
| **Hot row hoặc hot range** | Một số key ranges có read/write pressure cao dù CPU trung bình thấp hơn | Key Visualizer, Hot tablets, hottest-node CPU |
| **Ứng dụng/network chậm** | Client p99 cao nhưng không có hot key và server latency ổn | Client metrics, gRPC retries, VPC/network, connection pools |

Không coi mọi request chậm là vấn đề cần đổi row key. Nếu tất cả ranges đồng thời tăng latency, điều tra quota, cluster CPU, mạng, replica routing hoặc sự cố diện rộng trước.

### 1.2. Row-key anti-pattern

~~~text
# Không phù hợp cho bảng có nhiều INSERT tuần tự toàn hệ thống
2026-11-19T10:00:00.001Z#event-001
2026-11-19T10:00:00.002Z#event-002
2026-11-19T10:00:00.003Z#event-003

# Phương án được khảo sát: đặt định danh có cardinality cao trước thời gian
student-a17#2026-11-19T10:00:00.001Z
student-b42#2026-11-19T10:00:00.002Z
student-c09#2026-11-19T10:00:00.003Z
~~~

Với thiết kế thứ nhất, thời gian ở đầu key luôn tăng; các hàng mới tập trung ở đuôi keyspace. Thiết kế thứ hai phân tán theo student **nếu nhiều students ghi đồng thời**, đồng thời giúp đọc chuỗi sự kiện của một student bằng prefix. Nhưng nếu một student chiếm 80% traffic thì prefix đó vẫn có thể thành hotspot: phải đo phân bố thực tế.

## 2. Key Visualizer quan sát điều gì?

Key Visualizer tạo **heatmap**: trục **X là thời gian**, trục **Y là row-key ranges**, còn màu biểu diễn mức độ của chỉ số đang chọn. Màu tối thường là giá trị thấp; màu sáng là giá trị cao **so với các giá trị đang hiển thị**.

Bigtable có thể có vô số row keys, nên Key Visualizer chia keyspace thành khoảng **1.000 contiguous key buckets** (mỗi bucket chứa xấp xỉ cùng số row keys), rồi hiển thị những phép tổng hợp thích hợp. Với nhóm **Warnings** và **Performance**, công cụ có thể cung cấp chi tiết hơn về key hoặc key range có vấn đề. Bucket boundaries được cập nhật theo dữ liệu; không giả định một tọa độ Y trong các scan khác nhau luôn chỉ cùng một hàng.

### 2.1. Điều kiện xuất hiện và quyền xem

- Theo hướng dẫn Bigtable hiện hành, bảng phải có **ít nhất 1 GB dữ liệu trên mỗi cluster** để Key Visualizer có dữ liệu trực quan; có thể mất **tới một giờ** sau khi đạt ngưỡng để dữ liệu xuất hiện.
- Chọn **đúng table và cluster**: Bigtable instance có nhiều cluster có thể nhận lưu lượng khác nhau theo app profile/replication.
- Người xem cần quyền xem Bigtable và Key Visualizer phù hợp, ví dụ các quyền `bigtable.keyvisualizer.get` và `bigtable.keyvisualizer.list`. Sử dụng role ít quyền nhất theo chính sách, **không cấp Bigtable Admin chỉ để xem biểu đồ**.
- Key Visualizer có thể hiện **row key prefixes/ranges**; nếu row key chứa email, mã khách hàng hoặc PII, ảnh chụp heatmap/tooltip cũng có thể nhạy cảm. Chỉ chia sẻ với người được phân quyền và ẩn/redact nội dung trước khi đưa vào ticket.

**Bảng dưới 1 GB không có scan không đồng nghĩa hoạt động bình thường.** Với bảng nhỏ, dùng Cloud Monitoring, application metrics, hot tablets khi hỗ trợ và load test để điều tra. Không tạo thêm dữ liệu thật chỉ để vượt ngưỡng.

### 2.2. Key buckets không phải dữ liệu thô từng hàng

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Một dải sáng = một row cụ thể” | Phần lớn heatmap tổng hợp **một khoảng nhiều rows**. Drill down Warnings để xem chi tiết khi có. |
| “Một dải sáng = một Bigtable node” | Key ranges/buckets **không** ánh xạ cố định một-một với node. |
| “Màu vàng là lỗi” | `Ops`/Reads/Writes dùng màu tương đối; phải xem Warnings, latency và mức độ ảnh hưởng. |
| “Biểu đồ không sáng nghĩa là p99 luôn thấp” | Có thể lỗi network, client, hoặc dữ liệu không được scan/đã được tổng hợp. |
| “Đổi thời gian nhưng giữ vị trí Y để so hai row” | Bucket boundaries có thể được tính lại; phải dựa trên key range/tooltip thật. |

## 3. Bộ chỉ số cần biết khi điều tra

| Nhóm | Metric trên Key Visualizer | Cách dùng |
| --- | --- | --- |
| **Activity** | `Ops` | Hoạt động đọc + ghi gần đúng, đo theo **operations per row per minute**. Bắt đầu điều tra ở đây. |
| **Warnings** | `Read pressure index` | Composite index dựa trên CPU/latency đọc cho row/key range; **≥100 kéo dài** là tín hiệu đáng điều tra. |
| **Warnings** | `Write pressure index` | Tương tự cho ghi; ≥100 kéo dài có thể liên quan hot writes hoặc row quá lớn. |
| **Warnings** | `Large rows` | Phát hiện row **>256 MB** hoặc key ranges trung bình **>200 MB/row**; cần xem thiết kế row/data retention. |
| **Reads** | `Read CPU`, `Read bytes client` | Xác định range nào tiêu thụ compute đọc hoặc bytes trả về client. |
| **Writes** | `Write CPU`, `Write bytes client` | Xác định range nào có tải ghi hoặc byte ghi lớn. |
| **Performance** | `Latency`, `Latency (max)` | Đối chiếu điểm nóng với thời gian xử lý trên row/key range. |
| **Size** | `Data stored`, `Rows` | Phân bố dung lượng **đã nén** và số row xấp xỉ theo bucket. |

**Lưu ý pressure index:** đây là **chỉ số tổng hợp không có đơn vị quy đổi ra CPU%**. Không viết alert kiểu “read pressure 100 = CPU 100%”. Giá trị **100 trở lên** trong nhiều khoảng đo 15 phút thường chỉ hiệu năng kém ở key range đó; áp tiêu chí thời gian, xác minh latency và tần suất thay vì kết luận từ một điểm dữ liệu.

### 3.1. Phối hợp metrics thay vì chỉ nhìn một heatmap

~~~text
Ops sáng tại một prefix
  ├─ Read CPU / Read bytes sáng + Read pressure cao
  │    -> Kiểm tra quá nhiều reads, scan/filter lớn, row quá lớn, cache.
  ├─ Write CPU / Write bytes sáng + Write pressure cao
  │    -> Kiểm tra hot row/range, timestamp-leading key, ghi trùng.
  ├─ Large rows sáng
  │    -> Kiểm tra dữ liệu dồn vào ít row, number of cells/versions, GC.
  └─ Latency vẫn thấp, không có Warnings
       -> Hoạt động cao có thể hoàn toàn bình thường.
~~~

**Đừng đồng nhất lượng bytes với số operations:** một số ít lần đọc row rất lớn có thể làm `Read bytes client` cao nhưng `Ops` không nổi bật. Ngược lại, rất nhiều thao tác point lookup nhỏ có thể làm `Ops` cao hơn tương đối.

## 4. Đọc heatmap theo mẫu hình

Mẫu màu giúp đề xuất giả thuyết, **không phải chẩn đoán tự động**. Hãy luôn đối chiếu metric hiện tại, khoảng thời gian, row-key prefix, logs và tải thực.

| Mẫu heatmap | Giả thuyết thường gặp | Kiểm tra tiếp |
| --- | --- | --- |
| **Dải ngang sáng kéo dài** tại một key range | Một tập row nhận nhiều đọc/ghi hoặc có row lớn | Read/Write pressure, Latency, Large rows; drill xuống key range |
| **Dải chéo sáng** chạy qua các key ranges theo thời gian | Ứng dụng scan tuần tự hoặc liên tục ghi/đọc các khóa tăng dần | Query pattern, thời điểm batch import, schema timestamp-leading |
| **Các dải sáng/tối lặp theo chu kỳ** | Batch job, báo cáo hoặc traffic theo giờ | Khớp lịch Cloud Scheduler/Dataflow/ETL và p99 cùng thời điểm |
| **Bất ngờ sáng tại một range** | Một job hoặc consumer mới bắt đầu truy cập range đó | Thời điểm deploy, workload logs, query filter/prefix |
| **Nhiều ranges cùng sáng theo một khoảng X** | Burst toàn hệ thống, tăng traffic hoặc vấn đề diện rộng | Cluster CPU, network, app profiles, client/server latency |
| **Mẫu hạt mịn phân bố đều** | Tải chia khá đều trên keyspace | Xác minh latency/SLO; không cần “sửa” chỉ vì một vài ô sáng |

### 4.1. Dải ngang: hot key range hay hoạt động hợp lệ?

Ví dụ bảng `student-progress` có các keys:

~~~text
course-001#student-0001
course-001#student-0002
course-001#student-0003
course-002#student-0001
...
~~~

Trong giờ phát hành khóa học mới, `course-001` nhận phần lớn reads để hiển thị danh sách học viên. Key Visualizer có thể hiện một dải ngang sáng tại prefix này.

**Trình tự kết luận:**

1. Mở `Ops` để xác định thời điểm/prefix hoạt động khác biệt.
2. Chuyển sang `Read pressure index`, `Latency` và `Read bytes client` đúng vùng đó.
3. Nếu pressure/latency vẫn tốt, workload có thể bình thường; theo dõi capacity và SLO thay vì thay schema ngay.
4. Nếu đọc nhiều dẫn tới p99 cao, thử **filter giảm bytes**, cache các kết quả đọc phổ biến hoặc thiết kế lại phân bố key/range. Không đưa dữ liệu giao dịch cần tính mới nhất vào cache không có TTL/invalidation.

### 4.2. Dải chéo: quét tuần tự có nhất thiết sai?

Một job sao lưu/tổng hợp đọc từng range trong thời gian dài có thể tạo đường chéo. Nếu job được lên lịch và CPU/latency vẫn dưới SLO, đây là **hành vi dự kiến**. Nếu đó là pattern từ writer ghi `timestamp#eventId` tăng tuần tự với **Write pressure** cao, có thể là **hotspot ghi**.

Phân biệt qua **metric, thời điểm chạy job, read/write mix và latency**. Chỉ nhìn hình dạng đường chéo không đủ để khẳng định cần thay row key.

### 4.3. Dải thẳng đứng: sự cố không gắn một prefix

Nếu nhiều key ranges tăng latency cùng một thời điểm:

- Xem toàn cluster CPU, khả năng cân bằng node và autoscaling đang thay đổi ra sao.
- Kiểm tra app profile routing: ứng dụng có chuyển toàn bộ request sang một cluster khác không?
- Kiểm tra client-side retries/deadlines, VPC/network và kết nối server.
- Kiểm tra hoạt động import/batch hoặc thay đổi code áp lên nhiều prefixes.

Key Visualizer chỉ phản ánh một phần các yếu tố hiệu năng. Không dùng nó thay thế Cloud Monitoring hoặc client trace.

## 5. Quy trình mở Key Visualizer và khoanh vùng sự cố

### 5.1. Trước khi mở: khóa đúng phạm vi

Ghi lại **project, Bigtable instance, cluster, table, app profile, thời điểm lỗi, SLO và quyền được cấp**. Một instance có nhiều clusters với routing khác nhau; so heatmap của cluster A với latency client chủ yếu đọc cluster B sẽ dễ dẫn tới chẩn đoán sai.

Người vận hành được phép dùng Console hoặc lệnh **chỉ đọc** sau để xác nhận resource (nếu phiên bản CLI hỗ trợ):

~~~bash
# Chỉ đọc. Chạy sau khi đã xác nhận project được phép.
gcloud config get-value project
gcloud bigtable instances list --project="YOUR_PROJECT_ID"

# Nếu lệnh/flag thay đổi ở phiên bản SDK, xem --help.
gcloud bigtable instances describe "YOUR_INSTANCE_ID" \
  --project="YOUR_PROJECT_ID"
~~~

Không in toàn bộ thông tin mạng/tên resource vào kênh công khai. Việc xem Key Visualizer bên dưới là **chỉ đọc**, không cần tạo bảng, viết dữ liệu hoặc nâng node count.

### 5.2. Các bước trực tiếp trong Google Cloud Console

1. Chọn **đúng project** rồi mở **Bigtable → Instances**.
2. Chọn **instance** cần điều tra; bên trái chọn **Key Visualizer**.
3. Chọn **table** và **cluster**, sau đó **Select**.
4. Chọn khoảng thời gian chứa sự cố bằng **time-range sliders**, rồi **Update**; Key Visualizer hiển thị những mốc scan sẵn có, không nhất thiết đúng từng giây bạn chọn.
5. Bắt đầu ở `Ops`. Ghi nhận prefix/range nổi bật, giờ bắt đầu/kết thúc và liệu mẫu có lặp lại.
6. Chuyển sang **Warnings**: `Read pressure index`, `Write pressure index`, `Large rows`. Nếu mục bị vô hiệu hóa, có thể không có cảnh báo trong loại đó ở khoảng đang xem.
7. So sánh **Read/Write CPU và bytes**, `Latency`/`Latency (max)`, rồi dùng **Multimetric** để nhìn các metric cùng lúc.
8. **Zoom/drill down** đúng vùng; dùng tooltip/pin và key hierarchy để đối chiếu prefix thực.
9. Ghi giả thuyết, mức ảnh hưởng tới p99, biện pháp dự kiến và bằng chứng trước/sau. Không chỉnh row-key schema chỉ từ một màu sáng.

**Lưu ý thời gian:** heatmap hiển thị khoảng dữ liệu được scan/đã tính toán; nó **không phải log realtime theo từng request**. Một bảng mới đạt ngưỡng 1 GB có thể chưa có scan trong khoảng tối đa khoảng một giờ. Khi đang xử lý sự cố tức thời, dùng Monitoring và logs trước.

### 5.3. Chế độ xem kết hợp

~~~mermaid
flowchart TD
    INC["Cảnh báo p99 / error rate tăng"] --> FIX["Chốt project, cluster,<br/>table, time window, SLO"]
    FIX --> OPS["Key Visualizer: Ops"]
    OPS --> WARN{"Warnings / Latency<br/>có bất thường?"}
    WARN -->|Có| DRILL["Zoom key range + tooltip;<br/>đọc Read/Write CPU & bytes"]
    WARN -->|Không| OTHER["Kiểm tra cluster CPU,<br/>client latency, network, quota"]
    DRILL --> CORR["So hot tablets, Monitoring,<br/>job/deploy timeline"]
    OTHER --> CORR
    CORR --> HYP["Chọn giả thuyết và<br/>thử thay đổi được phê duyệt"]
    HYP --> VERIFY["Đo trước/sau:<br/>p99, pressure, error, cost"]
~~~

### 5.4. Dùng quyền tối thiểu và bảo vệ thông tin key

- Cần các quyền xem Key Visualizer phù hợp như `bigtable.keyvisualizer.list` và `bigtable.keyvisualizer.get`, cộng quyền xem instance/table liên quan; **kiểm tra role hiện có** trước khi xin cấp mới.
- Các role như Bigtable Reader/User có thể kèm quyền **đọc dữ liệu** rộng hơn nhu cầu giám sát. Với môi trường nhạy cảm, cân nhắc **custom role** theo chính sách tổ chức thay vì cấp một role quá rộng.
- Row keys có thể chứa PII hoặc thông tin khách hàng nếu schema cũ đặt email/số điện thoại trong key. Khi đính kèm ảnh heatmap, **che prefixes, project/instance IDs** và chi tiết tenant nhạy cảm.
- Không thay IAM, route, autoscaling, GC hoặc schema trong bước **điều tra ban đầu**. Mọi thay đổi cần owner, kế hoạch quay lại và chỉ số thành công.

## 6. Đặt Key Visualizer cạnh các công cụ còn lại

| Công cụ | Góc nhìn | Dùng khi |
| --- | --- | --- |
| **Key Visualizer** | Hoạt động/pressure/latency/size theo **row-key range và thời gian**. | Tìm keyspace nóng, row quá lớn hoặc pattern theo giờ. |
| **Cloud Monitoring cluster charts** | CPU trung bình và **hottest node**, nodes, throughput, latency, autoscaling. | Xác định cluster quá tải hay một node bị nóng. |
| **Hot tablets** | Các tablets tiêu thụ CPU cao, gắn với key ranges. | Khoanh vùng hot tablets, đối chiếu với key prefixes. |
| **Client-side metrics** | End-to-end latency, application blocking, gRPC attempts/retries/deadlines. | Server ổn nhưng người dùng vẫn chậm. |
| **Cloud Logging/application traces** | Request path, job, batch, deploy, lỗi ứng dụng theo thời điểm. | Tìm tác nhân tạo burst hoặc truy vấn rộng. |
| **Bigtable Access patterns/System insights** | Loại truy vấn/mô hình tải và quan sát tổng hợp. | Muốn bổ sung bối cảnh cho Key Visualizer. |

Ví dụ **hottest-node CPU cao hơn nhiều so với CPU trung bình** cộng với `Write pressure index` tập trung vào một row range thường ủng hộ giả thuyết hotspot. Ngược lại, **tất cả nodes CPU rất cao** và nhiều ranges tăng cùng lúc thường đòi đánh giá capacity/tốc độ workload rộng hơn.

Lưu ý với **replicated Bigtable instances**: mỗi cluster có tính toán capacity, phục vụ đọc/ghi theo app profiles và replication behavior riêng. So cả cluster-specific latency/CPU và replication latency; Key Visualizer trên **một cluster** không phản ánh mọi request thực tế của các cluster khác.

## 7. Chọn biện pháp khắc phục theo nguyên nhân

### 7.1. Hot write range do row key tăng tuần tự

Một cấu trúc dễ gây hotspot:

~~~text
20261119T100001Z#student-001#event-aaa
20261119T100002Z#student-002#event-bbb
20261119T100003Z#student-003#event-ccc
~~~

Vì timestamp đứng đầu và tăng liên tục, hoạt động ghi có thể tập trung vào một đầu keyspace. Hai phương án để **benchmark trước khi migration**:

| Thiết kế | Khi nên cân nhắc | Chi phí đánh đổi |
| --- | --- | --- |
| `studentId#reverseTimestamp#eventId` | Nhiều students ghi độc lập; cần truy vấn events gần đây **theo student**. | Một student ghi quá nhiều vẫn có thể nóng; không tối ưu toàn bộ events mới nhất. |
| `shard#studentId#reverseTimestamp#eventId` | Một vài students rất nóng; cần phân phối writes trên nhiều shards. | Query theo student phải đọc nhiều shards rồi merge/sort; phức tạp migration và index logic. |
| `hash(eventId)#eventId` | Chủ yếu point lookup theo eventId, không scan thời gian. | Range query theo thời gian/user cần bảng/materialized view khác. |

**Reverse timestamp** giúp xếp sự kiện mới trước trong **mỗi prefix**, nhưng không tự tránh hotspot nếu chỉ có một prefix nhận mọi write. Tốt hơn phải kết hợp key có **độ phân tán cao** và đúng access pattern.

Ví dụ logic tạo **row key với 16 shards** (chỉ minh họa trong Python, không ghi Bigtable):

~~~python
import hashlib

def make_row_key(student_id: str, event_id: str, epoch_ms: int) -> bytes:
    if not (0 <= epoch_ms <= 9_999_999_999_999):
        raise ValueError("timestamp out of supported range")
    digest = hashlib.sha256(event_id.encode("utf-8")).digest()
    shard = int.from_bytes(digest[:4], "big") % 16
    reverse_ms = 9_999_999_999_999 - epoch_ms
    # Tránh email/PII trong khóa; student_id là opaque ID đã kiểm soát.
    return f"{shard:02d}#{student_id}#{reverse_ms:013d}#{event_id}".encode()
~~~

Hàm tạo prefix đều hơn **nếu event IDs có entropy đủ tốt**. Việc chia 16 buckets **không bảo đảm cân bằng** khi app tạo event IDs thiên lệch hoặc xử lý không đồng đều; phải thử tải/đo. Để đọc toàn bộ sự kiện của một học viên, cần đọc mỗi shard prefix của student rồi merge theo timestamp. Việc thêm shard **không tự động chuyển dữ liệu cũ** sang schema mới.

### 7.2. Hot read range do một nhóm dữ liệu quá phổ biến

Ví dụ 70% requests cùng đọc tiến độ của một lớp học. Khi `Read pressure index` và latency của prefix đó cùng cao:

1. Đo **số request đến cùng key/range** và kích thước dữ liệu trả về.
2. Giảm độ rộng của **row-range scans** và dùng **filters** phù hợp để không trả cột/versions không cần.
3. Cache dữ liệu đọc nhiều nhưng ít thay đổi (ví dụ metadata khóa học) bằng **Memorystore (Redis)** hoặc lớp cache khác, kèm TTL/invalidation và hạn chế dữ liệu nhạy cảm.
4. Nếu một row bị đọc quá nhiều, cân nhắc **tách nội dung** hoặc tạo các bản sao đọc theo patterns phù hợp, chấp nhận nhất quán và chi phí cập nhật thêm.
5. Nếu đồng thời có thiếu capacity diện rộng, điều chỉnh node/autoscaling theo kế hoạch — nhưng không dùng tăng node để bỏ qua hot row.

**Memorystore không phải nơi thay thế Bigtable làm nguồn dữ liệu chính trong mọi trường hợp**: cache có thể hết hạn, mất dữ liệu hoặc bị evict tùy cấu hình. Các dữ liệu tiến độ học tập quan trọng phải có nguồn bền vững và chiến lược invalidation rõ ràng.

### 7.3. Large rows: tránh tích quá nhiều cells/versions

Key Visualizer cảnh báo `Large rows` khi một row vượt **256 MB** hoặc range có trung bình trên **200 MB/row**. Bigtable khuyến nghị tránh row >256 MB vì có thể ảnh hưởng hiệu năng và khả năng đọc.

Ví dụ row `student-42` chứa **toàn bộ lịch sử tiến độ từ nhiều năm**, hàng triệu cell versions. Đọc một phần vẫn có thể phải xử lý row rất lớn. Các hướng thiết kế:

- Chia dữ liệu thành **nhiều rows theo ngày/tháng/khóa học**, nhưng vẫn giữ prefix giúp query đúng.
- Đặt **garbage collection policy** theo số versions/tuổi dữ liệu để hạn chế tích lũy; hiểu rằng GC không nhất thiết xóa ngay lập tức hoặc hoàn nguyên hết dung lượng trong vài giây.
- Tách dữ liệu lớn vào Cloud Storage, chỉ giữ metadata/index cần tra cứu trong Bigtable.
- Thử filters giảm bytes trả về nhưng nhớ rằng **filter không tự sửa row đã quá lớn**.

Không xoá nhiều dữ liệu production ngay khi thấy cảnh báo. Xác minh retention, backup, khả năng phục hồi và các consumer đang phụ thuộc dữ liệu cũ.

### 7.4. Ghi bị lặp hoặc quá thường xuyên

Một batch job có thể ghi lại cùng trạng thái dù giá trị không đổi, hoặc lặp toàn bộ write sau timeout. Biện pháp:

- Batch writes ở mức client thích hợp, giới hạn concurrency và áp retry có backoff.
- **Deduplicate** theo event/business key trước khi tạo mutation khi nghiệp vụ cho phép.
- Dùng idempotency cho side effects; tránh tạo thêm column qualifier/version mới vì retry không kiểm soát.
- Đo **write volume thực, retries, latency và conflicts**; không giả định batching luôn giảm số bytes cần lưu.

### 7.5. Khi nào có thể tăng nodes?

Nếu CPU của nhiều nodes cao, throughput liên tục vượt khả năng cluster và access pattern phân bố hợp lý, thêm nodes hoặc cấu hình autoscaling có thể cải thiện khả năng phục vụ. Nhưng với **hot single row/tablet** nhận tỷ lệ lớn tải, tăng tổng nodes có thể chỉ cải thiện hạn chế; cần sửa cách truy cập/row keys.

Biện pháp tăng nodes có **chi phí**, và autoscaling không bảo đảm có thể đáp ứng ngay traffic spike. Mọi thay đổi capacity cần đối chiếu SLO, quota, giới hạn sản phẩm và ngân sách.

## 8. Runbook 15–30 phút đầu của một sự cố latency

Runbook dưới đây **chỉ mô tả điều tra**. Các sửa đổi schema, số nodes hay cache phải qua change review.

| Bước | Hành động | Bằng chứng cần ghi |
| --- | --- | --- |
| 1 | Xác nhận **triệu chứng** ở application: p95/p99, deadline exceeded, số request lỗi. | Request ID/trace, khoảng thời gian, service/region. |
| 2 | Chọn đúng **project–instance–cluster–table** và app profile. | Cluster route, time window, baseline trước sự cố. |
| 3 | Xem **CPU trung bình và hottest node** trong Monitoring; xem hot tablets nếu cần. | Toàn cluster hay chỉ vài ranges/nodes nóng? |
| 4 | Trong Key Visualizer: `Ops` → Warnings → `Latency` → read/write CPU/bytes. | Key ranges, thời điểm, metric bất thường. |
| 5 | Ghép với **deploy, ETL jobs, query logs/client metrics** cùng mốc thời gian. | Ai tạo tải, read/write mix, payload/scan size. |
| 6 | Chọn **một giả thuyết chính** và biện pháp rủi ro thấp: giảm scan, cache, giảm batch overload. | Owner, approval, rollout/rollback và dự kiến tác động. |
| 7 | So kết quả sau thay đổi trong Monitoring và scan tiếp theo. | p99, error rate, pressure duration, bytes/ops, cost. |

**Một ví dụ kết luận hợp lý:** “10:00–10:30, `student-42#...` có `Read pressure index >100` và read p99 tăng; cùng lúc 80% request báo cáo đọc prefix này. Cần thử cache theo TTL và giảm scan, sau đó đo lại.” Không viết “Key Visualizer cho thấy Bigtable bị lỗi” khi chưa chứng minh mối liên hệ.

### 8.1. Khi Key Visualizer chưa có scan hoặc không hiển thị cảnh báo

| Hiện tượng | Giải thích có thể | Bước tiếp |
| --- | --- | --- |
| Không chọn được bảng | Dưới ngưỡng 1 GB **trên cluster** hoặc chưa đủ thời gian xử lý; quyền/phạm vi sai | Kiểm tra dung lượng/cluster/quyền, Monitoring; không nạp dữ liệu giả chỉ để có scan |
| `Warnings` bị vô hiệu hóa | Không có cảnh báo loại đó trong khoảng đang xem | Xem `Ops`, `Latency`, Monitoring và client errors |
| Mọi key đều tối hoặc đều sáng | Thang màu tương đối/brightness hoặc không có tương phản lớn | Đọc tooltip và giá trị tuyệt đối, đổi metric/brightness |
| “Key space not to scale” | Phân bố row keys không đủ để chia đẹp thành các buckets | Không coi đó là lỗi lưu trữ; kết hợp Monitoring/hot tablets |
| “Values per row are approximate” | Dữ liệu/table thay đổi nhanh khiến ước lượng có sai lệch | Đối chiếu metric khác và kỳ đo mới |
| Màu sáng nhưng không lỗi | Tải cao nhưng trong capacity | Xác minh SLO, không thay schema vô cớ |

Với sự cố **đang diễn ra**, không đợi Key Visualizer cập nhật mới bắt đầu xử lý; dùng Monitoring, client logs và khả năng quan sát node/tablet có độ trễ cập nhật phù hợp.

## 9. Lab quan sát chỉ đọc: điều tra một key range nóng

**Mục tiêu:** dùng một Bigtable table **đã tồn tại** để hoàn thành phiếu chẩn đoán Key Visualizer; **không** tạo instance, thay autoscaling, thêm dữ liệu hay xóa bảng. Nếu không có quyền hoặc table nhỏ hơn ngưỡng hiển thị, hoàn thành **lab giấy** ở mục 9.3.

### 9.1. Điều kiện và chuẩn bị

Cần được owner cho phép xem một **Bigtable instance, table và cluster**, có quyền đọc Key Visualizer/Monitoring phù hợp. Với môi trường production, chỉ quan sát; người học không được tự sửa cấu hình hoặc nạp traffic thử.

Trong phiếu thực hành, ghi:

~~~text
Project:        <được phê duyệt>
Instance:       <được phê duyệt>
Cluster:        <được phê duyệt>
Table:          <được phê duyệt>
App profile:    <nếu có>
Time window:    <thời gian sự cố hoặc khung đại diện>
Read/write SLO: <p95/p99 và error budget đã thống nhất>
~~~

Với table đủ điều kiện, Google Cloud Console → **Bigtable → Instances → chọn instance → Key Visualizer → chọn table/cluster**. Mở time-range slider bao phủ sự kiện muốn điều tra. Không tải xuống hay chia sẻ raw row keys nếu chúng chứa ID nhạy cảm.

### 9.2. Thu thập bằng chứng theo trình tự

| Bước trong Console | Câu hỏi phải trả lời | Ghi chú |
| --- | --- | --- |
| **Ops** | Range/prefix nào sáng rõ hơn và vào giờ nào? | Chỉ ghi prefix đã ẩn danh và cửa sổ thời gian. |
| **Read pressure** | Có cảnh báo ≥100 kéo dài ở đúng range không? | Nếu không có, ghi “không thấy cảnh báo”. |
| **Write pressure** | Có ghi nóng cục bộ không? | So với deploy/ETL timeline. |
| **Large rows** | Có row >256 MB hoặc range quá lớn? | Không truy vấn toàn row để xác nhận trên production. |
| **Latency** | Nơi có pressure cao có latency tăng cùng thời điểm? | So p95/p99 ứng dụng. |
| **Read/Write CPU, bytes** | Nghẽn chủ yếu bởi request count hay payload lớn? | Phân loại trước khi sửa schema. |
| **Monitoring/hot tablets** | Có node/tablet quá tải, hay cả cluster đang đầy? | Ghi CPU trung bình so hottest node. |

**Mẫu báo cáo điều tra ngắn:**

~~~text
Triệu chứng: p99 đọc tăng từ [baseline] lên [observed] tại [time].
Phạm vi: [instance/cluster/table]; request path [đã ẩn dữ liệu].
Key Visualizer: [metric] bất thường ở prefix [masked-prefix].
Đối chứng: [Monitoring/hot tablets/client logs] cùng thời điểm.
Giả thuyết: [hot read / hot write / large row / không liên quan keyspace].
Hành động đề xuất: [một thay đổi, owner, rollback plan].
Tiêu chí xác minh: p99 < [SLO], error rate < [SLO],
                   pressure cải thiện, chi phí không vượt budget.
~~~

Nếu không có pressure warning nhưng chỉ thấy Ops sáng, câu trả lời đúng có thể là **“chưa đủ bằng chứng về hotspot ảnh hưởng SLO”**, không phải buộc tìm một lỗi để sửa.

### 9.3. Lab giấy khi không có Bigtable đủ điều kiện

Xem bảng **số liệu giả định** dưới đây. Tất cả keys đã ẩn danh, các con số chỉ dùng để luyện phân tích, **không phải ảnh/metric thực từ Google Cloud**.

| Key range | Ops tương đối | Read pressure | Write pressure | Latency p99 tương đối | Large rows |
| --- | ---: | ---: | ---: | --- | --- |
| `00#student-*` | 35 | 12 | 22 | Thấp | Không |
| `01#student-*` | 420 | **125** | 34 | **Cao** | Không |
| `02#student-*` | 60 | 10 | 18 | Thấp | Không |
| `03#student-*` | 70 | 16 | **140** | **Cao** | Không |
| `04#student-*` | 8 | 7 | 9 | Thấp | **Có** |

**Yêu cầu:**

1. Range nào nghi vấn hot reads? — `01#student-*`, vì Read pressure ≥100 cùng latency cao.
2. Range nào nghi vấn hot writes? — `03#student-*`, vì Write pressure ≥100 cùng latency cao.
3. Range nào cần kiểm tra row size? — `04#student-*`, dù Ops thấp.
4. Có cần tăng nodes ngay không? — **Chưa đủ dữ liệu**; xem CPU theo nodes/tablets, request pattern và độ dài bất thường trước khi quyết định.
5. Vì sao không kết luận `00#student-*` có lỗi? — Ops cao/thấp là tương đối; pressure và latency không cho thấy vấn đề.

Với kết quả trên, đề xuất **ba thử nghiệm độc lập**: cache/filter cho range đọc nóng; giảm timestamp-leading/hot write cho range ghi nóng; chia row hoặc chỉnh retention với row quá lớn. Đo mỗi thay đổi so với baseline; không áp đồng thời nếu muốn biết nguyên nhân cải thiện.

## 10. Tình huống thiết kế và bài tập

### Tình huống A — Timestamp đứng đầu, p99 ghi tăng

Một pipeline Pub/Sub → Dataflow → Bigtable ghi `rowKey=YYYYMMDDHHmmss#eventId`. Có 6.000 sự kiện/s ở peak, CPU trung bình toàn cluster khoảng 40% nhưng hottest-node CPU gần giới hạn và Key Visualizer hiện dải chéo cùng Write pressure cao.

**Yêu cầu:** đưa ra chẩn đoán, phương án key và hai cách xác minh.

**Hướng giải:** nghi timestamp-leading hotspot. Thử key bắt đầu bằng ID có cardinality cao (user/device) nếu truy vấn theo ID, hoặc thêm shard prefix phân bố từ event ID khi cần. Xác minh bằng **Key Visualizer pressure/hot tablets** và **write p99/hottest-node CPU** trên workload representative. Phải lập migration/backfill và điều chỉnh query/read paths.

### Tình huống B — Một lớp học có lượt đọc đột biến

Nền tảng công bố kết quả thi, 80% yêu cầu GET đọc chung prefix `course-top-42#...`, độ trễ đọc tăng; writes bình thường.

**Yêu cầu:** có nên đổi mọi row keys sang UUID ngẫu nhiên không?

**Hướng giải:** không nên đổi toàn bảng theo phản xạ. Đo `Read pressure`, `Read bytes client` và row size; cân nhắc cache hợp lệ (ví dụ Memorystore cho metadata/điểm tổng hợp đã công bố), filter, tách row quá lớn hoặc các bản sao đọc có quản lý. UUID ngẫu nhiên cho tất cả rows có thể phá locality của query theo course.

### Tình huống C — Row lớn nhưng không nhiều request

Một row tích lũy các phiên bản trạng thái học tập nhiều năm, kích thước nén gần 300 MB. `Ops` không nổi bật nhưng `Large rows` xuất hiện, đôi khi đọc lỗi.

**Yêu cầu:** nêu hai biện pháp và rủi ro.

**Hướng giải:** chia lịch sử theo ngày/tháng/khóa học thành nhiều rows; đặt GC policy/retention theo yêu cầu, hoặc chuyển blob lớn sang Cloud Storage. Cần migration dữ liệu, đọc song song giai đoạn chuyển tiếp, backup và kiểm chứng không mất dữ liệu. Tăng node không làm một row đơn lẻ nhỏ lại.

### Tình huống D — Heatmap màu trắng nhưng SLO vẫn tốt

Một job phân tích chạy mỗi đêm, quét tuần tự một phần bảng, tạo dải chéo rất sáng. `Read/Write pressure` không báo lỗi, client p99 vẫn trong SLO.

**Yêu cầu:** đây có phải incident không và cần làm gì?

**Hướng giải:** không nhất thiết. Đối chiếu với lịch job, xác minh quota/cost/capacity và tác động tới workload khác. Có thể để nguyên, hoặc chuyển giờ/batch nhỏ hơn nếu chi phí/latency tăng trong tương lai. **Độ sáng tương đối không phải cảnh báo độc lập**.

### Tình huống E — Không thấy scan trong Console

Một Bigtable table mới có 200 MB dữ liệu/cluster và một đội muốn “test Key Visualizer” bằng cách tạo thêm 800 MB dữ liệu giả lên production.

**Yêu cầu:** có nên làm không? Nêu một hướng an toàn hơn.

**Hướng giải:** **không**. Công cụ cần ít nhất 1 GB mỗi cluster để có scan, nhưng nạp dữ liệu tùy tiện gây phí, rác dữ liệu và có thể ảnh hưởng hệ thống. Dùng Cloud Monitoring/hot tablets/client metrics hoặc lab giấy; nếu cần benchmark thật, lập project/instance thử nghiệm và ngân sách **được phê duyệt riêng**.

### Bài tập định lượng: hiểu mức lệch tải

Trong một phút, bảng có 2 triệu thao tác, 1,2 triệu thao tác dồn vào **một prefix**, còn 0,8 triệu phân bố trên nhiều prefixes.

1. Prefix nóng chiếm bao nhiêu phần trăm thao tác? **60%**.
2. Có thể từ `60% Ops` suy rằng latency chắc chắn cao không? **Không**; đối chiếu pressure, latency và khả năng phục vụ thực.
3. Nếu đó là 60% **reads**, một cache hợp lệ giảm 50% số request tới Bigtable **trong nhóm prefix nóng**, bao nhiêu request dự kiến bớt đi? **600.000/phút** trong mô hình giả định, chưa tính cache miss/invalidation.
4. Vì sao không dùng kết quả mô hình đó làm dự báo chi phí chính xác? — Vì cache hit thực, traffic thay đổi, request sizes và phương pháp tính giá/dung lượng khác nhau.

## 11. Checklist triển khai giám sát lâu dài

| Điều cần có | Tiêu chí chấp nhận |
| --- | --- |
| **Baseline** | SLO p95/p99 read/write, CPU, hottest node, throughput, chi phí được đo trước sự cố. |
| **Quy trình drill down** | On-call biết chọn project/instance/cluster/table, thời gian, metric và prefix. |
| **Nguồn đối chứng** | Có Monitoring, client metrics, hot tablets và deploy/job timeline. |
| **Cảnh báo phù hợp** | Alert theo p99/error/CPU thật; Key Visualizer dùng điều tra nguyên nhân. |
| **Schema review** | Kiểm tra row keys có timestamp/sequence prefix, hot entity hoặc row quá lớn không. |
| **Thay đổi an toàn** | Không tự sửa production chỉ từ heatmap; có owner, approval, benchmark và rollback. |
| **Bảo mật** | Chỉ cấp quyền cần xem; hình chụp heatmap/key prefix được redacted nếu chứa PII. |
| **TCO** | Xem cost of nodes, reads/writes, replication, cache, storage/GC và migration. |

### Tự kiểm tra

1. **Key Visualizer khác Monitoring cluster CPU ra sao?** — Nó phân tích hoạt động theo **key ranges**, còn Monitoring cho góc nhìn hạ tầng/latency rộng hơn.
2. **Trục X/Y của heatmap là gì?** — X: thời gian; Y: khoảng row keys.
3. **Một key bucket có bằng một tablet không?** — Không; bucket là đơn vị biểu diễn thống kê.
4. **Ops màu trắng có chắc đang lỗi không?** — Không; màu tương đối, cần xem Warnings và SLO.
5. **Read/Write pressure ≥100 kéo dài có ý nghĩa gì?** — Tín hiệu có khả năng hiệu năng kém ở row/range tương ứng, cần điều tra.
6. **Large rows cảnh báo ở mức nào?** — Row >256 MB hoặc key range trung bình >200 MB/row.
7. **Vì sao không có scan ở bảng nhỏ?** — Cần ít nhất 1 GB dữ liệu **mỗi cluster**, cộng thời gian xử lý.
8. **Timestamp đứng đầu row key có rủi ro gì?** — Ghi tăng tuần tự dồn vào một vùng khóa.
9. **Tăng nodes có tự xử lý mọi hotspot?** — Không; hot row/range có thể cần đổi schema/access.
10. **Điều gì phải làm trước khi chia ảnh heatmap?** — Kiểm tra/ẩn thông tin row-key prefix, project và dữ liệu nhạy cảm.

## 12. Tài liệu chính thức

- [Bigtable — Overview of Key Visualizer](https://cloud.google.com/bigtable/docs/keyvis-overview): heatmap, key ranges và giới hạn của công cụ.
- [Bigtable — Use Key Visualizer](https://cloud.google.com/bigtable/docs/keyvis-getting-started): điều kiện 1 GB/cluster, giao diện, time window và cách xem warnings.
- [Bigtable — Key Visualizer metrics](https://cloud.google.com/bigtable/docs/keyvis-metrics): Ops, pressure index, latency, size và key buckets.
- [Bigtable — Heatmap patterns](https://cloud.google.com/bigtable/docs/keyvis-patterns): dải ngang, truy cập chu kỳ, dải chéo và burst.
- [Bigtable — Explore heatmaps](https://cloud.google.com/bigtable/docs/keyvis-exploring-heatmaps): zoom, multimetric, tooltips và key format.
- [Bigtable — Diagnostic messages](https://cloud.google.com/bigtable/docs/keyvis-diagnostics): warnings, approximate values và các giới hạn scan.
- [Bigtable — Hot tablets](https://cloud.google.com/bigtable/docs/hot-tablets): khoanh vùng tablets/node CPU nóng.
- [Bigtable — Schema design best practices](https://cloud.google.com/bigtable/docs/schema-design): row-key distribution, time-based rows và giảm hotspots.
- [Bigtable — Monitoring](https://cloud.google.com/bigtable/docs/monitoring-instance): cluster/system insights và quan sát theo mức hạ tầng.
- [Bigtable — Troubleshoot latency](https://cloud.google.com/bigtable/docs/latency): phân biệt node overutilization, hotspots và client-side latency.
- [Bigtable — IAM roles and permissions](https://cloud.google.com/iam/docs/roles-permissions/bigtable): quyền xem dữ liệu/Key Visualizer theo least privilege.
- [Bigtable — Pricing](https://cloud.google.com/bigtable/pricing): đánh giá chi phí nodes, replication và storage theo thời điểm.

**Kết luận:** Key Visualizer giúp trả lời **“độ trễ và mức tải tập trung vào row key nào, trong khoảng thời gian nào?”**. Hãy đọc `Ops` để định vị, xác minh bằng **Read/Write pressure, Latency và Large rows**, rồi đối chiếu **Monitoring, hot tablets và client metrics**. Mục tiêu cuối không phải làm heatmap tối màu, mà là giữ **SLO, phân bố tải hợp lý, dữ liệu đúng và chi phí trong ngân sách**, với thay đổi schema/cache được đo lường và có thể hoàn nguyên.
