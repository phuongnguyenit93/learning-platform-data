# Region, endpoint, RAM role và thông tin xác thực STS

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot chạy trên ECS cần truy vấn thông tin instance, đọc/ghi object trong OSS và gọi một số OpenAPI khác của Alibaba Cloud. Ứng dụng phải biết resource nằm ở region nào, kết nối qua endpoint public hay VPC, và xác thực bằng danh tính nào. Nếu cấu hình sai một trong ba phần này, request có thể bị gửi tới sai dịch vụ/region, bị từ chối quyền hoặc thất bại khi STS token hết hạn.

Bốn khái niệm cốt lõi:

- **Region** xác định khu vực cloud nơi resource được tạo và quản lý.
- **Endpoint** là địa chỉ mạng của API sản phẩm mà SDK gửi request tới.
- **RAM role** là danh tính không có AccessKey dài hạn; principal được tin cậy phải assume role để nhận quyền.
- **STS credentials** là bộ thông tin xác thực tạm thời do Security Token Service cấp cho role session.

Bài học thuộc chương **Alibaba Cloud** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure, Google Cloud và Alibaba Cloud qua thư viện tương ứng; người học cần cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa cloud provider.

Sau bài học, bạn có thể:

1. Phân biệt region ID, endpoint, endpoint public/VPC và resource location.
2. Chọn đúng endpoint khi tạo mới, truy vấn hoặc cập nhật resource.
3. Giải thích trust policy và permission policy của RAM role.
4. Mô tả luồng AssumeRole và ba thành phần của STS credentials.
5. Chọn RAM role trên ECS, OIDC/RRSA trên ACK hoặc AssumeRole cho hệ thống bên ngoài.
6. Cấu hình Credentials tool của Alibaba Cloud Java SDK V2 trong Spring Boot.
7. Dùng credential provider có cache/auto-refresh, xử lý token expiry và lỗi endpoint.

## 2. Region và endpoint là hai thông tin khác nhau

### 2.1. Region xác định nơi resource tồn tại

**Region ID** là mã khu vực, ví dụ:

- Singapore: **ap-southeast-1**
- Malaysia (Kuala Lumpur): **ap-southeast-3**
- Indonesia (Jakarta): **ap-southeast-5**
- China (Hangzhou): **cn-hangzhou**

Danh sách region được Alibaba Cloud công bố theo từng sản phẩm và có thể thay đổi. Không phải dịch vụ nào cũng có mặt ở mọi region. Khi tạo database, bucket, instance hoặc queue, resource thường gắn với region được chọn; thao tác đọc/cập nhật/xóa cần gọi đúng region có resource đó.

**Region của ứng dụng** có thể khác region của resource. Ví dụ ứng dụng chạy tại Singapore nhưng cần truy vấn một bucket ở Malaysia. SDK phải gửi request tới endpoint của region bucket; không dùng region của máy chạy ứng dụng để thay thế vị trí resource.

### 2.2. Endpoint xác định API đích

**Endpoint** là domain name mà client kết nối để gọi API của một sản phẩm. Endpoint có thể khác nhau theo:

- Sản phẩm (ECS, OSS, RDS, SMS, SLS...).
- Region mà sản phẩm triển khai.
- Mô hình triển khai tập trung hay theo region.
- Network path: public internet hoặc private/VPC.
- API control plane hay data plane của sản phẩm.

Ví dụ endpoint public của ECS ở Singapore có dạng:

~~~text
ecs.ap-southeast-1.aliyuncs.com
~~~

Ví dụ endpoint OSS public của Singapore có dạng:

~~~text
oss-ap-southeast-1.aliyuncs.com
~~~

Không suy ra endpoint của một sản phẩm bằng cách thay tên sản phẩm vào mẫu của sản phẩm khác. Một số dịch vụ dùng endpoint tập trung không có region trong hostname; một số dùng endpoint riêng cho từng region. Tra cứu endpoint trong tài liệu sản phẩm hoặc OpenAPI Explorer.

### 2.3. Public endpoint và VPC endpoint

| Loại endpoint | Đường kết nối | Khi nào dùng |
| --- | --- | --- |
| **Public endpoint** | Qua internet/public network | Local development, ứng dụng ngoài Alibaba Cloud hoặc workload cần truy cập public API |
| **VPC endpoint** | Qua mạng riêng trong VPC | ECS/ACK và các resource cùng region cần gọi dịch vụ qua private network |
| **Internal endpoint riêng của sản phẩm** | Domain nội bộ theo quy ước sản phẩm | Các dịch vụ như OSS có endpoint internal riêng |
| **Central endpoint** | API được phục vụ từ một hoặc một số region trung tâm | Sản phẩm công bố endpoint tập trung; không tự gắn region vào hostname |

VPC endpoint có thể giảm độ trễ và tránh lưu lượng public, nhưng thường yêu cầu workload ở đúng region/VPC và network policy cho phép. Endpoint VPC của từng sản phẩm có định dạng riêng; tài liệu SDK khuyến nghị chỉ định chính xác endpoint thay vì tự ghép hostname.

**Quy tắc chọn endpoint:**

- Khi **tạo resource mới**, chọn region gần workload/người dùng và đáp ứng yêu cầu dữ liệu, compliance, availability.
- Khi **đọc, cập nhật hoặc xóa resource đã tồn tại**, dùng endpoint của region nơi resource đang nằm.
- Khi ứng dụng chạy trong VPC, kiểm tra endpoint VPC được hỗ trợ và đường DNS/routing.
- Khi chạy từ local hoặc hệ thống ngoài VPC, dùng public endpoint phù hợp.
- Khi endpoint được cấu hình tường minh, kiểm tra cả protocol HTTPS, hostname và region của resource.

### 2.4. Ngoại lệ cần nhớ với OSS

OSS có thêm khái niệm **Dedicated Region ID**. Ví dụ:

| Khái niệm | Ví dụ |
| --- | --- |
| Region ID chung | **ap-southeast-1** |
| Dedicated Region ID của OSS | **oss-ap-southeast-1** |
| OSS public endpoint | **oss-ap-southeast-1.aliyuncs.com** |
| OSS internal endpoint | **oss-ap-southeast-1-internal.aliyuncs.com** |
| Bucket domain | **my-invoice-bucket.oss-ap-southeast-1.aliyuncs.com** |

Một số API/SDK dùng Region ID chung, trong khi endpoint hoặc tham số riêng của OSS dùng dedicated region ID. Đọc đúng trường trong tài liệu SDK thay vì đổi tiền tố một cách máy móc.

Ví dụ OSS Java SDK V2 yêu cầu cấu hình credential và region/endpoint phù hợp với bucket. Nếu dùng SDK V1 với Signature Version 4, cần chỉ định region theo yêu cầu của phiên bản SDK. Bucket tạo ở Hangzhou mà client dùng endpoint Singapore sẽ bị OSS từ chối và yêu cầu gửi lại request tới endpoint đúng.

## 3. RAM user, RAM role và STS

### 3.1. RAM user và RAM role

**RAM (Resource Access Management)** quản lý danh tính và quyền truy cập Alibaba Cloud.

| Đặc điểm | RAM user | RAM role |
| --- | --- | --- |
| Danh tính đại diện | Người dùng hoặc ứng dụng cụ thể | Một tập quyền được principal tin cậy assume |
| AccessKey dài hạn | Có thể có | Không có |
| Cách sử dụng | Gọi API trực tiếp bằng credential của user | Assume role để nhận credential tạm thời |
| Thời hạn credential | Dài hạn cho tới khi xoay vòng/thu hồi | Hết hạn theo role session |
| Trust policy | Không dùng theo mô hình role assumption | Bắt buộc xác định principal được phép assume |
| Use case | Developer local, automation legacy hoặc nguồn credential ban đầu | Workload trên cloud, cross-account, federation và quyền tạm thời |

Không sử dụng AccessKey của Alibaba Cloud root account trong ứng dụng. Nếu cần AccessKey dài hạn cho môi trường phát triển hoặc để assume role, dùng RAM user chuyên biệt, quyền tối thiểu và lưu secret trong secret manager.

RAM role không phải một RAM user khác tên. Role không có password hay AccessKey riêng; STS cấp bộ credential tạm thời khi principal assume role thành công.

### 3.2. Hai policy có vai trò khác nhau

Khi cấu hình RAM role, cần phân biệt:

1. **Trust policy** (resource-based policy gắn với role): xác định ai được phép assume role.
2. **Access/permission policy** (identity-based policy gắn với role): xác định role được phép làm gì sau khi assume.

Ví dụ: role tên **InvoiceUploaderRole** có thể chỉ cho phép một ECS service hoặc một workload ACK được assume. Sau khi assume, role chỉ được upload object vào bucket/prefix hóa đơn. Trust policy không tự cấp quyền upload; access policy không tự cho phép một principal bất kỳ assume role.

Với AssumeRole thông thường, cả hai điều kiện phải đúng:

- Principal gọi STS có quyền identity-based cho phép hành động **sts:AssumeRole** trên role đích.
- Trust policy của role đích cho phép principal đó trong phần **Principal**, **Action** và **Condition** tương ứng.

Nếu thiếu một trong hai, STS từ chối. Với federation qua **AssumeRoleWithOIDC** hoặc **AssumeRoleWithSAML**, cần cấu hình IdP và trust policy phù hợp với giao thức; không áp dụng máy móc quyền AssumeRole của RAM user.

### 3.3. Trust policy mẫu cho truy cập liên tài khoản

Giả sử account A sở hữu role đích; account B có một RAM role CI/CD cần truy cập tạm thời. Trust policy của role ở account A có thể tin cậy đúng role từ account B:

~~~json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Principal": {
        "RAM": [
          "acs:ram::111122223333:role/ci-deployer"
        ]
      }
    }
  ]
}
~~~

Đây là ví dụ minh họa. Thay account ID và role ARN bằng giá trị thật; thêm điều kiện phù hợp với yêu cầu bảo mật. Tránh dùng principal quá rộng như toàn bộ account nếu không cần. Với bên thứ ba, cân nhắc **ExternalId** để giảm rủi ro confused deputy.

Role ở account A cần có access policy riêng, ví dụ chỉ cho phép đọc object của bucket báo cáo. Principal ở account B cũng cần quyền assume role theo chính sách của mình. Cả hai phía đều phải được kiểm tra.

### 3.4. Session policy và RoleSessionName

Khi gọi AssumeRole, có thể truyền **session policy** để thu hẹp quyền của phiên hiện tại. Quyền hiệu lực là giao của permission policies gắn với role và session policy; session policy không thể mở rộng quyền role.

**RoleSessionName** là tên của phiên assume role và xuất hiện trong ActionTrail, giúp truy vết ai hoặc workload nào thực hiện hành động. Nên dùng tên dễ nhận diện, ví dụ **order-api-prod** hoặc **invoice-worker-2026-11**; không đưa secret hay dữ liệu cá nhân vào tên session.

## 4. STS hoạt động như thế nào?

### 4.1. Luồng AssumeRole

~~~mermaid
sequenceDiagram
    participant App as Spring Boot workload
    participant RAM as RAM
    participant STS as Security Token Service
    participant OSS as OSS API

    App->>STS: AssumeRole / AssumeRoleWithOIDC
    STS->>RAM: Kiểm tra caller và trust policy
    RAM-->>STS: Cho phép nếu đủ điều kiện
    STS-->>App: Temporary credentials + Expiration
    App->>OSS: Signed API request + SecurityToken
    OSS->>RAM: Đánh giá permission của role
    RAM-->>OSS: Allow / Deny
    OSS-->>App: API response
~~~

1. Ứng dụng có một danh tính nguồn (RAM user, RAM role, ECS instance role hoặc OIDC identity).
2. Ứng dụng gọi STS để assume role.
3. RAM xác minh principal có được tin cậy và được phép assume role hay không.
4. STS trả về temporary credentials.
5. Ứng dụng dùng credentials này để ký request tới OSS, ECS hoặc dịch vụ khác.
6. Khi credential hết hạn, provider lấy phiên mới theo cơ chế refresh được hỗ trợ.

### 4.2. STS credentials gồm những gì?

Một bộ STS credentials có ba thành phần:

- **AccessKeyId**: ID của AccessKey tạm thời.
- **AccessKeySecret**: secret tương ứng để ký request.
- **SecurityToken**: token chứng minh credential được STS cấp cho role session.

Ngoài ra, response có **Expiration** để biết thời điểm credential hết hạn. Khi dùng STS, phải truyền cả ba thành phần theo yêu cầu SDK. Chỉ có AccessKeyId và AccessKeySecret mà thiếu SecurityToken sẽ khiến request bị từ chối.

### 4.3. Thời hạn phiên

Theo tài liệu RAM/STS hiện hành:

- Thời hạn mặc định của AssumeRole API là **3.600 giây (1 giờ)**.
- Thời hạn yêu cầu có thể từ **900 giây (15 phút)** đến maximum session duration của role.
- Maximum session duration của role có thể cấu hình trong khoảng **1–12 giờ**.
- Thời hạn thực tế không thể vượt maximum session duration được cấu hình trên role.

Chọn thời hạn ngắn nhất đáp ứng công việc. Với tác vụ upload ngắn, phiên ngắn giảm thời gian credential bị lạm dụng nếu rò rỉ. Với workload chạy liên tục, dùng credential provider có cache và auto-refresh thay vì tự tạo token quá thường xuyên.

### 4.4. STS token không tự động refresh trong mọi trường hợp

Credential dạng STS tĩnh được truyền vào ứng dụng có thời hạn. Khi hết hạn, ứng dụng phải nhận credential mới từ nguồn cấp. Các provider như **ram_role_arn**, **ecs_ram_role**, **oidc_role_arn** và **credentials_uri** trong Alibaba Cloud Credentials tool hỗ trợ cache và tự refresh. Dùng một client/provider singleton để tái sử dụng cache.

Không gọi AssumeRole cho từng HTTP request của ứng dụng. Cách đó làm tăng độ trễ, tải lên STS và nguy cơ throttling.

## 5. Chọn cơ chế credentials theo môi trường

| Môi trường | Cơ chế phù hợp | Ghi chú |
| --- | --- | --- |
| Developer workstation | Alibaba Cloud CLI profile hoặc RAM user test qua environment variables | Dùng account test và permission tối thiểu |
| ECS | Instance RAM role | SDK lấy STS credential qua metadata; không nhúng AccessKey vào image |
| ECI | RAM role gắn với instance/container theo tính năng hỗ trợ | Dùng credential provider phù hợp |
| ACK | RRSA/OIDC RAM role cho Kubernetes ServiceAccount | Role được assume bằng OIDC token file |
| CI/CD ngoài Alibaba Cloud | OIDC federation hoặc RAM role qua STS | Ưu tiên federation; ExternalId khi tích hợp bên thứ ba |
| Mobile/browser client | STS credential giới hạn quyền hoặc signed URL | Không phát AccessKey dài hạn xuống client |
| Legacy external application | RAM user AccessKey được quản lý trong secret manager, dùng để assume role | Có kế hoạch rotate và migrate sang federation |

### 5.1. ECS instance RAM role

Khi workload chạy trên ECS:

1. Tạo RAM role có trust principal là ECS service theo hướng dẫn sản phẩm.
2. Gắn access policy chỉ cho phép API cần thiết, ví dụ đọc metadata hoặc ghi vào bucket cụ thể.
3. Attach role vào ECS instance.
4. Khởi tạo Credentials tool theo default chain hoặc loại **ecs_ram_role**.
5. SDK lấy credential tạm thời từ Instance Metadata Service (IMDS) và tự refresh.

Một ECS instance chỉ gắn được một instance RAM role tại một thời điểm. Nếu ứng dụng cần thêm quyền, điều chỉnh policy gắn với role đó theo least privilege thay vì tạo nhiều AccessKey trong máy.

Alibaba Cloud Credentials tool dùng metadata ở chế độ bảo mật **IMDSv2**. Với Java Credentials tool, chế độ bảo mật cần phiên bản **credentials-java 0.3.10 trở lên**. Có thể đặt **ALIBABA_CLOUD_ECS_METADATA** để chỉ rõ role name và giảm một lần truy vấn metadata. Khi muốn bắt buộc chế độ bảo mật, cấu hình **ALIBABA_CLOUD_IMDSV1_DISABLED=true** theo tài liệu SDK; nếu metadata không truy cập được, ứng dụng phải báo lỗi thay vì âm thầm chuyển sang credential tĩnh.

### 5.2. ACK RRSA/OIDC

Với ứng dụng chạy trong Kubernetes ACK, **RRSA (RAM Roles for Service Accounts)** cho phép gắn danh tính OIDC với Kubernetes ServiceAccount. Luồng xử lý:

1. Bật RRSA/OIDC cho cluster và có OIDC provider trong RAM.
2. Tạo RAM role tin cậy OIDC provider.
3. Giới hạn trust condition theo issuer, audience và subject/ServiceAccount phù hợp.
4. Gắn role ARN vào cấu hình ServiceAccount theo hướng dẫn ACK.
5. Credentials tool đọc OIDC token file và gọi **AssumeRoleWithOIDC**.
6. SDK dùng STS credential và tự refresh.

Default credential chain của Java Credentials tool nhận các biến:

~~~text
ALIBABA_CLOUD_ROLE_ARN
ALIBABA_CLOUD_OIDC_PROVIDER_ARN
ALIBABA_CLOUD_OIDC_TOKEN_FILE
~~~

Không dùng token file của pod khác hoặc chia sẻ ServiceAccount có quyền rộng cho nhiều workload. Một service account nên có đúng phạm vi quyền cần thiết.

### 5.3. Hệ thống bên ngoài Alibaba Cloud

Nếu ứng dụng chạy ở cloud khác hoặc data center riêng, có thể dùng OIDC federation nếu nền tảng cấp identity token tương thích. Nếu chưa có federation, một RAM user chuyên biệt có thể dùng AccessKey để gọi AssumeRole; credential nguồn chỉ có quyền assume đúng role đích.

Với tích hợp bên thứ ba, sử dụng **ExternalId** do bên thứ ba tạo và giới hạn principal/trust policy. Không chia sẻ AccessKey của account owner. Khi workload có thể dùng OIDC, ưu tiên OIDC để tránh lưu secret dài hạn.

## 6. Alibaba Cloud Java SDK Credentials tool

### 6.1. Cài dependency

Ví dụ Maven cho Java SDK V2 của ECS và Credentials tool:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>${credentialsVersion}</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>ecs20140526</artifactId>
        <version>${ecsSdkVersion}</version>
    </dependency>
</dependencies>
~~~

Chọn version hiện hành từ Maven Repository hoặc SDK Center cho từng artifact; không lấy version của SDK ECS để điền cho Credentials tool. Nếu chỉ dùng credentials-java độc lập mà không có product SDK kéo theo Tea dependency, thêm package **com.aliyun:tea** theo tài liệu Credentials tool.

SDK V2 dùng package theo tên sản phẩm/API version, ví dụ **com.aliyun:ecs20140526**. SDK V1 dùng artifact và package khác; không trộn ví dụ cấu hình hoặc class giữa V1 và V2.

### 6.2. Default credential chain

Nếu khởi tạo Credentials tool mà không truyền Config, nó tìm credential theo chuỗi mặc định. Tài liệu Java Credentials tool hiện hành mô tả thứ tự:

1. Java system properties.
2. Environment variables chứa AccessKey hoặc STS token.
3. OIDC RAM role qua biến môi trường.
4. Shared credentials file tại đường dẫn mặc định, ví dụ **~/.aliyun/config.json**.
5. ECS instance RAM role qua metadata.
6. Credentials URI.

Tên biến môi trường quan trọng:

| Biến | Ý nghĩa |
| --- | --- |
| **ALIBABA_CLOUD_ACCESS_KEY_ID** | AccessKey ID của RAM user hoặc STS session |
| **ALIBABA_CLOUD_ACCESS_KEY_SECRET** | AccessKey secret |
| **ALIBABA_CLOUD_SECURITY_TOKEN** | SecurityToken khi dùng STS |
| **ALIBABA_CLOUD_ROLE_ARN** | RAM role ARN |
| **ALIBABA_CLOUD_OIDC_PROVIDER_ARN** | OIDC provider ARN |
| **ALIBABA_CLOUD_OIDC_TOKEN_FILE** | Đường dẫn file chứa OIDC token |
| **ALIBABA_CLOUD_ECS_METADATA** | Role name trên ECS, nếu muốn chỉ định rõ |
| **ALIBABA_CLOUD_CREDENTIALS_URI** | URI cấp temporary credentials |

**Lưu ý về thứ tự:** nếu máy/container còn đặt ALIBABA_CLOUD_ACCESS_KEY_ID và ALIBABA_CLOUD_ACCESS_KEY_SECRET, SDK sẽ tìm thấy credential tĩnh trước OIDC hoặc ECS role. Điều này có thể khiến ứng dụng dùng nhầm RAM user thay vì role dự định. Xóa biến môi trường cũ khỏi production khi muốn dùng workload identity.

### 6.3. Tạo credential client và product client singleton

Ví dụ Spring Boot cấu hình một Credentials client theo default chain, rồi truyền provider vào ECS Java SDK V2:

~~~java
package demo.cloud;

import com.aliyun.credentials.Client;
import com.aliyun.teaopenapi.models.Config;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AlibabaCloudClientConfiguration {

    @Bean
    public Client alibabaCredentialsClient() throws Exception {
        // Lấy credential từ default chain: OIDC, ECS role,
        // shared profile hoặc nguồn được cấu hình cho môi trường.
        return new Client();
    }

    @Bean
    public com.aliyun.ecs20140526.Client ecsClient(
            Client credentialsClient,
            @Value("${aliyun.ecs.endpoint}") String endpoint) throws Exception {

        Config config = new Config();
        config.setCredential(credentialsClient);
        config.setEndpoint(endpoint);

        return new com.aliyun.ecs20140526.Client(config);
    }
}
~~~

Tạo client một lần trong Spring context để sử dụng lại connection và credential cache. Không khởi tạo Credentials client hoặc product client mới cho mỗi request. Product SDK client có thể được tái sử dụng; theo dõi lifecycle/đóng tài nguyên theo hướng dẫn của SDK cụ thể.

### 6.4. Cấu hình application.yml

~~~yaml
aliyun:
  region-id: ${ALIBABA_CLOUD_REGION_ID:ap-southeast-1}
  ecs:
    endpoint: ${ALIBABA_CLOUD_ECS_ENDPOINT:ecs.ap-southeast-1.aliyuncs.com}
~~~

Ví dụ trên dùng ECS public endpoint của Singapore. Khi workload chạy trong VPC, hãy thay bằng VPC endpoint chính thức của ECS region đó nếu được hỗ trợ. Không dùng endpoint OSS cho ECS hoặc ngược lại.

Trong code gọi API, region của resource vẫn có thể là một request parameter. Ví dụ truy vấn ECS instance ở Singapore:

~~~java
import com.aliyun.ecs20140526.models.DescribeInstancesRequest;
import com.aliyun.ecs20140526.models.DescribeInstancesResponse;
import com.aliyun.teautil.models.RuntimeOptions;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class EcsQueryService {
    private final com.aliyun.ecs20140526.Client ecsClient;
    private final String regionId;

    public EcsQueryService(
            com.aliyun.ecs20140526.Client ecsClient,
            @Value("${aliyun.region-id}") String regionId) {
        this.ecsClient = ecsClient;
        this.regionId = regionId;
    }

    public DescribeInstancesResponse describeInstances() throws Exception {
        DescribeInstancesRequest request =
                new DescribeInstancesRequest().setRegionId(regionId);

        return ecsClient.describeInstancesWithOptions(
                request, new RuntimeOptions());
    }
}
~~~

IAM/RAM role của workload cần quyền đọc ECS instance, ví dụ policy read-only phù hợp hoặc custom policy giới hạn API/resource cần thiết. Nếu chỉ gọi DescribeInstances, không cấp quyền tạo/xóa instance.

### 6.5. Cấu hình provider tường minh khi cần

Nếu không muốn dùng default chain, Credentials tool hỗ trợ loại provider như **ram_role_arn**, **ecs_ram_role**, **oidc_role_arn** và **credentials_uri**. Ví dụ với ACK OIDC:

~~~java
import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;

Config credentialConfig = new Config();
credentialConfig.setType("oidc_role_arn");
credentialConfig.setRoleArn(System.getenv("ALIBABA_CLOUD_ROLE_ARN"));
credentialConfig.setOidcProviderArn(
        System.getenv("ALIBABA_CLOUD_OIDC_PROVIDER_ARN"));
credentialConfig.setOidcTokenFilePath(
        System.getenv("ALIBABA_CLOUD_OIDC_TOKEN_FILE"));

Client credentialClient = new Client(credentialConfig);
~~~

Đoạn code này minh họa cách cấu hình provider. Trong Spring Boot, đặt nó trong một @Bean singleton. Provider OIDC có thể tự gọi AssumeRoleWithOIDC và tự refresh STS credentials. Không in token file hoặc giá trị credential ra log.

## 7. AssumeRole thủ công và khi nào cần dùng

### 7.1. Luồng RAM user AccessKey → RAM role

Với một hệ thống ngoài Alibaba Cloud chưa hỗ trợ OIDC, Credentials tool có thể dùng AccessKey của RAM user làm credential nguồn, sau đó assume role:

~~~java
import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;

Config credentialConfig = new Config();
credentialConfig.setType("ram_role_arn");
credentialConfig.setAccessKeyId(System.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID"));
credentialConfig.setAccessKeySecret(System.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET"));
credentialConfig.setRoleArn(System.getenv("ALIBABA_CLOUD_ROLE_ARN"));
credentialConfig.setRoleSessionName("invoice-worker");
credentialConfig.setRoleSessionExpiration(3600);

Client credentialClient = new Client(credentialConfig);
~~~

Credential nguồn cần quyền **sts:AssumeRole** và role đích phải tin cậy principal đó. Credentials tool sẽ gọi STS và cache/refresh credential role theo cơ chế được hỗ trợ. Nếu môi trường đã có ECS role hoặc OIDC, không cần tạo AccessKey nguồn chỉ để dùng đoạn code này.

### 7.2. Khi nào dùng STS token trực tiếp?

Có thể cấp STS credential ngắn hạn cho client di động/trình duyệt để upload trực tiếp lên OSS, hoặc cho một tác vụ tạm thời. Phải giới hạn:

- Role chỉ có quyền với bucket/prefix cần thiết.
- Session policy thu hẹp quyền theo phiên nếu phù hợp.
- Thời hạn ngắn theo tác vụ.
- Token không được lưu trong local storage/log hoặc gửi qua kênh không bảo mật.
- Client không được quyền gọi các API quản trị ngoài nhu cầu.

Với file upload/download, signed URL có thể đơn giản hơn nếu chỉ cần cho phép một thao tác cụ thể. Nếu dùng STS, backend cần quản lý việc cấp token và tránh phát token có quyền rộng.

### 7.3. Tránh dùng STS tĩnh trong ứng dụng chạy lâu

Provider kiểu **sts** nhận AccessKeyId, AccessKeySecret và SecurityToken có sẵn. Nếu token hết hạn, ứng dụng phải có logic lấy token mới và cập nhật client. Đừng khởi tạo một static STS credential lúc startup rồi để service chạy vô thời hạn.

Ưu tiên provider tự refresh như RAM role ARN, ECS RAM role, OIDC role ARN hoặc Credentials URI. Các provider này dùng cache và tự làm mới khi token hết hạn; ECS role provider còn chủ động refresh trước thời điểm hết hạn.

## 8. Bảo mật và vận hành

### 8.1. Least privilege

- Tạo một role cho mỗi workload hoặc nhóm workload có cùng trách nhiệm.
- Chỉ cấp action cần thiết và resource ARN/prefix cụ thể.
- Tách role đọc, ghi, quản trị và triển khai nếu trách nhiệm khác nhau.
- Thu hẹp trust policy theo account, role, service hoặc OIDC subject cần thiết.
- Dùng session policy để giảm thêm quyền trong một lần assume nếu cần.
- Ghi RoleSessionName có ý nghĩa để truy vết ActionTrail.

### 8.2. Bảo vệ credential và metadata

- Không hardcode AccessKey/STS token trong source, Docker image, YAML commit hoặc log.
- Không dùng root AccessKey.
- Dùng RAM role/STS ngắn hạn cho workload trên Alibaba Cloud.
- Bảo vệ IMDS khỏi SSRF và hạn chế quyền truy cập metadata từ process không tin cậy.
- Với ECS, ưu tiên IMDSv2/security-hardened mode theo tài liệu Credentials tool.
- Với ACK, không mount OIDC token của ServiceAccount sang container không cần quyền.
- Nếu AccessKey dài hạn bị lộ, disable/rotate ngay, kiểm tra ActionTrail và đánh giá các resource có thể bị truy cập.

### 8.3. Không log dữ liệu xác thực

Có thể log các thông tin phục vụ điều tra như:

- Region ID và loại endpoint (public/VPC), không cần log token.
- Role ARN hoặc tên role đã được phê duyệt để log.
- Request ID, service code và error code.
- Thời điểm request, latency, retry count.
- Tên profile/provider đang dùng, nhưng không ghi AccessKey ID/secret hoặc SecurityToken đầy đủ.

Không log toàn bộ object request/response nếu có dữ liệu cá nhân, nội dung bí mật hoặc token.

## 9. Kiểm thử cấu hình region, endpoint và STS

### 9.1. Ma trận kiểm thử

| Test | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| Region đúng | Resource và API request cùng region | API tìm thấy resource |
| Endpoint đúng | Endpoint thuộc dịch vụ và region của resource | Request kết nối và được xử lý |
| Endpoint public | Workload có đường internet phù hợp | Kết nối được API |
| Endpoint VPC | Workload cùng region/VPC và DNS/routing đúng | Request đi qua private network |
| Endpoint sai region | Dùng endpoint region khác resource | Có thể lỗi endpoint/resource location hoặc không tìm thấy resource |
| RAM role thiếu permission | Role không có action API cần gọi | Bị AccessDenied |
| Trust policy sai | Principal không nằm trong trust policy | AssumeRole bị từ chối |
| Caller thiếu sts:AssumeRole | Source identity không có quyền assume | STS từ chối trước khi cấp token |
| STS hết hạn | Dùng token tĩnh quá expiration | Request bị từ chối; provider auto-refresh cần cấp phiên mới |
| OIDC subject sai | Token không khớp condition của trust policy | AssumeRoleWithOIDC thất bại |
| Biến AK còn sót | Env AK được đặt cùng OIDC/ECS role | Default chain có thể chọn AK trước role |

### 9.2. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **InvalidEndpoint / 404** | Endpoint sai sản phẩm, sai region hoặc sai network path | Tra cứu endpoint trong tài liệu sản phẩm/OpenAPI Explorer |
| **The bucket must be addressed using the specified endpoint** | OSS client gửi tới endpoint không khớp region bucket | Dùng endpoint của bucket location |
| **AccessDenied** khi gọi API | Role thiếu action/resource permission hoặc policy condition không khớp | Kiểm tra principal runtime và access policy |
| **AssumeRole bị từ chối** | Caller thiếu sts:AssumeRole hoặc trust policy không tin caller | Kiểm tra cả hai policy ở nguồn và role đích |
| **InvalidAccessKeyId** | AccessKey sai, bị disable hoặc SDK chọn credential ngoài ý muốn | Kiểm tra credential source và trạng thái RAM user |
| **InvalidSecurityToken / token expired** | Thiếu SecurityToken hoặc token đã hết hạn | Dùng cả ba STS fields và bật provider auto-refresh |
| **SignatureDoesNotMatch** | Secret sai, endpoint/region/signature config không khớp hoặc clock skew | Kiểm tra credentials, endpoint, region và đồng hồ hệ thống |
| **OIDC AssumeRoleWithOIDC fail** | Provider ARN, role ARN, token file, issuer/audience/subject hoặc trust condition sai | Kiểm tra RRSA, ServiceAccount và trust policy |
| **ECS metadata timeout** | Chưa attach role, metadata bị chặn hoặc chế độ bảo mật không tương thích | Kiểm tra instance role, IMDS và credentials-java version |
| **Credential provider không refresh** | Dùng STS static credential hoặc tạo provider mới liên tục | Dùng auto-refresh provider singleton |

### 9.3. Runbook điều tra theo thứ tự

1. Xác định ứng dụng đang gọi dịch vụ nào và resource nằm ở region nào.
2. Kiểm tra endpoint có đúng product/region/network không.
3. Xác định credential provider thực tế đang được chọn; chú ý environment variables có ưu tiên cao.
4. Kiểm tra principal/role ARN hiện tại mà không log secret.
5. Nếu assume role, kiểm tra quyền sts:AssumeRole của caller và trust policy của role đích.
6. Kiểm tra access policy của role đối với action/resource API.
7. Kiểm tra STS Expiration và auto-refresh provider.
8. Ghi RequestId/ErrorCode và tra cứu log/audit tương ứng.

Không sửa bằng cách cấp quyền Administrator hoặc thay endpoint ngẫu nhiên. Hãy tìm đúng lớp lỗi: network, endpoint, identity, trust, permission hay expiration.

## 10. Bài tập thực hành

**Bài tập:** triển khai một Spring Boot service trên ECS để đọc metadata ECS và upload hóa đơn lên OSS bằng RAM role và STS.

1. Chọn region test, tạo bucket OSS và một ECS instance trong region phù hợp.
2. Tạo RAM role cho ECS; trust policy cho phép ECS service assume role.
3. Gắn access policy giới hạn quyền upload object vào bucket/prefix test.
4. Attach role vào ECS instance; không cấu hình AccessKey tĩnh trong environment.
5. Cấu hình endpoint ECS và OSS đúng region/network.
6. Thêm Alibaba Cloud Credentials tool và SDK V2 product dependencies.
7. Tạo singleton credential client và singleton product client trong Spring context.
8. Gọi một API read-only của ECS để kiểm tra identity và endpoint.
9. Upload file test lên OSS và xác nhận object được tạo.
10. Thử bỏ quyền upload, đổi endpoint sai và chờ credential hết hạn để quan sát lỗi/auto-refresh.
11. Nếu triển khai trên ACK, lặp lại bằng RRSA/OIDC và so sánh trust policy.

**Câu hỏi ôn tập:**

1. Region ID và endpoint khác nhau thế nào?
2. Vì sao endpoint của OSS có quy ước khác endpoint ECS?
3. Khi nào nên dùng public endpoint và khi nào dùng VPC endpoint?
4. RAM role khác RAM user ở credential lifecycle ra sao?
5. Trust policy và access policy có nhiệm vụ gì?
6. Vì sao AssumeRole cần kiểm tra quyền của caller và trust policy của role đích?
7. STS credential gồm những trường nào và vì sao SecurityToken bắt buộc?
8. Thời hạn mặc định của STS token là bao lâu? Giới hạn tối thiểu và tối đa phụ thuộc điều gì?
9. Vì sao ECS/ACK workload nên dùng RAM role hoặc OIDC thay vì AccessKey tĩnh?
10. Default credential chain có thể chọn nhầm AccessKey tĩnh trong trường hợp nào?
11. Vì sao cần singleton Credentials client và provider có auto-refresh?
12. Khi nhận SignatureDoesNotMatch hoặc AccessDenied, cần kiểm tra lớp nào trước?

## 11. Tài liệu tham khảo

- [Alibaba Cloud SDK — Manage credentials (Java V2)](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): credential types, default chain, ECS role, OIDC và auto-refresh.
- [RAM — RAM role overview](https://www.alibabacloud.com/help/en/ram/user-guide/ram-role-overview): principal, trust policy, role session và permission policies.
- [RAM — Assume a RAM role](https://www.alibabacloud.com/help/en/ram/user-guide/assume-a-ram-role): AssumeRole, caller permission, trust policy và session duration.
- [STS overview](https://www.alibabacloud.com/help/en/ram/user-guide/what-is-sts): temporary credentials, role assumption và session policy.
- [Alibaba Cloud SDK — Configure endpoints](https://www.alibabacloud.com/help/en/sdk/developer-reference/endpoint-configuration): endpoint public/VPC và cách cấu hình Java SDK V2.
- [OpenAPI — Endpoint types](https://www.alibabacloud.com/help/en/openapi/endpoints): endpoint tập trung, regional và VPC.
- [OSS — Regions and endpoints](https://www.alibabacloud.com/help/en/oss/user-guide/regions-and-endpoints): region IDs, public/internal endpoints và network path.
- [OSS — Access OSS via endpoints and bucket domains](https://www.alibabacloud.com/help/en/oss/user-guide/access-oss-via-bucket-domain-name): Region ID, Dedicated Region ID, endpoint và bucket domain.
- [ECS — Attach an instance RAM role](https://www.alibabacloud.com/help/en/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance): RAM role, metadata và STS credentials.
- [ECS — Java SDK V2 examples](https://www.alibabacloud.com/help/en/ecs/developer-reference/use-sdk-for-java): Maven dependency, client initialization và DescribeInstances sample.

**Kết quả mong đợi:** người học cấu hình đúng region và endpoint theo resource, hiểu RAM role/trust policy/access policy, dùng STS credentials ngắn hạn và tự refresh, đồng thời tích hợp an toàn với Spring Boot trên local, ECS, ACK hoặc môi trường ngoài Alibaba Cloud.
