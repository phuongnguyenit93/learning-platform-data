# Môi trường triển khai

Một ứng dụng có thể chạy trên máy phát triển, môi trường kiểm thử, hệ thống staging và production. Mỗi nơi có tài nguyên, endpoint, thông tin xác thực, chính sách mạng, giới hạn vận hành và dữ liệu khác nhau. **Môi trường triển khai (deployment environment)** là tập hợp những điều kiện và tài nguyên mà ứng dụng hoặc thành phần được cài đặt, cấu hình và vận hành trong đó.

Trong ngữ cảnh **DSL xây dựng và triển khai**, môi trường là một khái niệm quan trọng vì cùng một ứng dụng thường cần được xây dựng, kiểm tra và phát hành qua nhiều giai đoạn. DSL có thể mô tả môi trường đích, tài nguyên cần có, cấu hình riêng, dependency, chính sách và cách triển khai. Toolchain đọc các khai báo đó để validate, tạo deployment plan, sinh manifest hoặc gọi nền tảng triển khai.

Ví dụ, một DSL có thể khai báo các môi trường:

~~~text
environment "development" {
    region = "ap-southeast-1"
    replicas = 1
    logLevel = "debug"
}

environment "production" {
    region = "ap-southeast-1"
    replicas = 4
    logLevel = "warn"
}
~~~

Hai môi trường dùng cùng một ứng dụng nhưng có cấu hình khác nhau. Development có thể ưu tiên phản hồi nhanh và khả năng quan sát; production cần tính sẵn sàng, bảo mật, kiểm soát thay đổi và khả năng phục hồi.

Môi trường triển khai không chỉ là một tên như dev hoặc prod. Nó bao gồm target platform, account/project, region, cluster, namespace, network, identity, secrets, quota, policy, dependency và trạng thái hiện tại. DSL cần mô hình hóa các yếu tố đó đủ rõ để một deployment có thể được kiểm tra, tái hiện và kiểm soát.

## 1. Môi trường triển khai là gì?

**Deployment environment** là ngữ cảnh nơi một phiên bản ứng dụng hoặc một nhóm tài nguyên được triển khai và vận hành. Một môi trường thường có:

- Nền tảng đích như máy ảo, container platform, Kubernetes, cloud service hoặc máy chủ nội bộ.
- Account, subscription, project hoặc tenant của nền tảng.
- Region, zone, cluster, namespace và network.
- Tài nguyên như CPU, memory, storage, database, queue và load balancer.
- Cấu hình ứng dụng như endpoint, feature flag, log level và replica count.
- Identity, role, credential và secret provider.
- Chính sách bảo mật, compliance, network và resource quota.
- Dữ liệu, dependency và dịch vụ bên ngoài.
- Quy trình release, rollout, health check, monitoring và rollback.

Một môi trường có thể là hệ thống lâu dài như production, môi trường dùng chung như staging, hoặc môi trường tạm thời được tạo cho một pull request.

### 1.1. Môi trường không chỉ là file cấu hình

File cấu hình chỉ mô tả một phần của môi trường. Ví dụ, file có thể khai báo service cần một database endpoint, nhưng database đó phải thực sự tồn tại, có thể truy cập, có schema tương thích và cấp quyền phù hợp.

Vì vậy cần phân biệt:

- **Environment definition:** mô tả môi trường mong muốn và các thuộc tính của nó.
- **Environment configuration:** giá trị cấu hình áp dụng cho ứng dụng trong môi trường.
- **Environment state:** tài nguyên và trạng thái thực tế đang tồn tại.
- **Deployment target:** đích cụ thể mà một lần triển khai sẽ tác động tới.

Một DSL có thể mô tả definition và configuration. Tooling có thể truy vấn target để quan sát state trước khi tạo plan.

### 1.2. Môi trường và target

Một environment có thể chứa nhiều target. Ví dụ production có thể có:

- Cluster cho API.
- Cluster cho background workers.
- Database cluster.
- Object storage.
- CDN.

Ngược lại, cùng một target platform có thể phục vụ nhiều environment thông qua account, namespace hoặc project khác nhau. Cần định nghĩa rõ identity của môi trường và cách ánh xạ nó tới target.

### 1.3. Môi trường có vòng đời

Môi trường có thể được tạo, cập nhật, khóa, chuyển trạng thái, sao lưu, phục hồi và xóa. Với môi trường tạm thời, vòng đời thường ngắn và gắn với branch hoặc pull request. Với production, thay đổi cần có phê duyệt, audit và quy trình phục hồi.

## 2. Các loại môi trường phổ biến

Tên môi trường không phải tiêu chuẩn bắt buộc. Một tổ chức có thể dùng dev, test, QA, staging, pre-production, production hoặc tên riêng. Điều quan trọng là mục tiêu, dữ liệu, quyền và chính sách của từng môi trường được xác định rõ.

| Môi trường | Mục tiêu chính | Đặc điểm thường gặp |
|---|---|---|
| Local | Phát triển trên máy cá nhân | Nhanh, dễ reset, dữ liệu giả |
| Development | Tích hợp công việc đang phát triển | Thay đổi thường xuyên, log chi tiết |
| Test/QA | Kiểm thử chức năng và tích hợp | Dữ liệu kiểm thử, kiểm soát phiên bản |
| Staging | Diễn tập release gần production | Cấu hình và topology tương tự production |
| Pre-production | Kiểm tra cuối trước release | Quy trình phê duyệt và dữ liệu hạn chế |
| Production | Phục vụ người dùng thật | Bảo mật, sẵn sàng và kiểm soát nghiêm ngặt |
| Preview/Ephemeral | Kiểm tra một thay đổi cụ thể | Tạo tự động, tồn tại ngắn hạn |

### 2.1. Local environment

Local environment thường chạy trên máy developer hoặc container local. Nó giúp thử nhanh mà không cần triển khai lên hạ tầng dùng chung.

Ví dụ:

~~~text
environment "local" {
    database {
        engine = "postgres"
        host = "localhost"
        port = 5432
        databaseName = "orders_dev"
    }

    service {
        replicas = 1
        logLevel = "debug"
    }
}
~~~

Local environment nên dùng dữ liệu giả hoặc dữ liệu đã được làm sạch. Credential local không nên được tái sử dụng cho staging hoặc production.

### 2.2. Development environment

Development environment hỗ trợ tích hợp nhiều nhánh công việc. Nó có thể dùng dịch vụ dùng chung, database riêng theo team hoặc tài nguyên được tạo tự động.

Đặc điểm thường gặp:

- Cho phép deploy thường xuyên.
- Log và tracing chi tiết.
- Có thể bật feature flag thử nghiệm.
- Dữ liệu có thể được reset.
- Quyền thao tác rộng hơn production nhưng vẫn có giới hạn.

### 2.3. Test và QA environment

Test environment được dùng để chạy automated test, integration test, regression test hoặc kiểm thử thủ công. Điều quan trọng là trạng thái môi trường có thể tái lập.

Một test environment nên:

- Dùng dependency và schema version được pin.
- Có dữ liệu fixture rõ ràng.
- Có cách reset hoặc tạo mới.
- Không dùng dữ liệu production nhạy cảm nếu chưa được xử lý phù hợp.
- Cung cấp endpoint và identity riêng cho test runner.

### 2.4. Staging environment

Staging mô phỏng production để phát hiện vấn đề trước khi phát hành. Nó nên tương đồng về nền tảng, network, policy, deployment mechanism và observability.

Staging không nhất thiết có cùng quy mô tài nguyên production. Nếu khác biệt về quota hoặc topology có thể ảnh hưởng hành vi, cần ghi nhận để hiểu giới hạn của kết quả kiểm thử.

### 2.5. Production environment

Production phục vụ người dùng thật và dữ liệu thật. Mọi khai báo và thao tác ở đây cần được kiểm soát theo policy của tổ chức.

Production thường yêu cầu:

- Identity riêng và quyền tối thiểu.
- Secret được quản lý tập trung.
- Network và data access được giới hạn.
- Deployment có plan, audit và phê duyệt.
- Health check, metrics, logs và alert.
- Rollout có kiểm soát.
- Backup, recovery và rollback strategy.
- Quota và capacity planning.

### 2.6. Preview và ephemeral environment

Ephemeral environment được tạo cho một thay đổi cụ thể, ví dụ branch hoặc pull request. Nó có thể tự động tạo namespace, database tạm, endpoint preview và dữ liệu fixture.

Khi pull request đóng hoặc hết thời hạn, môi trường được thu hồi. DSL nên mô tả owner, expiry, resource limits và cleanup policy để tránh tài nguyên bị bỏ quên.

## 3. Phân biệt build environment, test environment và deployment environment

Các môi trường này liên quan nhưng có mục tiêu khác nhau.

| Khái niệm | Dùng để làm gì? | Ví dụ |
|---|---|---|
| Build environment | Biên dịch, đóng gói artifact | JDK, compiler, build container |
| Test environment | Thực thi test và xác minh hành vi | Test database, mock service, test cluster |
| Deployment environment | Chạy artifact sau khi phát hành | Staging cluster, production account |
| Runtime environment | Cung cấp điều kiện khi process đang chạy | OS, runtime, env vars, mounted secrets |

Build environment có thể khác deployment environment. Ví dụ ứng dụng được build trên Linux CI rồi chạy trong container Linux tối giản. Toolchain cần pin compiler, dependency và build image để artifact có thể tái lập.

### 3.1. Build once, promote many

Một nguyên tắc release phổ biến là xây dựng artifact một lần, sau đó promote cùng artifact qua test, staging và production. Điều này giúp tránh việc mỗi môi trường nhận một binary khác nhau do build lại với dependency hoặc thời điểm khác nhau.

Ví dụ:

~~~mermaid
flowchart LR
    A[Source revision] --> B[Build once]
    B --> C[Immutable artifact]
    C --> D[Test]
    D --> E[Staging]
    E --> F[Production]
~~~

Môi trường có thể cung cấp configuration riêng khi chạy, nhưng artifact nên được định danh bằng version, digest hoặc checksum.

### 3.2. Khi nào cần build theo target?

Một số ứng dụng cần artifact khác nhau theo kiến trúc CPU, OS, runtime hoặc target platform. Khi đó target phải là một phần của build specification. Cần phân biệt khác biệt bắt buộc về binary với khác biệt cấu hình môi trường.

### 3.3. Runtime configuration

Runtime configuration được nạp khi ứng dụng khởi động hoặc trong quá trình chạy. Nó có thể bao gồm endpoint, secret reference, feature flag và giới hạn tài nguyên. Thay đổi runtime configuration có thể yêu cầu reload hoặc restart tùy ứng dụng.

## 4. Mô hình hóa môi trường trong DSL

DSL xây dựng và triển khai có thể cung cấp một construct riêng để khai báo environment.

Ví dụ:

~~~text
environment "staging" {
    platform = kubernetes
    account = account.nonProduction
    region = "ap-southeast-1"
    cluster = cluster.staging

    namespace = "orders-staging"

    application "orders-api" {
        replicas = 2
        image = artifact.ordersApi
    }
}
~~~

Khai báo này kết hợp identity của môi trường, platform, account, region, cluster, namespace và application deployment.

### 4.1. Environment identity

Tên environment cần ổn định và duy nhất trong phạm vi được quy định. Không nên dùng display name thay cho identity nếu tên hiển thị có thể thay đổi.

Identity có thể gồm:

- Tên logic như staging.
- Organization hoặc project.
- Account/subscription.
- Region.
- Cluster hoặc namespace.
- Environment ID do nền tảng quản lý.

### 4.2. Environment metadata

Metadata có thể mô tả:

- Owner hoặc team chịu trách nhiệm.
- Mục đích sử dụng.
- Cost center.
- Expiration date.
- Data classification.
- Criticality.
- Compliance scope.
- Liên kết tới dashboard hoặc runbook.

Metadata hỗ trợ governance và vận hành nhưng không thay thế authorization.

### 4.3. Environment type

DSL có thể phân loại môi trường:

~~~text
environment "production" {
    type = Production
    criticality = High
}
~~~

Environment type có thể kích hoạt policy mặc định như yêu cầu phê duyệt, cấm debug mode hoặc bắt buộc backup. Policy cần được enforce ở compiler, deployment controller hoặc nền tảng, không chỉ dựa vào tên environment.

### 4.4. Environment capability

Không phải mọi môi trường đều hỗ trợ mọi tính năng. Một target có thể hỗ trợ autoscaling, một target khác chỉ hỗ trợ fixed replicas. DSL nên mô tả capability hoặc backend profile để checker xác nhận tính năng được dùng có sẵn.

## 5. Target platform và topology

Deployment environment gắn với một hoặc nhiều nền tảng đích.

Các loại target thường gặp:

- Máy chủ vật lý hoặc máy ảo.
- Container runtime.
- Kubernetes cluster.
- Cloud application platform.
- Serverless runtime.
- Database hoặc managed data service.
- Edge device hoặc on-premises appliance.

### 5.1. Platform abstraction

DSL có thể cung cấp khái niệm trung lập như Service, Database, Network và Storage. Backend chuyển các khái niệm đó thành resource cụ thể trên nền tảng.

Ví dụ:

~~~text
service "catalog" {
    replicas = 3
    port = 8080
}
~~~

Backend Kubernetes có thể sinh Deployment và Service. Backend khác có thể sinh container service hoặc VM configuration. Cần xác định rõ những semantics nào được bảo toàn giữa các backend.

### 5.2. Platform-specific configuration

Khi cần tính năng riêng của platform, DSL có thể cung cấp extension block:

~~~text
service "catalog" {
    replicas = 3

    kubernetes {
        serviceType = "ClusterIP"
        topologySpread = true
    }
}
~~~

Extension cần được validate theo target. Nếu backend khác không hiểu block này, toolchain nên báo unsupported configuration hoặc bỏ qua theo một contract được khai báo rõ.

### 5.3. Topology

Topology mô tả cách các thành phần được bố trí và kết nối:

- Một hay nhiều region.
- Availability zones.
- Cluster và namespace.
- Public/private subnet.
- Database placement.
- Service-to-service network.
- Replication và failover.

Topology ảnh hưởng latency, availability, security và chi phí. DSL có thể biểu diễn topology như một graph thay vì chỉ là danh sách tài nguyên.

### 5.4. Region và availability zone

Region là vùng địa lý của provider; availability zone là một vùng lỗi độc lập trong region theo mô hình provider. Một ứng dụng quan trọng có thể phân bố replica qua nhiều zone. Không nên giả định tên zone hoặc khả năng cross-zone giống nhau giữa các provider.

## 6. Cấu hình riêng cho từng môi trường

Cùng một ứng dụng thường cần giá trị khác nhau theo môi trường:

- Số replica.
- CPU và memory.
- Endpoint database.
- Log level.
- Feature flag.
- Timeout và retry.
- Public/private access.
- Cache size.
- Autoscaling threshold.

Ví dụ cấu hình gốc và override:

~~~text
application "orders-api" {
    image = artifact.ordersApi
    port = 8080
    replicas = 2
    logLevel = "info"
}

environment "development" {
    override application.orders-api.replicas = 1
    override application.orders-api.logLevel = "debug"
}

environment "production" {
    override application.orders-api.replicas = 5
    override application.orders-api.logLevel = "warn"
}
~~~

### 6.1. Base configuration

Base configuration chứa những thuộc tính dùng chung giữa các môi trường. Nó giảm lặp và giúp cấu hình nhất quán.

### 6.2. Environment overlay

Overlay chỉ chứa những giá trị khác biệt. Khi áp dụng, engine merge overlay với base theo quy tắc được định nghĩa.

### 6.3. Tránh copy toàn bộ cấu hình

Nếu mỗi môi trường có một bản sao độc lập, thay đổi schema hoặc policy có thể chỉ được cập nhật ở một nơi. Base plus overlay giúp giảm drift giữa các cấu hình, nhưng cần merge semantics rõ ràng.

### 6.4. Không để override tùy ý

Một số field cần bị khóa theo policy, ví dụ encryption, audit, network exposure hoặc backup. Environment overlay không nên có quyền vô hiệu hóa policy bắt buộc.

## 7. Profiles, overlays và precedence

Khi có nhiều lớp cấu hình, engine cần xác định thứ tự áp dụng.

Ví dụ nguồn:

1. Schema default.
2. Module default.
3. Application base.
4. Environment overlay.
5. Deployment-specific values.
6. Runtime environment variables.
7. Explicit deployment parameters.

Thứ tự này chỉ là ví dụ. Hợp đồng thực tế phải nêu rõ nguồn nào thắng khi cùng khai báo một field.

### 7.1. Merge theo field

Object có thể được merge đệ quy:

~~~text
base:
    resources:
        cpu = "250m"
        memory = "256Mi"

production:
    resources:
        memory = "1Gi"
~~~

Kết quả có thể là cpu giữ nguyên và memory đổi thành 1Gi.

### 7.2. Merge list

List có thể replace, append, union hoặc merge theo key. Không nên dùng một quy tắc chung cho mọi thuộc tính. Ví dụ allowlist network có thể cần replace để tránh giữ lại entry cũ ngoài ý muốn.

### 7.3. Null, absent và delete

Overlay cần phân biệt:

- Không khai báo field: giữ giá trị base.
- Khai báo null: đặt null nếu schema cho phép.
- Delete/unset: xóa giá trị kế thừa nếu DSL hỗ trợ.

### 7.4. Provenance

Tooling có thể lưu nguồn của mỗi giá trị cuối cùng:

| Field | Giá trị hiệu lực | Nguồn |
|---|---|---|
| replicas | 5 | production overlay |
| image | orders-api:4.2 | release artifact |
| logLevel | warn | production policy |
| memory | 1Gi | production overlay |

Provenance giúp giải thích vì sao môi trường nhận giá trị khác với file base.

## 8. Secrets, credentials và identity

Mỗi môi trường có thể cần credential khác nhau để truy cập database, cloud API, registry hoặc dịch vụ bên ngoài.

Không nên ghi password, token, private key hoặc credential thật vào source DSL được commit.

Ví dụ:

~~~text
environment "production" {
    database {
        endpoint = "orders-db.internal"
        username = "orders-service"
        password = secretRef("prod/orders/database-password")
    }
}
~~~

### 8.1. Secret reference

Secret reference lưu định danh của secret trong secret manager. Giá trị thực được resolve trong môi trường có quyền phù hợp.

### 8.2. Identity thay cho credential tĩnh

Khi nền tảng hỗ trợ, workload identity hoặc managed identity giúp service nhận quyền từ identity được cấp cho workload mà không phải nhúng access key dài hạn.

### 8.3. Tách build identity và runtime identity

Build pipeline có thể cần quyền đọc source, package registry và artifact repository. Runtime workload cần quyền truy cập database hoặc service. Hai identity nên có scope riêng.

### 8.4. Secret theo môi trường

Development, staging và production nên dùng secret riêng. Không nên copy credential production sang môi trường thử nghiệm. Nếu cần dữ liệu tương tự production, hãy dùng dữ liệu đã mask hoặc synthetic.

### 8.5. Rotation

Secret có thể được rotate. Cần xác định ứng dụng đọc secret lúc khởi động hay theo cơ chế refresh. Deployment DSL có thể mô tả restart/reload policy khi secret version thay đổi.

### 8.6. Redaction

Lệnh render, plan và log không được in giá trị secret. Chỉ hiển thị reference hoặc trạng thái đã resolve theo cách an toàn.

## 9. Network và connectivity

Một deployment chỉ hoạt động nếu các thành phần có thể kết nối theo policy.

DSL có thể mô tả:

- Public và private subnet.
- Ingress và egress rule.
- DNS zone.
- Service discovery.
- Load balancer.
- Firewall hoặc security group.
- Private endpoint.
- TLS termination.
- Network policy giữa các workload.

Ví dụ:

~~~text
network "application" {
    visibility = Private
    allowEgress = [
        service.database,
        service.paymentProvider
    ]
}

service "orders-api" {
    network = network.application
    ingress {
        source = loadBalancer.internal
        port = 8080
    }
}
~~~

### 9.1. Network segmentation

Tách network theo lớp ứng dụng giúp giảm khả năng một workload bị xâm nhập có thể truy cập mọi tài nguyên. Chỉ mở các luồng cần thiết.

### 9.2. Ingress và egress

Ingress mô tả traffic đi vào workload; egress mô tả traffic đi ra. Cần xác định source/destination, protocol, port và direction rõ ràng.

### 9.3. DNS và service discovery

Endpoint có thể thay đổi theo environment. Thay vì hardcode địa chỉ IP, DSL có thể tham chiếu service name hoặc DNS record do platform quản lý.

### 9.4. TLS

Production thường yêu cầu TLS cho traffic bên ngoài và có thể cả traffic nội bộ. DSL có thể tham chiếu certificate hoặc secret, nhưng việc cấp phát và rotation certificate thuộc provider hoặc certificate manager.

### 9.5. Kiểm tra connectivity

Static validation có thể kiểm tra rule và reference. Một deployment preflight có thể kiểm tra DNS, route, port hoặc endpoint thực tế. Không nên coi cấu hình network hợp lệ là bằng chứng dịch vụ đích đang reachable.

## 10. Tài nguyên, quota và capacity

Môi trường có giới hạn tài nguyên. Một khai báo có thể hợp lệ về cú pháp nhưng không thể triển khai vì thiếu CPU, memory, IP, storage hoặc quota.

Ví dụ:

~~~text
service "orders-api" {
    replicas = 4
    resources {
        cpuRequest = "500m"
        cpuLimit = "1"
        memoryRequest = "512Mi"
        memoryLimit = "1Gi"
    }
}
~~~

### 10.1. Request và limit

Một số platform phân biệt tài nguyên được yêu cầu và mức tối đa. Request ảnh hưởng scheduling; limit kiểm soát mức sử dụng. Semantics chính xác phụ thuộc platform.

### 10.2. Quota

Quota có thể giới hạn tổng CPU, memory, storage, số IP hoặc số resource. Tooling có thể truy vấn quota hiện tại để đánh giá plan.

### 10.3. Capacity planning

Capacity planning xem xét tải dự kiến, peak traffic, số replica, overhead và khả năng tăng trưởng. Không nên chỉ nhân replicas với memory request mà bỏ qua sidecar, daemon, cache và hệ thống nền.

### 10.4. Autoscaling

DSL có thể mô tả min/max replicas và metric:

~~~text
autoscaling {
    minReplicas = 2
    maxReplicas = 12
    targetCpuUtilization = 65
}
~~~

Checker cần xác nhận min không lớn hơn max, metric được platform hỗ trợ và quota có thể đáp ứng giới hạn tối đa.

## 11. Dependency giữa các thành phần môi trường

Ứng dụng thường phụ thuộc database, queue, cache, object storage, secret manager hoặc service bên ngoài.

Ví dụ:

~~~text
database "orders" {
    engine = "postgres"
}

service "orders-api" {
    dependsOn = [
        database.orders,
        secretStore.production
    ]
}
~~~

### 11.1. Dependency graph

Toolchain có thể xây graph từ reference và dependency declaration. Graph giúp xác định thứ tự provisioning, readiness và cleanup.

### 11.2. Dependency readiness

Tài nguyên đã được tạo chưa chắc đã sẵn sàng. Database có thể cần khởi tạo schema, queue cần policy hoặc service cần pass health check.

DSL có thể định nghĩa readiness condition:

~~~text
waitFor database.orders {
    condition = "accepting-connections"
    timeout = 120s
}
~~~

### 11.3. Dependency cycle

Nếu service A chờ B và B chờ A, rollout có thể deadlock. Checker nên phát hiện cycle khi quan hệ được mô hình hóa tĩnh.

### 11.4. External dependency

Một API bên ngoài có thể không thuộc quyền quản lý của DSL. Khai báo nên mô tả endpoint, timeout, TLS và health expectation, nhưng không giả định toolchain có thể provision hoặc sửa hệ thống bên ngoài.

## 12. Artifact và version trong môi trường

Deployment environment nên nhận artifact đã được xác định rõ, không phụ thuộc vào tag thay đổi tùy ý.

Artifact có thể là:

- Container image.
- JAR, WAR hoặc binary.
- Static site bundle.
- Serverless package.
- Database migration bundle.
- Configuration package.

Ví dụ:

~~~text
artifact "orders-api" {
    repository = "registry.example.com/commerce/orders-api"
    digest = "sha256:..."
}

environment "staging" {
    deploy artifact.orders-api
}
~~~

### 12.1. Immutable artifact

Artifact bất biến được nhận diện bằng version hoặc digest. Nếu tag có thể trỏ tới nội dung mới, deploy cùng tag không bảo đảm deploy cùng binary.

### 12.2. Build metadata

Artifact có thể gắn:

- Source commit.
- Build number.
- Compiler và toolchain version.
- Dependency lockfile hash.
- Build timestamp.
- SBOM.
- Signature hoặc provenance attestation.

Metadata giúp truy vết artifact được tạo từ source và quy trình nào.

### 12.3. Promote cùng artifact

Một artifact đã kiểm thử ở staging nên được promote lên production theo cùng digest. Environment configuration thay đổi theo target nhưng binary không bị build lại.

### 12.4. Compatibility

Một artifact có thể yêu cầu runtime version, database schema version hoặc platform capability tối thiểu. Checker nên xác nhận những điều kiện này trước khi deploy.

## 13. Build và deployment pipeline theo môi trường

Một pipeline thường đi qua build, test, staging và production.

~~~mermaid
flowchart TD
    A[Source revision] --> B[Build artifact]
    B --> C[Unit and integration tests]
    C --> D[Publish immutable artifact]
    D --> E[Deploy to test environment]
    E --> F[Automated verification]
    F --> G[Deploy to staging]
    G --> H[Acceptance and operational checks]
    H --> I{Release approved?}
    I -->|No| J[Stop and investigate]
    I -->|Yes| K[Promote same artifact to production]
    K --> L[Health monitoring]
~~~

### 13.1. Build stage

Build stage compile và package source, tạo artifact và metadata. Nó nên chạy trong môi trường được pin version để kết quả có thể tái lập.

### 13.2. Test stage

Test stage xác minh unit, integration, contract và security behavior. Test environment cần dependency phù hợp và dữ liệu có thể reset.

### 13.3. Staging stage

Staging xác nhận artifact và cấu hình hoạt động trên topology gần production. Có thể chạy smoke test, migration rehearsal, load test hoặc acceptance test.

### 13.4. Production stage

Production deployment có thể yêu cầu phê duyệt, change window, rollout strategy và monitoring. Policy cần xác định điều kiện được phép tiếp tục hoặc dừng.

### 13.5. Pipeline là workflow có trạng thái

Mỗi stage có thể thành công, thất bại, bị hủy hoặc chờ phê duyệt. DSL pipeline nên mô hình hóa trạng thái và điều kiện chuyển tiếp, thay vì chỉ là danh sách lệnh không có trạng thái.

## 14. Environment promotion

Promotion là quá trình đưa cùng một artifact hoặc release candidate từ môi trường có mức rủi ro thấp sang môi trường có mức rủi ro cao hơn.

Ví dụ:

~~~text
release "orders-4.2" {
    artifact = artifact.ordersApi

    promote {
        from = environment.test
        to = environment.staging
        require = verification.integration
    }

    promote {
        from = environment.staging
        to = environment.production
        require = [
            verification.acceptance,
            approval.releaseManager
        ]
    }
}
~~~

### 14.1. Promotion gate

Gate là điều kiện phải đạt trước khi chuyển môi trường:

- Test pass.
- Security scan đạt policy.
- Artifact signature hợp lệ.
- Migration rehearsal thành công.
- Staging smoke test pass.
- Approval được cấp.
- Change window đang mở.

### 14.2. Không build lại khi promote

Nếu build lại ở từng môi trường, artifact có thể khác nhau dù source revision giống nhau. Promote cùng artifact giúp bảo đảm binary đã kiểm thử chính là binary được phát hành.

### 14.3. Environment-specific config

Configuration có thể được resolve theo môi trường khi promote. Cần ghi lại version hoặc hash của config đã dùng cho mỗi release để truy vết.

### 14.4. Promotion record

Một promotion record có thể chứa artifact digest, environment source/target, approver, timestamp, config revision và verification result.

## 15. Validation và preflight trước deployment

Trước khi thay đổi môi trường, toolchain nên kiểm tra càng nhiều điều kiện có thể xác minh càng tốt.

Các lớp validation:

1. Parse DSL và kiểm tra syntax.
2. Resolve reference và type-check.
3. Validate schema và environment overlay.
4. Kiểm tra target capability.
5. Kiểm tra artifact tồn tại và digest.
6. Kiểm tra policy, identity và permission.
7. Kiểm tra quota và resource constraints.
8. Kiểm tra dependency và readiness expectation.
9. Tạo plan và hiển thị tác động.

Ví dụ:

~~~text
deploy plan --environment staging
~~~

Kết quả plan có thể cho biết:

~~~text
Environment: staging
Artifact: orders-api@sha256:...

Changes:
  Create: deployment/orders-api
  Update: service/orders-api
  Keep: database/orders

Preflight:
  Artifact available: yes
  Required secrets referenced: yes
  Cluster quota: sufficient
  Network policy: valid

No changes have been applied.
~~~

### 15.1. Static validation

Static validation chỉ cần DSL source, schema và metadata. Nó có thể phát hiện sai cú pháp, reference thiếu, field sai kiểu hoặc policy vi phạm.

### 15.2. Environment-aware validation

Validation có thể cần kết nối target để đọc capability, quota, permission hoặc trạng thái tài nguyên. Kết quả phụ thuộc snapshot môi trường và có thể thay đổi trước lúc apply.

### 15.3. Validation không phải guarantee

Preflight thành công không bảo đảm deploy sẽ thành công. Tài nguyên có thể thay đổi, network có thể lỗi hoặc service bên ngoài có thể unavailable sau bước kiểm tra. Cần xử lý lỗi trong lúc apply và verify sau deployment.

### 15.4. Read-only preflight

Nếu chỉ kiểm tra, tool nên dùng quyền đọc và không tạo hoặc sửa resource. Những thao tác có side effect cần được phân biệt rõ trong CLI và DSL.

## 16. Deployment plan và apply

Plan mô tả thay đổi dự kiến; apply thực hiện thay đổi lên target.

~~~mermaid
flowchart TD
    A[Desired environment model] --> B[Read current state]
    B --> C[Compute diff]
    C --> D[Validate policy and dependencies]
    D --> E[Deployment plan]
    E --> F{Approved?}
    F -->|No| G[Stop]
    F -->|Yes| H[Apply changes]
    H --> I[Verify readiness]
    I --> J[Record deployment state]
~~~

### 16.1. Plan

Plan nên mô tả resource nào được tạo, cập nhật, thay thế hoặc xóa. Với thay đổi quan trọng, cần hiển thị tác động như downtime, data migration hoặc quyền truy cập.

### 16.2. Plan review

Người review cần thấy:

- Environment và target identity.
- Artifact digest.
- Configuration revision.
- Resource changes.
- Policy result.
- Approval requirements.
- Thay đổi có destructive hay không.

### 16.3. Plan có thể stale

Nếu trạng thái môi trường đổi sau khi plan được tạo, plan có thể không còn đúng. Tooling nên gắn plan với state version hoặc fingerprint và yêu cầu tính lại khi phát hiện thay đổi đáng kể.

### 16.4. Apply

Apply nên có thể theo dõi progress, cancellation, retry và partial failure. Nếu một phần tài nguyên đã được cập nhật trước khi lỗi xảy ra, cần biết state nào đã thay đổi và cách tiếp tục hoặc phục hồi.

### 16.5. Idempotency

Apply lặp lại nên hội tụ về desired state theo semantics của tool. Idempotency giúp retry sau lỗi mạng hoặc process restart, nhưng không có nghĩa mọi action đều không có tác động lặp. Migration hoặc action một lần cần cơ chế tracking riêng.

## 17. Deployment strategies

Chiến lược rollout quyết định cách phiên bản mới được đưa tới người dùng.

### 17.1. Recreate

Dừng phiên bản cũ rồi tạo phiên bản mới. Cách này đơn giản nhưng có thể gây downtime.

### 17.2. Rolling update

Thay từng nhóm instance. Trong thời gian rollout, phiên bản cũ và mới có thể chạy đồng thời. Cần kiểm tra tương thích API và database schema giữa hai phiên bản.

### 17.3. Blue-green deployment

Hai môi trường hoặc nhóm tài nguyên song song được duy trì. Phiên bản mới được triển khai vào nhóm inactive, kiểm tra xong rồi chuyển traffic.

~~~mermaid
flowchart LR
    U[User traffic] --> R[Router]
    R --> B[Blue: current]
    R -. switch .-> G[Green: new]
    G --> V[Verification]
    V --> S[Switch traffic]
~~~

### 17.4. Canary deployment

Chỉ một phần traffic được gửi tới phiên bản mới. Nếu metrics và error rate đạt điều kiện, tỷ lệ traffic tăng dần.

### 17.5. Feature flag

Feature flag tách việc deploy code khỏi việc bật tính năng. Flag có thể được cấu hình theo environment, tenant hoặc nhóm người dùng. Cần có owner, expiry và quy tắc xóa flag cũ.

### 17.6. Strategy theo khả năng ứng dụng

Không phải ứng dụng nào cũng hỗ trợ rolling hoặc blue-green an toàn. Stateful workload, singleton job hoặc schema migration có thể cần chiến lược riêng.

## 18. Health check và readiness

Sau khi deploy, cần xác định service đã sẵn sàng phục vụ hay chưa.

Các loại check thường gặp:

- Liveness: process còn hoạt động không?
- Readiness: service có thể nhận traffic không?
- Startup: ứng dụng đã hoàn tất khởi tạo chưa?
- Dependency health: database, queue hoặc service cần thiết có hoạt động không?
- Synthetic check: một luồng nghiệp vụ quan trọng có chạy được không?

Ví dụ:

~~~text
service "orders-api" {
    healthCheck {
        path = "/health/ready"
        interval = 10s
        timeout = 3s
        failureThreshold = 3
    }
}
~~~

### 18.1. Liveness và readiness khác nhau

Liveness phát hiện process bị treo hoặc không thể phục hồi. Readiness xác định có nên gửi traffic vào instance. Nếu liveness phụ thuộc trực tiếp vào database tạm thời unavailable, platform có thể restart mọi instance liên tục.

### 18.2. Startup probe

Ứng dụng khởi động lâu có thể cần startup probe để tránh bị đánh dấu unhealthy trước khi hoàn tất initialization.

### 18.3. Health check không nên tiết lộ thông tin

Endpoint health công khai không nên trả credential, connection string hoặc chi tiết nội bộ. Có thể cung cấp endpoint sâu hơn cho monitoring nội bộ với quyền phù hợp.

## 19. Database migration trong môi trường triển khai

Deployment ứng dụng thường cần thay đổi schema database. Migration là một phần của release và có thể ảnh hưởng tương thích giữa phiên bản cũ và mới.

Ví dụ:

~~~text
deployment "orders-api" {
    beforeDeploy {
        migration = artifact.ordersSchemaMigration
        strategy = ExpandContract
    }
}
~~~

### 19.1. Expand and contract

Một cách giảm rủi ro:

1. Expand: thêm column hoặc table mới mà phiên bản cũ vẫn hoạt động.
2. Deploy code có thể đọc/ghi cấu trúc mới.
3. Migrate dữ liệu.
4. Xác nhận mọi consumer đã chuyển đổi.
5. Contract: xóa cấu trúc cũ trong release sau.

### 19.2. Migration một lần

Migration cần được tracking theo version hoặc identifier để không chạy lặp ngoài ý muốn. Nếu deploy retry, engine phải biết migration nào đã hoàn tất.

### 19.3. Backup và recovery

Thay đổi schema có thể không rollback dễ dàng. Cần backup hoặc phương án phục hồi trước migration có rủi ro.

### 19.4. Staging rehearsal

Chạy migration trên staging với dataset có quy mô và hình dạng phù hợp giúp ước lượng thời gian, lock và tác động. Dữ liệu staging cần được quản lý theo policy.

## 20. Observability trong từng môi trường

Môi trường triển khai cần khả năng quan sát để biết ứng dụng đang hoạt động ra sao.

Ba nhóm dữ liệu chính:

- Logs: sự kiện và thông tin chẩn đoán.
- Metrics: số liệu định lượng như request rate, latency, error rate và saturation.
- Traces: đường đi của request qua nhiều service.

### 20.1. Environment labels

Log, metric và trace nên có nhãn environment, service, version và region để phân biệt dữ liệu giữa staging và production.

### 20.2. Alert policy

Ngưỡng alert có thể khác theo môi trường. Development có thể ít alert hơn; production cần alert cho SLO, error budget, availability và resource saturation.

### 20.3. Không log secret

Environment-specific logging không được làm lộ token, password, PII hoặc request body nhạy cảm. Redaction cần được áp dụng trước khi dữ liệu tới log sink.

### 20.4. Deployment marker

Ghi lại thời điểm deploy, artifact digest và configuration revision giúp liên hệ thay đổi với sự thay đổi metrics hoặc lỗi.

## 21. Drift và reconciliation

Drift là khác biệt giữa cấu hình mong muốn được mô tả trong DSL và trạng thái thực tế của môi trường.

Ví dụ:

- DSL khai báo replicas = 4, nhưng operator thay thủ công thành 2.
- DSL yêu cầu private network, nhưng firewall rule được mở rộng.
- Artifact digest mong muốn khác digest đang chạy.
- Secret reference đã đổi version nhưng workload chưa reload.

### 21.1. Drift detection

Tool có thể đọc state hiện tại, chuẩn hóa về model và so sánh với desired state. Kết quả cần phân biệt thay đổi được quản lý bởi DSL với tài nguyên ngoài phạm vi.

### 21.2. Reconciliation

Reconciliation đưa actual state về gần desired state. Có thể chạy tự động hoặc theo yêu cầu.

### 21.3. Drift không phải lúc nào cũng cần tự sửa

Một thay đổi ngoài DSL có thể là hotfix khẩn cấp hoặc thay đổi đã được phê duyệt. Cần policy xác định có cảnh báo, yêu cầu review hay tự reconcile.

### 21.4. Ownership

Mỗi resource nên có owner hoặc controller rõ ràng. Nếu hai công cụ cùng quản lý một field, chúng có thể liên tục ghi đè lẫn nhau.

## 22. Rollback và recovery

Rollback đưa ứng dụng hoặc cấu hình về một trạng thái trước đó. Không phải mọi thay đổi đều có thể rollback đơn giản.

### 22.1. Rollback artifact

Nếu artifact mới lỗi, có thể deploy lại digest trước đó. Cần giữ artifact và metadata đủ lâu để rollback.

### 22.2. Rollback configuration

Configuration revision trước có thể được áp dụng lại nếu schema và runtime vẫn tương thích.

### 22.3. Database migration

Migration có thể không đảo ngược an toàn. Expand-contract giúp giữ tương thích trong giai đoạn chuyển đổi. Với dữ liệu đã bị biến đổi, rollback có thể cần restore hoặc forward fix.

### 22.4. Rollback trigger

Trigger có thể gồm:

- Error rate vượt ngưỡng.
- Readiness thất bại.
- Latency tăng mạnh.
- Synthetic transaction thất bại.
- SLO burn rate vượt policy.

### 22.5. Recovery plan

Môi trường quan trọng cần có backup, restore procedure, recovery time objective (RTO) và recovery point objective (RPO). DSL có thể mô tả policy hoặc tham chiếu runbook, nhưng cần kiểm thử restore thực tế.

## 23. Bảo mật và governance theo môi trường

Mỗi môi trường có mức rủi ro khác nhau. Policy cần gắn với environment classification và được enforce ở nơi có thẩm quyền.

Ví dụ:

~~~text
policy "production-baseline" {
    requireTLS = true
    requireAudit = true
    requireBackup = true
    allowPublicDebug = false
    requireApproval = true
}

environment "production" {
    policy = policy.production-baseline
}
~~~

### 23.1. Separation of duties

Người viết source, người review và người phê duyệt production có thể là các vai trò khác nhau. Toolchain nên lưu lại danh tính và quyết định phê duyệt.

### 23.2. Least privilege

Deployment identity chỉ nên có quyền trên target và resource cần thiết. Developer không nhất thiết cần quyền trực tiếp thay đổi production.

### 23.3. Data classification

Environment có thể được phân loại theo loại dữ liệu được xử lý. Production có thể chứa dữ liệu nhạy cảm; test nên dùng synthetic hoặc masked data.

### 23.4. Audit trail

Ghi lại ai đã deploy artifact nào, vào môi trường nào, dùng config revision nào, plan nào và approval nào.

### 23.5. Policy as code

Policy có thể được mô tả bằng DSL hoặc rule engine để kiểm tra tự động. Ví dụ cấm public database, yêu cầu encryption hoặc bắt buộc resource owner.

## 24. Ephemeral environment và cleanup

Ephemeral environment giúp kiểm thử một thay đổi trong môi trường cô lập.

Ví dụ:

~~~text
environment "preview-pr-482" {
    lifecycle = Ephemeral
    owner = "pull-request-482"
    expiresAfter = 48h

    application = application.ordersApi
    database = database.previewTemplate
}
~~~

### 24.1. Isolation

Mỗi preview environment nên có namespace, database/schema hoặc resource identity riêng để tránh ghi đè dữ liệu của preview khác.

### 24.2. Cost limit

Preview có thể tạo nhiều tài nguyên cùng lúc. Cần giới hạn replicas, storage, lifetime và số environment đang tồn tại.

### 24.3. Automatic cleanup

Khi branch hoặc pull request đóng, controller có thể xóa resource. Cleanup nên dựa vào owner tag hoặc environment ID, không dựa vào tên gần đúng.

### 24.4. Cleanup protection

Production và môi trường dùng chung cần protection để tránh bị xóa bởi quy tắc TTL. Cleanup command cần xác minh target identity và policy.

### 24.5. Dữ liệu preview

Preview nên dùng fixture hoặc dữ liệu đã mask. Không sao chép dữ liệu production nhạy cảm vào môi trường tạm nếu không có quy trình được phê duyệt.

## 25. Multi-environment và multi-region

Một ứng dụng có thể triển khai ở nhiều region hoặc nhiều account.

Ví dụ:

~~~text
environment "production-asia" {
    region = "ap-southeast-1"
    account = account.productionAsia
    cluster = cluster.asia
}

environment "production-europe" {
    region = "eu-west-1"
    account = account.productionEurope
    cluster = cluster.europe
}
~~~

### 25.1. Shared configuration

Một phần cấu hình được chia sẻ, ví dụ artifact, application port và policy. Một phần khác phụ thuộc region, như endpoint, data residency và capacity.

### 25.2. Data residency

Một số hệ thống phải giữ dữ liệu trong region hoặc jurisdiction cụ thể. DSL có thể mô tả placement policy và checker xác nhận resource không bị triển khai sai vùng.

### 25.3. Failover

Multi-region có thể dùng active-active hoặc active-passive. Cần mô tả replication, routing, failover trigger và trạng thái database. Không nên coi chỉ có hai environment definition là đã có disaster recovery.

### 25.4. Configuration consistency

Tooling có thể so sánh các environment để phát hiện policy hoặc version bị lệch. Khác biệt có chủ đích cần được khai báo thành overlay thay vì chỉnh sửa thủ công.

## 26. Kiểm thử và xác minh môi trường

Một environment definition cần được kiểm tra cả về cấu trúc lẫn hành vi.

### 26.1. Static validation

- Environment name và identity hợp lệ.
- Target reference tồn tại trong catalog.
- Region và platform được hỗ trợ.
- Configuration đúng schema.
- Required secret reference được khai báo.
- Resource constraint hợp lệ.
- Không có dependency cycle.

### 26.2. Integration validation

- Credential có thể xác thực.
- Network route hoạt động.
- Database endpoint reachable.
- Artifact có thể pull hoặc download.
- Permission đủ cho deployment operation.

### 26.3. Post-deployment verification

- Workload đã sẵn sàng.
- Health check pass.
- Synthetic request thành công.
- Metrics và logs xuất hiện.
- Dependency được kết nối.
- Version đang chạy khớp artifact digest mong muốn.

### 26.4. Environment contract tests

Contract test có thể xác nhận một environment cung cấp đúng endpoint, protocol, schema và capability mà ứng dụng cần. Điều này hữu ích khi nhiều team sở hữu các service khác nhau.

## 27. DSL và cách tổ chức file môi trường

Có nhiều cách tổ chức source:

### 27.1. Một file cho mỗi môi trường

~~~text
environments/
    development.dsl
    staging.dsl
    production.dsl
~~~

Cách này dễ nhìn nhưng có thể lặp cấu hình.

### 27.2. Base và overlay

~~~text
environments/
    base.dsl
    development.overlay.dsl
    staging.overlay.dsl
    production.overlay.dsl
~~~

Cách này giảm lặp và làm rõ phần khác biệt.

### 27.3. Module theo domain

~~~text
deploy/
    network.dsl
    database.dsl
    services/
        orders.dsl
        payments.dsl
    environments/
        staging.dsl
        production.dsl
~~~

Chia theo domain giúp ownership rõ hơn trong project lớn.

### 27.4. Manifest và lockfile

Manifest có thể khai báo module, provider và version. Lockfile ghi lại dependency đã resolve. Điều này giúp build/deploy có kết quả ổn định hơn.

### 27.5. Không chứa secret trong file source

File môi trường nên tham chiếu secret provider hoặc variable source được quản lý. Không commit secret thật vào repository.

## 28. CLI và thao tác với môi trường

Toolchain có thể cung cấp các lệnh:

~~~text
dsl env list
dsl env validate staging
dsl deploy plan --environment staging
dsl deploy apply --environment staging
dsl deploy status --environment production
dsl env diff staging production
dsl env destroy preview-pr-482
~~~

Tên lệnh chỉ là ví dụ. Mỗi lệnh cần nêu rõ:

- Environment identity.
- Target được truy cập.
- Quyền cần thiết.
- Có side effect hay không.
- Output và exit code.

### 28.1. Explicit target

Với thao tác có tác động, nên yêu cầu environment hoặc target rõ ràng. Dùng default production ngầm có thể gây nhầm lẫn nguy hiểm.

### 28.2. Dry run

Dry run có thể tạo plan mà không apply. Cần nói rõ mức độ mô phỏng: một số tool vẫn truy vấn API hoặc tạo temporary resource trong quá trình dry run.

### 28.3. Confirmation

Thao tác phá hủy hoặc tác động production có thể yêu cầu xác nhận, approval token hoặc policy gate. Confirmation nên hiển thị target identity đầy đủ để tránh thao tác nhầm môi trường.

### 28.4. Status

Status nên hiển thị artifact version, config revision, rollout state, health và thời điểm deploy gần nhất.

## 29. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Coi môi trường chỉ là tên dev/prod | Thiếu target, identity và policy | Mô hình hóa account, region, cluster và owner |
| Build lại artifact ở từng môi trường | Binary khác nhau giữa các stage | Build once, promote cùng digest |
| Copy toàn bộ cấu hình cho mỗi môi trường | Dễ drift và khó cập nhật | Dùng base plus overlay |
| Ghi secret vào DSL source | Rò rỉ credential qua Git hoặc log | Dùng secret reference và workload identity |
| Dùng chung credential mọi môi trường | Tăng phạm vi ảnh hưởng khi lộ secret | Identity và secret riêng theo environment |
| Chọn target ngầm | Deploy nhầm môi trường | Yêu cầu target rõ và hiển thị identity |
| Chỉ validate cú pháp | Thiếu quota, permission hoặc connectivity | Bổ sung environment-aware preflight |
| Coi preflight là bảo đảm | State có thể đổi trước apply | Kiểm tra lại và xử lý lỗi lúc apply |
| Không có rollout strategy | Có thể gây downtime | Chọn strategy phù hợp workload |
| Không kiểm tra readiness | Traffic tới instance chưa sẵn sàng | Health/readiness checks |
| Migration không tương thích | Phiên bản cũ hoặc mới có thể lỗi | Expand-contract và rehearsal |
| Không lưu artifact digest | Khó biết binary đang chạy | Pin digest và ghi release metadata |
| Không có drift detection | Thay đổi thủ công không được phát hiện | So sánh desired và actual state |
| Ephemeral resource không cleanup | Tốn chi phí và tăng attack surface | Owner, TTL và cleanup policy |
| Staging khác production quá nhiều | Test không phản ánh release thật | Giữ topology/policy tương đồng |
| Cùng một tool quản lý resource không có ownership | Controller ghi đè lẫn nhau | Xác định resource owner rõ ràng |

## 30. Quy trình thiết kế môi trường triển khai bằng DSL

Khi xây dựng mô hình environment, có thể thực hiện theo các bước:

1. **Xác định environment classes:** local, development, test, staging, production và preview.
2. **Định nghĩa identity:** organization, account, project, region, cluster và namespace.
3. **Mô tả target capability:** platform, runtime, network và resource type được hỗ trợ.
4. **Xác định application topology:** service, database, queue, storage và dependency.
5. **Thiết kế base configuration:** các thuộc tính dùng chung và schema version.
6. **Thiết kế overlay:** giá trị riêng theo environment, merge semantics và precedence.
7. **Quản lý identity và secrets:** workload identity, secret reference, rotation và redaction.
8. **Định nghĩa network policy:** ingress, egress, DNS, TLS và service discovery.
9. **Đặt resource constraints:** requests, limits, quota và autoscaling.
10. **Pin artifact và dependency:** digest, toolchain, module và lockfile.
11. **Thiết kế deployment pipeline:** build, test, promote, approval và apply.
12. **Chọn rollout strategy:** recreate, rolling, blue-green hoặc canary.
13. **Định nghĩa readiness và observability:** health check, metrics, logs, traces và alerts.
14. **Thiết kế drift và recovery:** reconciliation, rollback, backup và disaster recovery.
15. **Thiết kế lifecycle:** tạo, cập nhật, expiry và cleanup.
16. **Xây validation:** static, environment-aware, preflight và post-deployment verification.
17. **Kiểm thử và audit:** environment contract tests, policy tests và deployment records.

Mỗi environment nên có owner, mục đích, dữ liệu được phép, target identity và quy trình thay đổi được tài liệu hóa.

## 31. Ví dụ tổng hợp: triển khai một ứng dụng qua ba môi trường

Giả sử một hệ thống có API orders, database PostgreSQL và background worker.

~~~text
artifact "orders-api" {
    repository = "registry.example.com/commerce/orders-api"
    digest = "sha256:abc123..."
}

artifact "orders-worker" {
    repository = "registry.example.com/commerce/orders-worker"
    digest = "sha256:def456..."
}

application "orders" {
    service "api" {
        image = artifact.orders-api
        port = 8080
        replicas = 2
    }

    service "worker" {
        image = artifact.orders-worker
        replicas = 1
    }
}

environment "development" {
    type = Development
    cluster = cluster.dev

    override application.orders.api.replicas = 1
    override application.orders.worker.replicas = 1
    override application.orders.api.logLevel = "debug"

    database = database.devOrders
}

environment "staging" {
    type = Staging
    cluster = cluster.staging

    override application.orders.api.replicas = 2
    override application.orders.worker.replicas = 2

    database = database.stagingOrders
    secrets = secretSet.stagingOrders
    policy = policy.staging
}

environment "production" {
    type = Production
    cluster = cluster.production

    override application.orders.api.replicas = 5
    override application.orders.worker.replicas = 3

    database = database.productionOrders
    secrets = secretSet.productionOrders
    policy = policy.production

    rollout {
        strategy = Canary
        initialTrafficPercent = 5
        successWindow = 10m
    }
}
~~~

Đây là cú pháp minh họa; một DSL thực tế cần schema và grammar tương ứng.

### 31.1. Development

Developer có thể deploy nhanh, dùng database riêng, bật log chi tiết và ít replica. Secret chỉ cấp quyền vào dữ liệu development.

### 31.2. Staging

Staging dùng cùng artifact digest, database staging và secret staging. Nó chạy smoke test, contract test và kiểm tra rollout trước production.

### 31.3. Production

Production dùng cùng artifact digest đã được xác minh, nhưng có resource sizing, secret, policy và rollout strategy riêng. Deployment có thể yêu cầu approval và theo dõi metrics trong canary window.

### 31.4. Promotion

~~~mermaid
flowchart LR
    A[Build orders artifacts] --> B[Deploy development]
    B --> C[Integration tests]
    C --> D[Deploy staging]
    D --> E[Acceptance and security checks]
    E --> F[Approval]
    F --> G[Canary production]
    G --> H[Progressive rollout]
    H --> I[Monitor and record release]
~~~

Artifact digest không đổi giữa các stage. Configuration revision và promotion record được lưu riêng cho từng environment.

## 32. Tiêu chí của một mô hình môi trường tốt

Một mô hình environment tốt làm rõ ứng dụng được triển khai ở đâu, bằng identity nào, với artifact nào, configuration nào và theo policy nào. Nó cho phép phân biệt trạng thái mong muốn với trạng thái thực tế, tạo plan trước khi apply và xác minh kết quả sau deployment.

Các câu hỏi quan trọng:

- Environment có identity và owner rõ ràng không?
- Build, test, staging và production có mục tiêu riêng không?
- Cùng artifact digest có được promote qua các môi trường không?
- Configuration dùng base và overlay với precedence xác định không?
- Secret và identity có được tách riêng theo môi trường không?
- Target platform và capability có được kiểm tra không?
- Network, quota, dependency và readiness có được mô hình hóa không?
- Preflight có phân biệt kiểm tra tĩnh và kiểm tra trạng thái thật không?
- Plan có gắn với snapshot hoặc fingerprint của target không?
- Rollout, migration và rollback có chiến lược phù hợp không?
- Drift có được phát hiện và xử lý theo ownership policy không?
- Ephemeral environment có TTL và cleanup không?
- Metrics, logs, traces và deployment marker có đủ để vận hành không?
- Audit record có thể truy vết artifact, config, approver và target không?

Môi trường triển khai là ngữ cảnh kết hợp giữa nền tảng, tài nguyên, cấu hình, identity, policy và trạng thái vận hành. Khi DSL mô tả các yếu tố đó bằng những khai báo có kiểu, reference rõ ràng và quy tắc promotion xác định, toolchain có thể xây dựng, kiểm tra và triển khai ứng dụng nhất quán qua nhiều môi trường. Điều này giúp release có thể tái lập, thay đổi có thể review và trạng thái production có thể quan sát, kiểm soát và phục hồi.
