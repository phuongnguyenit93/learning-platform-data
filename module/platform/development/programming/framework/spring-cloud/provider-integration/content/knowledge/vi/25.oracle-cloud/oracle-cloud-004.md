# Xác thực bằng tệp cấu hình, instance principal hoặc resource principal

Mọi lời gọi tới Oracle Cloud Infrastructure (OCI) đều cần một danh tính được xác thực và quyền truy cập phù hợp. Spring Cloud OCI cung cấp core starter để tự cấu hình authentication provider và hạ tầng dùng chung cho các starter dịch vụ như Object Storage, Vault, Queue và Streaming.

Có ba cách xác thực thường gặp trong bài này:

- **Configuration file (FILE):** ứng dụng dùng profile trong tệp OCI config, thường phù hợp với máy phát triển hoặc môi trường kiểm soát được private key.
- **Instance Principal:** ứng dụng chạy trên OCI Compute sử dụng danh tính của chính compute instance.
- **Resource Principal:** một OCI resource như function sử dụng danh tính và token do OCI cấp cho resource đó.

Cả ba cách đều tách biệt authentication khỏi authorization. Authentication trả lời “ai đang gọi API”; IAM policy quyết định “danh tính đó được phép làm gì với resource nào”. Một ứng dụng xác thực thành công vẫn có thể nhận HTTP 403 nếu policy chưa cấp quyền.

Bài học thuộc chương **Oracle Cloud** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**, tập trung vào cấu hình danh tính và quyền khi Spring Boot truy cập các dịch vụ managed của OCI, đồng thời đặt các lựa chọn này trong bối cảnh tích hợp storage, messaging, dữ liệu và secret.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt authentication, identity và authorization trong OCI.
2. Cấu hình Spring Cloud OCI dùng profile trong tệp config.
3. Giải thích cấu trúc profile, API signing key, fingerprint, tenancy và region.
4. Phân biệt FILE với SIMPLE và SESSION_TOKEN.
5. Cấu hình Instance Principal cho ứng dụng chạy trên OCI Compute.
6. Tạo dynamic group và policy tối thiểu cho instance.
7. Cấu hình Resource Principal cho OCI Functions hoặc resource được hỗ trợ.
8. Tạo dynamic group/policy cho resource principal.
9. Phân biệt Resource Principal với OKE Workload Identity.
10. Cấu hình region và compartment đúng thứ tự ưu tiên.
11. Chẩn đoán lỗi 401, 403, sai region và credential hết hạn.
12. Kiểm thử danh tính thực tế và audit các lời gọi OCI.

## 2. Authentication và authorization là hai bước riêng

Khi Spring Boot gọi OCI Object Storage, Vault hoặc Queue, SDK phải ký request bằng một danh tính hợp lệ. OCI xác minh chữ ký/token rồi kiểm tra IAM policy để quyết định có cho phép operation không.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Auth as OCI Authentication
    participant IAM as OCI IAM Policy
    participant Svc as OCI Service

    App->>Auth: Lấy credential / token
    Auth-->>App: Identity + signing capability
    App->>IAM: Gửi request đã ký
    IAM->>IAM: Xác định principal và policy
    alt Được cấp quyền
        IAM->>Svc: Cho phép operation
        Svc-->>App: Kết quả API
    else Thiếu quyền
        IAM-->>App: 403 NotAuthorized
    end
~~~

Ví dụ:

- FILE profile xác thực bằng OCI user và API signing key.
- Instance Principal xác thực bằng danh tính của Compute instance.
- Resource Principal xác thực bằng danh tính của resource, ví dụ OCI Function.
- IAM policy cấp quyền cho principal đọc object, ghi object hoặc đọc secret.

Không nhúng API key của user có quyền quản trị vào workload chỉ để làm cho request hết lỗi 403. Hãy xác định principal thực tế và cấp quyền tối thiểu cho principal đó.

## 3. Spring Cloud OCI core starter

Spring Cloud OCI cung cấp core starter để auto-configure OCI authentication và hạ tầng dùng chung. Các service-specific starter sử dụng cấu hình chung này.

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter:2.0.4")
}
~~~

Nếu ứng dụng chỉ cần một dịch vụ, service starter tương ứng có thể kéo theo core starter. Ví dụ, Object Storage dùng spring-cloud-oci-starter-storage, Vault dùng spring-cloud-oci-starter-vault. Kiểm tra dependency graph của đúng release để biết core đã được kéo theo chưa.

Các property chung quan trọng:

| Property | Ý nghĩa |
| --- | --- |
| spring.cloud.oci.config.type | Kiểu authentication |
| spring.cloud.oci.config.profile | Tên profile trong OCI config file |
| spring.cloud.oci.config.file | Đường dẫn tới OCI config file |
| spring.cloud.oci.config.userId | User OCID cho SIMPLE |
| spring.cloud.oci.config.tenantId | Tenancy OCID cho SIMPLE |
| spring.cloud.oci.config.fingerprint | Fingerprint của public API key |
| spring.cloud.oci.config.privateKey | Đường dẫn private key cho SIMPLE |
| spring.cloud.oci.config.passPhrase | Passphrase nếu private key được mã hóa |
| spring.cloud.oci.config.region | Region lấy từ auth configuration |
| spring.cloud.oci.config.federation-endpoint | Endpoint token federation tùy chọn cho principal-based auth |
| spring.cloud.oci.region.static | Region cố định dùng cho API call |
| spring.cloud.oci.compartment.static | Compartment mặc định |

Trong Spring Cloud OCI 2.0.4, FILE là giá trị mặc định của spring.cloud.oci.config.type. Các kiểu được hỗ trợ gồm FILE, SIMPLE, INSTANCE_PRINCIPAL, RESOURCE_PRINCIPAL, SESSION_TOKEN và WORKLOAD_IDENTITY. Hãy xác minh property theo đúng release line đang dùng.

## 4. Configuration file authentication (FILE)

FILE là cách phổ biến để phát triển local. Ứng dụng đọc một profile trong OCI SDK/CLI config file. Profile thường chứa:

- user: OCID của OCI user.
- tenancy: OCID của tenancy.
- fingerprint: fingerprint của public key đã đăng ký.
- key_file: đường dẫn private API signing key.
- region: region mặc định.
- pass_phrase: passphrase nếu private key được mã hóa.

Ví dụ config file:

~~~ini
[DEFAULT]
user=ocid1.user.oc1..example
fingerprint=11:22:33:44:55:66:77:88
tenancy=ocid1.tenancy.oc1..example
region=ap-singapore-1
key_file=/home/developer/.oci/oci_api_key.pem

[INVOICE_DEV]
user=ocid1.user.oc1..example
fingerprint=11:22:33:44:55:66:77:88
tenancy=ocid1.tenancy.oc1..example
region=ap-singapore-1
key_file=/home/developer/.oci/invoice_dev_api_key.pem
~~~

Đây là ví dụ minh họa; không dùng OCID hoặc fingerprint giả trong môi trường thật. File mặc định thường nằm tại ~/.oci/config trên Linux/macOS hoặc thư mục .oci trong user profile trên Windows.

### 4.1. Cấu hình Spring Boot

Có thể chọn profile và file cụ thể:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: INVOICE_DEV
        file: /run/secrets/oci/config
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

Nếu dùng vị trí mặc định và profile DEFAULT, có thể chỉ cần:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

Không đặt private key content vào application.yaml. Config file nên nằm ngoài source repository và chỉ user/process cần thiết mới được đọc. Trên Linux, giới hạn quyền file theo nguyên tắc least privilege; không để private key có quyền đọc toàn hệ thống.

### 4.2. Tạo config file

OCI CLI có thể hỗ trợ tạo cấu hình tương tác. Một quy trình local phổ biến:

1. Cài OCI CLI theo tài liệu chính thức.
2. Chạy oci setup config hoặc quy trình bootstrap phù hợp.
3. Tạo API signing key.
4. Đăng ký public key với OCI user.
5. Lưu private key ở vị trí được bảo vệ.
6. Chọn region và profile.
7. Kiểm tra cấu hình bằng OCI CLI.
8. Cấu hình Spring Boot dùng cùng file/profile.

OCI CLI thành công giúp kiểm tra profile và key cơ bản, nhưng chưa chứng minh ứng dụng có đúng IAM policy cho operation cụ thể. Cần thử operation của service bằng đúng identity.

### 4.3. Khi nào dùng FILE?

Phù hợp:

- Local development.
- Công cụ quản trị chạy trong môi trường máy cá nhân có bảo vệ credential.
- CI job tạm thời có secret injection và key lifecycle được kiểm soát.
- Môi trường on-premises chưa có federation/workload identity phù hợp.

Không nên dùng API key cá nhân của developer làm identity lâu dài cho production Compute/Functions. Key có thể bị sao chép, hết hạn do rotate hoặc mang quyền rộng hơn service cần.

## 5. SIMPLE và SESSION_TOKEN: các lựa chọn liên quan

Mặc dù trọng tâm bài là FILE, Instance Principal và Resource Principal, Spring Cloud OCI còn hỗ trợ hai lựa chọn thường gặp.

### SIMPLE

SIMPLE đưa các trường credential vào Spring configuration:

~~~properties
spring.cloud.oci.config.type=SIMPLE
spring.cloud.oci.config.userId=INJECT_USER_OCID
spring.cloud.oci.config.tenantId=INJECT_TENANCY_OCID
spring.cloud.oci.config.fingerprint=INJECT_FINGERPRINT
spring.cloud.oci.config.privateKey=/run/secrets/oci/private-key.pem
spring.cloud.oci.config.passPhrase=INJECT_KEY_PASSPHRASE
spring.cloud.oci.config.region=ap-singapore-1
~~~

Các trường userId, tenantId, fingerprint, privateKey và region là bắt buộc theo hướng dẫn core starter; passPhrase là tùy chọn. Không đặt literal private key hoặc passphrase trong repository. SIMPLE vẫn là API key authentication của user, không phải identity gắn với Compute instance hay Function.

### SESSION_TOKEN

SESSION_TOKEN dùng session token tạm thời, thường được tạo từ OCI CLI qua oci session authenticate. Session token mặc định có thời hạn ngắn (thường 60 phút); khi hết hạn cần xác thực lại/refresh theo workflow.

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: SESSION_TOKEN
        profile: DEFAULT
        file: /run/secrets/oci/session-config
~~~

Cách dùng profile/file phải khớp với session config do OCI CLI tạo. SESSION_TOKEN hữu ích cho workflow local tạm thời, nhưng không phải lựa chọn tốt cho một workload server chạy liên tục nếu không có cơ chế gia hạn phù hợp.

## 6. Instance Principal là gì?

Instance Principal cho phép OCI Compute instance gọi OCI API bằng danh tính của chính instance. Ứng dụng không cần chứa OCI user OCID, API key hoặc config file của developer.

Luồng tổng quát:

1. Tạo Compute instance.
2. Tạo dynamic group và quy tắc nhận diện instance.
3. Tạo IAM policy cấp quyền cho dynamic group.
4. Cấu hình Spring Cloud OCI dùng INSTANCE_PRINCIPAL.
5. SDK lấy thông tin xác thực từ instance identity/authentication endpoint.
6. Request được ký bằng credential của instance.

Instance Principal dành cho Compute instance/VM trên OCI. Không chọn nó chỉ vì ứng dụng đang chạy trong bất kỳ container nào; container phải thực sự chạy trong môi trường Compute có hỗ trợ identity đó.

### 6.1. Cấu hình Spring Boot

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

Core starter có thể nhận federation-endpoint tùy chọn cho Instance Principal, Resource Principal hoặc Workload Identity. Thông thường không cần tự đặt endpoint nếu SDK/starter đã xác định đúng endpoint. Chỉ cấu hình khi môi trường hoặc tài liệu release yêu cầu endpoint cụ thể.

### 6.2. Tạo dynamic group

Dynamic group xác định tập OCI resource được xem là principal. Ví dụ chỉ đưa một Compute instance cụ thể vào nhóm:

~~~text
ALL {instance.id = 'ocid1.instance.oc1..example'}
~~~

Hoặc chọn instance theo compartment/tag phù hợp. Tránh đưa toàn bộ instance trong tenancy vào một dynamic group nếu workload chỉ cần quyền nhỏ.

Dynamic group không tự cấp quyền. Nó chỉ xác định membership; IAM policy mới cấp quyền cho nhóm đó.

### 6.3. Cấp IAM policy

Ví dụ ứng dụng chỉ cần đọc object trong một compartment:

~~~text
Allow dynamic-group InvoiceComputeInstances to read buckets in compartment InvoiceData
Allow dynamic-group InvoiceComputeInstances to read objects in compartment InvoiceData
~~~

Nếu ứng dụng cần upload object, policy cần verb/resource type phù hợp với thao tác ghi, ví dụ quyền manage objects trong scope cần thiết. Hãy giới hạn scope theo compartment hoặc điều kiện bucket khi policy grammar và use case cho phép.

Không cấp manage all-resources in tenancy chỉ để test nhanh. Chọn policy theo từng service và từng operation.

### 6.4. Kiểm tra Instance Principal

- Xác minh instance OCID có khớp dynamic group matching rule.
- Xác minh dynamic group đã được tạo đúng tenancy.
- Xác minh policy được tạo trong đúng tenancy/compartment.
- Xác minh region endpoint và network route.
- Kiểm tra Audit log để xác định principal thực tế của request.
- Gọi một operation nhỏ đúng với quyền được cấp.

Nếu thay đổi matching rule hoặc policy, có thể cần chờ IAM propagation/cache trước khi thử lại. Đừng thay credential sang user API key ngay khi gặp 403; trước tiên kiểm tra principal và policy.

## 7. Resource Principal là gì?

Resource Principal cho phép một OCI resource không phải Compute instance xác thực với OCI service khác. Trường hợp điển hình là OCI Functions gọi Object Storage, Vault hoặc một OCI API khác.

OCI runtime cấp token và credential material cho resource. SDK sử dụng các credential này để ký request. Ứng dụng không cần đóng gói API key của developer hoặc tự quản lý một private key cố định.

Resource Principal có thể được dùng bởi những resource được OCI hỗ trợ và cấu hình tương ứng. Không giả định mọi container hoặc mọi workload bên ngoài OCI đều có Resource Principal.

### 7.1. Cấu hình Spring Boot

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

Khi chạy trong OCI Functions, SDK lấy thông tin resource principal từ execution environment do OCI cung cấp. Không tự tạo file RPST hoặc chép token từ function runtime sang image. Không ghi token/private key ra log.

### 7.2. Dynamic group cho OCI Functions

Một dynamic group có thể chọn function theo resource type và compartment. Ví dụ:

~~~text
ALL {
  resource.type = 'fnfunc',
  resource.compartment.id = 'ocid1.compartment.oc1..example'
}
~~~

Matching rule cần khớp resource type/OCID thực tế của môi trường. Có thể giới hạn theo function/application/tag nếu chính sách tổ chức yêu cầu.

### 7.3. IAM policy cho Resource Principal

Ví dụ function cần đọc object:

~~~text
Allow dynamic-group InvoiceFunctions to read buckets in compartment InvoiceData
Allow dynamic-group InvoiceFunctions to read objects in compartment InvoiceData
~~~

Nếu function cần ghi object, dùng policy cho phép thao tác ghi và giới hạn phạm vi phù hợp. Không cấp quyền quản trị function hoặc network chỉ vì function cần đọc Object Storage; quyền triển khai/vận hành function và quyền runtime truy cập dịch vụ là hai nhóm policy khác nhau.

### 7.4. Token và cache

Resource Principal dựa trên token/credential do OCI runtime cấp và SDK quản lý. Token có thời hạn và được cache/refresh theo cơ chế của SDK/runtime. Không tự cache token vô hạn hoặc tự viết cơ chế ký request nếu OCI SDK đã cung cấp provider chuẩn.

Khi thay đổi dynamic group/policy, hiệu lực có thể không xuất hiện tức thì do propagation và token cache. Kiểm tra tài liệu service cụ thể để biết thời gian chờ; không giả định một con số chung cho mọi resource principal.

## 8. Phân biệt FILE, Instance Principal và Resource Principal

| Tiêu chí | FILE | Instance Principal | Resource Principal |
| --- | --- | --- | --- |
| Danh tính | OCI user | OCI Compute instance | OCI resource, ví dụ Function |
| Credential | API signing key trong config profile | Do Compute identity cung cấp | Token/credential do resource runtime cung cấp |
| Config file | Có | Không cần | Không cần |
| IAM grant | User/group policy | Dynamic group + policy | Dynamic group + policy |
| Nơi dùng điển hình | Local development | OCI Compute VM | OCI Functions hoặc resource được hỗ trợ |
| Vòng đời credential | Key do người vận hành quản lý | OCI/SDK quản lý | OCI runtime/SDK quản lý |
| Rủi ro chính | Lộ private key | Dynamic group/policy quá rộng | Policy/resource matching sai, token/runtime issue |

Quy tắc lựa chọn:

- Phát triển trên laptop: FILE hoặc SESSION_TOKEN.
- Chạy trên OCI Compute: ưu tiên Instance Principal.
- Chạy trong OCI Functions: ưu tiên Resource Principal.
- Chạy trên OKE: xem Workload Identity riêng.
- Chạy ngoài OCI: dùng API key/federation được tổ chức phê duyệt, không giả lập Instance Principal.

## 9. OKE Workload Identity không phải Resource Principal

OKE có cơ chế Workload Identity riêng. Nó xác định workload bằng tổ hợp cluster, namespace và Kubernetes service account. IAM policy có thể cấp quyền cho đúng workload đó.

Trong Spring Cloud OCI, cấu hình được hỗ trợ bằng:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
~~~

Cần cấu hình OKE enhanced cluster, namespace, service account và policy tương ứng. Policy workload identity sử dụng điều kiện principal như request.principal.type = 'workload', namespace, service account và cluster OCID.

Điểm khác biệt quan trọng:

- Workload Identity dành cho workload trên OKE.
- Nó chỉ khả dụng với enhanced clusters theo tài liệu OCI.
- Không dùng dynamic group cho OKE workload identity.
- IAM policy ràng buộc trực tiếp cluster, namespace và service account.
- OCI Java SDK phải hỗ trợ workload identity ở version đang dùng.
- Tái sử dụng một provider instance để tận dụng token caching, tránh tạo nhiều provider và fetch token lặp.

Không đổi WORKLOAD_IDENTITY thành RESOURCE_PRINCIPAL chỉ vì cả hai đều sử dụng token do OCI cấp. Chọn đúng provider theo runtime.

## 10. Region và compartment

Authentication có thể thành công nhưng request vẫn đi sai region hoặc nhắm sai compartment.

### Region precedence

Theo Spring Cloud OCI core:

spring.cloud.oci.region.static có độ ưu tiên cao hơn spring.cloud.oci.config.region và region trong OCI auth config file.

Ví dụ:

~~~yaml
spring:
  cloud:
    oci:
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

Đặt region static chỉ khi muốn một region mặc định cho các client. Nếu ứng dụng thao tác nhiều region, cần cấu hình client/operation theo region rõ ràng thay vì dựa vào một default duy nhất.

### Compartment

Compartment là scope quản lý resource và policy. spring.cloud.oci.compartment.static đặt compartment mặc định cho tích hợp có sử dụng property này; nó không tự cấp quyền và cũng không ghi đè mọi compartment ID mà operation/service yêu cầu.

Xác minh ba giá trị:

1. Region nơi resource thực sự tồn tại.
2. Compartment chứa resource.
3. Policy scope cho principal.

## 11. Cấu hình theo môi trường

Tách cấu hình local, test và production để không mang API key cá nhân sang workload.

### Local profile

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
        file: /home/developer/.oci/config
      region:
        static: ap-singapore-1
~~~

### Compute production profile

~~~yaml
spring:
  config:
    activate:
      on-profile: oci-compute
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
~~~

### Functions production profile

~~~yaml
spring:
  config:
    activate:
      on-profile: oci-functions
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
      region:
        static: ap-singapore-1
~~~

Không bật nhiều profile xác thực đồng thời theo cách tạo ra cấu hình mơ hồ. Chọn một identity strategy cho mỗi runtime deployment và xác minh cấu hình cuối cùng sau khi Spring merge profiles/environment variables.

## 12. Quyền tối thiểu theo dịch vụ

Principal nên chỉ được cấp đúng quyền cần cho operation.

| Use case | Quyền tham khảo | Ghi chú |
| --- | --- | --- |
| Liệt kê bucket | read buckets | Giới hạn compartment |
| Đọc object | read objects | Không cần quyền xóa |
| Upload object | manage objects hoặc quyền cụ thể phù hợp | Giới hạn bucket/compartment |
| Đọc secret | Quyền đọc secret bundle phù hợp | Không cấp quản trị Vault nếu không cần |
| Gửi message vào Queue | Quyền sử dụng queue phù hợp | Tách producer identity nếu cần |
| Consume message | Quyền consume/queue operation phù hợp | Xem policy service cụ thể |
| Ghi log | Quyền ghi log vào log group/log | Không cần quyền quản trị toàn bộ Logging |

Các verb và resource type chính xác phụ thuộc OCI service. Kiểm tra IAM policy reference và policy examples của đúng dịch vụ. Một policy quá rộng có thể che mất lỗi cấu hình nhưng làm tăng blast radius khi credential bị lộ.

## 13. Kiểm thử authentication

Kiểm thử cần xác minh cả principal và operation, không chỉ việc application context khởi động.

### Test matrix

| Môi trường | Cách test | Kết quả cần xác minh |
| --- | --- | --- |
| Local FILE | Dùng profile test | Đọc được bucket/object đã cấp quyền |
| Local SESSION_TOKEN | Dùng session token còn hạn | Request thành công trước expiry |
| Compute | Deploy lên instance thuộc dynamic group | Audit nhận diện instance principal |
| Functions | Invoke function trong app đã cấu hình resource principal | Function truy cập đúng service |
| OKE | Pod dùng service account đã cấu hình | Audit nhận diện workload identity |
| IAM negative test | Bỏ quyền một operation | Request bị từ chối đúng cách |

### Ví dụ kiểm thử Spring context

~~~java
@SpringBootTest
class OciAuthenticationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void ociCoreIsConfigured() {
        assertThat(context).isNotNull();
    }
}
~~~

Context test chỉ chứng minh application context khởi động. Nó không chứng minh OCI identity có quyền. Cần integration test gọi một API thật trong test compartment và xác minh Audit log/principal.

### Test least privilege

1. Cấp quyền đọc một bucket test.
2. Kiểm tra operation đọc thành công.
3. Thử ghi hoặc xóa object khi policy không cho phép.
4. Xác minh operation bị từ chối.
5. Mở rộng policy đúng operation cần thiết.
6. Chạy lại test để chứng minh chỉ quyền cần thiết được cấp.

## 14. Chẩn đoán lỗi thường gặp

### 401 NotAuthenticated hoặc lỗi signature

Kiểm tra:

- User OCID, tenancy OCID và fingerprint có khớp public key đã đăng ký không.
- Private key đúng file và đúng passphrase không.
- Config file/profile có được load không.
- Session token có hết hạn không.
- Máy có clock skew lớn không.
- Instance/resource principal provider có chạy trong runtime được hỗ trợ không.
- Region/federation endpoint có đúng không.

Không gửi private key, session token hoặc full signed request vào ticket/log.

### 403 NotAuthorizedOrNotFound

Authentication có thể đã thành công nhưng policy không cho phép operation. Kiểm tra:

- Principal thực tế là user, instance, resource hay workload.
- Dynamic group matching rule có khớp resource không.
- Policy có đúng dynamic group name/domain không.
- Verb/resource type có đủ không.
- Compartment/bucket scope có đúng không.
- Policy propagation/token cache đã có thời gian cập nhật chưa.

Không đổi sang một API key có quyền admin để “xác nhận nhanh”. Điều đó che giấu IAM defect.

### 404 hoặc resource không tìm thấy

Kiểm tra region, compartment, namespace/bucket/queue OCID và endpoint. Một resource ở region khác không thể được tìm thấy bằng client mặc định trỏ sai region.

### Chạy local được nhưng production thất bại

Local FILE profile và production Instance/Resource Principal là hai danh tính khác nhau. So sánh IAM policy, dynamic group membership, runtime, region, compartment và audit principal. Không suy ra production policy từ kết quả local.

### Instance Principal không lấy được credential

- Xác nhận process chạy trên OCI Compute instance.
- Kiểm tra instance metadata/authentication endpoint có truy cập được.
- Kiểm tra dynamic group matching rule.
- Kiểm tra policy.
- Xác minh SDK/starter version.
- Kiểm tra network/proxy không chặn endpoint metadata/federation.

### Resource Principal không hoạt động trong container

- Xác nhận container đang chạy trong OCI Functions hoặc resource runtime được hỗ trợ.
- Xác minh resource principal environment/credential do OCI runtime cấp.
- Kiểm tra dynamic group rule có nhận đúng Function.
- Kiểm tra policy và region.
- Không tự tạo RPST giả hoặc copy credential từ một function khác.

### Workload Identity lỗi trên OKE

- Xác minh cluster là enhanced cluster.
- Kiểm tra namespace và service account trong Pod spec.
- Kiểm tra cluster OCID trong IAM policy.
- Không tạo dynamic group cho workload identity.
- Xác minh OCI Java SDK version hỗ trợ.
- Tái sử dụng một provider để token cache hoạt động đúng.

## 15. Observability và audit

OCI Audit ghi nhận API activity và principal liên quan. Dùng audit để xác định request thực tế được thực hiện bởi identity nào và thời điểm nào.

Ở ứng dụng, ghi log các trường không nhạy cảm:

- Authentication type được chọn.
- Region và compartment ID phù hợp policy log.
- OCI service và operation.
- HTTP status/error code.
- OCI request ID khi có.
- Correlation ID của ứng dụng.

Không ghi:

- Private key hoặc passphrase.
- Session token/RPST.
- Authorization header hoặc request signature.
- Secret value.
- Nội dung payload nhạy cảm.

Có thể tạo metric theo auth type, 401/403, lỗi refresh token, request latency và service operation. Tránh dùng user OCID, request ID hoặc token làm metric label cardinality cao.

## 16. Bài thực hành: Invoice API trên Compute và Function

**Bối cảnh:** Invoice API chạy trên OCI Compute cần đọc file PDF từ Object Storage. Một OCI Function xử lý PDF sau khi nhận event và ghi kết quả về bucket output. Hai workload cần identity riêng và policy riêng.

### Phần A — Local development bằng FILE

1. Tạo OCI CLI config profile dành cho developer.
2. Đăng ký API signing public key.
3. Lưu private key ngoài repository.
4. Cấu hình Spring Cloud OCI dùng FILE và profile tương ứng.
5. Gọi API đọc object trong bucket test.
6. Xác minh policy chỉ cho phép đọc.

### Phần B — Compute bằng Instance Principal

1. Tạo Compute instance cho Invoice API.
2. Tạo dynamic group chỉ nhận instance đó hoặc tag/compartment được chọn.
3. Cấp policy đọc bucket/object cần thiết.
4. Cấu hình INSTANCE_PRINCIPAL.
5. Deploy ứng dụng và đọc PDF.
6. Xác minh Audit log nhận diện instance principal.
7. Thử ghi object khi policy chưa cho phép và xác minh bị từ chối.

### Phần C — Function bằng Resource Principal

1. Tạo OCI Function xử lý PDF.
2. Tạo dynamic group matching Function resource.
3. Cấp quyền đọc input bucket và ghi output bucket.
4. Cấu hình RESOURCE_PRINCIPAL.
5. Deploy function và xử lý một file test.
6. Xác minh không có API key cá nhân trong image/config.
7. Kiểm tra Audit log và output object.

### Phần D — So sánh và vận hành

1. So sánh principal của Compute và Function.
2. Tách policy để Function không có quyền đọc/xóa dữ liệu ngoài phạm vi.
3. Xoay API key local và kiểm tra app production không bị ảnh hưởng.
4. Thu thập 401/403 và request ID.
5. Viết runbook khi dynamic group hoặc policy thay đổi.

### Sản phẩm cần nộp

- Cấu hình FILE cho local.
- Cấu hình Instance Principal cho Compute.
- Cấu hình Resource Principal cho Function.
- Dynamic group matching rules.
- IAM policy matrix theo service/operation.
- Bằng chứng integration test đọc/ghi object.
- Audit evidence xác định đúng principal.
- Bảng lỗi 401/403 và cách xử lý.
- Runbook rotate key và cập nhật policy.

## 17. Câu hỏi tự kiểm tra

1. Authentication và authorization khác nhau ở đâu?
2. FILE profile cần những trường nào để ký request?
3. Vì sao không nên commit OCI private key vào repository?
4. SIMPLE khác FILE như thế nào?
5. SESSION_TOKEN phù hợp với workflow nào?
6. Instance Principal lấy danh tính từ đâu?
7. Dynamic group có tự cấp quyền không?
8. Vì sao Instance Principal cần IAM policy?
9. Resource Principal phù hợp với runtime nào?
10. OCI Function nhận resource principal credential từ đâu?
11. Vì sao không nên chép RPST hoặc private key ra log?
12. OKE Workload Identity khác Resource Principal ở đâu?
13. Workload Identity có dùng dynamic group không?
14. Region static có ưu tiên hơn region trong config file không?
15. Vì sao 403 không nhất thiết là lỗi authentication?
16. Làm sao kiểm tra principal thực tế qua Audit?
17. Làm sao kiểm thử least privilege cho Object Storage?

## 18. Ghi nhớ

- Spring Cloud OCI core starter auto-configures authentication và hạ tầng chung cho service starters.
- FILE là default; profile chứa user, tenancy, fingerprint, key file và region.
- SIMPLE cũng dùng API key của user; không biến nó thành workload identity.
- SESSION_TOKEN dùng credential tạm thời, phù hợp workflow local có refresh.
- Instance Principal dùng danh tính Compute instance; cần dynamic group và IAM policy.
- Resource Principal dùng danh tính resource được OCI hỗ trợ, điển hình là OCI Functions; cần dynamic group và IAM policy.
- OKE Workload Identity là cơ chế riêng, chỉ dùng với enhanced cluster và không dùng dynamic group.
- spring.cloud.oci.region.static ưu tiên hơn region trong auth config file.
- Authentication thành công không đồng nghĩa API được phép; 403 thường cần kiểm tra principal, policy, resource type và compartment.
- Không lưu API key, RPST, session token hoặc private key trong source control hay log.
- Kiểm thử trong runtime thật và dùng OCI Audit để xác minh principal.
- Cấp quyền tối thiểu theo workload, service, operation và compartment.

## Tài liệu tham khảo

- [Spring Cloud OCI 2.0.4 — OCI Core and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [OCI SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)
- [OCI SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
- [Calling Services from Instances](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)
- [Managing Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm)
- [Accessing OCI Resources from Running Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm)
- [Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)
