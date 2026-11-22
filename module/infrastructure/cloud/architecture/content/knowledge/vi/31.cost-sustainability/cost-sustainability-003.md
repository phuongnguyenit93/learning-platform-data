# Phân bổ chi phí theo sản phẩm, môi trường và tenant

## 1. Vì sao phải phân bổ chi phí cloud?

Hóa đơn cloud thường gom nhiều loại chi phí vào cùng một account hoặc subscription: compute, database, storage, network, logging, managed service, license và discount. Một nền tảng có nhiều sản phẩm, team, môi trường và tenant có thể nhìn thấy tổng chi phí nhưng không trả lời được sản phẩm nào đang tiêu thụ tài nguyên, môi trường staging tốn bao nhiêu, tenant nào tạo tải lớn hay khoản shared infrastructure nên chia cho ai.

**Cost allocation (phân bổ chi phí)** là quá trình gắn chi phí phát sinh với đơn vị chịu trách nhiệm hoặc đơn vị tạo ra nhu cầu tiêu thụ. Đơn vị phân bổ có thể là product, service, team, cost center, environment, tenant, project, region hoặc business capability.

Phân bổ chi phí có ba mục đích chính:

- **Visibility / showback:** cho từng team biết họ đang sử dụng bao nhiêu và khoản nào tạo nên chi phí.
- **Accountability / chargeback:** ghi nhận hoặc tính chi phí về cost center/đơn vị chịu trách nhiệm theo quy tắc tài chính đã thống nhất.
- **Optimization:** tìm ra chi phí không có owner, shared cost tăng bất thường, môi trường không cần thiết hoặc đơn vị có unit economics kém.

Một báo cáo chỉ chia tổng hóa đơn theo tỷ lệ headcount có thể đơn giản nhưng không phản ánh mức sử dụng thực. Ngược lại, cố đo chính xác từng request cho mọi loại tài nguyên có thể tốn nhiều công sức hơn giá trị nhận được. Thiết kế tốt chọn độ chính xác phù hợp với quyết định cần đưa ra, công bố rõ phần đo trực tiếp, phần ước tính và phần chưa phân bổ.

Trong module **CLOUD_ARCHITECTURE**, cost allocation kết nối kiến trúc kỹ thuật với hiệu quả kinh doanh và tính bền vững. Nó cho phép so sánh chi phí giữa sản phẩm, môi trường và tenant, đồng thời tạo dữ liệu đáng tin để quyết định tối ưu capacity, thiết kế multi-tenant và ưu tiên đầu tư.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt cost visibility, showback, chargeback và cost optimization.
2. Thiết kế taxonomy cho product, service, environment, team, tenant và cost center.
3. Dùng tag/label, account/project boundary và usage meter để phân bổ chi phí.
4. Phân bổ chi phí shared platform, network, support, logging và discount.
5. Xử lý unallocated spend, missing tags và dữ liệu billing trễ.
6. Phân biệt invoice/cash cost với amortized/effective cost.
7. Xây dựng unit economics theo product hoặc tenant.
8. Thiết lập budget, anomaly detection, governance và quy trình review.

## 2. Đơn vị phân bổ và mô hình tổ chức

Trước khi chọn công cụ, cần thống nhất tổ chức muốn trả lời câu hỏi nào. Một tài nguyên có thể thuộc một sản phẩm, do một team vận hành, chạy ở production và phục vụ hàng nghìn tenant. Các chiều này không thay thế nhau.

| Chiều phân bổ | Câu hỏi | Ví dụ |
|---|---|---|
| Product | Sản phẩm nào tiêu thụ chi phí? | Booking, Search, Analytics |
| Service/workload | Thành phần kỹ thuật nào gây chi phí? | Booking API, Payment worker |
| Environment | Chi phí thuộc môi trường nào? | Dev, staging, production |
| Team/owner | Ai chịu trách nhiệm vận hành? | Platform, data, payments |
| Cost center | Bộ phận tài chính nào ghi nhận? | CC-ENG-01 |
| Tenant/customer | Khách hàng hoặc tổ chức nào sử dụng? | tenant-042 |
| Project/initiative | Chi phí phục vụ chương trình nào? | Migration, launch-campaign |
| Region/location | Tài nguyên chạy ở đâu? | Region A, zone B |

### 2.1. Tách ownership khỏi consumer

Một shared database do Platform team sở hữu nhưng phục vụ Booking, Search và Reporting. Platform là owner kỹ thuật, còn ba sản phẩm là consumer. Nếu toàn bộ chi phí được gán cho Platform, nhóm sản phẩm không thấy chi phí họ tạo ra; nếu chia đều, sản phẩm tải thấp có thể trả quá nhiều.

Nên lưu hai loại thông tin:

- **Owner dimension:** đơn vị chịu trách nhiệm vận hành, bảo mật và tối ưu tài nguyên.
- **Consumer/allocation dimension:** đơn vị nhận phần chi phí dựa trên mức sử dụng hoặc quy tắc đã thống nhất.

Một tài nguyên có thể có một owner nhưng nhiều consumer. Điều này đặc biệt quan trọng với Kubernetes cluster, network egress, observability platform, data warehouse và shared database.

### 2.2. Hierarchy phân bổ

~~~mermaid
flowchart TD
    Org["Organization"] --> BU["Business unit"]
    BU --> Product["Product"]
    Product --> Service["Service / workload"]
    Service --> Env["Environment"]
    Env --> Resource["Cloud resource"]
    Product --> Tenant["Tenant usage"]
    Org --> Shared["Shared platform cost"]
    Shared --> Rule["Allocation rule"]
    Rule --> Product
~~~

Hierarchy cần phản ánh cách ra quyết định và báo cáo tài chính. Không nên tạo quá nhiều chiều mà không có owner hoặc không ai sử dụng trong quyết định.

## 3. Showback, chargeback và cost ownership

| Mô hình | Ý nghĩa | Khi phù hợp |
|---|---|---|
| **Cost visibility** | Hiển thị chi phí và cách hình thành | Giai đoạn đầu xây nền tảng FinOps |
| **Showback** | Báo cáo chi phí cho team/product mà chưa nhất thiết chuyển tiền nội bộ | Team cần ownership, học cách tối ưu |
| **Chargeback** | Ghi nhận hoặc tính chi phí nội bộ cho cost center/product theo chính sách | Tổ chức có quy trình tài chính và định nghĩa allocation đã thống nhất |
| **Unit-cost reporting** | Chia chi phí cho một đơn vị hoạt động | Định giá, product economics, capacity planning |

Không nên triển khai chargeback trước khi dữ liệu đủ tin cậy. Nếu các team không hiểu cách tính shared cost hoặc discount, họ có thể xem hóa đơn như một hình phạt thay vì thông tin hỗ trợ quyết định.

### 3.1. Nguyên tắc chargeback công bằng

- Cùng một loại chi phí dùng cùng quy tắc ở các sản phẩm tương đương.
- Công bố chi phí được đo trực tiếp và chi phí được ước tính.
- Có cách xử lý resource thiếu tag hoặc không xác định owner.
- Không phân bổ trùng cùng một khoản vào nhiều cost center.
- Quy định cách tính discount, credit, tax và support.
- Có quy trình dispute, correction và version hóa allocation rule.
- Giữ lại khoản unallocated có chủ đích nếu phân bổ thiếu bằng chứng sẽ gây hiểu sai.

## 4. Thiết kế taxonomy và tagging standard

Tag/label là metadata gắn với resource, billing record hoặc workload. Taxonomy tốt cần ít giá trị tự do, có danh sách hợp lệ và có owner duy trì.

### 4.1. Tag schema tham khảo

| Tag | Mục đích | Ví dụ |
|---|---|---|
| product | Sản phẩm chịu chi phí | booking |
| service | Workload cụ thể | booking-api |
| environment | Phân biệt môi trường | production |
| owner_team | Team vận hành | team-booking |
| cost_center | Mã tài chính | CC-ENG-01 |
| tenant_scope | Phạm vi tenant nếu resource chuyên biệt | tenant-042 |
| project | Dự án/initiative | checkout-v2 |
| data_classification | Mức phân loại dữ liệu khi cần | confidential |
| managed_by | Cách quản lý resource | terraform |
| expiry_date | Ngày review/retire theo policy | 2027-03-31 |

Không phải provider/resource type nào cũng hỗ trợ mọi tag hoặc đưa tag vào billing export. Cần phân biệt resource tag, cost allocation tag được kích hoạt trong billing, Kubernetes label và metadata trong CMDB.

### 4.2. Quy tắc đặt tên

- Dùng lowercase và dấu gạch ngang hoặc quy ước nhất quán.
- Chỉ dùng giá trị nằm trong catalog được quản lý.
- Không chứa PII, secret hoặc dữ liệu khách hàng nhạy cảm.
- Định nghĩa rõ tag bắt buộc, tag tùy chọn và tag không được dùng.
- Quy định kế thừa tag cho resource con nếu provider hỗ trợ.
- Giữ mapping khi product/team/cost center đổi tên.
- Kiểm tra tag coverage và giá trị không hợp lệ định kỳ.

### 4.3. Ví dụ resource metadata

~~~yaml
metadata:
  labels:
    product: booking
    service: booking-api
    environment: production
    owner_team: team-booking
    cost_center: CC-ENG-01
    managed_by: gitops
~~~

Đây là metadata minh họa. Với Kubernetes, labels hỗ trợ nhận diện workload; để tính cost cần thêm usage/capacity allocation từ node, pod, namespace hoặc container metrics và đối chiếu billing của cluster.

## 5. Phân bổ qua account, project, subscription và tag

Có ba cách tổng quát, thường kết hợp với nhau:

| Cách | Cơ chế | Ưu điểm | Hạn chế |
|---|---|---|---|
| Dedicated account/project | Mỗi product/environment có boundary billing riêng | Ranh giới rõ, dễ giao ownership | Nhiều account, shared services và quota phức tạp |
| Resource tags/labels | Gắn metadata theo resource | Linh hoạt, có nhiều chiều báo cáo | Thiếu tag, resource không taggable hoặc tag không vào billing |
| Usage-based allocation | Phân theo request, CPU/memory time, GB, query, message | Phù hợp shared resource và tenant | Cần đo usage, định nghĩa driver, xử lý overhead |

### 5.1. Khi nên tách account/project?

Tách account hoặc subscription hữu ích khi production và non-production cần boundary bảo mật/chi phí rõ; business unit có ngân sách và trách nhiệm riêng; có quy định data residency hoặc compliance; cần giới hạn blast radius và quyền quản trị; billing provider hỗ trợ cost view theo account/project.

Không nên tạo account riêng cho mọi tenant nếu số tenant rất lớn, vận hành identity/network/quotas trở nên phức tạp hoặc sản phẩm dùng kiến trúc multi-tenant shared resource. Khi đó cần usage metering ở lớp ứng dụng.

### 5.2. Kết hợp nhiều chiều

Account có thể xác định environment/product cấp cao; tag xác định service/team/cost center; application meter xác định tenant usage. Một báo cáo tổng hợp có thể drill-down từ organization tới product, service rồi tenant mà không cần một resource chuyên biệt cho mỗi tenant.

## 6. Phân bổ chi phí shared infrastructure

Đây thường là phần khó nhất. Một cluster, NAT gateway, load balancer, database, observability platform hoặc CI runner có thể phục vụ nhiều sản phẩm.

### 6.1. Chọn allocation driver

| Chi phí shared | Driver có thể dùng | Lưu ý |
|---|---|---|
| Kubernetes node/cluster | CPU request/usage, memory request/usage, pod allocation | Chọn cách phản ánh reservation và idle capacity |
| Database shared | CPU time, query time, storage, connection hoặc workload meter | Query count đơn thuần không phản ánh query cost |
| Object storage | GB-month, request class, data retrieval/egress | Tách storage và request/transfer |
| Network egress | Bytes theo source workload/tenant | Khó phân bổ nếu chỉ có NAT bill tổng |
| Observability | Log bytes, metric series, trace spans hoặc ingestion volume | Có thể phân bổ theo ingestion, có thể không phản ánh giá trị |
| CI/CD | Runner minutes, build duration, artifact/storage | Shared runner idle và cache cần policy |
| Support plan | Tỷ lệ chi phí eligible hoặc theo policy tài chính | Không nhất thiết tỷ lệ với usage kỹ thuật |
| Shared security platform | Asset count, workload count, user count hoặc fixed allocation | Chọn driver phản ánh beneficiary và governance |

### 6.2. Công thức phân bổ tỷ lệ

Với một pool shared có chi phí \(C\), consumer \(i\) có usage driver \(u_i\), chi phí phân bổ:

\[
C_i = C \times \frac{u_i}{\sum_{j=1}^{n}u_j}
\]

Ví dụ cluster có chi phí tháng 12.000 đơn vị tiền tệ và CPU allocation của ba sản phẩm lần lượt là 50, 30 và 20 core-hours theo đơn vị đã chuẩn hóa:

\[
C_{booking}=12,000\times 50/100=6,000
\]
\[
C_{search}=12,000\times 30/100=3,600
\]
\[
C_{analytics}=12,000\times 20/100=2,400
\]

Tổng phân bổ bằng chi phí pool. Phải thống nhất usage driver là request, usage thực tế hay reservation; không trộn các đơn vị khác nhau trong cùng công thức.

### 6.3. Fixed, variable và hybrid allocation

- **Fixed allocation:** chia đều hoặc theo tỷ lệ cố định; đơn giản và dễ dự báo nhưng có thể không công bằng khi usage lệch.
- **Variable allocation:** theo usage đo được; sát mức tiêu thụ nhưng cần telemetry chất lượng.
- **Hybrid allocation:** một phần fixed để phản ánh capacity reserved/ownership, phần còn lại variable theo usage.

Hybrid thường hữu ích cho platform có chi phí giữ capacity tối thiểu cộng với chi phí biến đổi theo traffic.

## 7. Unallocated spend và tag coverage

Không phải mọi hóa đơn đều map được ngay. Unallocated spend có thể đến từ resource không hỗ trợ tag, tag thiếu/sai, shared cost chưa có driver, billing export trễ hoặc account chưa có owner.

### 7.1. Phân loại khoản chưa phân bổ

1. **Missing metadata:** resource thiếu product/team/environment.
2. **Unsupported resource:** dịch vụ không hỗ trợ tag hoặc billing dimension.
3. **Shared pool:** có nhiều consumer nhưng chưa có usage driver.
4. **Central governance:** security, support, network core hoặc platform baseline.
5. **Timing/reconciliation:** credit, refund, tax hoặc usage adjustment chưa ghép được.
6. **Unknown/exception:** chưa tìm được nguồn hoặc owner.

### 7.2. Quy trình xử lý

- Gắn cost bucket unallocated thay vì tự ý gán cho một team.
- Tạo owner queue và SLA để xác minh.
- Tách missing tag với shared cost có chủ đích.
- Dùng resource inventory, deployment metadata và usage telemetry để truy nguyên.
- Cập nhật taxonomy hoặc allocation rule có version.
- Recalculate kỳ trước theo chính sách điều chỉnh đã thống nhất.
- Theo dõi tỷ lệ unallocated và tuổi của khoản chưa phân bổ.

### 7.3. Metric chất lượng phân bổ

| Metric | Câu hỏi |
|---|---|
| Tag coverage by spend | Bao nhiêu phần trăm chi phí có metadata cần thiết? |
| Unallocated spend ratio | Bao nhiêu phần trăm chưa có owner/driver? |
| Invalid tag count | Có giá trị ngoài catalog không? |
| Shared cost allocation coverage | Shared pool nào chưa có quy tắc? |
| Reconciliation delta | Tổng allocation có khớp billing source không? |
| Allocation freshness | Dữ liệu phân bổ cập nhật trễ bao lâu? |

Coverage nên đo theo tỷ lệ chi phí, không chỉ số lượng resource. Một resource nhỏ thiếu tag ít nghiêm trọng hơn một database lớn không có owner.

## 8. Gross cost, net cost, amortized cost và discount

Billing report có thể thể hiện nhiều góc nhìn khác nhau. Nếu các team dùng một con số khác nhau mà không biết semantics, showback/chargeback dễ phát sinh tranh chấp.

| Khái niệm | Ý nghĩa |
|---|---|
| **List/on-demand cost** | Giá tham chiếu trước discount hoặc commitment |
| **Net cost** | Chi phí sau discount/credit theo cách provider hiển thị |
| **Amortized/effective cost** | Phân bổ upfront/recurring commitment theo thời gian sử dụng |
| **Cash/invoice cost** | Khoản ghi nhận trên hóa đơn/kỳ thanh toán theo accounting policy |
| **Shared/central cost** | Chi phí nền tảng hoặc tổ chức chưa gắn trực tiếp product |
| **Tax/credit/refund** | Thành phần tài chính cần quy định cách đưa vào báo cáo |

Ví dụ, một commitment có khoản trả trước lớn có thể làm invoice tháng đầu cao nhưng effective cost của mỗi giờ sử dụng thấp hơn khi phân bổ trong thời hạn cam kết. Showback nên nói rõ đang dùng amortized hay cash view.

### 8.1. Discount và commitment allocation

Savings plan, reserved capacity, committed use discount hoặc enterprise discount có thể áp dụng cho nhiều workload. Có thể phân bổ theo resource/usage thực nhận discount; theo tỷ lệ usage eligible của product; theo owner của commitment khi tổ chức chọn cách ghi nhận rủi ro mua thừa; hoặc theo hybrid, tách benefit được tiêu thụ với commitment idle/unutilized.

Không phân bổ toàn bộ benefit cho một product trong khi chi phí commitment idle do team khác chịu nếu chính sách tài chính yêu cầu nhìn thấy rủi ro mua dư.

## 9. Phân bổ chi phí theo môi trường

Environment là chiều quan trọng vì dev/staging/test có thể chiếm tỷ lệ đáng kể mà không trực tiếp tạo doanh thu.

### 9.1. Các nhóm môi trường

- **Production:** workload phục vụ khách hàng, yêu cầu availability/SLO.
- **Staging/pre-production:** xác minh release, integration và performance.
- **Development:** môi trường làm việc thường ngày.
- **Test/QA:** chạy test tự động, ephemeral environment.
- **Sandbox/experiment:** thử nghiệm và học tập.
- **DR/backup:** năng lực dự phòng, retention và khả năng phục hồi.

### 9.2. Cost policy theo môi trường

| Môi trường | Cách kiểm soát |
|---|---|
| Production | Theo dõi unit cost, capacity headroom, SLO và cost per transaction |
| Staging | Auto shutdown khi không dùng, data size đại diện vừa đủ |
| Development | Quota theo team/user, resource TTL và instance nhỏ |
| Test/QA | Tạo ephemeral rồi xóa, cache dependency và giới hạn parallelism |
| Sandbox | Budget nhỏ, deny resource đắt nếu chưa được approve |
| DR | Phân biệt standby capacity với storage/replication cost; kiểm tra RTO/RPO |

Không tối ưu non-production bằng cách xóa mọi capacity dự phòng nếu việc đó làm test mất tính đại diện hoặc kéo dài thời gian release. DR cost cần đánh giá cùng RTO/RPO, không chỉ coi là idle waste.

## 10. Phân bổ theo product và service

Product là đơn vị kinh doanh; service là đơn vị kỹ thuật. Một product có thể dùng nhiều service và một service shared có thể phục vụ nhiều product.

### 10.1. Hai view bổ sung nhau

- **Product view:** tổng chi phí của Booking product, bao gồm service riêng và phần shared được phân bổ.
- **Service view:** chi phí Booking API, Inventory, Payment integration và worker để team kỹ thuật tối ưu.

Mapping product-service cần có owner và thời gian hiệu lực. Khi service được chuyển từ product này sang product khác hoặc tách thành service mới, lịch sử allocation cần được giữ để so sánh đúng.

### 10.2. Không chỉ phân bổ compute

Cost của một product có thể gồm compute/container/serverless; database/cache/search/streaming; object storage, backup và snapshot; network egress, NAT, load balancer và private connectivity; logging, metrics, tracing và security scanning; CI/CD, artifact registry và license; shared platform, support và commitment allocation.

Nếu chỉ lấy VM/container cost, product economics thường thấp hơn thực tế đáng kể.

## 11. Phân bổ tenant trong kiến trúc multi-tenant

Trong SaaS, một cluster hoặc database có thể phục vụ hàng trăm tenant. Provider invoice thường không có tenant ID, nên hệ thống cần usage meter ở application/data plane.

### 11.1. Các mô hình hạ tầng

| Kiến trúc | Khả năng attribution | Đánh đổi |
|---|---|---|
| Dedicated resources per tenant | Rõ qua resource/account | Chi phí nền cao, nhiều resource để quản lý |
| Shared application, isolated database per tenant | Tách DB/storage; compute app cần phân bổ riêng | Nhiều connection và migration |
| Shared database/schema/cluster | Cần query/row/CPU/storage metering | Khó đo chính xác, nguy cơ noisy neighbor |
| Hybrid tiers | Tenant lớn dùng dedicated, tenant nhỏ dùng shared | Cần nhiều mô hình vận hành và pricing |

### 11.2. Tenant usage meter

Có thể đo request count và compute duration theo tenant; CPU/memory time theo workload/tenant khi có thể liên kết; rows scanned, query runtime hoặc warehouse credits theo query principal/tenant context; storage bytes và data retention; message published/processed và queue time; data transfer/egress theo tenant; premium feature usage hoặc scheduled job duration.

Không nên dùng request count làm đại diện cho compute cost nếu mỗi request có độ phức tạp rất khác nhau. Có thể kết hợp weighted usage unit dựa trên benchmark và operation class.

### 11.3. Định nghĩa meter an toàn

| Trường | Ví dụ |
|---|---|
| Meter ID | tenant_compute_units |
| Tenant identity | Tenant ID đã xác thực từ server-side context |
| Operation | Search, booking, export |
| Quantity/unit | Compute ms, GB-hour, message |
| Timestamp/window | Thời điểm và kỳ đo |
| Source | Service/worker phát sinh |
| Idempotency key | Chống ghi nhận trùng |
| Schema version | Phiên bản semantics |

Không tin tenant ID do client tự khai báo nếu server chưa xác thực quyền sở hữu. Meter phải chống duplicate/replay, có reconciliation và retention phù hợp. Billing meter là dữ liệu nghiệp vụ nhạy cảm và cần audit.

## 12. Unit economics: chi phí trên một đơn vị giá trị

Tổng cloud spend tăng chưa chắc là xấu nếu số giao dịch hoặc doanh thu tăng nhanh hơn. Unit economics giúp so sánh chi phí theo hoạt động.

\[
Cost\ per\ booking = \frac{Allocated\ cloud\ cost\ for\ booking\ product}{Confirmed\ bookings}
\]

\[
Cost\ per\ tenant = \frac{Allocated\ tenant\ cost}{Active\ tenants}
\]

\[
Cost\ per\ 1,000\ searches = \frac{Search\ product\ cost}{Eligible\ searches}\times 1000
\]

### 12.1. Chọn denominator đúng

| Đơn vị | Khi phù hợp | Rủi ro |
|---|---|---|
| Per request | API có workload gần tương đương | Request phức tạp khác nhau |
| Per booking confirmed | Booking product economics | Phụ thuộc conversion và seasonality |
| Per active tenant | SaaS subscription economics | Tenant size khác nhau nhiều |
| Per GB stored/month | Storage-heavy product | Không phản ánh retrieval/egress |
| Per query/compute unit | Analytics/data platform | Query complexity khác nhau |
| Per job completed | Batch processing | Job size và SLA khác nhau |

Unit cost cần cùng cohort/time window và allocation rule. Nếu cost kỳ này chia cho số booking tạo ở kỳ này nhưng booking hoàn tất trễ, xu hướng có thể bị lệch.

### 12.2. Ví dụ theo dõi theo tháng

| Tháng | Allocated cost | Booking confirmed | Cost/booking |
|---|---:|---:|---:|
| M1 | 100.000 | 20.000 | 5,00 |
| M2 | 108.000 | 24.000 | 4,50 |
| M3 | 120.000 | 30.000 | 4,00 |

Trong ví dụ, tổng chi phí tăng nhưng unit cost giảm nhờ quy mô giao dịch tăng nhanh hơn. Cần kiểm tra chất lượng dịch vụ, cancellation và margin trước khi kết luận hiệu quả tốt hơn.

### 12.3. Unit economics không thay thế SLO

Giảm cost/booking bằng cách giảm replica quá thấp có thể làm latency và error tăng. Cần theo dõi cost cùng availability, latency, correctness, data freshness và support cost. Tối ưu chi phí có ý nghĩa khi giữ được chất lượng mà sản phẩm cam kết.

## 13. Kubernetes và container cost allocation

Cluster billing thường ghi nhận node, disk, network và control plane; còn team muốn biết namespace/pod nào tiêu thụ chi phí. Phải tách các phần:

- **Requested capacity:** CPU/memory đã request, phản ánh phần scheduler dành chỗ.
- **Actual usage:** CPU/memory thực dùng.
- **Idle/unallocated capacity:** capacity node chưa được workload sử dụng.
- **System overhead:** daemonset, kube-system, monitoring, CNI, ingress và cluster service.
- **Shared storage/network:** PVC, load balancer, egress và volume.

### 13.1. Allocation theo request hay usage?

| Cơ sở | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Resource request | Team giữ chỗ capacity dù không dùng hết | Cluster capacity planning và trách nhiệm reservation |
| Actual usage | Team tiêu thụ CPU/memory thực tế | Cost optimization và workload efficiency |
| Hybrid | Một phần theo request, một phần theo usage | Muốn phản ánh reserved capacity và phần biến đổi |

Nếu chỉ phân theo usage, team request quá mức có thể chiếm node capacity nhưng ít trả chi phí. Nếu chỉ phân theo request, workload burst có thể dùng nhiều hơn nhiều so với reservation. Chính sách cần nêu rõ mục tiêu.

### 13.2. Shared overhead

Cluster overhead có thể phân bổ theo tỷ lệ CPU/memory request; tỷ lệ usage; số pod/namespace; fixed share cho mỗi team cộng với variable share; hoặc giữ lại trong cost center Platform.

Không tính overhead hai lần nếu node cost đã bao gồm system pod và báo cáo lại các service đó như chi phí riêng mà không loại trừ khỏi pool.

## 14. Network, storage và data platform allocation

### 14.1. Network

Network cost có thể bao gồm public egress, inter-zone/inter-region transfer, NAT gateway, load balancer, private connectivity và CDN. Allocation driver nên dựa trên source workload, bytes transferred, request count hoặc fixed share theo thiết kế.

Egress khó phân bổ nếu nhiều service dùng chung NAT hoặc gateway. Cần flow log/telemetry, network accounting hoặc proxy meter; nếu không đo được, ghi rõ shared pool và quy tắc xấp xỉ.

### 14.2. Storage

Storage cần tách capacity GB-month theo bucket/table/volume; snapshot/backup và retention; request class, retrieval và early deletion nếu provider tính phí; replication và cross-region storage; lifecycle transition và data transfer.

Chỉ phân theo dung lượng hiện tại có thể bỏ sót chi phí backup hoặc retrieval. Data owner cần chọn retention theo compliance và business value, không xóa dữ liệu chỉ để giảm hóa đơn mà chưa đánh giá.

### 14.3. Database và warehouse

Database shared có thể phân bổ theo query execution time, CPU, storage, connection, transaction hoặc tenant meter. Warehouse có query credits/compute units thì cần mapping user/role/project/job tag tới product/tenant.

Query count đơn thuần không đủ vì một query scan hàng terabyte khác một query point lookup. Cần query duration/compute consumption hoặc weighted units được benchmark.

## 15. Ngân sách, forecast và anomaly detection

Sau khi phân bổ, mỗi product/team có thể đặt budget hoặc target spend theo kỳ.

### 15.1. Budget hierarchy

- Organization budget: tổng mức chi dự kiến.
- Product budget: chi phí được giao cho sản phẩm.
- Environment budget: production/non-production.
- Project budget: migration, experiment hoặc launch.
- Tenant usage allowance: quota hoặc plan limit theo hợp đồng.

Budget là công cụ quản lý, không phải giới hạn kỹ thuật tự động trừ khi có policy enforcement. Không nên mặc định cắt workload production khi vượt budget; cần alert, approval và quyết định dựa trên SLO/contract.

### 15.2. Forecast

Forecast có thể dựa trên run rate hiện tại và seasonality; roadmap/launch/traffic forecast; commitment expiry và pricing change; growth của tenant, storage, log volume hoặc data retention; dự án migration, backfill và DR test.

Forecast nên phân biệt baseline, one-off cost và risk range; ghi giả định để người quản lý hiểu sai số.

### 15.3. Cost anomaly

Alert anomaly khi spend tăng đột ngột, nhưng cần phân biệt tăng do business growth với cấu hình sai:

- Log ingestion tăng vì debug logging.
- NAT/data transfer tăng sau thay đổi routing.
- Database compute tăng do query regression.
- Autoscaling giữ capacity quá cao.
- Backup/snapshot không được dọn theo retention.
- Test environment hoặc ephemeral resource không bị xóa.
- Tenant có traffic bất thường hoặc abuse.

Alert cần chỉ ra service, environment, owner, cost delta, usage driver và thay đổi gần nhất.

## 16. Governance và FinOps operating model

FinOps là mô hình cộng tác giữa engineering, finance, product và business để tạo giá trị từ cloud spend. Không nên giao toàn bộ tối ưu chi phí cho finance hoặc platform team.

### 16.1. Trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Finance | Billing source, accounting view, tax/credit và chargeback policy |
| Product owner | Unit economics, budget và trade-off value/cost |
| Engineering owner | Resource usage, optimization và service reliability |
| Platform/FinOps | Taxonomy, allocation pipeline, shared cost và reporting |
| Security/governance | Access, tag policy, retention và audit |
| Procurement | Contract, license, commitment và renewal |

### 16.2. Nhịp review

- Hằng ngày/tuần: anomaly, budget burn, unallocated spend và workload spike.
- Hằng tháng: showback/chargeback, unit-cost trend, shared allocation và forecast.
- Hằng quý: taxonomy, commitment utilization, product architecture và savings backlog.
- Khi có release/launch: dự báo chi phí, capacity và tenant impact trước/sau thay đổi.

### 16.3. FinOps feedback loop

~~~mermaid
flowchart LR
    Inform["Inform: visibility and allocation"] --> Optimize["Optimize: identify opportunities"]
    Optimize --> Operate["Operate: implement changes"]
    Operate --> Measure["Measure: cost, usage, SLO"]
    Measure --> Inform
~~~

Mỗi optimization cần owner, baseline, expected saving, reliability risk, implementation cost và kết quả đo sau thay đổi.

## 17. Bảo mật và chất lượng dữ liệu cost

Billing export và tenant meter có thể tiết lộ cấu trúc tổ chức, mức sử dụng và hoạt động khách hàng. Cần giới hạn quyền đọc billing detail theo role; không công khai raw tenant usage nếu không có authorization; lưu tenant ID đã chuẩn hóa, tránh PII không cần thiết; kiểm soát sửa allocation rule và lưu audit/version; bảo vệ pipeline ingest billing, kiểm tra schema và duplicate; reconcile tổng cost với nguồn billing chính thức; giữ lịch sử adjustment và correction.

Không dùng report allocation làm bằng chứng kế toán duy nhất nếu chưa được finance phê duyệt.

### 17.1. Data quality checks

- Tổng cost gốc = allocated + unallocated + các khoản ngoài scope được giải thích.
- Không có duplicate billing line hoặc usage meter.
- Allocation weights tổng bằng 100% cho mỗi pool cần phân bổ.
- Tag/catalog value nằm trong danh sách hợp lệ.
- Tenant meter không có tenant unknown quá ngưỡng.
- Billing period, currency và timezone được chuẩn hóa.
- Reprocessing cùng dữ liệu tạo kết quả nhất quán hoặc adjustment có audit.

## 18. Case study: phân bổ chi phí nền tảng đặt phòng

**Bối cảnh:** nền tảng đặt phòng có ba sản phẩm Booking, Search và Analytics; ba môi trường production, staging và dev; nhiều tenant dùng chung API, Kubernetes cluster, database, logging và network. Finance nhận một hóa đơn theo cloud account, còn các product owner muốn biết chi phí theo sản phẩm và chi phí phục vụ từng tenant.

### 18.1. Taxonomy

| Dimension | Giá trị ví dụ |
|---|---|
| Product | booking, search, analytics |
| Environment | production, staging, dev |
| Owner team | team-booking, team-search, team-data, platform |
| Cost center | CC-BOOKING, CC-SEARCH, CC-DATA, CC-PLATFORM |
| Service | booking-api, payment-worker, search-indexer |
| Tenant | Tenant ID đã xác thực trong application meter |

### 18.2. Allocation model

1. Compute service riêng được phân bổ trực tiếp theo resource tag/product/environment.
2. Kubernetes node cost được phân bổ theo request capacity cộng phần usage variable đã chuẩn hóa.
3. Database shared phân bổ theo query compute/CPU time và storage; baseline shared được giữ một phần ở Platform.
4. Network egress phân theo byte có source attribution; phần không đo được nằm trong shared network pool.
5. Logging phân theo ingestion bytes và retention; security audit baseline là central shared cost.
6. Tenant usage được đo tại application boundary theo operation class, compute duration và storage/egress.
7. Discount/commitment được phân bổ theo usage eligible và báo cáo riêng phần commitment không sử dụng.

### 18.3. Minh họa shared cost pool

Giả sử shared database pool có chi phí 9.000 đơn vị trong kỳ; query compute units của Booking, Search và Analytics lần lượt là 60, 25 và 15:

| Product | Driver share | Allocation |
|---|---:|---:|
| Booking | 60% | 5.400 |
| Search | 25% | 2.250 |
| Analytics | 15% | 1.350 |
| **Total** | **100%** | **9.000** |

Một phần fixed baseline có thể được giữ tại Platform nếu pool cần duy trì capacity chung bất kể usage. Khi đó phải tách fixed pool và variable pool, không cộng lại một lần nữa vào tổng product cost.

### 18.4. Dashboard product và tenant

Dashboard product hiển thị allocated cost, shared allocation, unallocated spend, cost per booking/search/query, environment split và SLO. Dashboard tenant hiển thị usage units, storage, request class, quota và cost estimate theo plan. Tenant-level amount có thể là internal unit economics, không nhất thiết bằng invoice giá bán.

### 18.5. Tiêu chí nghiệm thu

- Tổng allocation đối soát được với billing source.
- Tag coverage theo spend đạt mục tiêu đã duyệt.
- Mọi shared pool có driver, owner và version rule.
- Unallocated spend có owner queue và giảm theo thời gian.
- Product dashboard có unit cost cùng SLO/business metric.
- Tenant meter có idempotency, authorization và reconciliation.
- Staging/dev có budget/TTL; production/DR giữ guardrail theo SLO/RTO/RPO.
- Discount, credit và amortized view được giải thích trong report.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Dùng một account cho mọi thứ và không có tag | Không biết product/team nào tiêu tiền | Thiết kế hierarchy và taxonomy |
| Tạo tag tùy ý mỗi team | Báo cáo phân mảnh, giá trị không nhất quán | Catalog, schema và validation |
| Gán toàn bộ shared cost cho Platform | Product không thấy cost-to-serve | Allocation driver và showback |
| Chia đều shared cost dù usage rất lệch | Team tải thấp trả quá nhiều | Fixed/variable hoặc usage-based model |
| Bỏ qua network/logging/backup | Product cost thấp giả tạo | Bao gồm cost categories liên quan |
| Phân bổ tenant theo request count đơn thuần | Request nặng nhẹ bị coi như nhau | Weighted usage units và workload metering |
| Chargeback trước khi dữ liệu đáng tin | Tranh chấp và mất niềm tin | Bắt đầu bằng visibility/showback và reconciliation |
| Không báo unallocated spend | Chi phí không có owner kéo dài | Unallocated bucket, owner queue và SLA |
| Trộn cash với amortized cost | Các team so sánh số liệu khác semantics | Công bố cost view và accounting policy |
| Tính discount mà bỏ commitment idle | Không thấy rủi ro mua capacity dư | Tách consumed benefit và unutilized commitment |
| Tối ưu chi phí bằng cách phá SLO | Lỗi/latency làm tăng business cost | Theo dõi cost cùng reliability guardrail |
| Tag tenant ID/PII lên resource/metric công khai | Rò thông tin và cardinality cao | Meter bảo vệ, metadata tối thiểu và access control |
| Không version allocation rule | Không tái lập báo cáo lịch sử | Version, effective date và audit |

## 20. Checklist review cost allocation

### Taxonomy và ownership

- [ ] Có hierarchy product/service/environment/team/cost center/tenant.
- [ ] Owner kỹ thuật và consumer được phân biệt.
- [ ] Tag schema có catalog, owner, validation và quy tắc kế thừa.
- [ ] Resource/account/project boundary phù hợp mức cô lập cần thiết.
- [ ] Có inventory và quy trình xử lý asset thiếu tag/owner.

### Allocation method

- [ ] Chi phí direct, shared, central và unallocated được tách rõ.
- [ ] Mỗi shared pool có allocation driver, formula và owner.
- [ ] Không phân bổ trùng chi phí hoặc tính overhead hai lần.
- [ ] Có cách xử lý discount, credit, tax, commitment và amortization.
- [ ] Product/environment/tenant cost có source, unit và time window rõ.
- [ ] Allocation weights reconcile được với tổng billing source.

### Tenant và unit economics

- [ ] Tenant meter lấy identity từ server-side context đã xác thực.
- [ ] Meter có idempotency, schema version và reconciliation.
- [ ] Driver phản ánh workload complexity khi request không đồng nhất.
- [ ] Unit economics dùng denominator/cohort nhất quán.
- [ ] Cost được theo dõi cùng SLO, correctness và business value.

### FinOps governance

- [ ] Có showback trước khi áp dụng chargeback quy mô lớn.
- [ ] Budget, forecast và anomaly alert có owner.
- [ ] Tag coverage và unallocated spend được theo dõi theo tỷ lệ chi phí.
- [ ] Billing data và allocation rules có access control/audit.
- [ ] Có nhịp review và optimization backlog.
- [ ] DR, security baseline và compliance cost không bị cắt chỉ vì utilization thấp.

## 21. Bài tập thực hành

**Bối cảnh:** công ty có sản phẩm Booking, Search và Analytics chạy trên một cloud account. Production, staging và dev dùng chung một số cluster, database, NAT gateway và observability platform. Finance muốn chargeback cho từng product. Hiện có 18% chi phí không có tag; tenant usage mới chỉ đếm request; discount commitment được trừ toàn bộ vào Booking vì account owner là team Booking.

Hãy thiết kế lại:

1. Xây taxonomy product/service/environment/team/cost center/tenant.
2. Quyết định resource nào nên tách account/project và resource nào nên dùng tag/usage meter.
3. Chọn driver cho Kubernetes, database, NAT/egress, logging, backup và support.
4. Định nghĩa quy tắc fixed/variable cho shared platform.
5. Thiết kế quy trình xử lý 18% unallocated spend và KPI tag coverage.
6. Phân biệt cash invoice, net cost và amortized commitment benefit.
7. Thay request count bằng tenant usage meter có weighted operation class.
8. Viết công thức cost per booking, cost per search và cost per active tenant.
9. Thiết kế budget/anomaly dashboard và review cadence.
10. Đưa ra tiêu chí để chuyển từ showback sang chargeback mà không làm sai lệch SLO.

**Gợi ý tự kiểm tra:** Tổng allocation phải reconcile với billing source. Shared cost phải có driver được công bố. Commitment discount không nên chỉ được gán cho account owner nếu benefit được nhiều product tiêu thụ. Tenant meter phải chống duplicate và xác thực tenant ở server-side. Chi phí thấp hơn không phải kết quả tốt nếu availability, latency hoặc correctness suy giảm.

## 22. Ghi nhớ

Cost allocation biến hóa đơn cloud thành thông tin có thể hành động bằng cách gắn chi phí với product, service, environment, team, cost center và tenant. Tagging là nền tảng nhưng không đủ: shared infrastructure, network, database, observability và workload multi-tenant thường cần usage driver hoặc allocation rule riêng.

Một hệ thống phân bổ đáng tin phải có taxonomy, owner, dependency mapping, nguồn billing chính thức, quy tắc shared cost, cách xử lý discount/amortization và bucket unallocated minh bạch. Showback tạo visibility trước khi chargeback; unit economics giúp đánh giá cost-to-serve; budget và anomaly detection hỗ trợ hành động. Mọi quyết định tối ưu cần được đánh giá cùng SLO, business value, bảo mật và yêu cầu DR, để tiết kiệm chi phí không làm giảm chất lượng sản phẩm.
