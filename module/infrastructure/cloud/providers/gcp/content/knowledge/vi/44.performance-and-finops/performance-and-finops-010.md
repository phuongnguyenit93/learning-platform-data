# Tối ưu đường đi mạng và chi phí truyền dữ liệu

Một ứng dụng có thể dùng ít CPU và bộ nhớ nhưng vẫn phát sinh chi phí Google Cloud đáng kể nếu dữ liệu liên tục đi qua ranh giới zone, region, Internet, load balancer hoặc kết nối hybrid. Ví dụ, API Java chạy ở một region đọc cơ sở dữ liệu ở region khác, tải object từ Cloud Storage rồi truyền nguyên file qua API về client. Nếu mỗi request lặp lại đường đi này, chi phí truyền dữ liệu và độ trễ có thể tăng theo lượng người dùng nhanh hơn cả chi phí compute.

**Tối ưu đường đi mạng (network path optimization)** là quá trình xác định luồng dữ liệu thực tế, hiểu nơi tính phí và giảm những lần truyền không cần thiết, trong khi vẫn bảo đảm độ tin cậy, khả năng phục hồi, bảo mật và trải nghiệm người dùng. **Network FinOps** bổ sung đo lường, phân bổ trách nhiệm chi phí, tính unit economics và xác minh hiệu quả sau thay đổi.

Bài học thuộc chương **Hiệu năng và FinOps** của module **CLOUD_PROVIDERS_GCP**. Trong hành trình từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, người học cần biết chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở đây, chúng ta kết hợp kiến trúc mạng Google Cloud với thực hành đo đạc, tối ưu và kiểm chứng có kiểm soát.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt ingress, egress, intra-zone, cross-zone, inter-region, Internet và hybrid data transfer.
- Giải thích vì sao cùng một lưu lượng có thể phát sinh nhiều SKU: truyền dữ liệu, NAT, load balancing, CDN, storage operations và các dịch vụ liên quan.
- Dùng Cloud Billing, BigQuery Billing export, Network Topology, VPC Flow Logs và metrics để tìm nguồn phát sinh chi phí.
- Đánh giá placement giữa API, database, worker, cache và Cloud Storage.
- Chọn giữa tối ưu đường đi nội bộ, Cloud CDN, kết nối riêng và Network Service Tiers.
- Thiết kế tối ưu ứng dụng Java/Spring bằng cache, batching, pagination, compression và object download trực tiếp.
- Ước tính tác động tới latency, RTO/RPO, HA, bảo mật và chi phí trước khi thay đổi.
- Lập runbook thử nghiệm, giám sát và rollback cho một thay đổi mạng.

## 1. Bắt đầu bằng luồng dữ liệu, không bắt đầu bằng bảng giá

Giả sử hệ thống thương mại điện tử có:

- Web và mobile client trên Internet.
- External Application Load Balancer.
- API Java trên Cloud Run hoặc GKE.
- Cloud SQL lưu thông tin đơn hàng.
- Cloud Storage lưu ảnh và tài liệu đính kèm.
- Worker xử lý sự kiện từ Pub/Sub.
- Hệ thống ERP vẫn ở data center.

Các kết nối mang dữ liệu khác nhau:

~~~mermaid
flowchart LR
  U[Người dùng trên Internet] --> LB[External Application Load Balancer]
  LB --> API[Orders API Java]
  API --> DB[(Cloud SQL)]
  API --> GCS[(Cloud Storage)]
  API --> W[Pub/Sub / workers]
  API --> NAT[Cloud NAT / external egress]
  NAT --> ERP[ERP / bên thứ ba]
  GCS --> CDN[Cloud CDN nếu phù hợp]
  CDN --> U
  API -. logs / traces .-> OBS[Cloud Logging / Monitoring / Trace]
~~~

Đây là sơ đồ logic, không khẳng định mọi đường đi đều qua Cloud NAT. Ví dụ, kết nối tới Cloud SQL qua private IP và request tới một số Google APIs có thể không sử dụng đường NAT ra Internet; việc dùng endpoint nào và tính phí ra sao cần kiểm tra theo dịch vụ cụ thể.

Để tìm cơ hội tối ưu, đặt năm câu hỏi cho **mỗi đường kết nối**:

1. Ai là nguồn gửi và ai là người nhận?
2. Hai đầu nằm trong cùng zone, cùng region, khác region, Internet hay on-premises?
3. Mỗi ngày hoặc mỗi tháng truyền bao nhiêu GiB và bao nhiêu request?
4. Luồng này có thực sự cần đi qua từng hop hiện tại không?
5. Thay đổi đường đi có ảnh hưởng đến bảo mật, độ trễ, SLA hoặc khả năng chịu lỗi không?

Một network diagram chỉ thể hiện cấu hình chưa đủ. Cần **dữ liệu lưu lượng thực tế**, gồm giờ cao điểm, batch cuối ngày, replication và đợt backup.

## 2. Phân biệt các loại truyền dữ liệu

Khái niệm quan trọng nhất: **ingress thường khác egress về cách tính phí**, và “nằm trong Google Cloud” không đồng nghĩa mọi lần truyền đều miễn phí.

| Hướng truyền | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Ingress vào Google Cloud | Client gửi request đến API | Phí ingress theo dịch vụ; lưu ý load balancer và processing |
| Intra-zone | VM A → VM B cùng zone | Điều kiện miễn phí của VM-to-VM dùng địa chỉ nội bộ/IPv6 và loại mạng |
| Cross-zone cùng region | VM ở zone A → VM zone B | Có thể tính data transfer out theo GiB |
| Inter-region | Backend ở region A → database ở region B | Phí theo cặp vùng và dịch vụ liên quan |
| Internet egress | API trả response ra người dùng | Giá theo khu vực, tier, volume và loại sản phẩm |
| Hybrid egress | Google Cloud → on-prem qua VPN/Interconnect | Phí của kết nối, traffic và hạ tầng liên quan |
| Cloud Storage data transfer | Bucket → service ở vị trí khác | Bảng giá riêng của Cloud Storage và các ngoại lệ |
| CDN delivery/cache fill | CDN cache → client; origin → cache | Cache lookup, cache data transfer out, cache fill và thành phần khác |

Theo bảng giá **VM-to-VM của Google Cloud**, cùng zone với địa chỉ nội bộ trong điều kiện được nêu có thể không bị tính phí data transfer; VM-to-VM giữa các zone trong cùng region và liên vùng được tính theo các quy tắc khác. Tuy nhiên, không suy từ quy tắc VM-to-VM rằng **mọi** dịch vụ GCP đều miễn phí cùng region. Cloud Run, Cloud SQL, Cloud Storage, load balancing và các sản phẩm khác có bảng giá riêng.

### Ingress không có nghĩa toàn bộ request miễn phí

Ngay cả khi inbound data transfer không bị tính tiền theo một SKU mạng nhất định, hệ thống có thể vẫn trả phí:

- External Application Load Balancer forwarding rules và data processing.
- Cloud Armor nếu bật.
- Cloud NAT hoặc Private Service Connect khi thực sự có lưu lượng thuộc phạm vi tính phí.
- CPU/memory và số request của Cloud Run/GKE.
- Logging, tracing hoặc các thao tác lưu trữ sinh ra từ request.

Tối ưu cần nhìn **tổng chi phí trên mỗi giao dịch**, không chỉ một dòng “Network Internet Egress”.

### GiB, GB và đơn vị trên hóa đơn

Bảng giá Google Cloud thường ghi rõ đơn vị (GiB, GB, request, giờ). Một GiB bằng 2^30 byte, khác một GB bằng 10^9 byte. Khi tính chi phí, dùng đúng đơn vị trong SKU/Cloud Billing export, không trộn số “GB” do công cụ giám sát hiển thị với “GiB” trên bảng giá.

## 3. Mô hình hóa đường đi và chi phí theo từng hop

Trong FinOps, một đường request có thể phát sinh chi phí ở nhiều điểm. Ví dụ:

~~~mermaid
flowchart TD
  A[Browser tải 8 MB ảnh] --> B[Global external LB]
  B --> C{Có CDN cache hit?}
  C -->|Có| D[Serve từ edge cache]
  C -->|Không| E[Cloud Storage / backend origin]
  E --> F[Cache fill]
  F --> D
  D --> G[Internet client]
~~~

Nếu CDN cache hit, origin không phải trả lại toàn bộ nội dung từ lần truy cập đó. Nhưng không được kết luận “CDN miễn phí” vì có thể có **cache lookup**, **cache data transfer out**, **cache fill** khi miss và các khoản load balancing/storage operation tương ứng.

Trong Cloud CDN, một response cacheable phải đáp ứng quy tắc caching và HTTP headers. Nội dung có đặc tính cá nhân hóa hoặc chứa thông tin nhạy cảm cần thiết kế cache key và access control cẩn thận, hoặc không cache.

### Công thức chi phí tổng quát

Một ước tính sử dụng biểu thức:

~~~text
Network-related monthly cost
  = sum(data transfer GiB by route x applicable SKU price)
  + NAT gateway hours + NAT processed traffic + NAT IP hours
  + load balancer fixed and processing charges
  + CDN cache lookup + cache fill + cache data transfer out
  + VPN/Interconnect/PSC-related charges where applicable
  + applicable storage and service operations
  - discounts and credits allocated to those usage lines
~~~

Đây là **khung phân loại**, không phải một công thức kế toán được phép cộng mọi thành phần một cách mù quáng. Một số cơ chế tính phí thay thế một khoản khác; ví dụ với Cloud CDN, cacheable content có cấu trúc giá riêng. Luôn đối chiếu **actual SKU** để không đếm cùng lưu lượng hai lần.

### Bảng lưu lượng cần lập

| Source | Destination | Region / zone | Traffic | GiB/tháng | Latency p95 | Owner | Cost hypothesis |
|---|---|---|---|---:|---:|---|---|
| orders-api | Cloud SQL | Cùng region | JDBC | Chưa đo | Chưa đo | backend | Ít egress nếu placement đúng |
| orders-api | Cloud Storage | Khác region | Object reads | Chưa đo | Chưa đo | media | Inter-location transfer |
| worker | warehouse | Khác region | Batch ETL | Chưa đo | Chưa đo | data | Inter-region traffic |
| browser | backend/CDN | Internet | Download file | Chưa đo | Chưa đo | frontend | Internet/CDN egress |
| orders-api | ERP | Hybrid | HTTPS | Chưa đo | Chưa đo | integration | VPN/Interconnect + transfer |

Không điền số giả vào bảng production. Đặt “chưa đo” và giao cho owner thu thập trước khi ra quyết định.

## 4. Đo hiện trạng bằng Cloud Billing

**Cloud Billing Reports** là điểm khởi đầu để xem chi phí theo service, project, SKU, location, label và khoảng thời gian. Với nhiều project hoặc workload, nên bật **Cloud Billing export to BigQuery** để phân tích chi tiết và lặp lại được.

### Các bước thực hiện

1. Chọn billing account đúng với project đang nghiên cứu.
2. Xem chi phí 30–90 ngày và kỳ cao điểm nếu có.
3. Nhóm theo service hoặc SKU liên quan data transfer, NAT, load balancing, Cloud CDN và connectivity.
4. Lọc theo project, location và các nhãn hiện có.
5. Đối chiếu tỷ trọng chi phí với số lượng request, dữ liệu tải và các sự kiện phát hành.
6. Bật Billing export nếu cần truy vấn theo ngày, dự án, SKU hoặc phân bổ theo owner.
7. Tạo baseline và gắn ngày bắt đầu trước khi thực hiện thay đổi.

**Không đo riêng tổng số tiền:** một workload tăng traffic gấp đôi nhưng chi phí trên mỗi request giảm vẫn có thể là một cải thiện FinOps. Hãy xem cả **absolute cost** và **unit cost**.

### Ví dụ SQL cho Billing export

Giả sử đã bật **Standard usage cost export** và bảng có schema chuẩn. Thay project, dataset, tên bảng và ngày; sau đó điều chỉnh bộ lọc SKU theo **tên thực tế trong account của bạn**:

~~~sql
SELECT
  DATE(usage_start_time) AS usage_date,
  project.id AS project_id,
  service.description AS service_name,
  sku.description AS sku_name,
  SUM(cost) AS gross_cost,
  SUM(
    COALESCE(
      (SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit),
      0
    )
  ) AS credits,
  SUM(
    cost +
    COALESCE(
      (SELECT SUM(credit.amount) FROM UNNEST(credits) AS credit),
      0
    )
  ) AS net_cost
FROM
  `BILLING_PROJECT.BILLING_DATASET.gcp_billing_export_v1_ACCOUNT_ID`
WHERE
  usage_start_time >= TIMESTAMP('2026-10-01')
  AND usage_start_time < TIMESTAMP('2026-11-01')
  AND (
    LOWER(sku.description) LIKE '%data transfer%'
    OR LOWER(sku.description) LIKE '%egress%'
    OR LOWER(sku.description) LIKE '%nat%'
    OR LOWER(sku.description) LIKE '%load balancing%'
    OR LOWER(sku.description) LIKE '%cdn%'
  )
GROUP BY 1, 2, 3, 4
ORDER BY net_cost DESC;
~~~

Lưu ý: tên SKU có thể dùng nhiều thuật ngữ khác nhau và có thể thay đổi theo thời gian. Bộ lọc trên là **truy vấn khám phá**, không thể khẳng định thu đủ mọi chi phí mạng. Với báo cáo tài chính cuối cùng, xây danh sách SKU theo nguồn dữ liệu thực tế, xét credits, adjustments, taxes và cách tổ chức phân bổ.

Billing export cũng không nhất thiết có cùng mức chi tiết tài nguyên cho mọi sản phẩm. Detailed export cung cấp thêm dữ liệu resource-level khi có; dữ liệu cost allocation GKE có thể cần bật riêng. Lịch cập nhật export có độ trễ, vì vậy không dùng để theo dõi tức thời một incident.

## 5. Đo đường đi mạng bằng Network Intelligence Center

Google Cloud **Network Intelligence Center** cung cấp những công cụ giúp đi từ cấu hình mạng sang bằng chứng:

| Công cụ | Dùng để làm gì? | Không nên suy diễn |
|---|---|---|
| Network Topology | Xem tài nguyên và kết nối, egress giữa zone/region, Internet, hybrid | Không hiển thị mọi traffic ứng dụng hoặc mọi luồng không phát sinh trong kỳ |
| Connectivity Tests | Phân tích đường forward theo cấu hình, kiểm tra reachability và một số trường hợp live dataplane | Không đảm bảo hiệu năng production hoặc toàn bộ backend |
| Performance Dashboard | Xem packet loss/latency giữa các zone hoặc vùng hỗ trợ | Không thay p95 latency nghiệp vụ |
| Flow Analyzer / VPC Flow Logs | Phân tích thông tin flows nguồn–đích, cổng, bytes | Không tự giải thích ý nghĩa nghiệp vụ hoặc mọi kết nối |
| Network Analyzer | Phát hiện một số vấn đề cấu hình, routing và service networking | Không phải công cụ tính hóa đơn cuối cùng |

### Network Topology

Mở Network Intelligence Center > Network Topology. Lọc theo:

- Traffic type: **cross-zonal**, **to the internet**, **hybrid**.
- Project và các resource có high egress.
- Khoảng thời gian liên quan với thời điểm chi phí tăng.
- VM/instance group hoặc workload GKE (nếu có tính năng phù hợp).

Theo tài liệu, Network Topology có thể hiển thị các insight **High egress instances** và **High egress instance groups**, cùng những metric trung bình throughput, packet loss và latency theo phạm vi được hỗ trợ. Dữ liệu topology dựa vào kết nối đã thực sự xảy ra, không phải mọi phụ thuộc được khai báo.

Ví dụ, nếu API và Redis nằm khác zone, chart cross-zone egress có thể cho thấy lưu lượng cao. Trước khi đổi placement, xác nhận đây thực sự là luồng cache lớn bằng metric/flow logs hoặc công cụ theo dõi ứng dụng.

### Connectivity Tests

Dùng Connectivity Tests để kiểm tra đường đi trước và sau thay đổi VPC, route, firewall, private endpoint hoặc load balancer. Một số scenario hỗ trợ live dataplane test, nhưng kết quả một lần test không thay thế benchmark tải thực, vì ECMP và load balancer có thể chọn các backend khác nhau.

### VPC Flow Logs / Flow Analyzer

Flow Logs hữu ích để xác định source/destination IP, port, protocol, volume và thời điểm traffic. Tuy nhiên log có thể được sampling/aggregation, phát sinh chi phí Logging và không luôn giải thích app-level request. Khi thu thập, ghi lại cấu hình sampling và khoảng thời gian, không coi raw log bytes bằng đúng tổng GiB được tính phí.

Dùng label, resource metadata, application catalog và ownership để ánh xạ flow thành workload; không tự khẳng định một flow tới port 5432 chắc chắn là giao dịch PostgreSQL của một ứng dụng cụ thể.

## 6. Tối ưu placement: đưa các thành phần giao tiếp nhiều lại gần nhau

Một trong những cải thiện bền vững nhất là **giảm traffic qua ranh giới tính phí và độ trễ**.

### API và database

Nếu Java API ở `asia-southeast1` nhưng database đặt ở region khác, mỗi query/response có thể thêm RTT và phí transfer. Với ứng dụng OLTP gọi nhiều truy vấn nhỏ, độ trễ tăng còn khiến thread và connection pool chiếm tài nguyên lâu hơn.

Các hướng xem xét:

- Đặt API và database **cùng region** khi yêu cầu sản phẩm, data residency và DR cho phép.
- Dùng private connectivity và endpoint được hỗ trợ.
- Tránh mô hình microservice liên tục gọi database ở khu vực xa khi có thể dùng cache, data replica hoặc service-local data.
- Đo transaction latency sau thay đổi; đừng chỉ đo ping.
- Xem cross-zone behavior trong HA: database HA và GKE regional cluster có thể tạo traffic nội vùng giữa các zone, vẫn cần xem pricing của sản phẩm.

**Không dồn tất cả workload vào một zone chỉ để tránh cross-zone charges.** Làm vậy có thể phá hủy mục tiêu high availability khi một zone gặp sự cố. Chi phí tối ưu phải được so với RTO/RPO, SLO và tổn thất downtime.

### Data gravity và dịch vụ phân tích

Data gravity mô tả xu hướng compute nên nằm gần dữ liệu lớn để tránh copy dữ liệu nhiều lần. Nếu worker xử lý ảnh tải dữ liệu từ bucket ở region xa:

1. Đo object bytes đọc mỗi ngày và số lần đọc lại.
2. Xem bucket location và vị trí worker.
3. Xem có thể đặt worker gần dữ liệu hoặc thay đổi data pipeline không.
4. Nếu cần replication đa vùng, tính thêm phí lưu trữ, sao chép và consistency.
5. Chọn phương án dựa trên data residency và recovery requirements.

Với Cloud Storage, **region không nhất thiết được coi là cùng một location với multi-region bao trùm region đó** trong quy tắc tính data transfer. Cần tra bảng pricing theo chính xác bucket location và service consumer.

### Đặt cache hoặc replica gần consumer

Cache cục bộ hoặc regional cache có thể cắt số lần đọc database hoặc object ở region khác. Nhưng cache cần:

- TTL phù hợp.
- Quy tắc invalidation hoặc event-driven refresh.
- Kiểm soát dữ liệu nhạy cảm.
- Giám sát hit rate, stale data và memory.
- Chi phí vận hành bản thân cache.

Đối với data replica, cần hiểu replication lag và read-after-write consistency. Không dùng eventual consistency cho nghiệp vụ bắt buộc đọc dữ liệu mới ghi nếu chưa có cơ chế đảm bảo.

## 7. Kiến trúc đa zone và đa region: tối ưu có ràng buộc độ tin cậy

Một ứng dụng production thường trải trên nhiều zone/region để phục vụ khả dụng và disaster recovery. Phí data transfer là một phần **chi phí của khả năng phục hồi**, không phải mặc định là lãng phí.

| Mục tiêu | Lựa chọn | Trade-off |
|---|---|---|
| Chịu lỗi zone | Regional GKE cluster, HA database, multi-zone backend | Cross-zone traffic và replication |
| Chịu lỗi region | Multi-region deployment/replication | Inter-region transfer, storage và vận hành |
| Latency người dùng toàn cầu | Frontend tại nhiều region hoặc CDN | Quản lý dữ liệu, cache, routing phức tạp |
| Đơn giản hóa vận hành | Ít region hơn khi SLO cho phép | Blast radius lớn hơn |
| Giảm data gravity | Đặt jobs cạnh nguồn dữ liệu | Có thể tăng latency phục vụ các bên tiêu thụ ở xa |

### Đặt một ràng buộc rõ ràng

Ví dụ hệ thống có SLO 99,95%, RTO 15 phút và RPO 5 phút. Không tự đề xuất bỏ multi-zone database replication chỉ vì chi phí egress. Thay vào đó, tối ưu **lưu lượng nghiệp vụ không cần thiết** (polling, duplicate batch, payload quá lớn) trước; sau đó đánh giá những lựa chọn HA khác có giữ được RTO/RPO hay không.

### GKE và pod placement

Trên GKE, pod-to-pod traffic có thể chạy giữa node ở nhiều zone. Dùng topology spread constraints, affinity hoặc placement-aware design để xem xét locality của các component nói chuyện nhiều với nhau. Nhưng:

- Không phá vỡ phân bố replica cần cho HA.
- Tránh hardcode zone gây khó autoscaling hoặc phục hồi node.
- Theo dõi cross-zone flow và chính sách routing/Service.
- Tách các luồng dữ liệu khối lớn khỏi đường giao dịch đồng bộ khi có thể.

## 8. Cloud CDN: giảm lượt quay về origin, không chỉ giảm latency

Cloud CDN thích hợp với nội dung được nhiều người dùng tải lại như ảnh công khai, static assets, JavaScript bundle, CSS, tài liệu không cá nhân hóa hoặc một số API response cacheable đã được thiết kế rõ ràng.

### Khi nào CDN hiệu quả?

Ví dụ 1 triệu lượt tải cùng một ảnh trong tháng. Nếu mọi request đều tới origin, origin phải xử lý và truyền ảnh mỗi lần. Nếu tỷ lệ cache hit cao, CDN có thể trả nhiều request tại edge, giảm origin load và cải thiện latency người dùng.

Các chỉ số cần đo:

- **Hit ratio** theo request và theo bytes.
- Cache fill bytes.
- Cache data transfer out.
- Cache lookup requests.
- Origin traffic và CPU.
- Latency p50/p95 tại client.
- Tỷ lệ invalidation/revalidation.

### Các chế độ cache

Cloud CDN có các cache mode như:

- `CACHE_ALL_STATIC`: mặc định phù hợp nội dung tĩnh có thể cache.
- `USE_ORIGIN_HEADERS`: tuân theo chỉ dẫn cache hợp lệ từ origin.
- `FORCE_CACHE_ALL`: có thể ép cache content thành công bất chấp chỉ thị private/no-store ở origin; **không dùng cho dữ liệu cá nhân, trả tiền hoặc có yêu cầu phân quyền**.

Sử dụng các header HTTP như `Cache-Control`, `CDN-Cache-Control`, `ETag` và `Last-Modified` khi phù hợp. Thiết kế cache key cho hostname, protocol, query string, header hoặc cookie thật sự ảnh hưởng nội dung.

### Response Java minh họa

Với Spring Boot, asset công khai có version trong URL có thể trả cache directive:

~~~java
@GetMapping("/public/assets/{hash}/{fileName}")
public ResponseEntity<Resource> publicAsset(
        @PathVariable String hash,
        @PathVariable String fileName) {
    Resource body = findApprovedPublicAsset(hash, fileName);

    return ResponseEntity.ok()
        .cacheControl(
            CacheControl.maxAge(Duration.ofDays(30))
                .cachePublic()
                .immutable()
        )
        .body(body);
}
~~~

Đây là ví dụ ý tưởng, không phải controller có thể build độc lập: cần imports, implementation `findApprovedPublicAsset`, validation chống path traversal và quyền truy cập phù hợp. Chỉ dùng cache dài khi URL bất biến theo content hash; việc đổi nội dung cùng URL có thể khiến client nhận dữ liệu cũ.

Với response chứa thông tin đơn hàng, token hoặc hồ sơ cá nhân, thường cần `Cache-Control: private, no-store` tùy chính sách, **không ép CDN cache**.

### Kiểm tra chi phí CDN

CDN có cache lookup, cache data transfer out và cache fill; cache miss có thể còn chịu processing/operation charges theo loại origin. Vì vậy:

~~~text
So sánh:
  Phương án A = origin egress + origin compute/operations + LB processing
  Phương án B = CDN egress + cache fill + lookup + applicable LB/storage charges
               + origin compute remaining on cache misses
~~~

Giá trị nên được lấy từ bảng giá hiện hành và billing SKU thực tế, không sử dụng một mức giá CDN “cố định” cho mọi khu vực.

## 9. Network Service Tiers: Premium hay Standard?

**Premium Tier** và **Standard Tier** là lựa chọn mạng cho các dịch vụ internet-facing được hỗ trợ; không phải công tắc biến mọi lưu lượng private VPC thành một tier rẻ hơn.

| Yếu tố | Premium Tier | Standard Tier |
|---|---|---|
| Mục tiêu | Tối ưu hiệu năng toàn cầu | Tối ưu chi phí cho ứng dụng Internet theo region |
| Đường đi | Tận dụng backbone Google đến gần người dùng | Có thể dùng ISP/transit networks nhiều hơn |
| Dịch vụ global | Hỗ trợ global load balancing/CDN | Có giới hạn, không hỗ trợ Cloud CDN |
| Backend multi-region | Phù hợp kiến trúc global | Thường cần thiết kế theo region |
| Chi phí Internet egress | Theo bảng Premium | Theo bảng Standard |
| Mạng nội bộ VPC | Mạng private vẫn dùng backbone Google | Standard không áp dụng cho private VPC traffic |

Nếu ứng dụng phục vụ người dùng quốc tế và cần global external Application Load Balancer hoặc CDN, Standard Tier không phải lựa chọn thay thế tương đương. Khi cân nhắc Standard:

1. Xác nhận loại load balancer/IP/backend được hỗ trợ.
2. Kiểm tra SLA, geography và yêu cầu độ trễ.
3. Kiểm tra tính sẵn sàng trong region và giá theo destination.
4. Benchmark p95 latency, packet loss và availability bằng traffic đại diện.
5. Chuyển hướng dần có rollback, không chỉ đổi tier trong một outage.

**Không dùng thay đổi tier làm cách cứu một outage đang diễn ra.** Theo tài liệu Network Service Tiers, chuyển traffic từ Standard sang Premium trong một outage Standard có hạn chế; chọn tier phải là quyết định kiến trúc có kế hoạch.

## 10. Cloud NAT và đường truy cập Google APIs

### Cloud NAT không phải đường ra miễn phí

Public Cloud NAT giúp tài nguyên không có external IP tạo kết nối outbound theo phạm vi hỗ trợ. Đây là lựa chọn bảo mật và vận hành, nhưng chi phí thường gồm:

- Phí theo giờ của NAT gateway.
- Phí xử lý traffic qua NAT (theo GiB).
- Phí địa chỉ IP dùng bởi gateway.
- **Phí data transfer out** của traffic rời mạng, nếu áp dụng.

Nếu workload tạo nhiều luồng ra Internet, Cloud NAT có thể tăng chi phí so với chỉ xem egress SKU. Tối ưu:

- Tìm top talkers bằng NAT metrics/logs và flow logs.
- Dùng cache/batching để giảm request ra ngoài.
- Đưa luồng gọi Google APIs vào đường private phù hợp khi hỗ trợ.
- Kiểm tra tỷ lệ lỗi NAT, port allocation và số lượng external IP.
- Không xóa NAT gateway nếu workload vẫn cần truy cập một API bên thứ ba.

### Private Google Access

**Private Google Access** cho phép VM chỉ có internal IP truy cập các Google APIs/services đủ điều kiện. Tính năng được bật theo **subnet**, với routing/DNS phù hợp.

Nó không đồng nghĩa:

- Mọi API của mọi nhà cung cấp đều có thể truy cập.
- Mọi data transfer tới Google APIs đều miễn phí.
- Private API connectivity luôn có cùng semantics với Internet routing.
- Một subnet có Private Google Access không cần firewall/DNS/routing kiểm tra.

Nếu sử dụng `private.googleapis.com` hoặc `restricted.googleapis.com`, cần cấu hình DNS và routes đúng; `restricted.googleapis.com` có phạm vi hỗ trợ khác và được dùng trong những thiết kế có VPC Service Controls.

### Private Service Connect và private services access

Private Service Connect (PSC) dùng endpoint/backend hoặc service attachment tùy kịch bản; private services access là cơ chế khác để kết nối đến các managed services qua VPC peering. Không dùng các thuật ngữ này thay thế nhau. Chúng có thể mang **phí endpoint/data processing/service riêng** theo cấu hình.

Lựa chọn một đường private cần dựa vào **supported service**, security boundary, region, DNS, network and billing, không chỉ suy rằng “private” luôn rẻ hơn “public”.

### Cloud Storage và Google APIs

Đối với VM cần đọc Cloud Storage, private API access phù hợp có thể tránh việc sử dụng NAT cho chính đường truy cập API. Tuy vậy, data transfer từ bucket khác location và storage operation charges vẫn có thể áp dụng. Luôn phân biệt **cách kết nối** với **đơn giá dữ liệu của dịch vụ**.

## 11. Hybrid networking: Cloud VPN, Cloud Interconnect và on-premises

Khi một phần hệ thống vẫn chạy on-premises, dữ liệu có thể đi qua Cloud VPN hoặc Cloud Interconnect. Chi phí không chỉ là data transfer:

- Phí vận hành VPN tunnel hoặc Interconnect connection/attachment.
- Phí data transfer qua kết nối tương ứng.
- Phí hạ tầng/port/cross-connect của đơn vị cung cấp, nếu có.
- Chi phí routing, NAT, thiết bị mạng và vận hành.
- Chi phí dữ liệu trùng lặp giữa hai địa điểm.

### Tình huống phổ biến

Ứng dụng chuyển lên GKE ở Google Cloud, nhưng database vẫn trong data center. Một request có thể thực hiện 20 query qua VPN. Mỗi query thêm RTT và data transfer. Nếu thường xuyên gọi hàng nghìn request/giây, độ trễ tổng thể lớn và chi phí traffic có thể không còn hợp lý.

Giải pháp có thể là:

- Chuyển app và database trong cùng migration wave khi khả thi.
- Giảm số round-trip bằng query batching hoặc thay đổi API.
- Đặt cache gần app cho dữ liệu read-mostly.
- Định nghĩa rõ thời gian hybrid transition và ngày loại bỏ luồng tạm.
- Chọn VPN/Interconnect theo băng thông, tính sẵn sàng và security, không chỉ giá.
- Đo bytes truyền liên tục và replication traffic.

Giảm lưu lượng không được đánh đổi tính toàn vẹn giao dịch hoặc RPO. Nếu dùng cache/dữ liệu sao chép, phải kiểm chứng stale data và cơ chế consistency.

## 12. Tối ưu ở tầng ứng dụng Java và API

Kiến trúc mạng tốt sẽ ít hiệu quả nếu ứng dụng phát sinh nhiều request hoặc payload hơn cần thiết.

### 12.1 Pagination và chỉ trả trường cần dùng

Thay vì trả 100.000 bản ghi trong một response, dùng pagination, giới hạn page size và chỉ trả những field client cần. Phân biệt server-side filtering với fetch-all rồi lọc ở client.

~~~http
GET /v1/orders?limit=50&cursor=NEXT_PAGE_TOKEN
Accept: application/json
~~~

Các cursor phải có tính ổn định và chống truy cập trái phép. Không dùng offset quá lớn cho dữ liệu biến động mạnh khi cursor-based pagination phù hợp hơn.

### 12.2 HTTP compression

Gzip/Brotli có thể giảm bytes với JSON, HTML và dữ liệu text. Nhưng:

- File JPEG/PNG/MP4/ZIP vốn đã nén, thường ít lợi ích khi nén lại.
- Compression tăng CPU, có thể ảnh hưởng latency với payload nhỏ.
- Không bật nén tùy tiện cho dữ liệu nhạy cảm trong các tình huống dễ phát sinh compression side channel.
- Cần kiểm tra proxy/load balancer, CDN và client hỗ trợ nén.

Đo **response size thực tế trên wire**, CPU, latency p95 và error rate trước/sau.

### 12.3 Batching

Nếu Java worker gửi từng event nhỏ qua HTTP tới dịch vụ ở region khác, có thể batch theo kích thước hoặc thời gian phù hợp. Cần giới hạn:

- Maximum batch size.
- Flush interval.
- Timeout và retry with backoff.
- Idempotency và deduplication.
- Queue memory/backpressure.
- Lỗi một phần trong batch.

Batching có thể giảm overhead per-request và kết nối, nhưng không phải lúc nào cũng giảm tổng payload bytes; nó có thể tăng latency nếu flush chờ quá lâu.

### 12.4 Connection reuse và pooling

HTTP keep-alive/HTTP/2 và JDBC connection pooling giảm handshake và setup overhead. Tuy nhiên:

- Pool quá lớn có thể làm cạn kết nối Cloud SQL.
- Retry thiếu jitter có thể khuếch đại traffic và chi phí.
- Long-lived connections cần health checks và idle timeout đúng.
- Connection reuse không tự giảm dung lượng response.

### 12.5 Cache có chủ đích

Cache có thể ở client, CDN, regional Redis/Memorystore hoặc application process. Mỗi tầng có:

- Hit rate và TTL.
- Invalidation policy.
- Consistency requirement.
- Memory footprint và chi phí.
- Security boundary.

Đo hiệu quả bằng **origin bytes averted** và **latency improvement**, không chỉ tỷ lệ hit request.

## 13. Tránh biến API Java thành proxy tải file khối lớn

Một anti-pattern thường gặp:

~~~mermaid
flowchart LR
  U[Browser] --> API[Java API]
  API --> GCS[(Cloud Storage object)]
  GCS --> API
  API --> U
~~~

API đọc toàn bộ ảnh/video từ Cloud Storage rồi trả về client. Cách này có thể làm:

- Tăng CPU/memory hoặc request duration của API.
- Tăng băng thông qua API và egress phù hợp.
- Tạo thêm hop và latency.
- Khó hưởng lợi từ edge cache.

### Phương án trực tiếp có kiểm soát

~~~mermaid
flowchart LR
  U[Browser] --> AUTH[Java API: xác thực và cấp quyền]
  AUTH --> URL[Signed URL / truy cập được kiểm soát]
  URL --> GCS[(Cloud Storage)]
  GCS --> U
~~~

Với dữ liệu **được phép** truy cập trực tiếp, API có thể cấp signed URL thời hạn ngắn hoặc dùng luồng frontend được hỗ trợ, sau đó client tải từ Cloud Storage mà không bắt API phải streaming mọi byte.

Cần cân nhắc:

- Signed URL là bearer capability: người có URL trong thời hạn có thể truy cập đối tượng theo scope URL.
- Không ghi signed URL đầy đủ vào log hoặc analytics.
- Đặt expiry ngắn, method và object cụ thể.
- Kiểm soát MIME type, content disposition, CORS và chính sách caching.
- Với nội dung công khai có nhiều lượt truy cập, đánh giá Cloud CDN/Cloud Storage backend bucket.
- Với dữ liệu cá nhân hóa, kiểm tra quyền và hạn chế chia sẻ trước khi chọn CDN.

**Trực tiếp không phải tự động miễn phí.** Cloud Storage có bảng giá data transfer, operation và storage riêng; lợi ích có thể đến từ việc giảm backend proxy load và hop trung gian. Đo tổng chi phí trước/sau.

## 14. Tạo mô hình FinOps theo unit economics

Chỉ số trung bình theo tháng có thể che hiệu quả kinh doanh. Hãy chọn đơn vị phù hợp:

- Chi phí network / 1.000 API requests.
- GiB Internet egress / 1.000 active users.
- Chi phí CDN / 1.000 file downloads.
- Chi phí inter-region replication / GiB dữ liệu được sao chép.
- Chi phí network / một đơn hàng thành công.
- Error rate và latency tương ứng mỗi unit.

Ví dụ **toàn bộ số liệu sau là giả định**, không phải bảng giá Google Cloud:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| Orders thành công/tháng | 800.000 | 800.000 |
| Data transfer liên quan đường đi đang xét | 10 TiB | 7 TiB |
| Origin requests cho ảnh công khai | 4 triệu | 1 triệu |
| p95 latency tải ảnh | 650 ms | 230 ms |
| Tổng chi phí các SKU liên quan | Cần đo | Cần đo |

Mục tiêu không phải chỉ giảm TiB. Phải đo **phí CDN mới phát sinh**, thay đổi load balancer/Cloud Storage operations và hiệu năng. Có thể tổng bytes giảm nhưng tổng bill tăng nếu request/lookup hoặc service pricing thay đổi.

### Phân bổ chi phí có trách nhiệm

- Dùng labels, project hierarchy và owner mapping cho cost allocation.
- Với Shared VPC, xác định bên nào chịu trách nhiệm lưu lượng giữa host và service projects.
- Với external LB/CDN dùng chung, phân bổ theo request/bytes hoặc phương pháp nhất quán đã được nhóm FinOps phê duyệt.
- Ghi lại giả định và mức độ bao phủ chi phí: một số SKU không có resource label đủ chi tiết.
- Không quy toàn bộ chi phí networking của shared platform cho ứng dụng có traffic lớn nhất nếu chưa có số liệu phù hợp.

## 15. Case study: tối ưu API ảnh sản phẩm

**Bối cảnh giả định:** Spring Boot API trả thông tin sản phẩm và một số ảnh. User tập trung ở Đông Nam Á, database và API cùng region, nhưng object storage ở một location khác. Trước đó API gọi Cloud Storage, tải file rồi trả về browser. Nhóm nhận thấy Internet egress và cross-location transfer tăng nhanh.

### Bước 1: Đo và tìm nguồn gốc

- Dùng Billing Reports lọc Network và Cloud Storage SKUs.
- Dùng Network Topology/Flow Analyzer tìm đường egress lớn của backend phù hợp.
- Dùng application metrics đo số lần API tải object, bytes và latency.
- Kiểm tra Cloud Storage bucket location và response cacheability.
- Kiểm tra object public/private, lifecycle và quyền truy cập.

### Bước 2: Đưa ra ba phương án

| Phương án | Ưu điểm | Rủi ro / chi phí cần đo |
|---|---|---|
| Giữ API proxy, bật cache trong app | Ít thay đổi client | Memory, invalidation, vẫn qua app |
| Dùng signed URL trực tiếp | Giảm hop qua Java API | Security URL, CORS, data transfer từ Storage |
| Dùng Cloud CDN cho ảnh công khai | Edge caching, giảm origin load | Cache fill/lookup/egress, invalidation và cache key |

Không áp dụng CDN cho ảnh đơn hàng cá nhân chỉ vì hit rate cao; phân loại dữ liệu trước.

### Bước 3: Thử nghiệm có kiểm soát

1. Chọn nhóm ảnh public có content hash, không chứa thông tin người dùng.
2. Tạo phương án canary và giới hạn traffic.
3. Kiểm tra HTTP headers/cache key/TTL.
4. Đo hit ratio, cache fill, origin traffic, p95 latency.
5. Theo dõi request error, 404, stale content và quyền truy cập.
6. So sánh chi phí SKU sau khi đủ dữ liệu billing.
7. Nếu đạt, tăng dần traffic; nếu không đạt, rollback routing/cache config.

### Bước 4: Đánh giá kết quả

Sự thay đổi chỉ được xem là thành công khi:

- p95 latency không xấu hơn mục tiêu, tốt nhất được cải thiện.
- Không rò rỉ nội dung private.
- Tổng chi phí phục vụ cùng mức traffic giảm theo số liệu bill hợp lệ.
- Backend CPU/memory/requests giảm hoặc giữ trong giới hạn.
- Không tăng lỗi, stale data hoặc incident.

## 16. Runbook tối ưu network path theo chu trình đo – thử – quyết định

### Bước 1: Xác định vấn đề

Ví dụ: tăng 35% chi phí egress so với kỳ trước nhưng số đơn hàng chỉ tăng 5%. Xác minh thay đổi không chỉ do khác số ngày hoặc billing delay.

### Bước 2: Xác định top SKUs và top flows

- Billing export cho tiền và SKU.
- Network Topology/Flow Logs cho traffic path.
- Service metrics cho request count/bytes và business unit.
- Logs/traces cho đường call và payload lớn.

### Bước 3: Thiết lập giả thuyết

Ví dụ “worker đang tải cùng object nhiều lần qua hai region; thêm cache hoặc đổi worker placement có thể giảm cross-region transfer”. Ghi rõ phương pháp kiểm chứng và rủi ro.

### Bước 4: Đề xuất phương án

So sánh ít nhất:

- Không thay đổi (baseline).
- Tối ưu ứng dụng: cache, batch, compression.
- Tối ưu placement, network endpoint, tier hoặc CDN khi phù hợp.

### Bước 5: Đặt guardrails

- p95/p99 latency và error rate.
- Availability/SLO, RTO/RPO.
- Không thay đổi phân loại dữ liệu/ACL.
- Chi phí trần và traffic canary.
- Thời gian quan sát đủ trước khi kết luận.
- Phương án rollback cấu hình DNS, route, CDN hoặc deployment.

### Bước 6: Triển khai canary

Áp dụng thay đổi cho phạm vi nhỏ và theo dõi metrics. Không thử thay đổi mạng lớn trực tiếp trên production khi chưa có staged rollout.

### Bước 7: So sánh trước/sau

- Chuẩn hóa theo cùng traffic, thời gian và lượng công việc.
- Tách tác động của release khác, đợt marketing hoặc thay đổi workload.
- Xem billing lag và credits.
- Kiểm tra các SKU mới phát sinh.
- Ghi savings thực tế và confidence.

### Bước 8: Ra quyết định và chuẩn hóa

Giữ thay đổi nếu đáp ứng guardrails; nếu không, rollback. Cập nhật network diagram, runbook, ownership và FinOps dashboard.

## 17. Các lỗi và cách khắc phục thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Internet egress tăng đột biến | Payload lớn, endpoint bị scrape, downloads tăng | Kiểm tra client/URL, quota, CDN, compression |
| Cross-zone egress tăng | Pod/VM giao tiếp nhiều giữa zone | Kiểm tra placement và HA requirements |
| Inter-region cost tăng | DB/worker/bucket khác region | Map source–destination và traffic volume |
| Cloud NAT cost cao | Nhiều GiB xử lý, external IP hoặc gateway chạy liên tục | Kiểm tra NAT logs/metrics và eligible private API paths |
| Không truy cập Google APIs qua private | Private Google Access/DNS/routes sai | Kiểm tra subnet và endpoint support |
| Dùng Standard Tier nhưng CDN không khả dụng | Cloud CDN yêu cầu Premium | Chọn kiến trúc/tier phù hợp |
| CDN hit rate thấp | Cache-Control sai, nhiều cache key, URL không ổn định | Kiểm tra headers, key, TTL và response type |
| CDN giảm origin bytes nhưng bill không giảm | Cache fill/lookup/egress hoặc LB processing tăng | Đối chiếu đầy đủ SKU |
| API image download chậm | Java proxy file lớn, thiếu streaming/caching | So sánh direct download, signed URL và CDN nếu phù hợp |
| Flow Logs không khớp hóa đơn | Sampling, aggregation hoặc coverage khác nhau | Kết hợp billing export, metrics và logs |
| App nhanh hơn nhưng database error tăng | Thay đổi connection routing/latency hoặc pool | Kiểm tra DB pool, IAM, TLS, capacity |
| Private Service Connect vẫn có phí | Endpoint/processing charges tùy sản phẩm | Kiểm tra PSC pricing và billing SKUs |
| Giảm cross-zone nhưng outage impact tăng | Dồn workload vào một zone | Khôi phục HA, tối ưu tại tầng app trước |
| Không thấy dữ liệu BigQuery Billing export | Export chưa bật, billing lag hoặc quyền thiếu | Xem cấu hình export, lịch cập nhật và dataset IAM |

## 18. Checklist trước khi thay đổi đường đi mạng

- [ ] Đã phân loại các luồng intra-zone, cross-zone, inter-region, Internet và hybrid.
- [ ] Có chủ sở hữu, mục đích, địa điểm và bandwidth của top flows.
- [ ] Đã so sánh baseline 30–90 ngày hoặc đủ chu kỳ nghiệp vụ.
- [ ] Đã kiểm tra SKU thực tế thay vì giả định mọi traffic nội bộ miễn phí.
- [ ] Đã hiểu các khoản NAT, load balancing, CDN, storage và connectivity liên quan.
- [ ] Đã kiểm tra placement của API, DB, cache, worker và bucket.
- [ ] Đã kiểm tra security, data residency và quyền truy cập.
- [ ] Đã xác nhận SLO, HA, RTO/RPO không bị giảm ngoài phê duyệt.
- [ ] Nếu dùng CDN, đã kiểm tra cacheability, cache key, TTL và nội dung nhạy cảm.
- [ ] Nếu dùng Standard Tier, đã kiểm tra feature compatibility và benchmark.
- [ ] Nếu dùng Private Google Access/PSC, đã kiểm tra DNS/routes và pricing.
- [ ] Có canary, monitoring, alert và rollback plan.
- [ ] So sánh unit cost theo cùng traffic/business volume.
- [ ] Có theo dõi sau phát hành và người chịu trách nhiệm đánh giá kết quả.

## Câu hỏi ôn tập

1. Vì sao traffic giữa hai VM ở hai zone của cùng region có thể bị tính phí dù không đi Internet?
2. Cloud NAT có làm data transfer out miễn phí không? Những loại phí nào có thể cộng thêm?
3. Private Google Access khác Private Service Connect ở điểm nào?
4. Vì sao không nên đưa tất cả API và database vào một zone chỉ để giảm cross-zone traffic?
5. Một Cloud Storage bucket ở multi-region có luôn được coi là cùng location với một VM nằm trong một region thuộc multi-region đó không?
6. Khi nào Cloud CDN giảm origin load nhưng không nhất thiết làm tổng chi phí giảm?
7. Điều gì cần kiểm tra trước khi chuyển Internet-facing service từ Premium Tier sang Standard Tier?
8. VPC Flow Logs có thể dùng trực tiếp như hóa đơn tính phí theo GiB không? Vì sao?
9. Khi nào signed URL có thể cải thiện đường download so với streaming file qua Java API?
10. Những metric và guardrails nào chứng minh một phương án network optimization đã thành công?

## Kết luận

Tối ưu đường đi mạng trên Google Cloud là bài toán kết hợp **kiến trúc**, **dữ liệu thực tế** và **FinOps**, không đơn giản là bật một dịch vụ “rẻ hơn”. Cần biết traffic đi từ đâu đến đâu, đi qua zone/region/Internet/hybrid nào, bị tính phí ở những lớp nào và đang phục vụ nghiệp vụ gì.

Cloud Billing và BigQuery cho biết các SKU đang phát sinh tiền; Network Topology, Connectivity Tests, VPC Flow Logs và application metrics cung cấp bằng chứng về lưu lượng và hiệu năng. Các phương án như đặt ứng dụng gần dữ liệu, cache, CDN, private API access, batching, compression hoặc giảm proxy hop đều phải được kiểm nghiệm với **tổng chi phí**, p95 latency, bảo mật và SLO. Khi thay đổi được triển khai theo canary, có rollback và đo lường unit cost, nhóm kỹ thuật có thể giảm truyền dữ liệu không cần thiết mà không đánh đổi độ tin cậy của hệ thống.

## Tài liệu tham khảo

- [Google Cloud: Network pricing](https://cloud.google.com/vpc/network-pricing)
- [Google Cloud: Network Service Tiers overview](https://cloud.google.com/network-tiers/docs/overview)
- [Google Cloud: Network Service Tiers pricing](https://cloud.google.com/network-tiers/pricing)
- [Google Cloud: Cloud NAT pricing](https://cloud.google.com/nat/pricing)
- [Google Cloud: Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [Google Cloud: Private access options for services](https://cloud.google.com/vpc/docs/private-access-options)
- [Google Cloud: Cloud CDN overview](https://cloud.google.com/cdn/docs/overview)
- [Google Cloud: Cloud CDN caching](https://cloud.google.com/cdn/docs/caching)
- [Google Cloud: Cloud CDN pricing](https://cloud.google.com/cdn/pricing)
- [Google Cloud: Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Google Cloud: Network Topology overview](https://cloud.google.com/network-intelligence-center/docs/network-topology/concepts/overview)
- [Google Cloud: Connectivity Tests overview](https://cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview)
- [Google Cloud: Network Intelligence Center](https://cloud.google.com/network-intelligence-center/docs)
- [Google Cloud: Export Billing data to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery)
- [Google Cloud: Set up Billing export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)

