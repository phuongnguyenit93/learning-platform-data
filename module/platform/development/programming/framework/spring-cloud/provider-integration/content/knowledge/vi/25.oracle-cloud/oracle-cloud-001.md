# Spring Cloud Oracle, Spring Cloud OCI và ranh giới các dự án con

Oracle có nhiều thành phần phục vụ ứng dụng Spring: Oracle AI Database, các hàng đợi và luồng sự kiện gắn với database, Oracle Cloud Infrastructure (OCI), cùng dịch vụ Generative AI. Tên gọi Spring Cloud Oracle và Spring Cloud OCI có liên hệ chặt chẽ nhưng không đồng nghĩa. Hiểu đúng cấu trúc dự án giúp chọn đúng starter, API, dependency và mô hình vận hành.

**Spring Cloud Oracle** là dự án đa module tập hợp các tích hợp Spring Boot cho công nghệ Oracle. **Spring Cloud OCI** là một dự án con trong đó, tập trung vào dịch vụ managed của Oracle Cloud Infrastructure như Object Storage, Vault, Streaming, Queue, Functions và Autonomous Database. Các starter kết nối trực tiếp Oracle AI Database, binder cho TxEventQ và tích hợp Spring AI Oracle có ranh giới riêng.

Bài này xác định cấu trúc đó, chỉ ra khi nào dùng từng nhánh và cách ghép chúng trong một ứng dụng Spring Boot. Mục tiêu là giúp người học đặt đúng dependency và chọn đúng programming model trước khi đi sâu vào từng dịch vụ OCI.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích quan hệ giữa Spring Cloud Oracle, Spring Cloud OCI và OCI SDK.
2. Nhận diện các dự án con chính trong hệ sinh thái Spring Cloud Oracle.
3. Phân biệt tích hợp OCI managed services với tích hợp trực tiếp Oracle AI Database.
4. Chọn giữa OCI Queue, OCI Streaming, TxEventQ qua JMS/OKafka và Spring Cloud Stream binder.
5. Chọn đúng Maven group/artifact cho từng loại tích hợp.
6. Hiểu vai trò của core starter, service-specific starter và auto-configuration.
7. Chọn phương thức xác thực OCI phù hợp với local development, compute, Functions và OKE.
8. Phân biệt API Spring-friendly với semantics riêng của OCI service.
9. Xây dựng cấu hình, kiểm thử và triển khai theo version tương thích của Spring Boot.
10. Tránh trộn nhầm dependency, transaction boundary và trách nhiệm vận hành giữa các dự án con.

## 2. Vì sao có nhiều tên gọi?

Có ba khái niệm thường bị nhầm:

- **Oracle Cloud Infrastructure (OCI):** nền tảng cloud của Oracle, cung cấp compute, network, Object Storage, Vault, Queue, Streaming, Functions, Autonomous Database và nhiều dịch vụ managed khác.
- **Spring Cloud Oracle:** dự án tích hợp công nghệ Oracle vào programming model của Spring Boot.
- **Spring Cloud OCI:** nhánh tích hợp các dịch vụ OCI trong dự án Spring Cloud Oracle.

Spring Cloud Oracle không phải một dịch vụ cloud và cũng không phải một client SDK duy nhất. Nó là tập hợp starter, auto-configuration, template, resource abstraction, binder và mẫu ứng dụng. OCI SDK Java vẫn là lớp client nền cho các API OCI; starter Spring giúp cấu hình và sử dụng SDK theo cách quen thuộc với Spring.

### Cách hiểu tên gọi theo thời gian

Tài liệu và repository đã phát triển qua nhiều phiên bản. Dòng tài liệu cũ có thể gọi phần tích hợp OCI là Spring Cloud OCI hoặc Spring Cloud for OCI như tên một dự án/thư viện chính. Cấu trúc mới đặt phần này dưới dự án đa module Spring Cloud Oracle.

Vì vậy, khi đọc tài liệu hoặc dependency cũ, cần kiểm tra:

- Version đang dùng thuộc dòng 1.x hay 2.x.
- Tên artifact và package của đúng version.
- Phiên bản Spring Boot/Spring Framework được hỗ trợ.
- Module đã được đổi tên, chuyển vị trí hay thay thế chưa.

Không suy ra cấu trúc hiện tại chỉ từ một bài blog hoặc ví dụ dùng artifact cũ. Tài liệu tham chiếu và release notes của đúng version là nguồn quyết định.

## 3. Bản đồ các dự án con

Cấu trúc hiện hành có bốn nhánh bổ trợ nhau:

~~~mermaid
flowchart TD
    A[Spring Cloud Oracle] --> B[Oracle AI Database Spring Boot Starters]
    A --> C[Spring Cloud Stream Binder for TxEventQ]
    A --> D[Spring Cloud OCI]
    A --> E[Spring AI Oracle]
    B --> F[UCP / Wallet / AQ-JMS / OKafka / JSON / Spatial]
    C --> G[Spring Cloud Stream Supplier / Function / Consumer]
    D --> H[Vault / Object Storage / Queue / Streaming / Functions / ADB]
    E --> I[OCI Generative AI qua Spring AI APIs]
~~~

| Nhánh | Phạm vi | Khi nào chọn |
| --- | --- | --- |
| Oracle AI Database Spring Boot Starters | Kết nối database, UCP, Wallet, AQ/JMS, OKafka, JSON, Spatial và telemetry | Ứng dụng cần kết nối hoặc dùng tính năng Oracle AI Database |
| Spring Cloud Stream Binder for TxEventQ | Đưa Oracle Transactional Event Queues vào mô hình Supplier/Function/Consumer của Spring Cloud Stream | Muốn dùng TxEventQ qua Spring Cloud Stream |
| Spring Cloud OCI | Tích hợp các dịch vụ managed OCI qua starter và API theo idiom Spring | Ứng dụng cần Vault, Object Storage, Queue, Streaming, Functions, Logging hoặc dịch vụ OCI khác |
| Spring AI Oracle | Tích hợp mô hình OCI Generative AI qua abstraction Spring AI | Ứng dụng dùng chat model hoặc embedding model của OCI qua Spring AI |

Các nhánh cùng thuộc hệ sinh thái Oracle nhưng không phải một module duy nhất. Chúng có thể dùng chung một ứng dụng và một số nền tảng cấu hình, nhưng không nên thêm tất cả starter theo kiểu “bộ Oracle đầy đủ”.

### Sơ đồ chọn nhanh

~~~mermaid
flowchart TD
    A[Ứng dụng Spring cần tích hợp Oracle] --> B{Đích tích hợp là gì?}
    B -->|Database Oracle| C[Oracle AI Database starters]
    B -->|OCI managed service| D[Spring Cloud OCI]
    B -->|TxEventQ qua Spring Cloud Stream| E[TxEventQ Stream Binder]
    B -->|OCI Generative AI qua Spring AI| F[Spring AI Oracle]
    C --> G[UCP / Wallet / AQ-JMS / OKafka / JSON]
    D --> H[Storage / Vault / Queue / Streaming / Functions]
    E --> I[Supplier / Function / Consumer]
    F --> J[ChatModel / EmbeddingModel]
~~~

## 4. Spring Cloud Oracle và Spring Cloud OCI khác nhau thế nào?

### Spring Cloud Oracle: phạm vi tổng thể

Spring Cloud Oracle tập hợp các tích hợp dành cho hệ sinh thái Oracle. Phạm vi không chỉ có OCI. Ví dụ, UCP và Wallet phục vụ kết nối database; AQ/JMS và OKafka phục vụ messaging gắn với Oracle AI Database; TxEventQ binder tích hợp Spring Cloud Stream; Spring Cloud OCI kết nối các dịch vụ cloud; Spring AI Oracle đưa Generative AI vào ứng dụng Spring AI.

### Spring Cloud OCI: phạm vi cloud services

Spring Cloud OCI tập trung vào OCI. Một core starter cấu hình authentication và hạ tầng dùng chung; các service-specific starter bổ sung bean và API cho từng dịch vụ.

Các tích hợp tiêu biểu:

- Object Storage: API thao tác bucket/object và Spring Resource.
- Vault: property source và API quản lý/đọc secret.
- Streaming: gửi và nhận record từ OCI Streaming.
- Queue: thao tác queue và message của OCI Queue.
- Notifications: publish notification tới topic.
- Logging: gửi log tới OCI Logging.
- Email Delivery: tích hợp Spring Mail.
- Functions: gọi OCI Functions.
- Autonomous Database: thao tác vòng đời resource Autonomous Database.
- Oracle NoSQL Database: truy cập Oracle NoSQL.
- Generative AI: tích hợp OCI Generative AI; cần kiểm tra khuyến nghị phiên bản hiện tại vì nhánh Spring AI Oracle đã được tách riêng.

### OCI SDK vẫn là nền tảng bên dưới

Spring Cloud OCI không loại bỏ OCI SDK. Nó cung cấp auto-configuration, bean và cách dùng gần với Spring. Khi cần tính năng chưa được starter bao phủ, có thể dùng OCI SDK trực tiếp trong cùng ứng dụng, nhưng nên giữ một nơi chịu trách nhiệm về authentication, region, retry, timeout và client lifecycle.

Không tạo hai bộ client với hai credential profile khác nhau một cách vô tình. Nếu dùng starter và SDK trực tiếp cùng lúc, hãy thống nhất provider/credential strategy và quyền truy cập.

## 5. Ranh giới dependency và Maven coordinates

Các nhánh dùng groupId khác nhau. Đây là tín hiệu quan trọng để không chọn nhầm artifact.

| Loại tích hợp | GroupId thường gặp | Artifact minh họa |
| --- | --- | --- |
| Spring Cloud OCI core | com.oracle.cloud.spring | spring-cloud-oci-starter |
| OCI Object Storage | com.oracle.cloud.spring | spring-cloud-oci-starter-storage |
| OCI Vault | com.oracle.cloud.spring | spring-cloud-oci-starter-vault |
| OCI Streaming | com.oracle.cloud.spring | spring-cloud-oci-starter-streaming |
| OCI Queue | com.oracle.cloud.spring | spring-cloud-oci-starter-queue |
| Oracle AI Database UCP | com.oracle.database.spring | oracle-spring-boot-starter-ucp |
| Oracle AI Database Wallet | com.oracle.database.spring | oracle-spring-boot-starter-wallet |
| Oracle AI Database AQ/JMS | com.oracle.database.spring | oracle-spring-boot-starter-aqjms |
| Oracle AI Database OKafka | com.oracle.database.spring | oracle-spring-boot-starter-okafka |
| TxEventQ Spring Cloud Stream binder | com.oracle.database.spring.cloud-stream-binder | spring-cloud-stream-binder-oracle-txeventq |

Tên artifact và groupId có thể thay đổi giữa các major release. Bảng này giúp nhận diện ranh giới, không thay thế việc đối chiếu tài liệu đúng version.

### Core starter và service starter

Với Spring Cloud OCI:

- Core starter cung cấp cấu hình authentication và hạ tầng chung.
- Service starter kéo theo phần triển khai cần thiết cho một tích hợp cụ thể.
- Khi service starter đã khai báo transitive dependency của module tương ứng, không cần khai báo thêm implementation module riêng trừ khi tài liệu yêu cầu.

Ví dụ Maven cho ứng dụng cần Object Storage:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.oracle.cloud.spring</groupId>
        <artifactId>spring-cloud-oci-starter-storage</artifactId>
        <version>SPRING_CLOUD_ORACLE_VERSION</version>
    </dependency>
</dependencies>
~~~

Trong nhiều cấu hình, service starter kéo theo core cần thiết. Nếu ứng dụng cần dùng nhiều dịch vụ OCI, kiểm tra dependency tree và hướng dẫn phiên bản để tránh khai báo lặp hoặc trộn version.

### Không trộn artifact chỉ vì cùng là Oracle

Ví dụ:

- Dùng Object Storage thì chọn starter thuộc Spring Cloud OCI.
- Dùng JDBC với Oracle AI Database thì chọn JDBC driver và starter UCP phù hợp.
- Dùng TxEventQ qua JMS thì chọn AQ/JMS starter.
- Dùng TxEventQ qua Spring Cloud Stream thì chọn binder tương ứng.
- Dùng Kafka-style API trên TxEventQ thì xem OKafka.
- Dùng OCI Generative AI qua Spring AI thì xem Spring AI Oracle.

Một artifact thuộc nhánh database không tự trở thành OCI service starter chỉ vì Autonomous Database được triển khai trên OCI.

## 6. Version alignment: Spring Boot, Spring Cloud Oracle và OCI SDK

Tích hợp cloud phụ thuộc nhiều lớp version:

1. Java runtime.
2. Spring Boot.
3. Spring Framework.
4. Spring Cloud Oracle subproject.
5. Spring Cloud Stream hoặc Spring AI nếu dùng.
6. OCI Java SDK và các client transitively được kéo vào.
7. JDBC driver, UCP, Wallet hoặc NoSQL driver nếu dùng database starter.

Không nâng riêng một dependency transitive để chữa lỗi compile mà chưa kiểm tra compatibility matrix.

### Major version có thể đổi nền tảng

Dòng 2.x của Spring Cloud Oracle chuyển sang Spring Boot 4 và Spring Framework 7. Vì vậy không thể giả định starter 2.x thay thế drop-in cho ứng dụng đang dùng Spring Boot 3 hoặc 2.x.

Nếu ứng dụng hiện tại dùng Spring Boot 3:

- Xác định dòng Spring Cloud Oracle tương thích với Boot 3.
- Đọc migration guide/release notes của dòng đó.
- Không kéo starter 2.x chỉ vì đây là bản mới hơn.
- Chỉ nâng Boot major khi đã lập kế hoạch cho Spring Framework, Jakarta APIs, test libraries và các dependency liên quan.

Nếu ứng dụng dùng Spring Boot 4:

- Chọn bản Spring Cloud Oracle 2.x được tài liệu hỗ trợ.
- Đồng bộ version giữa OCI starter, database starter, binder và Spring AI Oracle.
- Dùng dependency management của dự án theo hướng dẫn chính thức.
- Kiểm tra dependency tree để phát hiện hai version OCI SDK hoặc Spring libraries cùng xuất hiện.

### Quy trình chọn version

~~~text
1. Xác định Spring Boot version của ứng dụng
2. Chọn release line Spring Cloud Oracle tương thích
3. Xác định đúng subproject và starter
4. Dùng version/BOM theo tài liệu của release line
5. Kiểm tra dependency tree
6. Chạy compile + integration test
7. Triển khai thử và quan sát authentication, connection, retry
~~~

Không copy dependency version từ sample có Boot version khác. Sample có thể đang minh họa API nhưng không phù hợp trực tiếp với baseline dự án của bạn.

## 7. OCI authentication: core starter chịu trách nhiệm gì?

OCI API cần danh tính để xác thực và authorization để kiểm tra quyền. Spring Cloud OCI core starter tự cấu hình authentication và hạ tầng dùng chung cho các starter dịch vụ.

Các kiểu authentication thường gặp:

| Kiểu | Môi trường điển hình | Đặc điểm |
| --- | --- | --- |
| FILE | Máy phát triển hoặc môi trường có OCI config profile | Đọc cấu hình từ file OCI CLI/SDK |
| SIMPLE | Trường hợp cần khai báo API key properties trực tiếp | Cần user OCID, tenancy OCID, fingerprint, private key và region |
| INSTANCE_PRINCIPAL | Compute instance OCI | Dùng danh tính của instance và dynamic group/policy |
| RESOURCE_PRINCIPAL | OCI Functions hoặc resource được hỗ trợ | Dùng danh tính resource thay vì nhúng user key |
| SESSION_TOKEN | Phiên làm việc tạm thời | Phù hợp workflow dùng session token |
| WORKLOAD_IDENTITY | Workload chạy trên OKE theo mô hình hỗ trợ | Liên kết workload với IAM identity |

Chọn phương thức theo nơi chạy ứng dụng và hướng dẫn authentication của OCI SDK. Không coi mọi kiểu đều có thể thay thế nhau trong mọi môi trường.

### FILE cho local development

Ví dụ:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: /path/to/oci/config
      region:
        static: YOUR_OCI_REGION
      compartment:
        static: YOUR_COMPARTMENT_OCID
~~~

Tên property và default phải được kiểm tra theo phiên bản starter. Có thể để SDK dùng vị trí mặc định nếu không khai báo file riêng. Không commit file config hoặc private key vào repository.

### SIMPLE và API key

SIMPLE dùng thông tin API key của OCI user. Các giá trị nhạy cảm không nên được ghi literal trong application.yaml:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: SIMPLE
        user-id: INJECT_USER_OCID_FROM_SECRET_STORE
        tenant-id: INJECT_TENANCY_OCID_FROM_SECRET_STORE
        fingerprint: INJECT_FINGERPRINT_FROM_SECRET_STORE
        private-key: /run/secrets/oci/private-key.pem
        pass-phrase: INJECT_KEY_PASSPHRASE_FROM_SECRET_STORE
        region: YOUR_OCI_REGION
~~~

Đây là cấu trúc minh họa; hãy xác nhận cách bind tên property trong release đang dùng. Ưu tiên secret manager hoặc mounted secret file, phân quyền đọc tối thiểu và xoay key theo quy trình.

### Workload identity và principal

Trong production, tránh gắn API key cá nhân của developer vào workload. Chọn identity gắn với compute/function/pod theo môi trường:

- Compute instance: Instance Principal với dynamic group và policy.
- OCI Functions: Resource Principal nếu runtime/service hỗ trợ.
- OKE: Workload Identity khi cluster/workload được cấu hình đúng.

Danh tính workload giúp không phải phân phối private key cá nhân đến container. Tuy nhiên, identity chỉ xác thực; policy vẫn phải cho phép đúng thao tác trên đúng compartment/resource.

## 8. Region, compartment và IAM policy

### Region

OCI resource thuộc một region. Cấu hình region mặc định giúp các starter dùng cùng vị trí nếu không có override riêng.

~~~yaml
spring:
  cloud:
    oci:
      region:
        static: YOUR_OCI_REGION
~~~

Region static của Spring Cloud OCI có thể có độ ưu tiên cao hơn region lấy từ profile hoặc auth config. Vì vậy cần kiểm tra property precedence khi cùng lúc khai báo nhiều nguồn.

Không hardcode region của ví dụ tài liệu vào production. Chọn region theo vị trí dữ liệu, latency, residency, DR và nơi resource thực sự được provision.

### Compartment

Compartment là ranh giới tổ chức và quản lý quyền cho OCI resource. Có thể cấu hình compartment mặc định:

~~~yaml
spring:
  cloud:
    oci:
      compartment:
        static: YOUR_COMPARTMENT_OCID
~~~

Một ứng dụng có thể thao tác resource thuộc nhiều compartment; property mặc định không thay thế compartment ID rõ ràng trong các operation cần target khác.

### IAM policy

Một cấu hình authentication thành công chưa có nghĩa API call được phép. Cần kiểm tra:

- User/group hoặc dynamic group/workload identity.
- Policy verb phù hợp: inspect, read, use, manage.
- Resource type và compartment scope.
- Permission đặc thù cho service hoặc operation.
- Policy cho service principal nếu OCI service cần truy cập resource khác.
- Quyền đọc secret, ghi object, publish/consume message tách biệt.

Bắt đầu với quyền tối thiểu cần cho use case. Không cấp manage-all trong tenancy chỉ để giải quyết nhanh lỗi 403.

## 9. Auto-configuration và Spring bean

Một starter Spring Boot thường thực hiện:

1. Đọc cấu hình Spring Environment.
2. Tạo authentication provider hoặc dùng provider có sẵn.
3. Cấu hình region/compartment.
4. Tạo OCI SDK client/template hoặc Spring abstraction.
5. Đăng ký bean trong application context.
6. Áp dụng conditional property để bật/tắt tích hợp.

Ứng dụng có thể inject bean qua constructor thay vì tự khởi tạo client ở mọi service.

~~~java
@Service
public class DocumentArchiveService {

    private final Storage storage;

    public DocumentArchiveService(Storage storage) {
        this.storage = storage;
    }

    // Các operation upload/download dùng Storage bean
}
~~~

Tên package và method import cụ thể phụ thuộc module/version. Đọc Javadoc hoặc sample tương ứng trước khi viết code hoàn chỉnh.

### Khi nào cần OCI SDK trực tiếp?

Dùng SDK trực tiếp nếu:

- Starter chưa expose operation cần thiết.
- Cần cấu hình client đặc thù theo service.
- Cần API mới hơn phiên bản Spring integration.
- Cần một capability chưa có abstraction Spring.

Giữ nguyên nguyên tắc: reuse authentication provider, region, retry, timeout và lifecycle. Không tạo client mới cho từng request; client SDK thường được thiết kế để tái sử dụng.

## 10. Object Storage: Spring Resource và Storage API

OCI Object Storage lưu object theo namespace, bucket và object name. Spring Cloud OCI cung cấp API Storage và tích hợp với Spring Resource.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

Starter có thể auto-configure bean Storage để thao tác bucket/object.

Ví dụ minh họa:

~~~java
@Service
public class InvoiceArchive {

    private final Storage storage;

    public InvoiceArchive(Storage storage) {
        this.storage = storage;
    }

    public void upload(
            String bucket,
            String objectName,
            InputStream content,
            StorageObjectMetadata metadata) {

        storage.upload(bucket, objectName, content, metadata);
    }
}
~~~

API thực tế và import cần khớp release. Xác định rõ ai sở hữu InputStream và đóng stream ở đúng nơi. Không đọc toàn bộ file lớn vào byte array nếu có thể stream.

### Spring Resource

Object có thể được truy cập qua Resource abstraction bằng URI dạng Object Storage:

~~~text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/<bucket>/o/<object>
~~~

Spring Cloud OCI có thể resolve object thành Resource để đọc như các resource khác. Tích hợp WritableResource cho phép ghi object qua OutputStream; upload hoàn tất khi stream được đóng theo contract của implementation.

Lợi ích:

- Có thể dùng ResourceLoader/ApplicationContext để resolve resource.
- Code đọc file gần với abstraction Spring.
- Có thể dùng Resource trong các API Spring nhận Resource.
- Không cần tự viết toàn bộ plumbing của OCI SDK cho thao tác phổ biến.

Resource abstraction không biến Object Storage thành filesystem POSIX. Không giả định rename, directory, atomic update hoặc locking giống file system. Object key là tên object; folder chỉ là quy ước prefix.

### Các quyết định thiết kế

- Bucket và object naming.
- Namespace và region.
- Content-Type, metadata và encryption.
- Multipart upload cho file lớn.
- Retention, lifecycle và versioning.
- Conditional write/overwrite policy.
- Quyền read/write/delete theo workload.
- Idempotency khi upload retry.
- Pre-authenticated access nếu use case cho phép và có thời hạn.

Không đặt thông tin nhạy cảm trong object metadata nếu không có kiểm soát tương ứng. Tránh log nội dung file hoặc URL truy cập có token.
## 11. Vault: secrets và Spring Environment

OCI Vault có thể được dùng theo hai cách chính trong tích hợp Spring Cloud OCI:

- Là property source để đưa giá trị cấu hình từ Vault vào Spring Environment.
- Là bean API để ứng dụng truy vấn secret theo nhu cầu thông qua VaultTemplate.

Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-vault</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

### Vault làm property source

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
      region:
        static: YOUR_OCI_REGION
      vault:
        enabled: true
        compartment: YOUR_COMPARTMENT_OCID
        property-refresh-interval: 10m
        property-sources:
          - vault-id: YOUR_VAULT_OCID
~~~

Một secret có thể được tham chiếu từ Spring Environment theo tên được cấu hình trong Vault integration. Cách đặt tên property, prefix và refresh behavior cần khớp version của starter.

Lợi ích:

- Secret không phải lưu trong application.yaml.
- Có thể quản lý quyền đọc secret qua OCI IAM.
- Có thể quản lý version/rotation ở Vault.
- Ứng dụng dùng Spring property conventions.

Tuy nhiên, việc property source refresh không có nghĩa mọi singleton bean đã inject giá trị cũ tự động được tạo lại. Kiểm tra cách binding, refresh scope và lifecycle của bean phụ thuộc secret. Với credential cần rotation, thiết kế cơ chế reload/refresh và kiểm thử khi secret đổi.

### VaultTemplate

Starter cũng có thể auto-configure VaultTemplate cho thao tác API:

~~~java
@Service
public class SecretLookupService {

    private final VaultTemplate vaultTemplate;

    public SecretLookupService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readSecret(String secretName) {
        GetSecretBundleByNameResponse bundle =
                vaultTemplate.getSecret(secretName);

        return vaultTemplate.decodeBundle(bundle);
    }
}
~~~

Tên class và method phải khớp Javadoc của release. Không log giá trị secret, không đưa secret vào exception message và không cache vô thời hạn nếu rotation là yêu cầu vận hành.

### Secret, key và quyền

OCI Vault có các khái niệm secret và key. Ứng dụng cần đọc secret không đồng nghĩa cần quyền quản lý encryption key hoặc quản trị toàn bộ Vault. Cấp quyền tối thiểu cho workload identity và compartment phù hợp.

Không dùng Vault để lưu mọi loại dữ liệu nghiệp vụ hoặc file lớn. Chọn dịch vụ theo loại dữ liệu: secret/config nhạy cảm dùng Vault; file/object dùng Object Storage; database record dùng database.

## 12. Messaging: ba mô hình cần phân biệt

Trong hệ sinh thái Oracle có nhiều lựa chọn messaging. Tên gọi gần nhau nhưng backend và semantics khác nhau.

| Lựa chọn | Backend | Programming model | Phù hợp khi |
| --- | --- | --- | --- |
| OCI Queue | OCI managed queue service | Queue/message API | Công việc độc lập, xử lý theo hàng đợi |
| OCI Streaming | OCI managed stream service | Stream/partition/cursor API | Ingest và consume luồng record với throughput cao |
| TxEventQ qua AQ/JMS | Oracle AI Database Transactional Event Queues | JMS, JmsTemplate, listener | Ứng dụng dùng Spring JMS và muốn queue gắn với database |
| TxEventQ qua OKafka | Oracle AI Database Transactional Event Queues | Kafka Java client APIs | Ứng dụng đã dùng producer/consumer Kafka-style |
| TxEventQ qua Stream Binder | Oracle AI Database Transactional Event Queues | Spring Cloud Stream Supplier/Function/Consumer | Ứng dụng theo mô hình function-based messaging của Spring Cloud Stream |

Không chọn chỉ theo chữ “queue” hoặc “stream”. Xác định nơi lưu message, transaction boundary, throughput, ordering, consumer group, retention, delivery/ack semantics và cách vận hành.

## 13. OCI Queue và OCI Streaming

### OCI Queue

OCI Queue là dịch vụ queue managed cho các message được xử lý độc lập. Spring Cloud OCI cung cấp starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-queue</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

Starter auto-configure bean Queue để thao tác queue và message.

Các việc cần thiết kế:

- Tạo queue và cấu hình retention.
- Delivery count và dead-letter behavior.
- Message visibility/acknowledgment semantics.
- Retry, poison message và quarantine.
- Consumer concurrency và flow control.
- Message ID, correlation ID và idempotency.
- IAM permission cho producer/consumer.

Queue phù hợp với tác vụ có thể được xử lý độc lập: tạo thumbnail, xử lý hóa đơn, gửi notification, chạy workflow nền. Consumer phải xử lý duplicate an toàn theo semantics của dịch vụ.

### OCI Streaming

OCI Streaming là dịch vụ ingest và consume stream record. Starter:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-streaming</artifactId>
    <version>SPRING_CLOUD_ORACLE_VERSION</version>
</dependency>
~~~

Starter có thể auto-configure bean Streaming để tạo stream và gửi/nhận message.

Ví dụ API-level:

~~~java
@Service
public class AuditStreamPublisher {

    private final Streaming streaming;

    public AuditStreamPublisher(Streaming streaming) {
        this.streaming = streaming;
    }

    public void publish(
            String streamId,
            byte[] key,
            byte[] payload) {
        streaming.putMessages(streamId, key, payload);
    }
}
~~~

Đoạn code minh họa cách dùng bean; method signature/import cụ thể cần kiểm tra đúng SDK/starter release.

Khi thiết kế stream:

- Chọn partition key phù hợp để phân phối tải và giữ ordering trong phạm vi cần thiết.
- Lưu cursor/checkpoint bền vững cho consumer.
- Xử lý record được đọc lại sau restart.
- Theo dõi consumer lag và retention window.
- Thiết kế schema/version và event identity.
- Không coi stream là queue work item có settlement giống nhau.

### Queue và Streaming không thay thế lẫn nhau

| Tiêu chí | OCI Queue | OCI Streaming |
| --- | --- | --- |
| Mô hình | Message queue | Event/data stream |
| Cách đọc | Nhận message để xử lý và settle theo API | Đọc record theo partition/cursor |
| Tiến độ | Message acknowledgment/visibility | Cursor/checkpoint |
| Ordering | Theo semantics và cấu hình queue | Theo partition/key và sequence |
| Use case | Work distribution | Event ingestion, stream processing |
| Recovery | Redelivery/retry/DLQ policy | Replay từ cursor trong retention |

Không dùng một abstraction consumer chung rồi giả định Queue và Streaming có cùng semantics. Viết adapter riêng nếu domain cần một interface chung, nhưng giữ các khác biệt về settlement/checkpoint trong implementation.

## 14. TxEventQ: AQ/JMS, OKafka và Spring Cloud Stream binder

TxEventQ là Oracle Database Transactional Event Queues, nằm trong Oracle AI Database. Đây là messaging gắn với database, không phải OCI Queue và cũng không phải OCI Streaming.

### AQ/JMS starter

AQ/JMS cung cấp hỗ trợ Oracle Advanced Queuing và TxEventQ như JMS provider. Ứng dụng Spring dùng abstraction JMS như JmsTemplate và listener.

Dependency thường dùng:

~~~xml
<dependency>
    <groupId>com.oracle.database.spring</groupId>
    <artifactId>oracle-spring-boot-starter-aqjms</artifactId>
    <version>ORACLE_DATABASE_STARTER_VERSION</version>
</dependency>
~~~

AQ/JMS phụ thuộc hạ tầng kết nối database và UCP. Cần cấu hình datasource, queue/topic, database user và quyền AQ phù hợp.

Một điểm đáng chú ý là cấu hình mặc định được tài liệu mô tả có thể chia sẻ transaction giữa datasource và JMS connection factory. Điều này cho phép một local database transaction đọc message, cập nhật dữ liệu và commit/rollback cùng unit of work khi được cấu hình đúng. Không suy rộng tính chất này sang OCI Queue, OCI Streaming hay broker khác.

### OKafka starter

OKafka cung cấp producer, consumer và administration API theo phong cách Kafka, nhưng backend là TxEventQ trong Oracle AI Database.

~~~xml
<dependency>
    <groupId>com.oracle.database.spring</groupId>
    <artifactId>oracle-spring-boot-starter-okafka</artifactId>
    <version>ORACLE_DATABASE_STARTER_VERSION</version>
</dependency>
~~~

Chọn OKafka khi ứng dụng đã dùng Kafka client concepts như producer, consumer, group, serializer và topic administration. Nếu muốn JMS API, dùng AQ/JMS. Nếu muốn function model của Spring Cloud Stream, cân nhắc binder.

### Spring Cloud Stream binder cho TxEventQ

Binder đưa TxEventQ vào mô hình Spring Cloud Stream. Ứng dụng khai báo Supplier, Function hoặc Consumer và cấu hình binding thay vì tự quản lý queue API ở từng service.

Artifact có group riêng:

~~~xml
<dependency>
    <groupId>com.oracle.database.spring.cloud-stream-binder</groupId>
    <artifactId>spring-cloud-stream-binder-oracle-txeventq</artifactId>
    <version>TXEVENTQ_BINDER_VERSION</version>
</dependency>
~~~

Ví dụ function:

~~~java
@Configuration
public class OrderEventFunctions {

    @Bean
    public Function<OrderCreated, OrderAccepted> validateOrder() {
        return event -> new OrderAccepted(
                event.orderId(),
                event.customerId());
    }
}
~~~

Binder kết nối tới datasource Oracle và TxEventQ theo cấu hình của nó. Cần kiểm tra permission database, UCP, binding names, consumer group, retry, error handling và transaction behavior theo version.

### Chọn giữa AQ/JMS, OKafka và binder

| Câu hỏi | Lựa chọn gợi ý |
| --- | --- |
| Ứng dụng đang dùng Spring JMS/JmsTemplate? | AQ/JMS |
| Cần Kafka Java client API? | OKafka |
| Đang dùng Spring Cloud Stream function bindings? | TxEventQ binder |
| Message phải nằm trong OCI managed queue tách khỏi database? | OCI Queue |
| Cần stream record ingest/partition/cursor? | OCI Streaming |

Không cài cả ba integration TxEventQ nếu chỉ cần một programming model. Chỉ kết hợp khi có lý do kiến trúc và đã xác định rõ queue ownership, transaction manager và consumer identity.

## 15. Autonomous Database: quản lý resource và kết nối dữ liệu là hai việc khác nhau

Tên Autonomous Database xuất hiện ở cả hai phía, nhưng cần phân biệt:

- Spring Cloud OCI Autonomous Database starter cung cấp operation quản lý vòng đời resource OCI, ví dụ tạo, đọc thông tin hoặc tạo wallet cho Autonomous Database.
- Oracle AI Database starters như UCP và Wallet phục vụ kết nối ứng dụng tới database để chạy query/transaction.

Đây là hai responsibility khác nhau.

### Quản lý lifecycle

Khi ứng dụng/platform automation cần provision hoặc tra cứu Autonomous Database, có thể dùng OCI service integration phù hợp. Các operation này thường cần quyền quản trị resource và không nên được cấp cho mọi business service.

### Kết nối database trong ứng dụng

Ứng dụng CRUD thường cần:

- Oracle JDBC driver.
- DataSource.
- UCP nếu dùng Oracle Universal Connection Pool.
- Wallet/mTLS nếu môi trường yêu cầu.
- Spring Data JDBC hoặc Spring Data JPA theo mô hình persistence.

Ví dụ cấu hình UCP:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//DB_HOST:1521/DB_SERVICE
    username: APP_USER
    password: INJECT_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
    type: oracle.ucp.jdbc.PoolDataSourceImpl
    oracleucp:
      connection-factory-class-name: oracle.jdbc.pool.OracleDataSource
      connection-pool-name: ProviderIntegrationPool
      initial-pool-size: 2
      min-pool-size: 2
      max-pool-size: 20
~~~

Thông số chỉ minh họa; sizing theo concurrency, database limits và workload. Không để password literal trong file cấu hình.

### Wallet

Với Autonomous Database hoặc database endpoint yêu cầu mTLS, Wallet starter có thể bổ sung cơ chế kết nối bảo mật. Wallet là credential/trust material nhạy cảm; quản lý mount, rotation, permission và backup theo policy.

Không nhầm việc tạo wallet qua API quản lý resource với việc ứng dụng sử dụng wallet để mở JDBC connection. Hai bước có thể thuộc hai service identity và lifecycle khác nhau.

## 16. Spring AI Oracle: tách biệt với Spring Cloud OCI

Spring AI Oracle cung cấp tích hợp model cho OCI Generative AI thông qua Spring AI APIs. Đây là nhánh riêng trong hệ sinh thái Spring Cloud Oracle.

Ứng dụng có thể làm việc với abstraction như:

- ChatModel hoặc ChatClient cho hội thoại.
- EmbeddingModel cho embedding.
- Streaming/tool calling/memory theo khả năng của model integration và version.

Không coi Spring AI Oracle là OCI Queue, OCI Streaming hay một Spring Cloud Stream binder. Đây là tích hợp AI model.

### Chọn đúng nhánh AI

- Ứng dụng cần gọi OCI Generative AI qua Spring AI: dùng Spring AI Oracle.
- Ứng dụng cần quản lý resource OCI hoặc gọi API service khác: dùng Spring Cloud OCI starter tương ứng.
- Ứng dụng dùng một model provider khác: giữ abstraction Spring AI nếu có implementation phù hợp.

Một số tài liệu/version cũ có module Generative AI nằm trong Spring Cloud OCI. Release notes mới hơn có thay đổi và khuyến nghị chuyển phần model integration sang Spring AI Oracle. Khi nâng version, đọc release notes thay vì giữ nguyên dependency cũ theo thói quen.

## 17. Ghép các nhánh trong một kiến trúc thực tế

Ví dụ một dịch vụ xử lý hóa đơn:

~~~mermaid
flowchart TD
    A[Spring Boot Invoice API] --> B[Oracle AI Database]
    A --> C[OCI Object Storage]
    A --> D[OCI Vault]
    B --> E[UCP / Wallet]
    C --> F[Spring Cloud OCI Storage]
    D --> G[Spring Cloud OCI Vault]
    B --> H[TxEventQ]
    H --> I[Spring Cloud Stream Binder]
    A --> J[OCI Queue hoặc Streaming]
    A --> K[OCI Generative AI]
    K --> L[Spring AI Oracle]
~~~

Một request có thể:

1. Xác thực user qua API layer.
2. Ghi invoice metadata vào Oracle AI Database.
3. Ghi outbox/TxEventQ event trong transaction phù hợp.
4. Lưu file PDF vào OCI Object Storage.
5. Đọc secret cần thiết từ Vault.
6. Phát event tới consumer để gửi email hoặc xử lý tiếp.
7. Dùng Generative AI để trích xuất/đề xuất nội dung nếu use case cần.

Không phải mọi bước nên chạy trong một request đồng bộ. Upload file, publish event và database transaction có failure boundary riêng. Dùng outbox/saga hoặc workflow state khi có nhiều side effect.

### Ranh giới transaction

| Operation | Transaction boundary |
| --- | --- |
| Insert invoice và outbox row trong cùng Oracle DB | Database transaction |
| TxEventQ consume/update nếu cấu hình JMS/binder hỗ trợ transaction chung | Transaction của Oracle AI Database theo integration |
| Upload object lên OCI Object Storage | OCI API operation riêng |
| Read secret từ Vault | OCI API call riêng |
| Publish vào OCI Queue/Streaming | OCI broker operation riêng |
| Gọi OCI Generative AI | External API call riêng |

Không giả định một @Transactional trên service bao trùm database, Object Storage, Vault và Generative AI. Nếu workflow cần nhiều bước, định nghĩa retry, idempotency, compensation và trạng thái partial completion.

## 18. Cấu hình môi trường và profile

Tách cấu hình theo môi trường:

| Môi trường | Authentication gợi ý | Cấu hình |
| --- | --- | --- |
| Local developer | FILE hoặc session token | OCI CLI profile, local config file |
| CI test | Identity/service principal dành cho test hoặc mock | Secret injection, test compartment |
| OCI Compute | Instance Principal | Dynamic group và policy |
| OCI Functions | Resource Principal | Resource identity và policy |
| OKE | Workload Identity nếu được hỗ trợ/cấu hình | Cluster/workload federation |
| On-premises | API key hoặc federation được phê duyệt | Secret store, network route, region |

Không dùng local developer profile làm credential production. Không đưa private key, token, password hoặc Vault secret vào source control.

Ví dụ profile tách biệt:

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

Trong production, dùng profile/identity phù hợp runtime và quản lý secret qua hệ thống được phê duyệt. Tránh lưu hai loại credential trong cùng file rồi chuyển qua lại bằng comment.

## 19. Bảo mật và quyền tối thiểu

Mỗi starter chỉ cần một phần quyền của OCI:

- Storage upload cần quyền ghi object/bucket theo use case.
- Storage download cần quyền đọc object.
- Vault integration cần quyền đọc secret bundle hoặc operation cụ thể.
- Queue producer và consumer cần quyền tương ứng.
- Streaming producer/consumer cần quyền với stream và stream pool phù hợp.
- Functions invocation cần quyền gọi function.
- Logging cần quyền ghi log.
- Autonomous Database lifecycle API có thể cần quyền quản lý resource rộng hơn quyền JDBC user.

Tách identity theo service khi rủi ro và ownership khác nhau. Một invoice API không nên tự động có quyền xóa bucket, tạo database và quản trị Vault chỉ vì cùng dùng một tenancy.

### Bảo vệ cấu hình

- Không commit OCI config file, API private key hoặc wallet.
- Không ghi secret vào log, trace, metric label hay exception.
- Dùng environment injection hoặc secret mount có quyền đọc tối thiểu.
- Xoay credential và xác minh workload nhận credential mới.
- Giới hạn quyền truy cập Vault và audit secret retrieval.
- Dùng TLS và cấu hình network access theo policy.
- Kiểm tra region/compartment để tránh ghi dữ liệu nhầm môi trường.

## 20. Retry, timeout và idempotency

OCI SDK và dịch vụ có retry/timeout semantics riêng. Starter không có nghĩa mọi operation tự động an toàn khi retry.

Phân biệt:

- Lỗi kết nối tạm thời.
- Throttling/quota.
- Permission denied.
- Validation error.
- Resource not found.
- Conflict/conditional write failure.
- Unknown outcome sau timeout.

### Quy tắc retry

- Retry lỗi transient theo policy.
- Tôn trọng retry-after hoặc backoff nếu API cung cấp.
- Không retry validation/authorization vô hạn.
- Giới hạn tổng retry budget.
- Đặt connect/read/operation timeout.
- Dùng idempotency key hoặc conditional operation cho side effect.
- Đối soát trạng thái nếu timeout khiến kết quả không rõ.

Ví dụ, upload object timeout không nhất thiết có nghĩa object chưa được ghi. Kiểm tra object key, ETag/version hoặc metadata trước khi gửi một thao tác mới có thể tạo side effect khác.

### Queue và stream

Với Queue, consumer cần idempotency và settlement đúng thời điểm. Với Streaming, consumer cần checkpoint/cursor bền vững và xử lý replay. Với TxEventQ, hiểu transaction và delivery behavior của database integration. Không áp dụng cùng một retry/ack algorithm cho cả ba.

## 21. Kiểm thử theo ranh giới dự án

Kiểm thử riêng từng integration trước khi kiểm thử workflow ghép nhiều dịch vụ.

### Unit test

- Test business service qua interface nội bộ.
- Mock Storage, VaultTemplate, Queue, Streaming hoặc database port.
- Xác minh mapping lỗi và idempotency.
- Không cần gọi OCI thật cho logic nghiệp vụ thuần.

### Integration test database

- Dùng Oracle database test environment hoặc Testcontainers theo image/driver được hỗ trợ.
- Kiểm thử UCP, Wallet/mTLS nếu cần.
- Kiểm thử AQ/JMS hoặc TxEventQ với quyền database đúng.
- Kiểm tra rollback/commit và message transaction boundary.

### Integration test OCI services

- Dùng test compartment và resource riêng.
- Cấp IAM policy tối thiểu cho test identity.
- Kiểm thử Object Storage upload/download/delete.
- Kiểm thử Vault read và secret rotation.
- Kiểm thử Queue delivery/ack/redelivery.
- Kiểm thử Streaming cursor/checkpoint/replay.
- Dọn resource test bằng lifecycle rõ ràng.

### Contract và compatibility test

- Kiểm tra starter/version với Spring Boot version dự án.
- Kiểm tra auto-configured bean và conditional properties.
- Kiểm tra OCI SDK version resolution.
- Kiểm tra serialization/schema compatibility.
- Kiểm tra lỗi 401/403, 404, throttling và timeout.
- Kiểm tra shutdown/close của client và listener.

Không chạy integration test với tenancy production hoặc resource chứa dữ liệu thật.

## 22. Observability và vận hành

Theo dõi riêng từng lớp:

| Lớp | Tín hiệu cần theo dõi |
| --- | --- |
| OCI authentication | Auth failure, token/key refresh, identity mode |
| IAM | 401/403, policy denial, compartment mismatch |
| Object Storage | Upload/download latency, error, bytes, object size |
| Vault | Secret read latency, refresh status, permission errors |
| OCI Queue | Queue depth, oldest message age, delivery attempts, DLQ |
| OCI Streaming | Consumer lag, partition throughput, checkpoint age |
| TxEventQ | Queue depth, database session/pool, transaction failures |
| UCP | Active/available connections, wait time, acquisition timeout |
| Spring AI Oracle | Model latency, token usage, timeout, response errors |

Dùng Micrometer/Actuator và OpenTelemetry phù hợp với ứng dụng. Không giả định mọi starter xuất toàn bộ metrics giống nhau; xác minh metric thực tế và bổ sung instrumentation ở adapter/service layer.

Log cần có request/correlation ID, operation, service/region, resource reference phù hợp và provider request ID khi có. Không log secret, private key, wallet content hoặc full sensitive payload.

## 23. Các lỗi tích hợp thường gặp

### Dùng nhầm starter

Triệu chứng: không có bean mong đợi hoặc kéo nhầm SDK. Kiểm tra groupId/artifact, dependency tree và đúng subproject.

### Authentication thành công ở local nhưng thất bại trong OCI runtime

Nguyên nhân thường là workload identity, dynamic group, resource principal hoặc IAM policy chưa được cấu hình đúng. Local FILE profile không chứng minh production identity hoạt động.

### Có identity nhưng API trả 403

Xác minh policy, verb, resource type, compartment và scope. Không giải quyết bằng cách nhúng API key của user có quyền cao hơn.

### Dùng Queue như Streaming

Queue settlement và stream checkpoint là hai mô hình khác nhau. Chọn service theo semantics cần thiết.

### Dùng TxEventQ binder nhưng lại cấu hình OCI Queue

TxEventQ là Oracle AI Database native messaging; OCI Queue là dịch vụ managed riêng. Binder TxEventQ cần datasource/database permissions.

### Dùng Autonomous Database lifecycle starter để chạy query

Starter quản lý lifecycle resource không thay thế JDBC DataSource, UCP hoặc Wallet. Chọn database starter phù hợp cho query/transaction.

### Nâng Spring Cloud Oracle nhưng giữ version SDK cũ bằng tay

Có thể gây dependency conflict. Đọc release notes, dùng dependency management và kiểm tra resolved tree trước khi override.

### Coi Spring Resource là filesystem

Object Storage không có đầy đủ semantics của filesystem. Thiết kế object key, overwrite, versioning và concurrency theo object storage.

## 24. Bài thực hành: chọn đúng nhánh Oracle cho Invoice Service

**Bối cảnh:** Xây dựng một Invoice Service bằng Spring Boot. Dịch vụ cần lưu metadata hóa đơn trong Oracle AI Database, lưu PDF trong OCI Object Storage, đọc secret từ OCI Vault và phát sự kiện InvoiceCreated cho consumer.

### Phần A — Phân tích yêu cầu

1. Xác định database là Oracle AI Database hay Autonomous Database.
2. Xác định file PDF lưu trong OCI Object Storage.
3. Chọn TxEventQ hay OCI Queue cho event theo transaction/ownership yêu cầu.
4. Xác định có cần Spring Cloud Stream binder hay JMS API.
5. Xác định runtime là local, Compute, Functions hay OKE.

### Phần B — Chọn dependency

1. Chọn UCP và Wallet nếu ứng dụng cần JDBC connection theo yêu cầu.
2. Chọn Spring Cloud OCI Object Storage starter.
3. Chọn Spring Cloud OCI Vault starter.
4. Chọn AQ/JMS, OKafka hoặc TxEventQ binder nếu backend là TxEventQ.
5. Chọn OCI Queue starter nếu event được gửi tới OCI Queue.
6. Không thêm Spring AI Oracle nếu ứng dụng không gọi Generative AI.

### Phần C — Cấu hình và quyền

1. Cấu hình region và compartment.
2. Chọn authentication phù hợp runtime.
3. Tạo IAM policy tối thiểu cho database/Storage/Vault/Queue.
4. Không lưu private key hoặc secret trong repository.
5. Kiểm tra startup và auto-configured bean.

### Phần D — Xử lý và phục hồi

1. Ghi invoice và event intent trong transaction database nếu dùng outbox.
2. Upload PDF bằng object key idempotent.
3. Ghi nhận trạng thái upload và event publish.
4. Xử lý timeout/unknown outcome bằng reconciliation.
5. Dùng inbox/idempotency ở consumer.
6. Kiểm thử duplicate, retry và partial failure.

### Sản phẩm cần nộp

- Sơ đồ module/dependency và transaction boundary.
- Bảng chọn starter kèm lý do.
- Cấu hình auth/region/compartment theo môi trường.
- IAM policy matrix cho từng workload.
- Mẫu code kết nối database, Object Storage, Vault và messaging.
- Kết quả integration test.
- Dashboard latency/error/backlog/connection pool.
- Runbook xử lý 403, throttling, timeout và duplicate.

### Câu hỏi tự kiểm tra

1. Spring Cloud Oracle có đồng nghĩa Spring Cloud OCI không?
2. Spring Cloud OCI khác OCI Java SDK ở đâu?
3. Vì sao database starters là nhánh riêng?
4. TxEventQ binder có backend là OCI Streaming không?
5. Khi nào dùng AQ/JMS, OKafka hoặc Spring Cloud Stream binder?
6. OCI Queue khác OCI Streaming ở semantics nào?
7. Spring Cloud OCI core starter chịu trách nhiệm gì?
8. Instance Principal và Resource Principal khác nhau theo runtime nào?
9. Vì sao local FILE authentication không nên dùng cho production workload?
10. Region và compartment ảnh hưởng việc gọi OCI service thế nào?
11. Object Storage Spring Resource có phải filesystem không?
12. Vault property refresh có tự tạo lại mọi singleton bean không?
13. Autonomous Database lifecycle API có thay thế UCP/JDBC không?
14. Spring AI Oracle thuộc ranh giới nào?
15. Vì sao phải kiểm tra Spring Boot compatibility trước khi nâng starter major version?
16. Vì sao một @Transactional không bao trùm database, Object Storage và OCI Queue?
17. Những gì cần kiểm tra khi gặp 403 dù authentication thành công?

## 25. Ghi nhớ

- Spring Cloud Oracle là dự án đa module cho công nghệ Oracle; Spring Cloud OCI là nhánh tích hợp OCI managed services.
- Oracle AI Database starters, TxEventQ binder, Spring Cloud OCI và Spring AI Oracle có trách nhiệm riêng.
- OCI SDK là lớp client nền; Spring starter cung cấp auto-configuration và Spring-friendly API.
- Dùng đúng groupId/artifact theo nhánh; không trộn database starter với OCI service starter.
- Dòng Spring Cloud Oracle 2.x chuyển sang Spring Boot 4/Spring Framework 7; phải kiểm tra release compatibility trước khi nâng.
- Core starter cấu hình OCI authentication và hạ tầng chung; service starter bổ sung bean cho dịch vụ cụ thể.
- Chọn FILE cho local khi phù hợp; production nên dùng principal/workload identity theo runtime và policy.
- Region, compartment và IAM policy đều ảnh hưởng việc gọi service; authentication không đồng nghĩa authorization.
- OCI Queue, OCI Streaming và TxEventQ là ba messaging model khác nhau; chọn theo delivery, ordering, transaction và checkpoint semantics.
- Spring Cloud OCI Object Storage cung cấp Storage API và Spring Resource; object storage không phải filesystem.
- Vault có thể làm property source hoặc dùng qua VaultTemplate; cần kiểm tra secret refresh và lifecycle bean.
- Autonomous Database lifecycle integration khác với JDBC/UCP/Wallet dùng để truy vấn dữ liệu.
- Spring AI Oracle là nhánh riêng cho model APIs; không nhầm với OCI Queue, Streaming hoặc Functions.
- Không giả định @Transactional bao trùm nhiều OCI services; dùng outbox, idempotency, saga và reconciliation theo failure boundary.
- Kiểm thử từng integration, IAM policy, version, retry, duplicate và observability trước khi triển khai.

## Tài liệu tham khảo

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud Oracle — OCI Core and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud Oracle — OCI Object Storage](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/storage/)
- [Spring Cloud Oracle — OCI Vault](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/vault/)
- [Spring Cloud Oracle — OCI Streaming](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/streaming/)
- [Spring Cloud Oracle — OCI Queues](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/queues/)
- [Spring Cloud Oracle — Oracle AI Database starters](https://oracle.github.io/spring-cloud-oracle/site/docs/category/oracle-ai-database-starters/)
- [Spring Cloud Oracle — AQ/JMS](https://oracle.github.io/spring-cloud-oracle/site/docs/database/aq-jms/)
- [Spring Cloud Oracle — OKafka](https://oracle.github.io/spring-cloud-oracle/site/docs/database/okafka/)
- [Spring Cloud Oracle — TxEventQ Stream Binder getting started](https://oracle.github.io/spring-cloud-oracle/site/docs/stream-binder/getting-started/)
- [Spring Cloud Oracle — Spring AI Oracle](https://oracle.github.io/spring-cloud-oracle/site/docs/category/spring-ai-oracle/)
- [Spring Cloud Oracle — Release notes and compatibility changes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [Oracle Cloud Infrastructure Java SDK authentication](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)
