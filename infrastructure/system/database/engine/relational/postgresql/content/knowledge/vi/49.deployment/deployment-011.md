# Đánh giá giới hạn dịch vụ được quản lý, chi phí và khả năng chuyển đổi

Khi triển khai PostgreSQL trên nền tảng cloud, đội ngũ thường phải lựa chọn giữa tự vận hành PostgreSQL trên máy ảo hoặc container và sử dụng dịch vụ PostgreSQL được quản lý (managed PostgreSQL). Dịch vụ được quản lý giảm công việc cài đặt, vá lỗi, backup, giám sát và failover, nhưng đi kèm giới hạn về quyền quản trị, cấu hình, extension, tài nguyên và cách vận hành. Chi phí cũng không chỉ là giá của instance: storage, I/O, backup, replica, truyền dữ liệu, giám sát và hỗ trợ đều có thể tạo thành phần đáng kể trong tổng chi phí.

Một quyết định triển khai tốt cần đánh giá đồng thời ba khía cạnh: **giới hạn dịch vụ có đáp ứng workload và yêu cầu vận hành không; tổng chi phí có phù hợp với tải thực tế và dự báo tăng trưởng không; và hệ thống có thể chuyển sang nhà cung cấp hoặc mô hình triển khai khác với mức gián đoạn, chi phí và rủi ro chấp nhận được không**. Những thông số cụ thể thay đổi theo nhà cung cấp, khu vực, phiên bản PostgreSQL, loại dịch vụ và gói cấu hình. Vì vậy, cần xác minh giới hạn hiện hành trong tài liệu và hợp đồng dịch vụ trước khi chốt kiến trúc.

## 1. Các mô hình triển khai PostgreSQL

### 1.1. Tự quản lý PostgreSQL

Đội ngũ cài PostgreSQL trên máy ảo, máy chủ vật lý hoặc container và chịu trách nhiệm vận hành toàn bộ stack:

- Cài đặt, nâng cấp major/minor version và quản lý extension.
- Cấu hình hệ điều hành, filesystem, storage, network và bảo mật.
- Backup, WAL archiving, PITR, replication, failover và diễn tập phục hồi.
- Giám sát, cảnh báo, tối ưu truy vấn, capacity planning và xử lý sự cố.
- Quản lý vòng đời máy chủ, vá lỗi, thay đổi cấu hình và kế hoạch DR.

Ưu điểm là quyền kiểm soát cao đối với hệ điều hành, extension, cấu hình và topology. Đội ngũ có thể thiết kế gần như mọi cơ chế PostgreSQL được hỗ trợ. Đổi lại, cần năng lực DBA/SRE, quy trình trực vận hành và ngân sách cho cả thời gian kỹ thuật lẫn hạ tầng dự phòng.

### 1.2. Managed PostgreSQL truyền thống

Nhà cung cấp vận hành control plane và nhiều tác vụ hạ tầng. Người dùng tạo database instance hoặc cluster qua console, API hay infrastructure as code. Dịch vụ thường cung cấp một phần hoặc toàn bộ các khả năng như:

- Cấp phát compute và storage.
- Backup tự động, lưu WAL và phục hồi theo thời điểm.
- High availability, standby và failover.
- Read replica, giám sát, log và cảnh báo.
- Vá lỗi hoặc nâng cấp theo lịch bảo trì.
- Tích hợp IAM, secret manager, mạng riêng và mã hóa.

Người dùng vẫn chịu trách nhiệm về schema, index, truy vấn, quyền trong database, thiết kế ứng dụng, capacity planning và kiểm thử nghiệp vụ. Nhà cung cấp quản lý máy chủ không có nghĩa là nhà cung cấp quản lý chất lượng dữ liệu hoặc hiệu năng ứng dụng.

### 1.3. Managed PostgreSQL tương thích hoặc dịch vụ mở rộng

Một số dịch vụ cung cấp giao diện tương thích PostgreSQL nhưng có kiến trúc storage, compute, replication hoặc extension riêng. Chúng có thể bổ sung khả năng scale, phân tán, đọc toàn cầu hoặc tích hợp sâu với nền tảng cloud.

Không nên đánh giá một dịch vụ chỉ dựa vào việc nó nhận cú pháp PostgreSQL. Cần xác định:

- Phiên bản và mức độ tương thích với PostgreSQL upstream.
- Hành vi của transaction, isolation, locking và SQL semantics.
- Extension nào có sẵn, bị giới hạn hoặc được thay bằng tính năng riêng.
- Khả năng dùng công cụ chuẩn như `pg_dump`, `pg_restore`, logical replication và các công cụ quan sát.
- Cách backup, restore, failover và nâng cấp thực tế.
- Phụ thuộc vào API, proxy, driver hoặc giao thức riêng của nhà cung cấp.

### 1.4. Serverless hoặc autoscaling database

Một số dịch vụ cung cấp khả năng tự động thay đổi compute, tạm dừng khi ít hoạt động hoặc scale theo tải. Mô hình này có thể phù hợp với workload biến động, môi trường phát triển, ứng dụng theo mùa hoặc workload có khoảng thời gian nhàn rỗi.

Đổi lại, cần đánh giá cold start, thời gian scale, giới hạn tốc độ tăng tài nguyên, connection behavior, mức compute tối thiểu, chi phí khi giữ tài nguyên nóng và cách tính tiền theo dung lượng lưu trữ hoặc request. Autoscaling không đồng nghĩa với tài nguyên vô hạn hoặc hiệu năng ổn định tức thời.

## 2. Xác định workload và yêu cầu trước khi so sánh nhà cung cấp

Không thể chọn dịch vụ phù hợp nếu chỉ so giá một instance có cùng số vCPU và RAM. Cần mô tả workload, mục tiêu dịch vụ và các phụ thuộc của ứng dụng trước.

### 2.1. Hồ sơ workload

| Nhóm thông tin | Dữ liệu cần thu thập | Vì sao cần |
|---|---|---|
| Dung lượng | Dữ liệu hiện tại, tốc độ tăng, index, WAL và dung lượng tạm | Xác định storage, khả năng mở rộng và chi phí backup. |
| Compute | CPU trung bình/đỉnh, RAM, cache hit, số truy vấn đồng thời | Chọn lớp compute và đánh giá headroom. |
| I/O | IOPS, throughput, latency đọc/ghi, tỷ lệ random/sequential | Kiểm tra giới hạn storage và mức I/O được tính phí. |
| Kết nối | Số connection đồng thời, tốc độ mở connection, pool size | Đánh giá `max_connections`, proxy và giới hạn kết nối. |
| Truy vấn | Loại query, join, transaction, batch, báo cáo nặng | Kiểm tra tương thích planner và hiệu năng. |
| Ghi dữ liệu | TPS, kích thước transaction, WAL generation, burst | Xác định khả năng ghi, replication và backup. |
| Tính sẵn sàng | RPO, RTO, SLA, cửa sổ bảo trì | Chọn HA, replica và DR. |
| Địa lý | Vị trí người dùng, ứng dụng, dữ liệu và DR | Đánh giá latency, residency và phí truyền dữ liệu. |
| Tăng trưởng | Tăng user, transaction, data và workload theo mùa | Ước lượng chi phí và điểm cần nâng cấp. |

Nên thu thập số liệu trong chu kỳ đại diện, bao gồm giờ cao điểm, batch cuối ngày, kỳ chốt sổ, đợt khuyến mãi hoặc sự kiện tăng tải. Số trung bình có thể che khuất những burst ngắn nhưng đủ làm dịch vụ chạm giới hạn.

### 2.2. Yêu cầu dịch vụ

Trước khi so sánh sản phẩm, hãy ghi rõ:

- RPO và RTO cho từng loại sự cố: lỗi instance, lỗi zone, lỗi region, lỗi logic và mất toàn bộ tài khoản cloud.
- SLA availability và mức gián đoạn chấp nhận được khi bảo trì, nâng cấp hoặc failover.
- Yêu cầu mã hóa, kiểm soát truy cập, audit, data residency và chứng nhận tuân thủ.
- Phiên bản PostgreSQL, extension, collation, locale và tính năng SQL bắt buộc.
- Mức độ cần truy cập OS, filesystem, replication slot, WAL, parameter và superuser.
- Yêu cầu tích hợp với CI/CD, secret manager, monitoring, backup catalog và hệ thống vận hành.
- Mức độ độc lập với nhà cung cấp và thời gian tối đa có thể dùng cho migration.

Phân loại yêu cầu thành **bắt buộc**, **mong muốn** và **có thể thay thế**. Một tính năng không hỗ trợ nhưng không nằm trên đường đi của workload có thể không phải lý do loại dịch vụ. Ngược lại, thiếu một extension bắt buộc hoặc không đạt RPO có thể là điều kiện loại ngay cả khi giá hấp dẫn.

## 3. Đánh giá giới hạn của managed PostgreSQL

Giới hạn dịch vụ thường nằm ở nhiều lớp. Một số giới hạn được công bố rõ ràng, một số phụ thuộc lớp instance hoặc được áp dụng động bởi control plane. Cần phân biệt giới hạn kỹ thuật, quota tài khoản và giới hạn theo hợp đồng.

### 3.1. Compute, memory và khả năng mở rộng

Kiểm tra các yếu tố:

- Số vCPU, RAM và các lớp instance có thể chọn.
- Tài nguyên tối thiểu/tối đa và các bước scale giữa các lớp.
- Scale dọc có cần restart hoặc failover hay không.
- Có thể scale compute độc lập với storage không.
- Có giới hạn về CPU credit, burst hoặc thời gian duy trì hiệu năng cao không.
- Serverless có scale-to-zero, cold start, ngưỡng scale và thời gian hội tụ ra sao.
- Tài nguyên có bị chia sẻ hoặc bị giới hạn bởi noisy neighbor theo loại dịch vụ không.

Một instance có nhiều vCPU hơn chưa chắc xử lý workload nhanh hơn nếu truy vấn bị giới hạn bởi I/O, lock contention, network hoặc thiết kế SQL. Cần benchmark bằng workload đại diện và kiểm tra latency ở percentile cao, không chỉ so TPS trung bình.

### 3.2. Storage, IOPS và throughput

Storage thường có nhiều cấu hình: loại volume, dung lượng provisioned, IOPS, throughput, khả năng autoscaling và độ trễ. Cần xác minh:

- Dung lượng nhỏ nhất/lớn nhất và cách tăng dung lượng.
- Có giảm dung lượng sau khi cấp phát hay phải tạo instance mới không.
- IOPS và throughput được cấp cố định, tính theo dung lượng hay giới hạn theo lớp instance.
- Hiệu năng burst có quota hoặc thời gian tích lũy không.
- Storage encryption, snapshot, backup và phí lưu trữ được tính thế nào.
- Temporary file, sort/hash spill và WAL có dùng chung quota hay storage riêng.
- Khi storage đầy, dịch vụ cảnh báo, tự mở rộng hay dừng ghi.

Đặc biệt, autoscaling storage có thể chỉ mở rộng một chiều. Nếu cấp dung lượng quá lớn để tránh đầy đĩa, chi phí có thể tiếp tục tăng ngay cả khi dữ liệu đã được dọn. Cần có cảnh báo ở nhiều ngưỡng, ví dụ dung lượng đã dùng, tốc độ tăng và thời gian dự kiến tới khi đầy.

### 3.3. Connection và giới hạn concurrency

PostgreSQL dùng process hoặc backend cho connection, vì vậy số lượng connection quá lớn có thể tiêu tốn RAM và làm tăng context switching. Managed service có thể áp dụng giới hạn `max_connections` theo memory hoặc lớp instance, giới hạn riêng trên proxy, hoặc quota kết nối theo tài khoản.

Kiểm tra:

- `max_connections` thực tế và khả năng thay đổi.
- Số connection dành riêng cho quản trị, replication và dịch vụ nội bộ.
- Có proxy/pooler do nhà cung cấp quản lý hay không.
- Pooler hỗ trợ transaction pooling, session pooling hay cả hai.
- Hành vi với prepared statement, temporary table, session variable, advisory lock và `LISTEN/NOTIFY` khi dùng transaction pooling.
- Giới hạn tốc độ mở connection, thời gian idle và timeout.
- Cách failover tác động đến connection pool và client retry.

Có thể kiểm tra trạng thái connection ở PostgreSQL:

```sql
SHOW max_connections;

SELECT
    state,
    count(*) AS connections
FROM pg_stat_activity
GROUP BY state
ORDER BY connections DESC;
```

Nếu ứng dụng tạo connection trực tiếp từ mỗi worker, tổng số connection có thể tăng nhanh theo số replica ứng dụng. Nên tính tổng connection tối đa từ mọi service, job, migration và công cụ quản trị, sau đó thiết kế pool có giới hạn.

### 3.4. Extension và quyền quản trị

Đây là một trong những khác biệt quan trọng nhất giữa PostgreSQL tự quản lý và managed PostgreSQL. Nhà cung cấp thường không cấp quyền superuser đầy đủ vì cần bảo vệ control plane và hạ tầng dùng chung. Một số thao tác được thực hiện qua role quản trị đặc biệt hoặc API riêng.

Kiểm tra danh sách extension có thể cài và phiên bản khả dụng:

```sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
```

Danh sách này cho biết extension mà server hiện tại công bố, nhưng không thay thế tài liệu dịch vụ: extension có thể hiện diện nhưng bị giới hạn chức năng, cần cấu hình đặc biệt hoặc không được hỗ trợ trong production tier.

Lập danh mục extension ứng dụng đang dùng, chẳng hạn:

- Extension phổ biến như `pg_stat_statements`, `uuid-ossp` hoặc `pgcrypto`.
- Extension phục vụ tìm kiếm, địa lý, vector hoặc phân tích.
- Extension cần shared preload libraries hoặc tham số server.
- Extension yêu cầu quyền superuser, truy cập filesystem hoặc cài binary ở OS.
- Extension tự phát triển hoặc phụ thuộc thư viện native.

Ngoài extension, cần kiểm tra khả năng thay đổi `shared_preload_libraries`, `wal_level`, `max_worker_processes`, `track_io_timing`, cấu hình logging, replication slot, logical replication, `COPY ... PROGRAM`, file access và các chức năng quản trị khác. Không giả định rằng quyền `rds_superuser` hoặc một role tương tự của nhà cung cấp có hành vi giống superuser PostgreSQL upstream.

### 3.5. Phiên bản PostgreSQL và vòng đời nâng cấp

Kiểm tra:

- Major version được cung cấp và thời điểm nhà cung cấp hỗ trợ phiên bản đó.
- Minor update có tự động áp dụng hay cần cửa sổ bảo trì.
- Có thể hoãn bản cập nhật bảo mật trong bao lâu.
- Nâng major version là in-place, tạo cluster mới hay bắt buộc migration.
- Có thể rollback sau major upgrade không, và trong bao lâu.
- Extension có tương thích với phiên bản đích không.
- Có môi trường staging để thử upgrade và kiểm tra extension trước production không.

Managed service có thể loại bỏ một số phiên bản cũ theo lịch riêng, khác với lịch hỗ trợ upstream. Nếu ứng dụng phụ thuộc một extension hoặc behavior cụ thể, phải kiểm tra thời gian hỗ trợ của cả PostgreSQL và extension. Nên lập kế hoạch nâng cấp trước ngày hết hỗ trợ để tránh bị buộc phải chuyển đổi trong thời gian ngắn.

### 3.6. Backup, PITR và retention

Không chỉ hỏi dịch vụ có backup tự động hay không. Cần xem:

- Backup tự động theo lịch và retention tối đa.
- PITR có sẵn không, độ phân giải và khoảng thời gian có thể phục hồi.
- Backup có thể khôi phục sang region, account hoặc project khác không.
- Có thể export backup về định dạng độc lập với nhà cung cấp không.
- Snapshot có nhất quán với transaction và extension hay không.
- Backup có được mã hóa bằng khóa do khách hàng quản lý không.
- Phí snapshot, backup vượt dung lượng, WAL và cross-region copy.
- Quy trình restore có cần tạo instance mới, có downtime và giới hạn số lần restore không.
- Nhà cung cấp có hỗ trợ kiểm thử restore định kỳ hoặc báo cáo tính toàn vẹn không.

Backup nội bộ của dịch vụ có thể rất thuận tiện khi phục hồi trong cùng nền tảng, nhưng chưa chắc là định dạng có thể dùng trực tiếp để dựng PostgreSQL trên hạ tầng khác. Nếu yêu cầu portability quan trọng, cần kiểm tra đường xuất dữ liệu và diễn tập restore sang môi trường độc lập.

### 3.7. HA, replica và DR

Managed service có thể cung cấp standby cùng zone, multi-zone HA, read replica hoặc cross-region replica. Các tính năng này có mục tiêu khác nhau:

| Khả năng | Mục tiêu | Điều cần xác minh |
|---|---|---|
| Standby HA cùng region | Giảm downtime khi lỗi node hoặc zone | RPO, RTO, cơ chế đồng bộ, failover tự động và quyền kiểm soát. |
| Read replica | Mở rộng tải đọc | Lag, consistency, khả năng promote và giới hạn số replica. |
| Cross-region replica | DR hoặc phục vụ người dùng ở vùng khác | Độ trễ WAN, RPO, chi phí truyền, promote và failback. |
| Backup copy ở region khác | Khôi phục khi mất region | Thời gian chuyển backup, retention và quyền truy cập độc lập. |

Một dịch vụ có nhãn “Multi-AZ” hoặc “HA” không tự động đáp ứng mọi RPO/RTO. Cần đọc cách đồng bộ, điều kiện failover, thời gian phát hiện, endpoint chuyển đổi, thời gian DNS hội tụ và các ngoại lệ trong SLA. Read replica cũng không luôn có thể promote ngay hoặc trở thành primary tương đương trong mọi cấu hình.

### 3.8. Network, bảo mật và giới hạn tích hợp

Đánh giá:

- Private network, VPC/VNet, subnet và khả năng truy cập từ nhiều vùng.
- TLS, certificate rotation, IAM database authentication và password policy.
- IP allowlist, firewall, private endpoint và giới hạn kết nối.
- KMS/customer-managed keys và quy trình xoay khóa.
- Audit log, query log, log export và thời gian lưu giữ.
- Tích hợp secret manager, monitoring, alerting và SIEM.
- Data residency, region availability và yêu cầu pháp lý.
- Quota API/control plane, tốc độ tạo instance, snapshot, replica và thao tác backup/restore.

Các quota control plane có thể ảnh hưởng đến khả năng tự động hóa, chẳng hạn giới hạn số instance, số API request, số snapshot hoặc số replica. Cần tính cả giới hạn này khi thiết kế CI/CD và quy trình DR, đặc biệt nếu cần tạo nhiều database mới cùng lúc sau sự cố vùng.

## 4. Đánh giá chi phí: nhìn vào tổng chi phí sở hữu

Giá niêm yết của một instance chỉ là một phần của chi phí. Một cấu hình có compute rẻ nhưng storage I/O đắt, backup retention lớn hoặc phí truyền dữ liệu cao có thể đắt hơn phương án khác khi chạy workload thực tế.

### 4.1. Các thành phần chi phí phổ biến

| Thành phần | Cách tính thường gặp | Câu hỏi cần đặt ra |
|---|---|---|
| Compute | Theo giờ, giây, lớp instance hoặc ACU/vCore | Có tính tiền standby và thời gian dừng không? |
| Storage | Theo GB-tháng hoặc dung lượng provisioned | Dung lượng cấp phát hay dung lượng dùng thực tế? |
| IOPS/throughput | Theo mức provisioned hoặc lượng I/O | Có gói I/O miễn phí, burst hay overage không? |
| Backup/snapshot | Theo dung lượng, retention hoặc bản sao | Phần backup miễn phí bằng dung lượng database hay có giới hạn khác? |
| WAL/archive | Theo storage và truyền dữ liệu | WAL giữ lâu hoặc phát sinh nhiều có tăng chi phí không? |
| HA/standby | Instance, storage hoặc phí HA riêng | Standby được tính như compute đầy đủ hay theo mức khác? |
| Read replica | Compute, storage và network | Mỗi replica có chi phí độc lập nào? |
| Network | Egress, cross-zone, cross-region hoặc internet | Dữ liệu truy vấn và replication đi qua vùng nào? |
| Monitoring/logging | Ingestion, retention, query và export | Log truy vấn nhiều có tạo phí đáng kể không? |
| Support | Gói hỗ trợ, SLA và dịch vụ tư vấn | Có bắt buộc gói hỗ trợ cao hơn để nhận SLA mong muốn không? |
| Migration | Công cụ, nhân lực, chạy song song và downtime | Có cần duy trì hai nền tảng trong giai đoạn chuyển đổi không? |

### 4.2. Ước lượng tổng chi phí hàng tháng

Một mô hình đơn giản:

\[
\text{TCO}_{month} = C_{compute} + C_{storage} + C_{io} + C_{backup}
 + C_{replica} + C_{network} + C_{monitoring} + C_{support}
\]

Khi so sánh nhiều phương án, nên tính cả chi phí vận hành nội bộ và chi phí chuyển đổi:

\[
\text{TCO}_{year} = 12 \times \text{TCO}_{month}
 + C_{engineering} + C_{migration} + C_{training}
\]

Đây là mô hình phân tích, không phải công thức tính hóa đơn của một nhà cung cấp cụ thể. Cần thay các thành phần bằng cách tính giá trong bảng giá và hợp đồng thực tế.

Ví dụ bảng dự toán:

| Hạng mục | Khối lượng giả định | Đơn giá | Chi phí tháng |
|---|---:|---:|---:|
| Primary compute | 730 giờ | Giá/giờ | Khối lượng × đơn giá |
| Standby HA | 730 giờ | Giá/giờ hoặc phí HA | Khối lượng × đơn giá |
| Storage | 800 GB-tháng | Giá/GB-tháng | Khối lượng × đơn giá |
| I/O provisioned | 6.000 IOPS-tháng | Giá/IOPS-tháng | Khối lượng × đơn giá |
| Backup vượt mức miễn phí | 300 GB-tháng | Giá/GB-tháng | Khối lượng × đơn giá |
| Cross-region egress | 500 GB | Giá/GB | Khối lượng × đơn giá |
| Monitoring/log ingestion | 100 GB | Giá/GB | Khối lượng × đơn giá |
| Support | 1 gói | Giá gói | Theo hợp đồng |

Các con số khối lượng ở đây chỉ minh họa cách lập mô hình; không phải giá hoặc giới hạn của nhà cung cấp. Hãy ghi rõ đơn vị thời gian, loại tiền tệ, region, loại storage, mức cam kết và thuế khi so sánh báo giá.

### 4.3. Tính chi phí theo workload thực tế

Để tránh dự toán thiếu, cần mô hình hóa ít nhất ba kịch bản:

- **Tải bình thường**: mức compute, I/O, storage và network thường gặp.
- **Tải đỉnh**: chiến dịch, cuối tháng, batch hoặc thời điểm nhiều người dùng cùng truy cập.
- **Sự cố/DR**: standby được promote, replica tăng tải, backup restore, cross-region transfer và hệ thống chạy song song.

Với autoscaling hoặc serverless, cần mô phỏng chu kỳ tăng/giảm tải, thời gian idle, cold start và mức compute tối thiểu. Một dịch vụ có thể rẻ trong giờ nhàn rỗi nhưng chi phí tăng nhanh khi giữ compute lớn liên tục.

### 4.4. Chi phí ẩn thường bị bỏ sót

**Backup và WAL:** retention dài, WAL phát sinh nhiều, snapshot nhiều bản hoặc backup copy ở region khác có thể tăng storage đáng kể.

**Network:** ứng dụng và database khác zone/region có thể phát sinh phí truyền dữ liệu và latency. Read replica ở vùng khác có chi phí truyền liên tục. Một truy vấn FDW hoặc batch ETL kéo nhiều dữ liệu qua mạng cũng có thể làm tăng egress.

**HA:** standby có thể cần compute và storage gần tương đương primary. Một số dịch vụ tính phí HA riêng, một số tính cả hai node. Cần đọc mô hình tính giá thay vì chỉ xem giá instance primary.

**Log và metric:** bật log mọi câu SQL hoặc lưu log dài ngày có thể tạo chi phí ingestion, indexing và retention. Nên xác định log nào cần thiết, sampling và chính sách lưu trữ.

**Tăng trưởng storage:** dung lượng tự mở rộng có thể làm hóa đơn tăng lâu dài. Xóa dữ liệu không nhất thiết làm giảm dung lượng provisioned hoặc chi phí ngay lập tức.

**Nâng cấp và migration:** chạy song song source/target, tạo snapshot, truyền dữ liệu ban đầu, kiểm thử, nhân sự và hỗ trợ chuyên gia đều có chi phí.

**Chi phí cơ hội:** dịch vụ thiếu tính năng có thể buộc đội ngũ xây thêm proxy, ETL, cache hoặc logic ứng dụng. Phần phát triển và bảo trì đó cũng thuộc TCO.

## 5. Kiểm soát và tối ưu chi phí

### 5.1. Right-size compute và storage

Chọn lớp tài nguyên dựa trên số liệu CPU, memory, cache hit, I/O latency, queue depth và concurrency. Tránh chọn theo số vCPU của máy chủ cũ rồi giữ nguyên mà không benchmark. Cần giữ headroom đủ cho peak và failover, nhưng cũng tránh cấp phát dư thừa kéo dài.

Storage cần dựa trên dữ liệu, index, WAL, temp file, growth và backup. Dự báo theo tháng/quý để biết khi nào cần mở rộng. Nếu dịch vụ không hỗ trợ thu nhỏ storage, hãy tính trước chi phí của việc cấp phát dư.

### 5.2. Tối ưu truy vấn và kết nối

Tối ưu query có thể giảm CPU, I/O và network, qua đó trì hoãn việc nâng lớp instance. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường phù hợp để xác định scan, join, sort và buffer hit. Kiểm tra `pg_stat_statements` nếu dịch vụ hỗ trợ extension này.

Connection pooling giảm số backend và chi phí mở kết nối. Tuy nhiên, cần kiểm thử hành vi session state, prepared statements, transaction và advisory locks trước khi bật transaction pooling.

### 5.3. Thiết kế retention và backup theo yêu cầu

Retention phải đáp ứng mục tiêu phục hồi và yêu cầu pháp lý, không nên chọn dài nhất chỉ vì có thể. Phân biệt backup vận hành nhanh, backup lưu trữ dài hạn và bản sao DR. Có chính sách lifecycle và kiểm thử restore định kỳ cho từng loại.

### 5.4. Đặt ngân sách và cảnh báo

Thiết lập budget theo project, môi trường và workload. Cảnh báo khi:

- Compute tăng bất thường hoặc autoscaling duy trì ở mức cao.
- Storage tăng nhanh hoặc gần ngưỡng quota.
- Backup/WAL vượt dự toán.
- Egress hoặc cross-region traffic tăng.
- Log ingestion vượt mức bình thường.
- Có instance, replica hoặc snapshot không còn owner.

Tag tài nguyên theo môi trường, ứng dụng, owner và cost center để phân bổ chi phí. Đánh giá chi phí trên mỗi đơn hàng, mỗi triệu truy vấn hoặc mỗi GB dữ liệu có thể hữu ích hơn chỉ nhìn tổng hóa đơn.

## 6. Khả năng chuyển đổi và rủi ro phụ thuộc nhà cung cấp

Portability là khả năng chuyển database và workload sang dịch vụ khác hoặc PostgreSQL tự quản lý với mức công sức, gián đoạn và rủi ro có thể dự đoán. Portability không có nghĩa mọi dịch vụ tương thích PostgreSQL đều thay thế nhau hoàn toàn.

### 6.1. Các lớp phụ thuộc

| Lớp | Ví dụ phụ thuộc | Tác động khi chuyển đổi |
|---|---|---|
| SQL và data type | Cú pháp riêng, type hoặc function không thuộc upstream | Cần sửa query, schema hoặc dữ liệu. |
| Extension | Extension không có ở đích hoặc khác phiên bản | Phải thay thế tính năng, chuyển dữ liệu hoặc chọn đích khác. |
| Quyền quản trị | Role đặc biệt, API quản trị, không có superuser | Runbook và công cụ triển khai phải viết lại. |
| Cấu hình | Parameter group, tham số bị khóa hoặc giá trị mặc định riêng | Hiệu năng và hành vi có thể thay đổi. |
| Backup | Snapshot độc quyền hoặc format riêng | Cần export/import hoặc công cụ trung gian. |
| Replication | CDC/API riêng, không hỗ trợ logical replication chuẩn | Cần thiết kế lại đồng bộ và cutover. |
| Network | Private endpoint, proxy, DNS, IAM auth | Ứng dụng và hạ tầng kết nối phải thay đổi. |
| Bảo mật | KMS, IAM, secret manager, audit | Phải chuyển khóa, danh tính và chính sách. |
| Monitoring | Metric, log và alert theo nền tảng | Dashboard, SLO và runbook phải tái tạo. |
| Automation | Terraform provider, API và control plane riêng | Pipeline tạo, nâng cấp và khôi phục phải thay đổi. |

### 6.2. Dùng tính năng PostgreSQL chuẩn khi có thể

Để tăng khả năng chuyển đổi:

- Ưu tiên SQL và data type thuộc PostgreSQL upstream.
- Hạn chế phụ thuộc vào function, extension hoặc syntax riêng nếu không tạo giá trị rõ ràng.
- Lưu DDL và migration trong repository, chạy được trên PostgreSQL tương thích.
- Quản lý role, grant, schema và extension bằng script có thể tái thực thi.
- Dùng driver và giao thức PostgreSQL chuẩn, tránh hard-code endpoint hoặc API riêng trong business logic.
- Tách cấu hình kết nối, TLS, secret và pooler khỏi mã ứng dụng.
- Duy trì backup logic độc lập và kiểm tra khả năng `pg_dump`/`pg_restore` khi dịch vụ hỗ trợ.
- Ghi lại các tham số cấu hình quan trọng cùng giá trị và lý do, thay vì dựa vào mặc định của nhà cung cấp.

Không phải lúc nào cũng nên tránh tính năng riêng. Một tính năng độc quyền có thể đem lại lợi ích lớn về hiệu năng, HA hoặc vận hành. Cần ghi rõ lợi ích, chi phí chuyển đổi và phương án thay thế trước khi sử dụng.

### 6.3. Thiết kế lớp cấu hình độc lập

Ứng dụng nên nhận cấu hình database từ environment hoặc secret manager:

```text
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USER
DATABASE_PASSWORD_REFERENCE
DATABASE_SSL_MODE
DATABASE_POOL_MAX
DATABASE_CONNECT_TIMEOUT
```

Tên biến chỉ là ví dụ. Điểm chính là ứng dụng không chứa hostname, credential hoặc quy tắc endpoint cố định trong mã. Khi chuyển dịch vụ, đội ngũ có thể thay cấu hình và secret theo môi trường mà không phải sửa business logic.

Tương tự, dùng migration tool độc lập với console của nhà cung cấp. Các thao tác cần API riêng nên nằm trong lớp adapter hoặc module hạ tầng, có tài liệu và kiểm thử riêng. Không nên để API cloud xuất hiện rải rác trong logic nghiệp vụ.

### 6.4. Lập danh mục tính năng riêng của nhà cung cấp

Với mỗi tính năng riêng, ghi:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Tên tính năng | Tên sản phẩm/API/extension hoặc hành vi riêng. |
| Mục đích | Vấn đề nào được giải quyết? |
| Phạm vi sử dụng | Thành phần nào của ứng dụng phụ thuộc? |
| Lợi ích | Hiệu năng, availability, chi phí hoặc giảm công vận hành. |
| Phương án thay thế | Cơ chế PostgreSQL chuẩn hoặc dịch vụ khác có thể thay thế. |
| Công sức chuyển đổi | Thay đổi schema, code, dữ liệu, automation và vận hành. |
| Rủi ro | Downtime, mất dữ liệu, chênh lệch hiệu năng hoặc thay đổi semantics. |
| Người sở hữu | Ai chịu trách nhiệm theo dõi và cập nhật escape plan? |

Danh mục này giúp đội ngũ biết phần nào của kiến trúc có thể chuyển dễ dàng và phần nào đã tạo lock-in. Nó cũng giúp đánh giá lại quyết định khi giá, giới hạn hoặc roadmap nhà cung cấp thay đổi.

## 7. Lập kế hoạch chuyển đổi sang nền tảng khác

Một escape plan có giá trị khi được thử, có thời gian và chi phí ước tính, và có người chịu trách nhiệm. Tài liệu chỉ ghi “có thể dùng `pg_dump`” chưa đủ nếu database lớn, extension không tương thích hoặc RTO không cho phép downtime dài.

### 7.1. Chọn phương pháp migration

| Phương pháp | Cách hoạt động | Phù hợp | Hạn chế |
|---|---|---|---|
| `pg_dump`/`pg_restore` | Export logic rồi import ở đích | Database nhỏ/vừa, migration có cửa sổ downtime, chọn lọc đối tượng | Thời gian dump/restore có thể dài; không phải đồng bộ liên tục. |
| Physical backup/restore | Chuyển data directory và WAL theo cơ chế vật lý | Đích tương thích về phiên bản và kiến trúc; dịch vụ cho phép truy cập backup vật lý | Managed service có thể không cung cấp file vật lý dùng được bên ngoài. |
| Logical replication | Đồng bộ thay đổi bảng từ source sang target | Cần giảm downtime cho workload hỗ trợ logical replication | DDL, sequence, large object và một số đối tượng cần xử lý riêng. |
| CDC pipeline | Đọc thay đổi qua log/connector rồi ghi vào đích | Nhiều nguồn/đích, biến đổi hoặc đồng bộ tùy chỉnh | Tăng thành phần vận hành, lag và xử lý exactly-once/idempotency phức tạp. |
| ETL theo batch | Xuất và nạp theo lịch hoặc watermark | Workload phân tích, chấp nhận độ trễ | Không phù hợp nếu cần cutover gần như không gián đoạn. |

`pg_dump` là đường chuyển đổi logic phổ biến, nhưng cần kiểm tra phiên bản client/server, quyền, extension, collation, role, large object, ownership và object phụ thuộc. Với database lớn, thời gian restore và tạo index có thể là yếu tố chi phối.

Logical replication có thể giảm thời gian dừng ghi, nhưng không đồng bộ mọi loại DDL. Cần chuẩn bị schema đích tương thích trước, theo dõi replication lag và đồng bộ sequence trước khi mở ghi. Một số dịch vụ quản lý replication slot hoặc quyền replication theo cách riêng, vì vậy phải xác minh hỗ trợ cụ thể.

### 7.2. Quy trình migration tổng quát

```text
Khảo sát source và target
          |
          v
Kiểm tra tương thích schema/extension
          |
          v
Tạo target và cấu hình bảo mật
          |
          v
Nạp dữ liệu ban đầu
          |
          v
Đồng bộ thay đổi phát sinh (nếu có)
          |
          v
Đối soát dữ liệu và benchmark
          |
          v
Đóng ghi source / chờ đồng bộ cuối
          |
          v
Chuyển endpoint ứng dụng
          |
          v
Kiểm thử nghiệp vụ và giám sát
          |
          v
Chốt migration hoặc rollback theo tiêu chí
```

### 7.3. Các bước chuẩn bị

1. **Inventory**: thu thập database, schema, bảng, index, constraint, sequence, view, function, trigger, extension, role và quyền.
2. **Compatibility check**: so sánh phiên bản PostgreSQL, extension, type, collation, locale, parameter và tính năng riêng.
3. **Capacity plan**: dự báo compute, memory, storage, IOPS, connection, WAL và network ở đích.
4. **Security plan**: tạo role, secret, TLS, network policy, audit và quyền tối thiểu.
5. **Migration rehearsal**: chạy thử trên bản sao dữ liệu gần production, đo thời gian và phát hiện lỗi.
6. **Data validation**: xác định row count, checksum theo phạm vi, tổng tiền, trạng thái và các bất biến nghiệp vụ.
7. **Cutover plan**: quy định freeze ghi, đồng bộ cuối, chuyển endpoint, kiểm tra và rollback.
8. **Rollback boundary**: xác định thời điểm nào còn có thể quay lại source mà không mất dữ liệu mới phát sinh.

### 7.4. Cutover và rollback

Trước cutover, cần thống nhất ai có quyền quyết định. Một trình tự thường gặp:

- Thông báo cửa sổ chuyển đổi và tạm dừng các job có thể ghi dữ liệu.
- Chặn hoặc đưa ứng dụng vào read-only mode theo cách có thể xác nhận.
- Chờ transaction đang chạy kết thúc và ghi nhận watermark cuối.
- Chờ logical replication/CDC bắt kịp hoặc hoàn tất batch cuối.
- Đối soát các bảng và bất biến quan trọng.
- Chuyển secret/endpoint, làm mới pool và khởi động luồng ghi ở target.
- Chạy smoke test, theo dõi error rate, latency và số liệu nghiệp vụ.

Rollback sau khi target đã nhận ghi không đơn giản là đổi DNS về source. Source có thể thiếu các giao dịch mới phát sinh trên target. Cần xác định trước một trong các chính sách: rollback chỉ trước khi mở ghi; reverse replication/CDC đã được chuẩn bị; hoặc khôi phục từ backup và chấp nhận một mức mất dữ liệu được phê duyệt. Không được mở hai phía ghi độc lập nếu chưa có cơ chế đồng bộ và giải quyết xung đột.

### 7.5. Diễn tập exit plan

Nên thực hiện migration thử theo chu kỳ hoặc sau thay đổi kiến trúc lớn. Đo:

- Thời gian export/import và đồng bộ cuối.
- Phí egress, snapshot, storage tạm và chạy song song.
- Tỷ lệ lỗi object/extension và số thay đổi code cần thiết.
- Độ chênh dữ liệu trước/sau cutover.
- Thời gian ứng dụng chuyển endpoint và phục hồi connection pool.
- RPO/RTO thực tế khi migration lỗi hoặc phải rollback.
- Công sức kỹ thuật và các thao tác phụ thuộc console/API nhà cung cấp.

Một exit plan đã được diễn tập giúp biến lock-in thành rủi ro có thể định lượng. Nếu không thể chuyển trong giới hạn downtime, cần quyết định rõ có chấp nhận lock-in đó hay đầu tư thêm lớp tương thích và cơ chế đồng bộ.

## 8. Xây dựng ma trận đánh giá nhà cung cấp

### 8.1. Điều kiện loại và tiêu chí chấm điểm

Nên tách tiêu chí bắt buộc khỏi tiêu chí có trọng số. Ví dụ, nếu dịch vụ không hỗ trợ extension cần thiết hoặc không đạt RPO tối thiểu, điểm giá rẻ không thể bù được điều kiện thiếu.

| Nhóm | Câu hỏi đánh giá | Bằng chứng |
|---|---|---|
| PostgreSQL compatibility | Phiên bản, SQL, extension và type có tương thích? | Test suite, danh sách extension, migration rehearsal. |
| Resource limits | Compute, storage, IOPS, connection và quota có đủ? | Tài liệu quota, benchmark và số liệu workload. |
| Availability | HA, failover, maintenance và SLA đáp ứng? | SLA, architecture docs, drill report. |
| Backup/DR | PITR, retention, cross-region restore và export có đủ? | Restore rehearsal và báo cáo RPO/RTO. |
| Security/compliance | IAM, TLS, KMS, audit, residency có đáp ứng? | Tài liệu bảo mật, chứng nhận và cấu hình thử. |
| Cost | TCO ở tải thường, peak và DR? | Cost model, báo giá và billing thử nghiệm. |
| Portability | Có thể dump/restore, logical replication hoặc CDC? | Exit plan và migration rehearsal. |
| Operations | Monitoring, support, maintenance và automation? | Runbook, API, support terms và thử nghiệm. |

### 8.2. Ví dụ ma trận có trọng số

Có thể chấm mỗi tiêu chí từ 1 đến 5, trong đó 1 là không đáp ứng và 5 là đáp ứng rất tốt. Trọng số phải phản ánh mức độ quan trọng của workload:

| Tiêu chí | Trọng số ví dụ | Nhà cung cấp A | Nhà cung cấp B |
|---|---:|---:|---:|
| Tương thích PostgreSQL/extension | 20% |  |  |
| RPO/RTO và HA | 20% |  |  |
| Hiệu năng và giới hạn tài nguyên | 15% |  |  |
| Tổng chi phí sở hữu | 20% |  |  |
| Bảo mật và tuân thủ | 10% |  |  |
| Portability/exit cost | 10% |  |  |
| Công cụ vận hành và hỗ trợ | 5% |  |  |

Điểm tổng hợp có thể tính:

\[
\text{Score} = \sum_i (\text{Weight}_i \times \text{Rating}_i)
\]

Trọng số và điểm chỉ hỗ trợ quyết định; không nên để tổng điểm che mất một điều kiện loại bắt buộc. Ghi nguồn bằng chứng và mức độ tin cậy cho từng điểm. Nếu chưa benchmark, đánh dấu chưa xác minh thay vì tự gán điểm.

### 8.3. Đánh giá theo nhiều kịch bản

Không nên chỉ chấm một cấu hình ở tải hiện tại. Tối thiểu hãy tính:

- Workload hiện tại và tăng trưởng dự kiến trong 12–36 tháng.
- Peak traffic và batch workload.
- HA/DR khi phải chạy nhiều node hoặc region.
- Khôi phục backup và migration sang nền tảng khác.
- Kịch bản giá tăng, quota thay đổi hoặc phiên bản bị ngừng hỗ trợ.

So sánh cả chi phí đơn vị, chẳng hạn chi phí trên một triệu transaction thành công, thay vì chỉ tổng tiền. Đồng thời xem hiệu năng ở p95/p99 và error rate để tránh phương án có giá thấp nhưng không đạt trải nghiệm người dùng.

## 9. Ví dụ phân tích một hệ thống bán hàng

Giả sử hệ thống bán hàng có database PostgreSQL 500 GB, workload ghi đều trong ngày và tăng mạnh vào các chiến dịch. Ứng dụng cần RPO tối đa 1 phút, RTO tối đa 15 phút cho giao dịch bán hàng. Hệ thống dùng một extension phổ biến để theo dõi query, một extension nghiệp vụ và một số function/trigger tự viết.

### 9.1. Đánh giá giới hạn

Đội ngũ cần xác nhận dịch vụ có extension nghiệp vụ, phiên bản tương thích, quyền tạo function/trigger, giới hạn connection và khả năng đồng bộ standby đáp ứng RPO. Nếu extension nghiệp vụ cần superuser hoặc thư viện native mà dịch vụ không cho cài, đó là điều kiện loại hoặc cần thay thế trước migration.

Đồng thời benchmark tải chiến dịch: CPU, memory, IOPS, storage throughput, WAL generation và p99 latency. Cần kiểm tra thời gian scale lên, thời gian failover và connection pool khi endpoint thay đổi.

### 9.2. Đánh giá chi phí

Mô hình chi phí phải bao gồm primary, standby HA, storage, IOPS, backup retention, log, network và support. Kịch bản DR cần tính thêm cross-region replica hoặc backup copy, storage ở vùng phụ và chi phí truyền dữ liệu. Nếu dùng read replica cho báo cáo, cộng cả compute, storage và lag monitoring.

Đánh giá thêm chi phí khi chạy song song source và target trong migration rehearsal, bởi database 500 GB có thể cần nhiều giờ hoặc nhiều ngày để chuyển và đối soát tùy network, index và workload.

### 9.3. Đánh giá portability

Lập danh mục DDL, extension, role, job, parameter và endpoint. Thử dựng PostgreSQL đích độc lập bằng migration script và `pg_dump`/`pg_restore`. Nếu cần downtime thấp, thử logical replication và xác định cách đồng bộ sequence, DDL, large object và các bảng không có khóa phù hợp.

Kết quả quyết định có thể là dùng managed PostgreSQL cho primary vì giảm gánh nặng HA, nhưng vẫn duy trì backup logic định kỳ và bộ migration có thể chạy trên PostgreSQL upstream. Nếu extension đặc thù không có ở dịch vụ, cần tính công sức thay thế và chạy benchmark trước khi chốt.

## 10. Runbook đánh giá trước khi đưa vào production

Một quy trình đánh giá có thể chia thành các giai đoạn:

### Giai đoạn 1: Khảo sát và điều kiện bắt buộc

- [ ] Ghi nhận phiên bản PostgreSQL, extension, schema và quyền cần thiết.
- [ ] Thu thập workload, peak, storage growth, connection và I/O.
- [ ] Xác định RPO/RTO, SLA, residency và yêu cầu compliance.
- [ ] Xác định tính năng bắt buộc và điều kiện loại dịch vụ.
- [ ] Kiểm tra tài liệu quota, giới hạn và vòng đời phiên bản.

### Giai đoạn 2: Benchmark và kiểm tra giới hạn

- [ ] Dựng môi trường thử với cấu hình gần production.
- [ ] Chạy query và transaction đại diện ở tải bình thường và peak.
- [ ] Kiểm tra connection pooling, failover và reconnect.
- [ ] Kiểm tra extension, quyền, tham số và log.
- [ ] Thử backup, PITR và restore sang môi trường độc lập.
- [ ] Đo p95/p99 latency, throughput, error rate và resource utilization.

### Giai đoạn 3: Cost model và vận hành

- [ ] Lập dự toán compute, storage, I/O, backup, HA, replica, network, log và support.
- [ ] Tính kịch bản tăng trưởng, peak, DR và chạy song song khi migration.
- [ ] Thiết lập tag, budget, alert và dashboard chi phí.
- [ ] Xác định maintenance window, nâng cấp và quy trình hỗ trợ sự cố.
- [ ] Xác định ai chịu trách nhiệm schema, query, backup policy và bảo mật.

### Giai đoạn 4: Portability và quyết định

- [ ] Lập danh mục tính năng riêng và phụ thuộc nhà cung cấp.
- [ ] Chạy thử export/import hoặc logical migration sang PostgreSQL độc lập.
- [ ] Đo thời gian, chi phí egress, sai lệch dữ liệu và downtime.
- [ ] Xác định cutover, rollback boundary và người có quyền quyết định.
- [ ] Chấm ma trận nhà cung cấp bằng bằng chứng đã kiểm chứng.
- [ ] Lưu quyết định kiến trúc, rủi ro chấp nhận và ngày đánh giá lại.

## 11. Những hiểu lầm thường gặp

| Nhận định | Thực tế cần kiểm tra |
|---|---|
| Managed PostgreSQL không cần DBA/SRE | Nhà cung cấp quản lý hạ tầng; ứng dụng vẫn cần quản lý query, schema, quyền, capacity và khôi phục nghiệp vụ. |
| Tương thích PostgreSQL nghĩa là thay thế hoàn toàn | Extension, superuser, parameter, replication và behavior có thể khác. |
| HA có nghĩa là không mất dữ liệu | RPO phụ thuộc đồng bộ WAL, topology và loại sự cố; cần đọc cam kết cụ thể. |
| Có backup tự động là đủ | Phải kiểm thử restore, retention, PITR, quyền truy cập và khả năng phục hồi ngoài provider. |
| Giá instance là toàn bộ chi phí | Storage, I/O, backup, standby, replica, egress, log và support có thể lớn. |
| Autoscaling luôn rẻ hơn | Scale có độ trễ, mức tối thiểu, cold start và chi phí compute khi tải cao. |
| Dùng PostgreSQL protocol là không lock-in | Control plane, backup, IAM, extension, monitoring và replication vẫn có thể độc quyền. |
| Có thể rollback bằng cách đổi DNS | Sau khi target nhận ghi, source có thể thiếu dữ liệu; cần reverse sync hoặc rollback boundary rõ. |
| `pg_dump` là escape plan đầy đủ | Cần thử extension, role, large object, collation, object phụ thuộc, thời gian restore và cutover. |

## 12. Kết luận

Managed PostgreSQL có thể giảm đáng kể công việc vận hành database, nhưng cần đánh giá kỹ giới hạn về tài nguyên, connection, extension, quyền quản trị, phiên bản, backup, HA, network và quota control plane. Chi phí phải được tính theo tổng thể compute, storage, I/O, backup, replica, network, log, support và công sức migration. Khả năng chuyển đổi cần được thiết kế từ đầu bằng SQL và migration có thể tái sử dụng, danh mục tính năng riêng, đường export dữ liệu và diễn tập exit plan.

Một quyết định triển khai đáng tin cậy dựa trên workload thực tế, bằng chứng benchmark, tài liệu giới hạn hiện hành, mô hình TCO nhiều kịch bản và một lần migration thử. Dịch vụ được chọn cần đáp ứng yêu cầu nghiệp vụ hôm nay, có đường tăng trưởng phù hợp và có phương án chuyển đổi rõ ràng nếu chi phí, giới hạn hoặc chiến lược nhà cung cấp thay đổi.

## Tài liệu tham khảo

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/)
- [PostgreSQL — SQL Dump](https://www.postgresql.org/docs/current/backup-dump.html)
- [PostgreSQL — Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Server Configuration](https://www.postgresql.org/docs/current/runtime-config.html)
- [PostgreSQL — Client Applications: pg_dump and pg_restore](https://www.postgresql.org/docs/current/reference-client.html)
