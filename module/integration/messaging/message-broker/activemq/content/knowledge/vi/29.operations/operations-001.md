# Đóng gói image, cấu hình và dữ liệu broker độc lập

> **Chương:** Vận hành  
> **Phạm vi:** Đóng gói và triển khai Apache ActiveMQ Classic/Artemis trong container sao cho **image chứa runtime bất biến**, **cấu hình được quản lý riêng**, **dữ liệu broker được lưu bền độc lập** và **secret có vòng đời riêng**. Bài tập trung cấu trúc thư mục, đường dẫn storage, Docker Compose/Kubernetes, backup/restore, nâng cấp và rollback. Không dùng một volume dữ liệu chung cho nhiều broker active.

## 1. Vì sao phải tách image, config và data?

Một broker có ba loại tài sản với vòng đời khác nhau:

1. **Image/runtime:** binary broker, JRE, thư viện, script khởi động, user/permission của hệ điều hành. Thành phần này cần version hóa, scan và promote qua các môi trường.
2. **Configuration:** `broker.xml` hoặc `activemq.xml`, acceptor/connector, queue/address policy, persistence settings, security policy, log level và resource limit. Cấu hình cần review, version control và thay đổi có kiểm soát.
3. **Data:** message persistent, journal, bindings, paging, large messages, KahaDB index/store, transaction recovery và metadata. Dữ liệu phải sống lâu hơn container và image.

**Secret** (password, keystore private key, certificate key password) là lớp thứ tư: cấp phát, phân quyền, audit và rotation riêng. Không bake chúng vào image hoặc repository.

~~~mermaid
flowchart TB
    I["OCI Image\nBroker binary + JRE + startup"] --> R["Broker Container"]
    C["Config version\nbroker.xml / activemq.xml"] -->|"read-only mount"| R
    S["Secrets\npassword / keystore / cert"] -->|"protected mount"| R
    D[("Persistent data volume\njournal / KahaDB / paging")] <-->|"read + write"| R
    L["Logs / metrics / traces"] <-->|"stdout / collector"| R
~~~

Khi triển khai image mới, container có thể được thay thế. **Data volume vẫn được giữ nguyên**; cấu hình được gắn theo version đã duyệt; secret được cấp từ secret manager. Khi thay cấu hình, không cần rebuild broker binary image. Khi nâng version broker, không nên đồng thời thay đổi không kiểm soát data layout và security.

### 1.1. Điều gì xảy ra nếu gộp cả ba vào container filesystem?

| Cách làm | Hậu quả |
|---|---|
| Broker ghi journal vào writable layer của container | Xóa/thay container có thể làm mất message persistent |
| Copy `broker.xml` vào image rồi sửa trực tiếp trong container | Thay container sẽ mất chỉnh sửa; không có nguồn cấu hình tái lập |
| Bake password/private key vào image | Secret tồn tại trong image layers, registry, cache và lịch sử build |
| Mount cùng data directory vào nhiều broker active | Hai tiến trình có thể ghi cùng store, gây corruption hoặc vi phạm lock |
| Upgrade image và xóa volume cùng lúc | Không thể phân biệt lỗi runtime với mất dữ liệu |
| Backup bằng cách copy file store đang được broker ghi | Snapshot có thể không nhất quán giữa journal/index/metadata |

**Mục tiêu vận hành:** có thể thay container, triển khai lại cấu hình và rotate secret mà không xóa nhầm dữ liệu broker.

## 2. Hợp đồng thư mục của một broker instance

Một layout dễ hiểu cho một instance:

~~~text
/opt/broker/                 # runtime thuộc image, không chứa message state
  bin/
  lib/
  ...

/etc/broker/                 # config được mount read-only
  broker.xml                 # Artemis
  activemq.xml               # Classic
  login.config               # nếu dùng JAAS

/run/secrets/broker/         # secret mount, read-only
  jms-user
  jms-password
  keystore.p12
  keystore-password
  truststore.p12

/var/lib/broker/             # persistent volume riêng của instance
  journal/
  bindings/
  paging/
  large-messages/
  kahadb/

/var/log/broker/             # log nếu không ghi stdout
~~~

Đây là **layout triển khai do tổ chức quy ước**, không phải đường dẫn bắt buộc của cả hai broker. Phải ánh xạ đúng đường dẫn mà distribution/image và config thực tế sử dụng. Một số image đặt Artemis instance tại `/var/lib/artemis-instance`; Classic distribution thường dùng `$ACTIVEMQ_HOME/conf` và `$ACTIVEMQ_DATA`. Hãy kiểm tra image contract trước khi mount.

| Thành phần | Vòng đời | Cách lưu |
|---|---|---|
| Broker binary/JRE | Theo release image | OCI image, tag + digest |
| `broker.xml`/`activemq.xml` | Theo config release | ConfigMap, bind mount hoặc artifact config |
| JAAS/user store/keystore | Theo secret/certificate version | Secret manager/secret volume |
| Journal/KahaDB/paging | Theo broker data lifecycle | Persistent volume/disk |
| Log | Theo retention/observability | stdout/stderr hoặc log volume riêng |
| Metrics/traces | Theo monitoring platform | Exporter/collector, không nằm trong journal |

Không mount toàn bộ `/opt/broker` hoặc toàn bộ broker instance lên một PVC nếu mục tiêu là tách vòng đời. Mount cả thư mục có thể che khuất binary/config nằm trong image và làm upgrade khó dự đoán.

## 3. Image: bất biến, định danh rõ ràng và có thể tái lập

Một image broker nên chứa:

- Một phiên bản broker và JRE tương thích đã được kiểm tra.
- Runtime libraries và startup/health scripts cần thiết.
- User/group hệ điều hành không có quyền root nếu image hỗ trợ.
- Metadata release, SBOM, scan result và source provenance.
- Không chứa message data, môi trường production-specific, password hoặc private key.

### 3.1. Pin image theo version và digest

Ví dụ Compose dùng biến image reference:

~~~yaml
services:
  broker:
    image: ${BROKER_IMAGE:?set an immutable broker image reference}
~~~

Giá trị production nên có version cụ thể và **digest**:

~~~text
BROKER_IMAGE=registry.example.internal/messaging/artemis:2.37.0@sha256:<approved-digest>
~~~

Chuỗi digest là placeholder; thay bằng digest thật do registry/build pipeline cung cấp. Tag giúp con người đọc version, digest giúp cố định đúng artifact. Không dùng `latest` cho production vì cùng một manifest có thể kéo image khác ở lần deploy sau.

Với Classic và Artemis, nên build/promote hai image artifact riêng. Không nhét cả hai broker vào một image rồi chọn provider bằng environment variable; binary, config schema, client compatibility và data format khác nhau.

### 3.2. Dockerfile wrapper tối giản khi cần chuẩn hóa metadata

Nếu tổ chức cần một image promotion layer để gắn metadata hoặc policy, có thể tạo wrapper từ image broker đã được pin:

~~~dockerfile
ARG BROKER_BASE_IMAGE
FROM ${BROKER_BASE_IMAGE}

LABEL org.opencontainers.image.title="messaging-broker-runtime"
LABEL org.opencontainers.image.description="Pinned broker runtime; config and data are external"
~~~

Build với base image đã duyệt:

~~~bash
docker build \
  --build-arg BROKER_BASE_IMAGE="registry.example.internal/base/artemis:2.37.0@sha256:<digest>" \
  -t registry.example.internal/platform/artemis-runtime:2.37.0 .
~~~

Dockerfile này cố ý không COPY broker config, secret hay data vào image. Nếu cần custom entrypoint/health script, chỉ thêm script vận hành không chứa môi trường production; kiểm tra UID, quyền file, signal handling và health semantics của base image trước khi override entrypoint.

**Không dùng** build argument cho password hoặc private key: build args có thể xuất hiện trong metadata/cache/history tùy builder. Bí mật phải được cấp lúc runtime qua secret integration.

## 4. Artemis: tách broker.xml khỏi journal và paging data

Artemis lưu nhiều loại dữ liệu. Với một broker instance:

- **Bindings:** metadata về address/queue/binding.
- **Journal:** message persistent và transaction records theo journal configuration.
- **Paging:** dữ liệu khi address vượt giới hạn memory và đi vào paging.
- **Large messages:** body lớn được lưu riêng theo cơ chế large-message.
- **Configuration:** `broker.xml`, `bootstrap.xml`, `login.config` và logging config thuộc cấu hình instance.

Trong `broker.xml`, đặt các thư mục dữ liệu thành đường dẫn tuyệt đối trên volume riêng. Ví dụ fragment trong `<core>`:

~~~xml
<core xmlns="urn:activemq:core">
  <name>artemis-a</name>
  <persistence-enabled>true</persistence-enabled>

  <bindings-directory>/var/lib/broker/artemis-a/bindings</bindings-directory>
  <journal-directory>/var/lib/broker/artemis-a/journal</journal-directory>
  <paging-directory>/var/lib/broker/artemis-a/paging</paging-directory>
  <large-messages-directory>/var/lib/broker/artemis-a/large-messages</large-messages-directory>

  <journal-type>NIO</journal-type>
  <!-- Các cấu hình acceptor, address, security, limits... -->
</core>
~~~

Đây là **fragment**, không phải `broker.xml` hoàn chỉnh. Khi ghép vào file thật, giữ đúng namespace và thứ tự phần tử theo XSD của phiên bản Artemis. `NIO` là lựa chọn portable; nếu dùng `ASYNCIO`, image/host cần thư viện native và kernel/filesystem phù hợp.

Các path ở trên phải cùng nằm trên volume data của broker A. Không để một số thư mục rơi về writable layer vì quên mount.

### 4.1. Một broker instance, một volume data độc lập

Ví dụ mount volume:

~~~yaml
services:
  artemis-a:
    image: ${ARTEMIS_IMAGE:?set approved image digest}
    volumes:
      - ./config/artemis-a/broker.xml:/var/lib/artemis-instance/etc/broker.xml:ro
      - artemis-a-data:/var/lib/broker/artemis-a
      - ./secrets/artemis-a:/run/secrets/broker:ro
    stop_grace_period: 60s

volumes:
  artemis-a-data:
~~~

Ví dụ giả định image đặt instance config tại `/var/lib/artemis-instance/etc`; thư mục data được cấu hình tuyệt đối như fragment trên. Nếu image dùng instance path khác, mount đúng path mà startup/bootstrap thực sự đọc.

Không mount `artemis-a-data` vào hai broker active. Broker A và B cần data directories, node identity và storage lifecycle riêng. Cluster forwarding không phải lý do để chia sẻ journal.

### 4.2. Không phải mọi file trong instance đều là data

Không cần đưa toàn bộ `etc/` vào PVC. Làm vậy sẽ khiến config cũ tồn tại qua các image upgrade và có thể che cấu hình mặc định mới của version mới. Chỉ mount **các file cấu hình được quản lý**, giữ data ở volume riêng và secrets ở mount riêng.

Nếu image entrypoint tự sinh `broker.xml` khi khởi động lần đầu, hãy xác định cơ chế bootstrap: config mount read-only phải tồn tại đúng lúc entrypoint cần đọc; không để entrypoint cố ghi vào ConfigMap hoặc file read-only.

## 5. Classic: tách activemq.xml khỏi KahaDB

ActiveMQ Classic thường dùng KahaDB persistent store. Cấu hình KahaDB chỉ rõ directory nằm trên persistent volume:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-a"
        persistent="true">

  <persistenceAdapter>
    <kahaDB directory="/var/lib/broker/classic-a/kahadb"/>
  </persistenceAdapter>

  <!-- transportConnectors, destinationPolicy, systemUsage,
       plugins và các phần tử broker khác -->
</broker>
~~~

Đây là fragment của `activemq.xml`; giữ nguyên phần tử/cấu hình khác và schema của đúng Classic release. `directory` phải là đường dẫn bền đã mount, không phải thư mục tạm trong container.

Classic cũng có thể lưu scheduler/job metadata hoặc plugin state ở các thư mục khác tùy cấu hình. Kiểm kê **mọi store đang bật**, không chỉ KahaDB, trước khi quyết định volume nào cần backup.

### 5.1. Ví dụ mapping container Classic

~~~yaml
services:
  classic-a:
    image: ${CLASSIC_IMAGE:?set approved image digest}
    volumes:
      - ./config/classic-a/activemq.xml:/opt/activemq/conf/activemq.xml:ro
      - classic-a-data:/var/lib/broker/classic-a
      - ./secrets/classic-a:/run/secrets/broker:ro
    stop_grace_period: 60s

volumes:
  classic-a-data:
~~~

Ví dụ giả định image đặt cấu hình tại `/opt/activemq/conf`; đường dẫn này cần khớp image thực tế. `activemq.xml` phải trỏ KahaDB đến `/var/lib/broker/classic-a/kahadb` (hoặc path tương ứng bên trong data volume). Đừng chỉ mount `/var/lib/broker/classic-a` mà vẫn để KahaDB ghi vào `$ACTIVEMQ_HOME/data` trong writable layer.

### 5.2. Không copy KahaDB đang chạy như file thông thường

KahaDB có journal, index/lock và file lifecycle. Copy directory trong lúc broker đang ghi có thể tạo snapshot không nhất quán. Dùng quy trình backup/snapshot được hỗ trợ, dừng broker sạch hoặc storage snapshot nhất quán theo hướng dẫn của version. Backup phải chứa metadata/config cần thiết để khôi phục cùng phiên bản store.
## 6. Cấu hình và secret: mount riêng, read-only

Cấu hình thường không chứa private secret. Có thể quản lý `broker.xml`/`activemq.xml` như code, review và version hóa; mount read-only vào container. Secret được cấp riêng:

~~~text
config/
  artemis-a/
    broker.xml
    logging.properties
  classic-a/
    activemq.xml
    login.config

secrets/                 # không commit vào Git
  artemis-a/
    jms-user
    jms-password
    broker-keystore.p12
    broker-keystore-password
  classic-a/
    jms-user
    jms-password
    broker-keystore.p12
    broker-keystore-password
~~~

Các tên file là quy ước ví dụ. Broker chỉ đọc file secret nếu security/SSL configuration thực tế tham chiếu đến chúng. Không giả định broker tự hỗ trợ cú pháp `${ENV_VAR}` hoặc tự đọc mọi file trong `/run/secrets`.

### 6.1. Classic user store/JAAS và Artemis security

Classic có thể dùng JAAS, properties login module, LDAP hoặc plugin. Artemis cũng có JAAS/security domain, properties login module hoặc LDAP. Cách cấu hình cụ thể phụ thuộc version và backend; **tách file user/role chứa password ra khỏi image**, cấp file qua secret mount hoặc tích hợp identity provider.

Quyền file secret chỉ cho UID/GID broker đọc. Không cấp read access cho mọi container trong cùng pod/task. Không log nội dung `users.properties`, `roles.properties`, keystore hay environment dump.

### 6.2. Cấu hình thay đổi cần rollout có kiểm soát

- Một số property có thể reload, một số cần restart broker hoặc listener.
- ConfigMap mount read-only không có nghĩa broker tự reload file.
- Nếu mount file bằng `subPath`, thay ConfigMap thường không cập nhật nội dung file trong container hiện hữu; cần rollout pod/container.
- Mỗi lần thay config nên gắn version/hash, review diff, test staging, rồi rollout.
- Không thay `broker.xml` và broker data format trong cùng một lần nâng cấp nếu chưa có migration/rollback plan.

## 7. Docker Compose: ba loại mount độc lập

Ví dụ triển khai một Artemis node trong môi trường lab/staging:

~~~yaml
services:
  artemis:
    image: ${ARTEMIS_IMAGE:?set approved image ref}
    restart: unless-stopped
    ports:
      - "61616:61616"
    volumes:
      # Configuration: read-only, do pipeline quản lý.
      - ./config/artemis/broker.xml:/var/lib/artemis-instance/etc/broker.xml:ro

      # Data: persistent, vòng đời dài hơn container.
      - artemis-data:/var/lib/broker/artemis-a

      # Secrets: mount read-only, không nằm trong image/config repo.
      - ./runtime-secrets/artemis-a:/run/secrets/broker:ro

    stop_grace_period: 60s

volumes:
  artemis-data:
~~~

Compose chỉ tạo được mount; nó **không tự làm cho broker đọc secret** hoặc tạo đúng data paths. `broker.xml` phải đặt journal/bindings/paging/large-message directories đúng như volume mount. Cổng, acceptor và health check phải khớp config thực tế.

File `.env` dùng để truyền `ARTEMIS_IMAGE` nên chứa image reference không bí mật; không dùng `.env` như kho password production. Với secret, ưu tiên Docker secrets/secret manager integration; bind mount ở ví dụ chỉ là lab/staging có quyền filesystem chặt.

### 7.1. Tách config release khỏi image release

Một release có thể được biểu diễn:

~~~text
broker-runtime:  artemis 2.37.0 @ sha256:...
broker-config:   artemis-a-config v12
broker-secrets:  secret versions user-v8 / tls-v4
broker-data:     volume artemis-a-data (không thay khi deploy config)
~~~

Khi đổi `broker.xml`, tăng version config và rollout. Khi đổi password/certificate, tăng secret version và thực hiện rotation. Khi nâng broker, promote image mới sau test tương thích data. **Không tạo image mới chỉ để thay queue policy**, và không xóa volume chỉ để “cài lại broker”.

## 8. Kubernetes: ConfigMap, Secret và PVC có lifecycle khác nhau

Một StatefulSet là lựa chọn phù hợp khi cần danh tính network ổn định và volume riêng theo ordinal. Ví dụ rút gọn cho **một Artemis replica**:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: artemis-a-config-v12
data:
  broker.xml: |
    <!-- Nội dung broker.xml đã được review và khớp image/version -->
---
apiVersion: v1
kind: Service
metadata:
  name: artemis
spec:
  clusterIP: None
  selector:
    app: artemis
  ports:
    - name: core
      port: 61616
      targetPort: 61616
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: artemis
spec:
  serviceName: artemis
  replicas: 1
  selector:
    matchLabels:
      app: artemis
  template:
    metadata:
      labels:
        app: artemis
    spec:
      containers:
        - name: broker
          image: registry.example.internal/messaging/artemis:2.37.0@sha256:<digest>
          ports:
            - name: core
              containerPort: 61616
          volumeMounts:
            - name: config
              mountPath: /var/lib/artemis-instance/etc/broker.xml
              subPath: broker.xml
              readOnly: true
            - name: data
              mountPath: /var/lib/broker/artemis-a
            - name: secrets
              mountPath: /run/secrets/broker
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: artemis-a-config-v12
        - name: secrets
          secret:
            secretName: artemis-a-secret-v8
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 50Gi
~~~

Đây là manifest minh họa; cần điền ConfigMap `broker.xml` thật, Secret, storage class, resource limits/requests, security context, probes và service ports theo môi trường. Đường dẫn config giả định instance path `/var/lib/artemis-instance`; phải khớp image. Đường dẫn data trong `broker.xml` phải nằm dưới `/var/lib/broker/artemis-a`.

**Chú ý:** ví dụ dùng `subPath` nên ConfigMap update không tự thay file trong pod đang chạy. Đặt tên ConfigMap theo version (`v12`) và thay reference để tạo rollout có kiểm soát. PVC `ReadWriteOnce` chỉ là access mode của storage, không phải cơ chế HA hay fencing đầy đủ.

### 8.1. Vì sao StatefulSet thay vì Deployment cho broker có local store?

StatefulSet cung cấp identity/ordinal và PVC gắn với pod ổn định hơn. Nó **không tự tạo cluster, replication hoặc backup**. Nếu chạy nhiều replica, cần config mỗi node có node identity riêng, connector/acceptor đúng, data volume riêng và cluster/HA policy đã thiết kế. Không tăng `replicas: 3` cho một broker image rồi mount cùng một PVC vào cả ba.

## 9. Mỗi broker active phải có data directory riêng

Ví dụ hai node Artemis A/B:

~~~text
artemis-a:
  image: artemis@sha256:...
  config: artemis-a/broker.xml
  secret: artemis-a-secrets
  data: pvc-artemis-a

artemis-b:
  image: artemis@sha256:...
  config: artemis-b/broker.xml
  secret: artemis-b-secrets
  data: pvc-artemis-b
~~~

Classic cũng theo nguyên tắc tương tự: mỗi active broker có store riêng. Các node trao đổi message qua cluster bridge/load balancing, hoặc tham gia một HA design rõ ràng. **Không dùng một KahaDB hoặc Artemis journal path cho nhiều broker process active** để tiết kiệm disk.

Các chế độ HA như shared store hoặc replication là kiến trúc chuyên biệt, cần tuân theo quy tắc lock/fencing/primary-backup của broker và storage. Không suy ra rằng hai StatefulSet replica có thể cùng mount volume và tự chọn một writer an toàn.

## 10. Health check: liveness khác readiness

Một TCP port mở không có nghĩa broker đã sẵn sàng nhận nghiệp vụ. Phân biệt:

- **Liveness:** process/VM còn sống, không deadlock; nếu thất bại liên tục, orchestrator có thể restart.
- **Readiness:** broker đã nạp config, mở acceptor, store sẵn sàng và có thể nhận traffic theo policy.
- **Business probe:** client thử xác thực và thao tác queue test/management được cấp quyền; chạy có kiểm soát, tránh tạo message rác.

Không đặt health check phụ thuộc một hệ thống ngoài (ví dụ DB không liên quan) khiến broker restart liên tục. Probe cần timeout ngắn, tần suất hợp lý, credentials test riêng và không log secret.

Với broker cluster, readiness có thể khác nhau giữa “node đã listen” và “cluster topology đã hình thành”. Nếu producer được route tới node khi cluster chưa ready, message có thể được lưu local rồi chuyển sau; test và SLO cần định nghĩa rõ.

## 11. Logging và observability không nên nằm chung volume journal

Ưu tiên log ra stdout/stderr để runtime thu thập, hoặc dùng log volume riêng có retention. Không ghi log vận hành vào cùng partition/directory của journal nếu có thể tránh; log tăng đột biến không được chiếm hết disk chứa message store.

| Tín hiệu | Điều cần biết |
|---|---|
| Queue/address pending count | Backlog tăng hay giảm? |
| Delivering/in-flight count | Consumer giữ bao nhiêu message chưa ACK? |
| Oldest message age | Job chờ lâu nhất bao nhiêu? |
| Producer send errors/latency | Broker/cluster có từ chối hoặc chậm? |
| Consumer count/reconnect | Worker pool có hoạt động? |
| Redelivery/DLQ | Có poison message hoặc crash loop? |
| Journal/KahaDB disk usage | Store sắp đầy? |
| Paging/large-message usage | Address đang đẩy dữ liệu ra disk? |
| Open files/file descriptors | Process có gần giới hạn OS? |
| Certificate expiry/auth failures | Security rotation có vấn đề? |

Đặt cảnh báo theo capacity và tốc độ tăng, không chỉ một ngưỡng cố định. Volume còn 20% free có thể là quá muộn nếu producer đang tạo backlog rất nhanh.

## 12. Backup/restore: dữ liệu broker không phải cache có thể tái tạo tùy ý

Message persistent, transaction records, bindings và metadata cần consistency. Backup đúng cách phải xác định:

1. Store nào đang active (Artemis journal/bindings/paging/large messages; Classic KahaDB và store khác).
2. Broker có hỗ trợ backup/replication/snapshot method nào trong version hiện hành.
3. Snapshot có nhất quán giữa nhiều thư mục/volume không.
4. Config và secret version nào cần để mở store đã backup.
5. Có thể restore vào cùng broker version hay cần migration.
6. RPO/RTO, retention, encryption và quyền truy cập backup.

**Không copy từng file journal/KahaDB khi broker đang ghi** rồi gọi đó là backup hợp lệ. Dùng broker dừng sạch, công cụ backup được hỗ trợ hoặc storage snapshot nhất quán theo hướng dẫn chính thức của version. Khi snapshot nhiều volume, cần một điểm nhất quán chung.

### 12.1. Bài kiểm tra restore phải chạy định kỳ

- Tạo một batch message có business ID xác định.
- Commit producer và ghi lại số message mong đợi.
- Thực hiện backup theo runbook.
- Khôi phục vào môi trường cô lập, không cho producer production kết nối.
- Khởi động đúng broker version/config tương thích.
- Consume/đối soát body, headers/properties và transaction state theo yêu cầu.
- Đo thời gian khôi phục; ghi số message mất/trùng.
- Chỉ khi test restore thành công mới xem backup là có thể sử dụng.

Backup có tồn tại trên object storage nhưng chưa từng restore **chưa phải bằng chứng khôi phục được**.
## 13. Upgrade image và config mà giữ data an toàn

Quy trình upgrade:

1. Pin image mới bằng version + digest; đọc release notes và kiểm tra compatibility của store/protocol/client.
2. Backup data nhất quán; thử restore trên bản sao.
3. Review diff config và các thay đổi mặc định trong `broker.xml`/`activemq.xml`.
4. Chạy broker mới với **bản sao data** trong staging, không dùng volume production để thử.
5. Chạy smoke test: connect, send/consume persistent message, transaction, redelivery, DLQ, management/metrics.
6. Chọn maintenance/rolling strategy phù hợp HA; không restart tất cả node đồng thời nếu thiết kế cần một node phục vụ.
7. Sau khi node mới healthy, kiểm tra queue counts, journal, DLQ và client reconnect.
8. Chỉ dọn image/config cũ sau khi hết rollback window.

### 13.1. Rollback image không luôn đơn giản

Broker có thể nâng cấp store hoặc metadata theo cách **không tương thích ngược**. Sau khi version mới đã ghi vào data volume, quay lại image cũ có thể không khởi động được hoặc đọc sai state.

Rollback an toàn thường là:

- Dừng/cô lập broker mới.
- Giữ nguyên volume đã lỗi để điều tra, không xóa.
- Khôi phục **snapshot trước upgrade** vào volume mới/được kiểm soát.
- Chạy lại image/config version cũ phù hợp snapshot.
- Reconcile message đã được producer gửi/consumer xử lý trong cửa sổ cutover bằng business ID/outbox/inbox.

**Không** chỉ thay image tag cũ rồi mount volume đã bị version mới mutate mà không kiểm tra compatibility.

## 14. Resource limits và disk: broker state cần được tính như dữ liệu

Broker sử dụng heap, direct/native memory, file descriptors và disk I/O. Khi đóng gói container:

- Đặt memory limit đủ cho heap **và** native/direct buffers, thread stacks, OS page cache theo workload.
- Không đặt heap bằng toàn bộ container memory limit.
- Đặt CPU request/limit theo latency/throughput thực đo; throttling quá mức làm chậm journal/dispatch.
- Đảm bảo volume có IOPS/throughput đủ cho persistence SLA.
- Theo dõi disk space, inode, journal growth, paging và large-message usage.
- Đặt `ulimit`/file descriptors theo số connections/queues/files thực tế.
- Không dùng ephemeral container filesystem cho persistent store.
- Không để log hoặc dump đầy volume data.

Broker có thể bị block khi disk đầy hoặc journal chậm. Việc container vẫn `Running` không có nghĩa broker còn phục vụ producer/consumer bình thường.

## 15. Thực hành: xác minh ba vòng đời độc lập

### Bài A — Thay container, giữ data

1. Dùng broker image đã pin, cấu hình queue durable và KahaDB/Artemis journal ở volume riêng.
2. Gửi 10 message persistent, commit transaction.
3. Ghi lại business IDs và queue count.
4. Dừng container sạch; xóa/recreate **container**, không xóa volume.
5. Start container mới cùng image/config/data volume.
6. Consume đủ 10 message, đối chiếu ID.

**Kết luận:** data được lưu ngoài writable layer. Test này không chứng minh HA hoặc disk failure recovery.

### Bài B — Đổi config không rebuild image

1. Giữ nguyên image digest.
2. Thay config version (ví dụ `redistribution-delay`, acceptor hoặc log level) trong config artifact.
3. Deploy mount/config version mới và restart/reload theo semantics.
4. Xác minh broker effective config.
5. Kiểm tra image digest không đổi và volume data vẫn giữ nguyên.

**Kết luận:** config có vòng đời độc lập với binary image.

### Bài C — Rotate secret không bake vào image

1. Cấp secret version B qua secret manager/secret volume.
2. Recreate broker/client connection theo cơ chế hỗ trợ.
3. Thử fresh authentication bằng B; sau cutover, thử A phải thất bại.
4. Kiểm tra image layers và config repo không chứa secret.
5. Ghi audit secret version đã triển khai.

**Kết luận:** secret có lifecycle và access control riêng.

### Bài D — Phân biệt volume của hai broker

1. Chạy hai broker active A/B với PVC/data directory riêng.
2. Gửi batch vào A, batch khác vào B.
3. Kiểm tra mỗi store có owner/process riêng.
4. Cluster-forward message theo config và đối soát business IDs.
5. Xác minh không có hai process mở cùng journal/KahaDB directory.

**Kết luận:** cluster message flow không đồng nghĩa dùng chung persistent store.

## 16. Checklist trước production

- [ ] Broker image pin version + digest, có scan/SBOM/provenance?
- [ ] Image không chứa message data, password, private key hay config production?
- [ ] `broker.xml`/`activemq.xml` được version hóa, review và mount read-only?
- [ ] Mọi storage path thực tế đều nằm trên persistent volume đã mount?
- [ ] Artemis đã tách bindings/journal/paging/large messages?
- [ ] Classic KahaDB (và store phụ nếu có) dùng volume bền?
- [ ] Secret mount tách riêng, read-only, có owner/rotation/audit?
- [ ] Broker chạy non-root theo UID/GID và file permissions phù hợp?
- [ ] Mỗi active broker có data directory/PVC riêng; không có shared writer tùy tiện?
- [ ] Log, metrics và traces không chiếm journal volume?
- [ ] Liveness/readiness probe phản ánh đúng trạng thái broker?
- [ ] Resource limits, disk/IOPS, file descriptors và memory được kiểm thử?
- [ ] Backup nhất quán, đã restore thử và có RPO/RTO?
- [ ] Upgrade test trên bản sao data, có rollback snapshot và reconciliation?
- [ ] Đã thử thay container giữ data, thay config không rebuild image và rotate secret độc lập?

## 17. Kết luận

Một broker được đóng gói tốt có **image bất biến**, **configuration được quản lý như code**, **secret được cấp theo vòng đời riêng** và **data store nằm trên persistent volume**. ActiveMQ Artemis cần tách bindings, journal, paging và large messages; ActiveMQ Classic cần đặt KahaDB vào storage bền. Đường dẫn phải được cấu hình tường minh và ánh xạ đúng vào container image thực tế.

Thay container không được làm mất message; thay config không cần rebuild binary image; rotate secret không được để private key/password tồn tại trong registry. Mỗi active broker có data store riêng, còn HA/replication/shared-store là thiết kế chuyên biệt với lock/fencing và failure model rõ ràng. Backup phải nhất quán và restore được; upgrade phải thử trên bản sao data trước khi chạm volume production.

Khi ba vòng đời image/config/data được tách rõ, đội vận hành có thể phát hành broker có thể tái lập, thay đổi cấu hình có kiểm soát và phục hồi dữ liệu mà không phụ thuộc writable layer của container.
