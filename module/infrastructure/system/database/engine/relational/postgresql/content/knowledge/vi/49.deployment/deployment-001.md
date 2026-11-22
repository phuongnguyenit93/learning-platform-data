# Lựa chọn máy chủ riêng, container hoặc dịch vụ PostgreSQL được quản lý

## 1. Chọn mô hình triển khai PostgreSQL theo nhu cầu vận hành

PostgreSQL có thể chạy trên máy chủ vật lý riêng, máy ảo (VM), container hoặc dịch vụ database được nhà cung cấp quản lý. Các lựa chọn này đều có thể chạy cùng một PostgreSQL engine, nhưng khác nhau về quyền kiểm soát hạ tầng, cách lưu trữ dữ liệu, quy trình cập nhật, tính sẵn sàng cao (HA), backup, bảo mật, khả năng mở rộng và khối lượng công việc mà đội ngũ phải tự vận hành.

**Máy chủ riêng** thường đem lại quyền kiểm soát lớn đối với OS, filesystem, storage, network và PostgreSQL configuration. Đổi lại, đội ngũ chịu trách nhiệm provisioning, hardening, monitoring, backup, patching, failover và phục hồi.

**Container** đóng gói PostgreSQL cùng runtime dependencies để triển khai nhất quán giữa các môi trường. Container giúp quản lý image, version và deployment lifecycle, nhưng không tự giải quyết persistence, HA, backup hay data-directory upgrade. Một container PostgreSQL vẫn cần storage bền vững và quy trình vận hành database đúng cách.

**Dịch vụ PostgreSQL được quản lý (managed PostgreSQL)** chuyển một phần công việc hạ tầng và database operations sang cloud provider hoặc platform vendor. Nhà cung cấp có thể quản lý provisioning, patching, backups, replicas, failover và monitoring ở mức dịch vụ. Người dùng đổi lại một phần quyền kiểm soát, phụ thuộc vào feature set, limits, pricing và quy trình của provider.

Không có mô hình tốt nhất cho mọi hệ thống. Lựa chọn phải dựa trên workload, availability/recovery objectives, compliance, data residency, kỹ năng vận hành, ngân sách, tốc độ phát triển và khả năng chấp nhận vendor dependency.

```text
                 PostgreSQL workload
                         |
                         v
              Define operational needs
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
     Control and      Fast managed     Portable,
     customization    operations       reproducible runtime
          |              |               |
          v              v               v
   Dedicated host    Managed service   Container platform
          |              |               |
          +--------------+---------------+
                         |
                         v
             Validate HA, backup, restore,
             security, cost and portability
```

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt PostgreSQL trên máy chủ riêng, VM, container và managed service.
2. Hiểu phần việc nào thuộc PostgreSQL, OS, container platform và provider.
3. Chọn mô hình dựa trên workload và yêu cầu production.
4. Đánh giá quyền kiểm soát so với gánh nặng vận hành.
5. Thiết kế persistent storage và filesystem cho PostgreSQL.
6. Hiểu vì sao container restart không phải database recovery.
7. Đánh giá Kubernetes StatefulSet/operator và các failure modes.
8. So sánh HA, failover, backup và PITR giữa các mô hình.
9. Lập kế hoạch security, network, secrets và access control.
10. Quản lý minor updates, major upgrades và extension compatibility.
11. Tính TCO gồm compute, storage, backups, network và nhân lực.
12. Đánh giá performance, limits, scaling và noisy neighbors.
13. Tránh vendor lock-in và xây exit strategy.
14. Chọn mô hình cho development, staging, production và regulated workloads.
15. Xây checklist, decision matrix và runbook trước khi triển khai.

---

## 2. Bốn lớp cần tách biệt khi đánh giá deployment

Một deployment PostgreSQL có ít nhất bốn lớp:

1. **PostgreSQL engine**: SQL, transactions, WAL, MVCC, indexes, extensions, roles và database configuration.
2. **Compute/operating system**: CPU, RAM, kernel, filesystem, storage drivers, process supervision, time synchronization và OS security.
3. **Deployment platform**: physical server, hypervisor/VM, container runtime, Kubernetes hoặc managed database control plane.
4. **Operations**: monitoring, backup, restore, failover, upgrades, incident response, capacity planning và access management.

### 2.1. PostgreSQL không tự quản lý toàn bộ host

PostgreSQL quản lý data files, WAL và database processes, nhưng không tự vá OS, thay ổ đĩa, cấu hình firewall hoặc bảo vệ cloud credentials.

### 2.2. Container không thay thế database engine

Container image cung cấp PostgreSQL binaries và runtime environment. PostgreSQL vẫn cần data directory, WAL, durable storage, backups và lifecycle management.

### 2.3. Managed không có nghĩa mọi thứ đều tự động

Provider có thể tự động hóa một số tasks, nhưng người dùng vẫn cần schema design, query tuning, roles, application compatibility, backup policy, restore testing và capacity decisions.

### 2.4. Phân định trách nhiệm trước khi ký hợp đồng

Với mỗi control, ghi rõ ai sở hữu: provider, platform team, database team hay application team. Các mục như encryption keys, patch window, failover, restore và incident escalation cần có owner cụ thể.

## 3. Máy chủ riêng là gì?

Trong bài này, máy chủ riêng bao gồm máy vật lý do tổ chức sở hữu/thuê và VM mà đội ngũ trực tiếp quản lý. PostgreSQL được cài như service trên OS.

Một máy chủ có thể:
- Chạy PostgreSQL trực tiếp trên Linux/Windows Server.
- Chạy nhiều PostgreSQL clusters/major versions trên cùng host.
- Dùng local NVMe, RAID, SAN hoặc network-attached block storage.
- Kết hợp primary với standby trên các hosts khác.
- Dùng monitoring, backup và configuration-management agents riêng.

### 3.1. Bare metal

Bare metal là server vật lý không đi qua hypervisor do khách hàng quản lý. Có thể kiểm soát hardware, storage topology và performance isolation tốt hơn, nhưng provisioning, replacement và capacity expansion thường chậm hơn.

### 3.2. Virtual machine

VM cung cấp compute/storage/network ảo hóa. Dễ tạo snapshot/template và thay đổi instance size hơn physical hardware, nhưng có thể chia sẻ tài nguyên host với workloads khác.

### 3.3. Dedicated VM/instance

Một cloud provider có thể bán dedicated host hoặc instance với mức isolation nhất định. Cần đọc chính xác guarantee về CPU, memory, storage và tenancy.

### 3.4. Không đồng nghĩa một server duy nhất

Một deployment tự quản lý vẫn có thể gồm primary, standby, backup host, proxy và monitoring nodes. “Dedicated server” mô tả cách sở hữu/vận hành compute, không quyết định topology HA.

## 4. Ưu điểm của máy chủ riêng

- Kiểm soát OS packages, kernel settings và filesystem.
- Chọn storage devices, RAID/layout và mount options.
- Cài extensions hoặc custom PostgreSQL builds theo nhu cầu.
- Điều chỉnh cấu hình database và OS ở mức sâu.
- Tùy biến network, firewall, routing và security agents.
- Chủ động maintenance windows và upgrade sequencing.
- Có thể dùng platform/hardware chuyên biệt cho workload.
- Ít phụ thuộc vào giới hạn tính năng của một managed provider.

### 4.1. Extension flexibility

Một số extensions hoặc native libraries không được provider managed hỗ trợ. Self-managed có thể cài package tương thích hoặc build theo hướng dẫn, nhưng phải chịu trách nhiệm security và upgrade.

### 4.2. Storage control

Có thể chọn local NVMe, RAID, filesystem và I/O policy phù hợp. Điều này hữu ích cho workload nhạy với latency, nhưng cần hiểu durability và failure behavior của từng storage layout.

### 4.3. Configuration control

Có quyền điều chỉnh nhiều OS/database parameters. Quyền này cần change management và benchmark; không phải mọi kernel/database tweak đều cải thiện performance.

### 4.4. Portability

Một cluster PostgreSQL chuẩn có thể di chuyển giữa hosts/platforms bằng backup/restore, replication hoặc logical migration. Portability vẫn phụ thuộc extensions, OS architecture, locale, storage và operational tooling.

## 5. Chi phí và trách nhiệm của máy chủ riêng

Máy chủ riêng chuyển phần lớn operational work sang đội ngũ:

- Provisioning và hardware/VM lifecycle.
- OS installation, hardening và patching.
- PostgreSQL installation/configuration.
- TLS, certificates, firewall và identity.
- Backup, WAL archiving và restore tests.
- Streaming replication, failover và fencing.
- Monitoring, logs, alerting và on-call.
- Capacity planning và storage expansion.
- Minor updates, major upgrades và extension upgrades.
- Incident response, replacement và disaster recovery.

### 5.1. Nhân lực là một phần của chi phí

Giá server không phải TCO. Tính thời gian DBA/SRE, on-call coverage, maintenance, incident recovery, backup storage và security review.

### 5.2. Phải có owner cho từng lớp

Nếu không có người chịu trách nhiệm OS patching, backup verification hoặc failover, self-managed production dễ trở thành hệ thống không ai thực sự vận hành.

### 5.3. Hardware failure là trách nhiệm của bạn

Ổ đĩa, RAM, NIC, power supply hoặc host có thể lỗi. Cần spare capacity, replacement process, replication và recovery plan.

### 5.4. Maintenance window

OS kernel update, firmware update, storage migration hoặc reboot có thể gây downtime. HA topology và rolling maintenance cần được thiết kế/test.

## 6. VM hay bare metal?

| Tiêu chí | Bare metal | VM |
|---|---|---|
| Hardware control | Cao | Thấp hơn, qua hypervisor |
| Provisioning | Thường chậm hơn | Nhanh hơn |
| Isolation | Theo hardware tenancy | Theo hypervisor/instance model |
| Storage | Có thể kiểm soát thiết bị trực tiếp | Phụ thuộc virtual/block storage |
| Resize | Thường cần thay hardware | Có thể đổi instance class |
| Portability | Phụ thuộc hardware | Dễ template/migrate hơn trong platform |
| Noisy neighbor | Ít hơn nếu dedicated | Tùy tenancy/host guarantees |
| Operations | Hardware lifecycle | Hypervisor/provider + guest OS |

### 6.1. Bare metal phù hợp khi

Workload cần predictable hardware performance, specialized storage/network hoặc tổ chức có data center/hardware operations trưởng thành.

### 6.2. VM phù hợp khi

Cần provisioning nhanh, capacity flexibility, automation và khả năng tái tạo host. VM là lựa chọn phổ biến cho self-managed PostgreSQL.

### 6.3. Virtualized storage cần benchmark

Không suy ra mọi VM storage đều chậm. Một cloud block volume có thể nhanh và bền hơn local disk tùy cấu hình. Đo latency, throughput, IOPS, queue depth và fsync behavior.

### 6.4. Dedicated tenancy không đảm bảo database HA

Một dedicated host vẫn có thể hỏng. HA cần failure domains khác nhau và replication/failover strategy.

## 7. Container PostgreSQL là gì?

Container đóng gói PostgreSQL server binaries, libraries, configuration defaults và entrypoint scripts trong image. Runtime khởi chạy container với process isolation và filesystem/network namespaces.

Một container thường có:
- Image tag/digest.
- PostgreSQL process làm foreground process.
- Environment/configuration.
- Mounted persistent volume cho data directory.
- Health/readiness checks.
- Network/service endpoint.
- Resource limits/requests nếu có orchestrator.

### 7.1. Image không phải database backup

Image chứa binaries và filesystem layers, không phải bản backup nhất quán của database đang chạy.

### 7.2. Container filesystem có thể ephemeral

Nếu data directory chỉ nằm trong writable container layer, container removal/replacement có thể làm mất dữ liệu. Production cần persistent volume hoặc storage được quản lý đúng cách.

### 7.3. Container lifecycle khác database lifecycle

Container có thể bị recreate trong khi database cần graceful shutdown, crash recovery và durable data. Orchestrator không hiểu mọi database semantics nếu không được cấu hình phù hợp.

### 7.4. Image tag không tự upgrade data format

Đổi image từ PostgreSQL 16 sang 17 không chuyển data directory major 16 thành format major 17. Cần major upgrade procedure riêng.

## 8. Ưu điểm của container

- Môi trường runtime nhất quán giữa developer, CI và production.
- Image version/digest có thể pin và promote.
- Dễ tạo ephemeral databases cho tests.
- Tách process/filesystem/network ở mức container.
- Tích hợp với deployment automation và orchestration.
- Có thể chạy sidecars/exporters/backup agents.
- Dễ scale ứng dụng và database test environments.
- Giảm “works on my machine” do package differences.

### 8.1. Reproducible images

Pin image tag cụ thể và tốt hơn là digest cho production releases. Tag trôi nổi như latest có thể thay đổi nội dung giữa các lần deploy.

### 8.2. Build provenance

Dùng official/vendor images đáng tin cậy, kiểm tra signatures/provenance nếu platform hỗ trợ và quét vulnerabilities.

### 8.3. Ephemeral environments

Container rất hữu ích để test migrations, extensions và application integration trong CI. Môi trường ephemeral có thể bị xóa sau test mà không ảnh hưởng production data.

### 8.4. Consistent tooling

Có thể chuẩn hóa psql, pg_dump, exporters và utility versions trong image/tooling pipeline, nhưng cần quản lý client/server version compatibility.

## 9. Rủi ro và trách nhiệm của container

Container không tự cung cấp:
- Durable storage.
- Database-aware backup.
- Point-in-time recovery.
- Replication/failover.
- Safe major-version upgrades.
- Connection pooling.
- Data integrity validation.
- Disaster recovery across failure zones.

### 9.1. Persistent volume

Phải mount volume vào data directory, xác định access mode, filesystem, ownership, durability và behavior khi pod/container chuyển node.

### 9.2. Graceful shutdown

Runtime cần gửi signal và cho PostgreSQL đủ thời gian shutdown. Timeout quá ngắn có thể buộc kill process, khiến lần startup sau phải crash recovery.

### 9.3. Resource limits

CPU throttling, memory limits và OOM kills ảnh hưởng database. Một container bị giới hạn RAM thấp có thể bị kernel terminate dù host còn RAM.

### 9.4. Storage latency

Container không làm storage nhanh hơn. Performance vẫn phụ thuộc underlying volume, network storage, filesystem và host I/O.

## 10. Docker Compose cho development và test

Một cấu hình đơn giản có thể dùng để phát triển local:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: local_only_password
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d app"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

Đây là ví dụ cho local development; không dùng mật khẩu minh họa hoặc cấu hình này nguyên trạng cho production.

### 10.1. Named volume

Named volume giữ dữ liệu qua container recreation trong cùng Docker host, nhưng không thay backup/off-host recovery.

### 10.2. Bind mount

Bind mount có thể thuận tiện cho local development, nhưng quyền file, filesystem semantics và host path khác nhau giữa OS.

### 10.3. Port binding

Bind database port vào loopback cho local access. Tránh expose PostgreSQL công khai chỉ để tiện development.

### 10.4. Healthcheck

pg_isready kiểm tra server có accept connections hay không; nó không chứng minh schema, replication, backup hay business queries đã sẵn sàng.

### 10.5. Version pinning

Trong CI/production, pin major/minor/digest theo release policy. Ví dụ postgres:17 vẫn có thể nhận minor image updates theo tag; cần quy trình promotion rõ.

## 11. Container production cần những thành phần nào?

Một production deployment tối thiểu cần thiết kế:
- Image và release policy.
- Persistent storage.
- Secret injection.
- Network policy/TLS.
- CPU/memory resources.
- Startup/readiness/liveness behavior.
- Graceful shutdown.
- Backup/WAL archive.
- Monitoring/logging.
- HA/failover.
- Upgrade/rollback.
- Restore and disaster recovery.

### 11.1. Image lifecycle

Patch base image và PostgreSQL minor releases theo policy. Không rebuild/redeploy tự động mà thiếu compatibility/release validation.

### 11.2. Runtime identity

Chạy process bằng non-root user phù hợp. Kiểm tra ownership/permissions trên mounted data directory.

### 11.3. Persistent storage lifecycle

Đảm bảo volume không bị xóa cùng workload object do cleanup policy. Xác định reclaim policy và snapshot retention.

### 11.4. Backup ngoài volume

Backup cần nằm ở failure domain độc lập. Snapshot cùng storage account/zone có thể không đủ cho disaster recovery.

## 12. Kubernetes StatefulSet và PostgreSQL

Kubernetes có các primitives để chạy stateful workloads, nhưng StatefulSet không tự là PostgreSQL HA solution.

Các thành phần thường có:
- StatefulSet với stable pod identity.
- PersistentVolumeClaim cho data.
- Headless/ClusterIP Service.
- Secrets/ConfigMaps.
- PodDisruptionBudget.
- Resource requests/limits.
- Probes.
- Operator/controller hoặc external database manager.
- Backup/restore tooling.

### 12.1. StatefulSet

StatefulSet quản lý identity và storage association của pods. Nó không tự hiểu primary/standby roles hoặc promote replica đúng cách.

### 12.2. PersistentVolumeClaim

PVC yêu cầu storage từ StorageClass. Kiểm tra performance, zone topology, expansion, snapshot và attach/detach semantics.

### 12.3. Operator

PostgreSQL operator có thể điều phối cluster creation, replicas, failover, backups và upgrades. Chất lượng/feature set phụ thuộc project/vendor/version.

### 12.4. Pod restart không phải failover

Restart primary pod có thể chỉ làm PostgreSQL restart trên cùng data volume. Failover cần xác định replica khỏe, promote an toàn, fence old primary và update routing.

### 12.5. PodDisruptionBudget

PDB hạn chế voluntary disruptions trong một số operations; nó không bảo vệ khỏi mọi node/power/network failures.

## 13. Kubernetes probes và shutdown behavior

Probe configuration sai có thể làm database restart liên tục hoặc nhận traffic quá sớm.

### 13.1. Liveness

Liveness probe quyết định container có cần restart hay không. Không dùng query quá nặng hoặc điều kiện phụ thuộc downstream services có thể khiến database khỏe bị restart trong tải cao.

### 13.2. Readiness

Readiness quyết định endpoint có nhận traffic hay không. Với PostgreSQL primary/replica, readiness cần xét role và trạng thái recovery phù hợp.

### 13.3. Startup probe

Startup probe cho database đủ thời gian crash recovery, replay WAL hoặc init data directory trước khi liveness bắt đầu.

### 13.4. Termination grace period

Cho PostgreSQL thời gian shutdown cleanly. Cần tính cả active transactions và checkpoint/shutdown time trong giới hạn orchestration.

### 13.5. Probe không thay monitoring

Probe là health signal cho orchestrator; monitoring cần query latency, locks, replication, storage, backup và application-level checks.

## 14. Kubernetes storage và failure domains

Storage cho PostgreSQL thường quan trọng hơn việc container có thể reschedule nhanh đến đâu.

### 14.1. Volume topology

Một zonal block volume có thể chỉ attach được trong một zone. Pod scheduling cần tôn trọng topology và khả năng recovery nếu zone mất.

### 14.2. StorageClass

Kiểm tra IOPS/throughput guarantees, expansion, encryption, snapshots, reclaim policy và CSI driver behavior.

### 14.3. Access modes

ReadWriteOnce/ReadWriteMany semantics phụ thuộc CSI/provider. Không dùng shared filesystem nhiều-writer cho PostgreSQL data directory nếu PostgreSQL/storage architecture không hỗ trợ.

### 14.4. Filesystem correctness

PostgreSQL dựa vào filesystem/storage guarantees cho durability và WAL. Dùng storage class được hỗ trợ/tested; không giả định mọi network filesystem đều phù hợp.

### 14.5. Backup và snapshots

Crash-consistent volume snapshot không luôn tương đương application-consistent backup. Tuân theo PostgreSQL-aware backup tool hoặc snapshot coordination procedure.

## 15. PostgreSQL operator: nên chọn khi nào?

Operator có thể giảm việc tự viết automation cho:
- Cluster bootstrap.
- Replication setup.
- Failover/reconciliation.
- Backup scheduling.
- Restore workflows.
- Rolling minor updates.
- Major upgrade orchestration ở mức hỗ trợ.
- Monitoring integration.

### 15.1. Operator là control plane

Operator quan sát desired state và reconcile resources. Cần hiểu custom resources, controller version, upgrade path và failure behavior.

### 15.2. Đọc support matrix

Kiểm tra PostgreSQL versions, extension support, storage backends, backup tools, replication modes và Kubernetes versions.

### 15.3. Không có operator nào loại bỏ DBA responsibilities

Schema design, query tuning, workload capacity, backup restore validation, security và incident decisions vẫn cần chuyên môn database.

### 15.4. Operator upgrade cũng cần kế hoạch

CRD/controller upgrades có thể thay đổi behavior. Test operator upgrade và database upgrade như hai lifecycle riêng.

## 16. Managed PostgreSQL là gì?

Managed PostgreSQL là dịch vụ trong đó provider quản lý một phần hoặc phần lớn infrastructure/database operations. Dịch vụ có thể là PostgreSQL native hoặc PostgreSQL-compatible service.

Provider có thể cung cấp:
- Instance provisioning và storage.
- Automated backups và PITR.
- Managed standby/read replicas.
- Automated failover.
- Minor patching/maintenance.
- Encryption at rest/in transit.
- Monitoring, logs và metrics.
- Network isolation/private endpoints.
- Scaling operations.
- Snapshot/restore và cross-region DR ở một số tiers.

### 16.1. Managed service vẫn là database có giới hạn

Có connection limits, storage limits, IOPS/throughput ceilings, maintenance windows, parameter restrictions và feature availability.

### 16.2. Provider quản lý control plane

Người dùng thao tác qua console/API/IaC. OS-level access và filesystem control thường không có.

### 16.3. PostgreSQL-compatible không luôn là PostgreSQL đầy đủ

Một số dịch vụ có internal architecture khác hoặc giới hạn extensions, SQL features, replication semantics và connection behavior. Kiểm tra compatibility.

### 16.4. Managed không đồng nghĩa zero operations

Ứng dụng vẫn cần migrations, indexes, roles, query tuning, capacity planning, restore testing và incident coordination.

## 17. Ưu điểm của managed PostgreSQL

- Giảm công việc provisioning và hardware maintenance.
- Backup/PITR tích hợp sẵn ở nhiều dịch vụ.
- HA/read replicas có workflow provider hỗ trợ.
- Monitoring/logging tích hợp.
- Encryption, IAM và private networking có sẵn ở một số platforms.
- Scaling compute/storage đơn giản hơn.
- SLA/support/escalation có thể rõ ràng.
- Dễ tích hợp với cloud IAM, secrets, monitoring và deployment tools.

### 17.1. Tập trung vào ứng dụng

Team nhỏ có thể dành nhiều thời gian hơn cho schema, query performance và product features.

### 17.2. Standardized operations

Provider có thể áp dụng patching, backup và failover procedures nhất quán.

### 17.3. Managed backups

Automated backups và PITR giảm khả năng quên backup schedule, nhưng vẫn cần restore drills.

### 17.4. Support contract

Với tier có support phù hợp, có thể nhận hỗ trợ vendor trong incidents/hardware/service events. Kiểm tra scope và response-time commitments.

## 18. Hạn chế của managed PostgreSQL

- Không có root/OS access.
- Chỉ một số extensions/versions được hỗ trợ.
- Một số PostgreSQL parameters bị khóa hoặc giới hạn.
- Maintenance windows và failover behavior do provider kiểm soát một phần.
- Pricing có thể cao khi tăng storage, IOPS, replicas, backups hoặc network egress.
- Có thể phụ thuộc proprietary APIs hoặc provider-specific features.
- Export/migration có thể tốn thời gian và chi phí.
- Observability có thể giới hạn so với self-managed host.
- SLA có exclusions và không đảm bảo mọi application-level recovery.

### 18.1. Extension availability

Kiểm tra danh sách extensions và version trước khi chọn provider. Không giả định superuser có thể cài mọi extension từ source.

### 18.2. Parameter groups

Một số settings cần parameter group hoặc reboot. Có thể không điều chỉnh được kernel/filesystem settings.

### 18.3. Connection/proxy layer

Managed services có thể cung cấp proxy/pooler riêng. Hiểu transaction/session semantics, failover DNS và connection draining.

### 18.4. Provider-specific behavior

Backup retention, replica lag, failover, maintenance và upgrade workflow khác nhau. Đọc documentation đúng service/tier/region.

## 19. Managed PostgreSQL và trách nhiệm chia sẻ

Dùng shared responsibility matrix:

| Hạng mục | Managed provider thường làm | Người dùng vẫn cần làm |
|---|---|---|
| Physical hardware | Mua, thay thế, vận hành | Chọn tier/region và capacity |
| Host OS | Patching/hardening theo dịch vụ | Theo dõi maintenance và compatibility |
| PostgreSQL process | Provision/restart theo service | Config, query tuning, extensions được hỗ trợ |
| Backups | Automated backup/PITR feature | Retention choice, restore tests, recovery objectives |
| HA | Replicas/failover mechanisms | Chọn topology/tier, test application reconnection |
| Network | Managed VPC/private endpoint options | Firewall, routes, TLS/client access |
| Identity | IAM integration options | Least privilege, role/grant design, secret lifecycle |
| Data/schema | Không hiểu business semantics | Migrations, constraints, validation |
| Application | Không chịu trách nhiệm | Drivers, pools, retries, consistency |
| DR | Một số cross-zone/region features | DR design, exercises và business sign-off |

Trách nhiệm cụ thể khác nhau theo provider và service tier. Yêu cầu contract/documentation để xác nhận thay vì dựa vào giả định.

## 20. So sánh tổng quan ba mô hình

| Tiêu chí | Máy chủ riêng/VM | Container tự quản lý | Managed PostgreSQL |
|---|---|---|---|
| OS control | Cao | Host control phụ thuộc platform | Thấp |
| PostgreSQL config | Rộng | Rộng trong image/runtime scope | Theo parameter support |
| Extension flexibility | Cao | Cao nếu image/package phù hợp | Theo allowlist/provider |
| Provisioning | Thủ công hoặc IaC | Image + platform automation | Console/API/IaC |
| Persistence | Do team thiết kế | PVC/volume do team/platform quản lý | Provider-managed storage |
| HA | Tự thiết kế | Operator/replication tooling | Provider feature/tier |
| Backup | Tự xây/chọn tool | Tự tích hợp database-aware backup | Thường tích hợp |
| Upgrades | Tự vận hành | Image + database migration plan | Provider workflow/maintenance |
| Portability | Cao nếu chuẩn hóa | Image dễ promote, storage vẫn phụ thuộc | Có thể có provider dependency |
| Operational burden | Cao | Cao đến rất cao nếu Kubernetes | Thấp hơn, không bằng zero |
| Cost model | Hardware/VM + nhân lực | Compute/storage/platform + nhân lực | Instance/storage/IOPS/features + egress |
| Best fit | Control/customization | Reproducibility/orchestration | Giảm hạ tầng tự quản lý |

### 20.1. Container không phải lựa chọn thứ tư độc lập với máy chủ

Container chạy trên VM hoặc bare-metal nodes. So sánh container là so deployment/runtime model; vẫn phải chọn underlying infrastructure và storage.

### 20.2. Managed có thể chạy container nội bộ

Provider có thể dùng containers/VMs bên trong control plane, nhưng người dùng tiêu thụ service abstraction. Điều quan trọng là contract và operations exposed.

### 20.3. Có thể kết hợp các mô hình

Ví dụ managed primary với self-managed analytics, hoặc Kubernetes cho application nhưng managed PostgreSQL cho database.

## 21. Chọn theo workload

### 21.1. Development local

Container thường thuận tiện: start/stop nhanh, version pinning và disposable databases. Dùng dữ liệu giả, secrets local và volume phù hợp.

### 21.2. CI integration tests

Container/ephemeral database giúp tạo môi trường sạch cho mỗi job. Test đúng PostgreSQL major/extensions cần dùng.

### 21.3. Small production application

Managed PostgreSQL thường giảm operational burden nếu feature set và cost phù hợp. Self-managed VM cũng có thể hợp lý khi team có operations capability.

### 21.4. High-throughput OLTP

Cần benchmark storage, CPU, connection behavior và latency. Bare metal/VM có thể đem lại control; managed tier mạnh cũng có thể phù hợp nếu limits đạt.

### 21.5. Specialized extensions

Self-managed host/container image có thể linh hoạt hơn. Managed service chỉ phù hợp nếu provider hỗ trợ extension/version cần thiết.

### 21.6. Regulated or data-residency workloads

Chọn theo jurisdiction, key ownership, audit, network isolation, backup location và provider compliance evidence. Self-managed không tự động compliant; managed cũng không tự động đáp ứng mọi policy.

## 22. Development, staging và production có thể khác nhau

Không nhất thiết dùng cùng hosting model cho mọi môi trường, nhưng cần giữ compatibility.

Một pattern:
- Development: local container.
- CI: ephemeral PostgreSQL container/database.
- Staging: managed tier hoặc VM gần production.
- Production: managed PostgreSQL hoặc self-managed HA topology.

### 22.1. Version parity

Giữ PostgreSQL major và extension versions tương thích. Nếu production dùng extension không có trong local image, tests có thể bỏ sót behavior.

### 22.2. Configuration parity

Không cần cùng resource size, nhưng settings quan trọng, locale, encoding, auth và connection semantics nên được kiểm soát.

### 22.3. Staging data

Dùng data volume/distribution đủ đại diện và tuân thủ privacy. Anonymize/mask production data khi cần.

### 22.4. Production-only features

Nếu production dùng managed proxy, IAM auth hoặc failover routing, staging nên test các behavior này.

## 23. HA trên máy chủ riêng

Một topology tự quản lý thường có:
- Primary.
- Một hoặc nhiều streaming standbys.
- WAL archiving.
- Failover manager/orchestrator.
- Proxy/VIP/DNS routing.
- Fencing để tránh split brain.
- Monitoring và alerting.

### 23.1. Replication

Physical streaming replication truyền WAL từ primary tới standby. Standby có thể synchronous hoặc asynchronous tùy policy.

### 23.2. Failover

Promotion phải bảo đảm old primary không tiếp tục nhận writes (fencing). Nếu hai primaries cùng nhận writes, data divergence có thể xảy ra.

### 23.3. Synchronous vs asynchronous

Synchronous có thể giảm data loss nhưng tăng commit latency và phụ thuộc availability của synchronous standby. Asynchronous giảm latency nhưng có thể mất các writes chưa được replica nhận khi failover.

### 23.4. Failback

Sau failover, old primary thường cần rewind/rebuild/rejoin theo quy trình; không đơn giản restart và đưa trở lại topology.

### 23.5. Test thực tế

Diễn tập node failure, network partition, storage failure, stale replica và router update. Một diagram HA không chứng minh failover hoạt động.

## 24. HA trong Kubernetes

Kubernetes cung cấp scheduling và orchestration, nhưng database failover cần PostgreSQL-aware controller/operator.

### 24.1. Primary election/promotion

Operator cần theo dõi cluster state, replication health và chọn standby có dữ liệu phù hợp để promote.

### 24.2. Fencing

Ngăn old primary tiếp tục ghi sau khi mất liên lạc với control plane. Fencing có thể cần storage/network/process-level mechanisms.

### 24.3. Service routing

Service selector/endpoint cần route tới primary mới. Clients phải reconnect và xử lý stale connections.

### 24.4. Pod anti-affinity và topology spread

Đặt replicas trên nodes/zones khác nhau để giảm correlated failures. Cần xét storage zone constraints.

### 24.5. Node/zone outage

Test behavior khi node hoặc availability zone mất. Persistent volume có thể không attach được ngay ở zone khác.

## 25. HA trong managed services

Managed services thường cung cấp:
- Multi-AZ standby.
- Automated failover.
- Read replicas.
- Managed proxy/endpoints.
- Automated maintenance/backup.

### 25.1. Failover time

Thời gian failover phụ thuộc detection, promotion, storage/network, DNS/proxy và application reconnect. Đọc SLA và test.

### 25.2. Endpoint behavior

Endpoint có thể giữ hostname nhưng đổi IP/target. Connection pools cần phát hiện broken connections và reconnect đúng cách.

### 25.3. Replica lag

Read replica có thể lag. Application cần routing policy và stale-read tolerance.

### 25.4. Provider failover không thay application resilience

Transaction đang chạy có thể bị disconnect. App cần retry logic đúng, idempotency và transaction boundary rõ.

## 26. Backup và PITR theo deployment model

| Mô hình | Backup strategy |
|---|---|
| Dedicated/VM | pgBackRest, Barman, WAL archive hoặc tool được hỗ trợ |
| Container/Kubernetes | PostgreSQL-aware backup operator/tool, off-cluster object storage |
| Managed | Automated snapshots/PITR và exports theo provider features |

### 26.1. Physical backup

Base backup cộng WAL archive có thể hỗ trợ PITR. Tool cần bảo đảm backup consistency và WAL continuity.

### 26.2. Logical backup

pg_dump/pg_dumpall phù hợp portability/object-level restore, nhưng không thay thế mọi PITR requirements.

### 26.3. Volume snapshots

Snapshot cần phối hợp database/storage để bảo đảm consistency. Crash-consistent snapshot có recovery implications; không coi mọi snapshot là application-consistent.

### 26.4. Backup location

Giữ backup ngoài failure domain chính. Cân nhắc account/project/region khác và access isolation.

### 26.5. Restore tests

Test restore toàn cluster/database/object, extension availability, roles, permissions và application connectivity. Ghi measured RTO.

## 27. RPO và RTO

Hai chỉ số quan trọng:

- **RPO (Recovery Point Objective)**: lượng dữ liệu tối đa có thể chấp nhận mất, tính theo thời gian hoặc business events.
- **RTO (Recovery Time Objective)**: thời gian tối đa để khôi phục service sau sự cố.

### 27.1. RPO ảnh hưởng replication/backup

Synchronous replication có thể giảm RPO cho một số failure classes; asynchronous replication có thể có non-zero data loss window. Backup frequency/WAL archiving cũng quyết định recovery point.

### 27.2. RTO phụ thuộc restore path

Restore vài TB có thể mất nhiều giờ dù backup đã thành công. Phải đo restore time, network throughput và extension/bootstrap steps.

### 27.3. Managed service không tự bảo đảm business RTO

Provider SLA về availability không nhất thiết là cam kết thời gian restore dữ liệu hoặc application recovery.

### 27.4. Chọn tier theo objectives

Đừng mua HA/DR tier đắt nếu business không cần, nhưng cũng không chọn single-zone deployment khi RPO/RTO không cho phép.

## 28. Storage design

Storage ảnh hưởng durability, latency, throughput, capacity và recovery.

### 28.1. Data và WAL

PostgreSQL dùng data files và WAL. Có thể đặt trên cùng volume hoặc tách theo thiết kế; tách volume không tự cải thiện performance nếu cùng backend/IOPS pool.

### 28.2. Filesystem

Dùng filesystem và mount configuration được PostgreSQL/platform hỗ trợ. Tránh tùy tiện chọn filesystem options có durability semantics không phù hợp.

### 28.3. IOPS và throughput

Đo workload random/sequential I/O, fsync latency và queue depth. Provisioned IOPS có thể tăng chi phí; chọn theo benchmark.

### 28.4. Capacity headroom

Dự phòng database growth, indexes, WAL, temporary files, vacuum, index builds và backup staging. Disk đầy có thể làm database ngừng hoạt động.

### 28.5. Encryption at rest

Xác minh ai quản lý encryption keys, rotation, snapshots, backups và replicas. Encryption volume không thay TLS cho network traffic.

## 29. CPU và memory sizing

### 29.1. CPU

Sizing theo peak query concurrency, parallelism, vacuum, replication và background jobs. Nhiều cores không đảm bảo một query serial chạy nhanh hơn.

### 29.2. Memory

Xem shared_buffers, OS page cache, work_mem, maintenance_work_mem và backend concurrency. Work_mem có thể được dùng nhiều lần trong một query.

### 29.3. Container limits

Trong container, PostgreSQL có thể nhìn thấy memory/CPU limits khác host resources. Kiểm tra cgroup-aware behavior và runtime configuration theo version.

### 29.4. Managed instance classes

So sánh CPU generation, memory ratio, burst credits (nếu có), storage bandwidth và network limits. Không chỉ so vCPU count.

### 29.5. Benchmark

Dùng workload representative, data volume gần production, warm/cold cache scenarios và concurrency thực tế.

## 30. Network và connection management

PostgreSQL connections tiêu thụ backend resources. Nhiều application instances có thể tạo connection count lớn hơn dự kiến.

### 30.1. Connection pooling

PgBouncer hoặc provider pooler có thể giảm backend connection count. Chọn session/transaction pooling theo application features và semantics.

### 30.2. Pool limits

Tính tổng pool size qua mọi application replicas, workers, migrations và admin tools. Đặt max_connections và pool caps có chủ đích.

### 30.3. TLS

Bật TLS theo policy, xác minh certificate và hostname. Managed private endpoints vẫn cần TLS tùy threat model/provider.

### 30.4. Network locality

Đặt application gần database để giảm round-trip latency. Tránh mỗi request tạo nhiều remote calls không cần thiết.

### 30.5. Firewall/private networking

Chỉ cho phép application, migration runner, monitoring và admin networks truy cập đúng ports. Không expose 5432 công khai khi không cần.

## 31. Security và secrets

Bất kể mô hình nào, database security cần:
- Least-privilege roles.
- TLS in transit.
- Encryption at rest.
- Network segmentation.
- Secrets manager.
- Credential rotation.
- Audit logging.
- Patch/vulnerability management.
- Backup access control.
- Data classification và retention.

### 31.1. Không dùng superuser cho ứng dụng

Application role chỉ cần SELECT/INSERT/UPDATE/DELETE và execute privileges phù hợp. Migration role riêng chịu trách nhiệm DDL.

### 31.2. Secret injection

Trong container/Kubernetes, dùng secret manager hoặc Kubernetes Secret tích hợp encryption/access policy. Không bake passwords vào image layers.

### 31.3. Managed IAM

IAM authentication có thể giảm static password management nhưng có token expiry, driver/proxy requirements và provider-specific behavior.

### 31.4. Admin access

Dùng bastion/VPN/private endpoint/zero-trust access theo policy. Ghi audit cho privileged actions.

### 31.5. Backup credentials

Backup jobs cần credentials riêng và quyền tối thiểu để đọc database/WAL và ghi storage target.

## 32. Monitoring và logging

Một deployment production cần monitoring ở database và platform layers.

Database metrics:
- Connections/active sessions.
- Query latency và slow queries.
- Transactions/commits/rollbacks.
- Locks/deadlocks.
- Cache hits, buffer reads.
- WAL generation/checkpoints.
- Replication lag.
- Vacuum/XID age/bloat.
- Temp files.
- Backup/archive status.

Platform metrics:
- CPU/RAM/swap.
- Disk capacity/IOPS/latency.
- Network throughput/errors.
- Container restarts/OOM.
- Volume attach errors.
- Node/zone health.
- Provider events/maintenance.

### 32.1. Logs

Centralize PostgreSQL logs và platform events. Redact secrets, personal data và query literals nhạy cảm.

### 32.2. Alerting

Alert theo SLO/capacity: disk headroom, replica lag, backup failures, connection saturation, long transactions, WAL archive backlog và repeated restarts.

### 32.3. Managed metrics

Provider metrics có thể khác PostgreSQL internal views. Kết hợp cả hai khi được phép.

### 32.4. Observability ownership

Xác định ai nhận alert và ai có quyền hành động. Alert không có on-call owner không tạo ra resilience.

## 33. Minor updates và OS patching

Minor PostgreSQL releases thường chứa bug/security fixes trong cùng major line. OS/container base image cũng cần security updates.

### 33.1. Self-managed

Đội ngũ chọn package repository, test release, schedule restart/failover và update từng node.

### 33.2. Container

Build/promote image mới, test extensions, restart theo rollout plan. Image mới không tự thực hiện major data migration.

### 33.3. Managed

Provider có thể patch theo maintenance window hoặc user-initiated action. Kiểm tra notification, reboot behavior và failover impact.

### 33.4. Change record

Ghi version trước/sau, release notes, backup evidence, nodes affected, downtime và post-update checks.

## 34. Major version upgrades

Major upgrade thay đổi data/catalog compatibility và có thể yêu cầu pg_upgrade, dump/restore hoặc provider workflow.

### 34.1. Self-managed host/VM

Cài binaries target, kiểm tra extension packages, chạy pg_upgrade --check, rehearsal, backup và cutover.

### 34.2. Container

Không chỉ đổi image tag. Cần target data directory và migration method. Có thể dùng old/new StatefulSets/volumes hoặc logical migration.

### 34.3. Managed

Provider có thể cung cấp in-place upgrade hoặc snapshot/restore workflow. Kiểm tra extension availability, parameter groups, replicas, downtime và rollback constraints.

### 34.4. Test application

Driver, ORM, query plans, authentication, extensions và background jobs cần test trên target major.

### 34.5. Rollback

Sau khi target nhận writes, quay về old major cần reverse sync/reconciliation hoặc restore strategy. Không chỉ thay image/endpoint.

## 35. Extension compatibility

Extensions phụ thuộc PostgreSQL major, shared libraries, OS/architecture và có thể cả PROJ/OpenSSL/GDAL hoặc native libraries.

### 35.1. Self-managed

Có thể cài packages/build phù hợp, nhưng cần security patching và upgrade testing.

### 35.2. Container

Tạo image có extension package tương thích với PostgreSQL base image. Pin package versions và rebuild khi security fixes.

### 35.3. Managed

Chỉ dùng extensions/provider versions trong supported list. Có thể phải chọn service/major khác nếu extension cần thiết không có.

### 35.4. Upgrade SQL objects

Cài binary không luôn update SQL extension version. Dùng ALTER EXTENSION UPDATE theo hướng dẫn và kiểm tra từng database.

## 36. Scaling trong từng mô hình

### 36.1. Máy chủ riêng

Scale up bằng CPU/RAM/storage hardware; scale out bằng read replicas hoặc sharding. Tự quản lý replication/failover và capacity.

### 36.2. Container platform

Scale application pods dễ hơn database pods. PostgreSQL stateful scaling cần operator, storage và replication-aware workflows. Không tăng replicas bằng cách nhân bản pod cùng data directory.

### 36.3. Managed service

Có thể resize compute/storage, thêm read replicas hoặc bật HA theo tier. Kiểm tra downtime, limits, replica lag, storage growth và cost.

### 36.4. Read scaling không phải write scaling

Read replicas giảm tải reads; write capacity vẫn tập trung ở primary trừ khi dùng sharding/multi-writer architecture.

### 36.5. Scale trigger

Dùng latency, CPU, I/O, storage, connection pressure, WAL và growth forecasts. Không scale chỉ theo CPU average.

## 37. Availability zones và disaster recovery regions

### 37.1. Multi-AZ

Replica/standby ở zone khác giúp giảm ảnh hưởng của một zone failure. Cần kiểm tra storage/network topology và failover time.

### 37.2. Cross-region DR

Replica/backup ở region khác bảo vệ khỏi region outage, nhưng tăng network cost và latency. Asynchronous replication có RPO.

### 37.3. Backup isolation

Backup nên có access isolation và failure domain khác primary. Ransomware/credential compromise có thể ảnh hưởng backup nếu cùng quyền truy cập.

### 37.4. Regional restore

Test restore vào region đích, bao gồm KMS keys, secrets, network, DNS, application deployment và extension availability.

### 37.5. Data residency

Kiểm tra vị trí của primary, replicas, backups, logs, telemetry và support access. Data residency không chỉ là database primary region.

## 38. Cost model và total cost of ownership

TCO cần gồm:

- Compute/instance/host.
- Storage capacity và provisioned IOPS.
- Backup/snapshot/WAL archive storage.
- Network egress/inter-region traffic.
- Read replicas/standby/DR region.
- Monitoring/logging retention.
- Support contract.
- Licensing nếu có platform/vendor fees.
- Engineering/DBA/SRE time.
- On-call and incident cost.
- Migration and exit costs.

### 38.1. Self-managed cost

Hardware/VM có thể rẻ hơn theo unit, nhưng phải cộng nhân lực, HA, backup tooling, replacement, security và downtime risk.

### 38.2. Container platform cost

Cộng Kubernetes/control plane, worker nodes, persistent volumes, network load balancers, operators, backup tools và platform engineering.

### 38.3. Managed cost

Cộng instance, storage, IOPS, backups, replicas, proxies, cross-zone/region transfer, support và overprovisioning headroom.

### 38.4. Cost per workload unit

So cost per transaction, per GB-month, per tenant hoặc per request ở workload thực tế. Không chỉ so giá list của một instance.

### 38.5. Cost of downtime

Một dịch vụ rẻ nhưng restore mất 12 giờ có thể đắt hơn managed HA tier nếu business loss lớn.

## 39. Vendor lock-in và portability

Managed service có thể tạo dependency vào:
- Proprietary APIs.
- IAM authentication.
- Extensions riêng.
- Backup/export formats.
- Monitoring agents.
- Replication/CDC features.
- Failover/proxy endpoints.
- Parameter/service behaviors.

### 39.1. PostgreSQL protocol compatibility

Một service dùng PostgreSQL wire protocol không đồng nghĩa hỗ trợ đầy đủ PostgreSQL semantics/extensions.

### 39.2. Portable schema

Giữ schema, SQL và extensions trong phạm vi portable khi đó là requirement. Tách provider-specific integrations sau abstraction boundaries.

### 39.3. Export path

Test pg_dump/pg_restore, logical replication hoặc data export vào PostgreSQL chuẩn. Đo thời gian và network cost.

### 39.4. Exit strategy

Ghi rõ target platform, data export, roles, extensions, sequences, large objects, CDC cutover và rollback. Một exit plan chưa từng test có thể không dùng được khi cần.

### 39.5. Lock-in có thể là trade-off hợp lý

Provider feature có thể tiết kiệm nhiều engineering effort. Điều quan trọng là hiểu dependency và mức độ chấp nhận được.

## 40. Compliance và regulatory requirements

Kiểm tra:
- Data residency/jurisdiction.
- Encryption at rest/in transit.
- Customer-managed keys nếu bắt buộc.
- Audit log availability/retention.
- Privileged access records.
- Backup location and retention.
- Data deletion/retention policies.
- Network isolation/private connectivity.
- Vulnerability/patch management.
- Certifications và audit reports của provider.
- Subprocessor/support access.
- Incident notification commitments.

### 40.1. Self-managed không tự động compliant

Tự kiểm soát server không chứng minh controls đã được triển khai hoặc audit.

### 40.2. Managed không tự động compliant

Chứng chỉ provider không bảo đảm cách cấu hình tenant/database của bạn đáp ứng policy.

### 40.3. Shared responsibility

Ghi rõ provider controls và customer controls, giữ evidence và review định kỳ.

### 40.4. Regulated data trong non-production

Mask/anonymize dữ liệu và áp dụng access policy cho dev/staging/CI.

## 41. Disaster recovery và exit readiness

Một mô hình deployment chỉ hoàn chỉnh khi có thể phục hồi và rời khỏi nó.

### 41.1. Restore drill

Khôi phục vào môi trường sạch, kiểm tra extension, roles, application connectivity và data integrity.

### 41.2. Failover drill

Test primary loss, promotion, routing, application reconnect và failback/rebuild.

### 41.3. Provider outage

Xác định escalation, status channels, alternate region và manual recovery options.

### 41.4. Export rehearsal

Thử export schema/data/global objects và import vào target PostgreSQL. Kiểm tra sequence state, large objects, ownership và extensions.

### 41.5. Recovery documentation

Runbook phải có endpoint, service identity, data directory/storage, restore commands, keys, owners và verification steps.

## 42. Decision matrix theo yêu cầu

| Yêu cầu | Máy chủ riêng/VM | Container tự quản lý | Managed PostgreSQL |
|---|---|---|---|
| OS/kernel customization | Rất phù hợp | Phụ thuộc host/platform | Hạn chế |
| Extension tùy chỉnh | Linh hoạt | Linh hoạt nếu image hỗ trợ | Theo provider |
| Local development parity | Có thể | Rất phù hợp | Ít tiện hơn |
| Ephemeral CI databases | Có thể nhưng nặng | Rất phù hợp | Có thể tốn chi phí |
| Ít nhân lực DBA/SRE | Khó | Khó nếu tự quản lý | Thường phù hợp hơn |
| HA tự thiết kế | Linh hoạt | Cần operator/tooling | Thường có sẵn theo tier |
| Hardware-level tuning | Cao | Phụ thuộc host | Hạn chế |
| Managed backup/PITR | Tự tích hợp | Tự tích hợp | Thường có |
| Data center/on-prem requirement | Phù hợp | Phù hợp | Chỉ nếu provider/on-prem offering đáp ứng |
| Predictable specialized I/O | Có thể kiểm soát cao | Phụ thuộc volume | Theo service tier |
| Provider integration | Tự tích hợp | Tự tích hợp | Tích hợp sâu |
| Portability | Cao nếu chuẩn hóa | Image portable, volume không hẳn | Cần đánh giá |
| Operational ownership | Team | Team/platform | Chia sẻ với provider |

Dùng bảng như công cụ thảo luận, không phải điểm số tuyệt đối. Feature cụ thể khác nhau theo vendor, tier và version.

## 43. Kịch bản lựa chọn thực tế

### Tình huống A: Developer laptop

Chọn container PostgreSQL với named volume hoặc ephemeral test database. Pin major version và không expose port ra public network.

### Tình huống B: Team nhỏ, ứng dụng production thông thường

Managed PostgreSQL có thể giảm operational burden đáng kể. Xác nhận extensions, backup/PITR, HA tier, region và cost trước khi quyết định.

### Tình huống C: On-premises bắt buộc

Máy chủ riêng/VM hoặc Kubernetes on-prem là lựa chọn phù hợp. Team cần sở hữu hardware/OS, backup, replication, security và DR.

### Tình huống D: Cần extension native đặc biệt

Self-managed VM/bare metal hoặc container image tùy chỉnh thường linh hoạt hơn. Kiểm tra build compatibility và security maintenance.

### Tình huống E: Team đã vận hành Kubernetes tốt

Có thể dùng operator đã được đánh giá, storage class tested, backup/restore automation và on-call database expertise. StatefulSet đơn lẻ không đủ.

### Tình huống F: Không có DBA/SRE on-call

Managed service thường là điểm khởi đầu an toàn hơn nếu provider SLA/support và features đáp ứng requirements. Vẫn cần người chịu trách nhiệm application/database operations.

### Tình huống G: Latency rất nhạy và workload chuyên biệt

Benchmark bare metal/VM, managed high-performance tiers và storage options. Quyết định theo measured p95/p99, durability và recovery behavior.

### Tình huống H: Regulated multi-region

So sánh provider compliance/data residency với self-managed control. Kiểm tra cả backups, logs, keys, replicas và support access.

## 44. Checklist trước khi chọn provider hoặc platform

### Workload

- [ ] Read/write ratio và peak TPS đã đo?
- [ ] Data size, working set và growth forecast đã có?
- [ ] Query p95/p99 và connection concurrency đã rõ?
- [ ] Extensions, collations và locale requirements đã liệt kê?
- [ ] Batch/analytics workload đã phân loại?

### Availability và recovery

- [ ] RPO/RTO đã được business phê duyệt?
- [ ] HA topology/failover behavior đã rõ?
- [ ] Backup retention và PITR window phù hợp?
- [ ] Restore drill đã hoàn thành?
- [ ] Cross-zone/region DR có cần thiết?

### Security/compliance

- [ ] Network private access/TLS?
- [ ] Encryption at rest và key ownership?
- [ ] IAM/roles/secret rotation?
- [ ] Audit logs và retention?
- [ ] Data residency/backup locations?
- [ ] Provider compliance evidence nếu cần?

### Operations

- [ ] Ai patch OS/PostgreSQL/extensions?
- [ ] Ai chạy minor/major upgrades?
- [ ] Ai nhận alerts/on-call?
- [ ] Có metrics/logs đủ sâu?
- [ ] Có capacity and cost alerts?
- [ ] Có incident escalation/support?

### Portability/cost

- [ ] SQL/extensions có portable?
- [ ] Export/restore path đã test?
- [ ] TCO tính đủ replicas, storage, egress và nhân lực?
- [ ] Có vendor-specific dependencies?
- [ ] Exit plan và thời gian migration đã ước lượng?

## 45. Runbook: triển khai PostgreSQL self-managed trên VM

1. Chọn OS/version và VM size theo benchmark.
2. Tạo network private và firewall rules.
3. Tạo storage volumes/filesystems phù hợp.
4. Cài PostgreSQL package từ repository tin cậy.
5. Tạo service/data directory với ownership đúng.
6. Cấu hình authentication, TLS và least-privilege roles.
7. Thiết lập WAL archive và backup tooling.
8. Thiết lập replication/HA nếu yêu cầu.
9. Cấu hình monitoring, logs và alerts.
10. Chạy load tests và restore drill.
11. Ghi version, configuration, backup policy và runbooks.
12. Đưa vào production sau khi failover/recovery được diễn tập.

### 45.1. Không expose port mặc định ra Internet

Chỉ mở network path từ app/admin networks được phép. Dùng private subnet/VPN/bastion theo policy.

### 45.2. OS maintenance

Đặt patch cadence, reboot procedure và failover plan trước khi áp dụng updates.

### 45.3. Storage verification

Xác minh mount sau reboot, filesystem permissions, free space và alert thresholds.

### 45.4. Restore test trước production

Thử khôi phục backup vào host khác, không chỉ kiểm tra backup job exit code.

## 46. Runbook: triển khai PostgreSQL container

1. Chọn image source đáng tin cậy.
2. Pin PostgreSQL major/minor hoặc digest.
3. Xác định data directory và persistent volume.
4. Tạo secrets ngoài image.
5. Thiết lập network/private service.
6. Cấu hình resources và graceful shutdown.
7. Cấu hình startup/readiness/liveness phù hợp.
8. Thiết lập PostgreSQL-aware backup và WAL archive.
9. Tích hợp monitoring/logging.
10. Test container restart, node loss và volume reattach.
11. Rehearse minor/major upgrade riêng.
12. Kiểm tra restore và disaster recovery.

### 46.1. Không dùng container writable layer làm storage duy nhất

Container recreation có thể xóa layer. Dùng persistent storage được quản lý.

### 46.2. Không scale replicas bằng cách nhân bản data directory

Mỗi PostgreSQL instance cần cluster identity/data state đúng. Replicas phải được tạo bằng base backup/replication/operator workflow.

### 46.3. Không đổi major image tag để upgrade

Major upgrade cần migration method. Image replacement đơn thuần không chuyển đổi data directory.

### 46.4. Container health

Healthcheck phải phản ánh trạng thái cần thiết nhưng không restart database liên tục khi đang recovery hoặc chịu tải.

## 47. Runbook: chọn và khởi tạo managed PostgreSQL

1. Chọn provider/service/region và PostgreSQL major version.
2. Kiểm tra extensions, parameter support và compatibility.
3. Chọn compute/storage tier theo benchmark.
4. Xác định HA/Multi-AZ và read replicas.
5. Cấu hình private networking, TLS và identity.
6. Chọn backup retention/PITR và encryption keys.
7. Thiết lập maintenance window và patch policy.
8. Tạo roles/database/schema theo least privilege.
9. Thiết lập metrics/log exports và alerts.
10. Test application reconnect/failover behavior.
11. Thực hiện restore drill và đo RTO.
12. Ghi provider limits, support path, cost và exit plan.

### 47.1. Đọc service-specific documentation

Không áp dụng thông tin của một provider/tier sang provider khác. Xác nhận feature availability ở region/version cụ thể.

### 47.2. Kiểm tra limits

Max connections, storage size, IOPS, replica count, backup retention và maintenance restrictions có thể khác nhau.

### 47.3. Endpoint và DNS

Hiểu endpoint behavior khi failover/resize/restore. Kiểm tra DNS caching và pooler reconnect.

### 47.4. Cost alerts

Đặt alerts cho storage growth, backup usage, replicas, IOPS và network egress.

## 48. Các lỗi thường gặp

- Chọn server theo giá compute mà bỏ qua storage/backup/HA.
- Cho rằng dedicated host đồng nghĩa HA.
- Cho rằng container image chứa persistent database state.
- Lưu data directory trong container layer ephemeral.
- Dùng shared volume nhiều-writer cho nhiều PostgreSQL primaries.
- Chỉ dùng liveness probe và restart database khi recovery.
- Coi StatefulSet là PostgreSQL failover controller.
- Không test volume detach/reattach hoặc zone failure.
- Dùng password trong Docker image hoặc source control.
- Expose PostgreSQL public mà không có network controls.
- Không tính tổng connection pools từ mọi application replicas.
- Cho rằng managed provider sẽ xử lý schema/query tuning.
- Giả định mọi extensions có trên managed service.
- Giả định PostgreSQL-compatible nghĩa là full compatibility.
- Không restore-test managed backups.
- Không hiểu asynchronous replica lag và read-after-write behavior.
- Đổi container image major mà không upgrade data directory.
- Không có owner cho patching, failover hoặc incidents.
- Không tính egress, backups, replicas và nhân lực vào TCO.
- Không có tested exit strategy khỏi provider.

## 49. Bài tập thực hành có đáp án

### Bài 1. Ba mô hình triển khai trong bài là gì?

**Đáp án:** PostgreSQL trên máy chủ riêng/VM, PostgreSQL trong container/platform và managed PostgreSQL.

### Bài 2. Dedicated server có tự bảo đảm HA không?

**Đáp án:** Không. HA cần replicas, failover, fencing, routing và recovery procedures.

### Bài 3. Bare metal khác VM ở điểm nào?

**Đáp án:** Bare metal chạy trực tiếp trên hardware; VM chạy qua hypervisor và tài nguyên ảo hóa.

### Bài 4. VM có thể là self-managed PostgreSQL không?

**Đáp án:** Có. Team vẫn chịu trách nhiệm guest OS, PostgreSQL và operations theo phạm vi của mình.

### Bài 5. Container image có phải backup database không?

**Đáp án:** Không. Image chứa runtime/binaries; backup phải bảo vệ database state và WAL theo recovery plan.

### Bài 6. Vì sao container cần persistent volume?

**Đáp án:** Writable container filesystem có thể bị xóa khi container bị remove/recreate; volume giữ data directory qua lifecycle đó.

### Bài 7. Named volume có thay backup off-host không?

**Đáp án:** Không. Volume chỉ cung cấp persistence trong phạm vi storage host/platform; cần backup độc lập.

### Bài 8. Docker Compose phù hợp nhất với tình huống nào?

**Đáp án:** Local development và integration tests, dù có thể dùng trong một số deployment nhỏ nếu operations được thiết kế đầy đủ.

### Bài 9. pg_isready healthcheck chứng minh điều gì?

**Đáp án:** Server có accept connection theo điều kiện kiểm tra; không chứng minh business queries hay backup/replication khỏe.

### Bài 10. Đổi image PostgreSQL 16 sang 17 có tự major-upgrade data không?

**Đáp án:** Không. Cần pg_upgrade, dump/restore, logical migration hoặc workflow được hỗ trợ.

### Bài 11. StatefulSet tự promote PostgreSQL standby khi primary lỗi?

**Đáp án:** Không. Cần PostgreSQL-aware operator/controller hoặc failover tooling.

### Bài 12. Vì sao cần startup probe?

**Đáp án:** Cho database đủ thời gian khởi động/crash recovery trước khi liveness probe can thiệp.

### Bài 13. Liveness probe quá aggressive gây gì?

**Đáp án:** Restart loop khi database chậm hoặc đang recovery, làm tình trạng tệ hơn.

### Bài 14. PVC có bảo đảm storage phù hợp PostgreSQL không?

**Đáp án:** Không. Cần xác minh CSI driver, durability, IOPS, latency, topology và filesystem semantics.

### Bài 15. Shared ReadWriteMany volume có thể cho nhiều PostgreSQL primaries cùng dùng data directory không?

**Đáp án:** Không. PostgreSQL cluster data directory không phải shared multi-writer filesystem workload.

### Bài 16. Operator làm gì?

**Đáp án:** Reconcile desired state và có thể tự động hóa bootstrap, replicas, failover, backups và upgrades theo feature support.

### Bài 17. Operator có thay DBA không?

**Đáp án:** Không. Query tuning, schema design, recovery validation và business decisions vẫn cần owner.

### Bài 18. Managed PostgreSQL là gì?

**Đáp án:** Dịch vụ provider quản lý một phần hoặc phần lớn infrastructure/database operations.

### Bài 19. Managed service có cho root access không?

**Đáp án:** Thường không. Người dùng thao tác qua service APIs/console và quyền database được provider hỗ trợ.

### Bài 20. Managed service có tự tối ưu mọi SQL queries không?

**Đáp án:** Không. Query/schema/index design và workload tuning vẫn thuộc người dùng.

### Bài 21. PostgreSQL-compatible có đồng nghĩa full PostgreSQL compatibility không?

**Đáp án:** Không. Kiểm tra SQL semantics, extensions, transactions, replication và unsupported features.

### Bài 22. Vì sao cần shared responsibility matrix?

**Đáp án:** Xác định rõ provider, platform, DBA và application team chịu trách nhiệm controls nào.

### Bài 23. RPO là gì?

**Đáp án:** Mức dữ liệu tối đa có thể chấp nhận mất tại thời điểm recovery.

### Bài 24. RTO là gì?

**Đáp án:** Thời gian tối đa để khôi phục service sau sự cố.

### Bài 25. Automated backup có thay restore drill không?

**Đáp án:** Không. Cần thực sự restore và kiểm tra dữ liệu, extensions, roles và application connectivity.

### Bài 26. Logical backup khác physical backup thế nào?

**Đáp án:** Logical export objects/data; physical backup bảo vệ cluster files/WAL và có thể hỗ trợ PITR theo tool.

### Bài 27. Volume snapshot có luôn application-consistent không?

**Đáp án:** Không. Cần database/storage coordination hoặc PostgreSQL-aware backup workflow.

### Bài 28. Vì sao asynchronous replica có thể mất writes khi failover?

**Đáp án:** Standby có thể chưa nhận/replay hết WAL mà primary đã xác nhận.

### Bài 29. Synchronous replication có trade-off gì?

**Đáp án:** Có thể giảm data loss cho failure classes nhưng tăng commit latency và phụ thuộc standby availability.

### Bài 30. Vì sao application phải reconnect sau failover?

**Đáp án:** Sessions/transactions đang mở có thể bị ngắt; endpoint có thể chuyển sang primary mới.

### Bài 31. PgBouncer giải quyết vấn đề gì?

**Đáp án:** Connection pooling và giảm backend connection churn/overhead.

### Bài 32. Vì sao tổng pool size phải tính qua mọi app instances?

**Đáp án:** Mỗi instance tạo pool riêng; tổng connections có thể vượt max_connections của database.

### Bài 33. Encryption at rest thay TLS không?

**Đáp án:** Không. At-rest bảo vệ storage; TLS bảo vệ traffic trên network.

### Bài 34. Secret có nên bake vào container image?

**Đáp án:** Không. Dùng secret manager hoặc injection runtime có access controls.

### Bài 35. Managed IAM auth có hoàn toàn không cần credential lifecycle?

**Đáp án:** Không. Token expiry, IAM policy, driver/proxy support và identity lifecycle vẫn cần quản lý.

### Bài 36. Khi nào self-managed phù hợp hơn managed?

**Đáp án:** Khi cần OS/storage/extension control, on-prem requirement hoặc có đội ngũ vận hành đủ năng lực.

### Bài 37. Khi nào managed thường phù hợp?

**Đáp án:** Khi muốn giảm infrastructure operations và provider features đáp ứng compatibility, availability, recovery, compliance và cost requirements.

### Bài 38. Vì sao TCO phải tính nhân lực?

**Đáp án:** Provisioning, patching, backup, failover, incidents và on-call là chi phí thực của self-managed systems.

### Bài 39. Read replicas có tăng write capacity không?

**Đáp án:** Không. Chúng chủ yếu offload reads khỏi primary.

### Bài 40. Container có phải lựa chọn thay thế underlying VM/bare metal?

**Đáp án:** Không. Container vẫn chạy trên host infrastructure; storage/compute failure domains vẫn cần thiết kế.

### Bài 41. Multi-AZ và cross-region DR khác nhau thế nào?

**Đáp án:** Multi-AZ bảo vệ một số zone failures trong region; cross-region DR bảo vệ rộng hơn nhưng có latency/cost/RPO trade-offs.

### Bài 42. Vì sao phải kiểm tra extension availability trước khi chọn managed service?

**Đáp án:** Provider có thể chỉ hỗ trợ một tập extensions/versions nhất định.

### Bài 43. Vì sao image digest hữu ích?

**Đáp án:** Nó pin chính xác image artifact, tránh tag bị thay đổi nội dung ngoài ý muốn.

### Bài 44. PodDisruptionBudget bảo vệ khỏi mọi node failures?

**Đáp án:** Không. Nó chủ yếu giới hạn voluntary disruptions theo policy.

### Bài 45. Managed provider failover có bảo đảm transaction đang chạy thành công?

**Đáp án:** Không. Session có thể bị disconnect; application cần xử lý retry/idempotency.

### Bài 46. Vendor lock-in đến từ đâu?

**Đáp án:** Proprietary APIs, extensions, auth, backup formats, proxy, monitoring và provider-specific behavior.

### Bài 47. Exit strategy nên test gì?

**Đáp án:** Export/import schema/data, roles, sequences, extensions, large objects, CDC cutover, timing và application reconnect.

### Bài 48. Một restore drill tốt phải xác minh gì?

**Đáp án:** Database starts, roles/extensions exist, data integrity, application connectivity và measured RTO.

### Bài 49. Vì sao staging nên gần production?

**Đáp án:** Để test version, extensions, configuration, data volume, storage, networking, failover và migration behavior thực tế.

### Bài 50. Tiêu chí chọn deployment model quan trọng nhất là gì?

**Đáp án:** Workload, RPO/RTO, security/compliance, extension/configuration needs, team operations capability, TCO, portability và provider limits.

## 50. Checklist đóng quyết định deployment

| Nhóm | Câu hỏi cần trả lời |
|---|---|
| Workload | CPU, memory, I/O, connections, growth và latency đã đo? |
| Control | Cần quyền OS, filesystem, extension hoặc kernel tới mức nào? |
| Platform | Physical, VM, container hay managed service? |
| Persistence | Data/WAL nằm trên storage nào và durability ra sao? |
| HA | Replica topology, failover, fencing và routing? |
| Backup | Physical/logical backup, WAL archive và retention? |
| Recovery | RPO/RTO đã được test bằng restore drill? |
| Upgrade | Ai patch OS/PostgreSQL/extensions và major versions? |
| Security | TLS, encryption, keys, secrets, roles và audit? |
| Network | Private endpoint, firewall, DNS và connection pooling? |
| Observability | DB/platform metrics, logs, alerts và on-call owner? |
| Compliance | Data residency, backup location, audit evidence và support access? |
| Compatibility | Extensions, drivers, tools và SQL behavior? |
| Cost | Compute, storage, IOPS, replicas, backups, egress và nhân lực? |
| Portability | Export/import và provider exit path đã thử? |
| Ownership | RACI rõ giữa provider, platform, DBA và application? |

## 51. Tài liệu tham khảo chính thức

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/) — installation, configuration, backup, replication và administration.
- [PostgreSQL Installation](https://www.postgresql.org/docs/current/installation.html) — cài đặt trên các nền tảng.
- [PostgreSQL Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config.html) — server settings.
- [PostgreSQL Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup/PITR/recovery.
- [PostgreSQL High Availability](https://www.postgresql.org/docs/current/high-availability.html) — replication và failover concepts.
- [PostgreSQL pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — major-version upgrade.
- [Docker Official PostgreSQL Image](https://hub.docker.com/_/postgres) — image usage, environment variables và persistence guidance.
- [Docker Storage](https://docs.docker.com/engine/storage/) — volumes và container storage.
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) — stateful workload identity/storage.
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) — PV/PVC/storage lifecycle.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — startup/readiness/liveness.
- [Kubernetes Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruption controls.
- [PgBouncer](https://www.pgbouncer.org/) — connection pooling.
- [Cloud Native PostgreSQL](https://cloudnative-pg.io/documentation/) — PostgreSQL operator concepts and operations.
- [AWS RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html) — ví dụ managed PostgreSQL service documentation.
- [Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/) — ví dụ managed service features/limits.
- [Google Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres) — ví dụ managed service operations.

Provider capabilities, service limits, supported extensions, backup semantics và pricing thay đổi theo region/tier/version. Kiểm tra documentation hiện hành và hợp đồng dịch vụ cho deployment cụ thể trước khi quyết định production.

## 52. Tổng kết: chọn nơi chạy theo trách nhiệm và recovery

```text
Need full OS/storage control?
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Self-managed?   Prefer provider-managed operations?
   |                   |
   v                   v
Bare metal/VM      Managed PostgreSQL
or container host       |
   |                    |
   v                    v
Can team own       Do features, limits,
backup/HA/patch?   RPO/RTO and cost fit?
   |                    |
   +---------+----------+
             |
             v
       Validate storage,
       security, upgrades,
       restore and exit path
             |
             v
       Production readiness
```

Những nguyên tắc cần nhớ:

1. **Máy chủ riêng tối đa quyền kiểm soát và trách nhiệm.** Đội ngũ phải sở hữu OS, PostgreSQL, storage, backup, HA, patching và on-call.
2. **VM và bare metal là lựa chọn compute/hardware.** Cả hai đều có thể chạy PostgreSQL self-managed; dedicated hardware không tự tạo HA.
3. **Container chuẩn hóa runtime, không tự quản lý database lifecycle.** Persistent volumes, backup, failover và major upgrade vẫn cần thiết kế riêng.
4. **StatefulSet không tự là PostgreSQL HA controller.** Dùng operator/tooling đã được kiểm chứng và test fencing, promotion, storage recovery.
5. **Managed PostgreSQL giảm hạ tầng tự vận hành.** Người dùng vẫn chịu trách nhiệm schema, queries, permissions, application resilience và restore validation.
6. **PostgreSQL-compatible không bảo đảm full compatibility.** Kiểm tra extensions, SQL semantics, parameters, limits và replication behavior.
7. **RPO/RTO phải được diễn tập.** Backup job thành công hoặc provider SLA không chứng minh business recovery đã đạt.
8. **Storage và networking quyết định nhiều tới database performance.** Benchmark latency, IOPS, throughput, durability và connection behavior.
9. **Security cần ở mọi mô hình.** TLS, encryption, least privilege, secrets, audit và network isolation vẫn cần cấu hình.
10. **TCO bao gồm cả nhân lực và downtime.** So sánh cost per workload unit, không chỉ giá instance.
11. **Portability cần được thử.** Export/restore, extension replacement, global objects và exit time là bằng chứng thực tế.
12. **Chọn theo capability của team và yêu cầu business.** Mô hình tốt là mô hình đáp ứng workload, recovery và compliance với chi phí vận hành chấp nhận được.

**Một câu để nhớ:** *Máy chủ riêng cho quyền kiểm soát, container cho runtime nhất quán, managed PostgreSQL cho operations được chia sẻ; hãy chọn theo workload, trách nhiệm, recovery objectives và tổng chi phí sở hữu.*

