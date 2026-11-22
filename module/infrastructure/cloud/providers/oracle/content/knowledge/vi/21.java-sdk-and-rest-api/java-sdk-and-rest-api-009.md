# Idempotency tokens, ETags và kiểm soát cập nhật đồng thời

## 1. Hai rủi ro trong ứng dụng tự động hóa OCI

Trong chương **OCI SDK và REST API với Java**, gọi API đúng cú pháp mới giải quyết một phần công việc. Một ứng dụng tự động hóa hạ tầng Oracle Cloud Infrastructure (OCI) còn phải xử lý hai tình huống phổ biến:

1. **Không biết thao tác trước đã thành công chưa.** Ứng dụng gửi yêu cầu tạo tài nguyên, dịch vụ đã thực hiện nhưng phản hồi bị mất. Nếu tạo lại như một thao tác mới, ứng dụng có thể tạo tài nguyên trùng và phát sinh chi phí ngoài dự kiến.
2. **Dữ liệu dùng để cập nhật đã cũ.** Hai worker cùng đọc cấu hình, mỗi worker sửa một phần rồi gửi bản cập nhật. Nếu không kiểm tra phiên bản, người ghi sau có thể làm mất thay đổi của người ghi trước.

Trong các API OCI có hỗ trợ, `opc-retry-token` giúp nhận diện một thao tác được gửi lại, còn ETag kết hợp `If-Match` giúp kiểm tra điều kiện phiên bản trước cập nhật hoặc xóa. Hai cơ chế này giải quyết hai vấn đề khác nhau và có thể cùng xuất hiện trong một quy trình tự động hóa. [Nguồn: OCI REST APIs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

Sau bài học, bạn có thể:

- Phân biệt retry token, ETag, request ID và mã thao tác nghiệp vụ.
- Lưu và tái sử dụng token cho cùng một ý định tạo tài nguyên.
- Dùng Java SDK đọc ETag và gửi cập nhật có điều kiện.
- Phân loại xung đột cần tính lại với lỗi tạm thời có thể retry.
- Phục hồi sau timeout mà không mặc định thao tác đã thất bại.
- Kết hợp các cơ chế này với IAM, giám sát và quản lý trạng thái của ứng dụng.

Ví dụ xuyên suốt là một dịch vụ Java quản lý VCN cho các môi trường học tập. Dịch vụ có thể chạy trên Compute hoặc OKE, lưu trạng thái công việc trong Oracle Database/Autonomous Database và cập nhật free-form tags của VCN. Nội dung tập trung vào tính đúng đắn của các lời gọi API; không yêu cầu triển khai một hệ thống orchestration hoàn chỉnh.

## 2. Phân biệt bốn loại giá trị nhận diện

| Giá trị | Nhận diện điều gì? | Cách sử dụng |
| --- | --- | --- |
| Mã thao tác nghiệp vụ, ví dụ `operationId` | Ý định của ứng dụng như tạo môi trường cho yêu cầu số 1042 | Khóa của sổ công việc bền vững do ứng dụng thiết kế |
| `opc-retry-token` | Một thao tác API được gửi lại trong phạm vi hỗ trợ của dịch vụ | Giữ nguyên khi retry cùng thao tác, không tái dùng cho ý định khác |
| ETag | Phiên bản/representation của một tài nguyên do dịch vụ trả về | Gửi lại nguyên giá trị qua `If-Match` khi thực hiện cập nhật có điều kiện |
| `opc-request-id` | Một request để truy vết và hỗ trợ điều tra | Ghi log cùng operation ID và thông tin kết quả |

Ví dụ, công việc `provision-env-1042` có thể cần ba thao tác tạo VCN, subnet và instance. Ứng dụng giữ một operation ID cho công việc tổng thể, nhưng mỗi thao tác API cần danh tính retry riêng nếu API đó hỗ trợ token. Không dùng một token chung cho cả ba thao tác chỉ vì chúng cùng phục vụ một môi trường.

Request ID cũng không thay thế retry token. Hai lần gửi lại có thể có request ID khác nhau nhưng vẫn thuộc cùng thao tác nghiệp vụ. ETag không phải thông tin xác thực, còn retry token không cấp quyền bỏ qua IAM.

## 3. Retry token: gửi lại cùng một thao tác

### 3.1. Tình huống phản hồi bị mất

Giả sử worker gửi yêu cầu tạo VCN với token `T1`:

```text
Worker                         OCI
  |                             |
  | CreateVcn, token=T1          |
  |---------------------------->|
  |                             | Tạo VCN R1
  |       phản hồi bị mất        |
  |<-------------X--------------|
  |                             |
  | CreateVcn, token=T1          | Retry cùng thao tác
  |---------------------------->|
```

Mục đích của token là cho dịch vụ nhận ra request sau thuộc thao tác đã gửi trước, thay vì thực hiện lại tác dụng tạo tài nguyên như một ý định độc lập. `CreateVcnRequest` trong Java SDK có trường `opcRetryToken` cho mục đích này. [Nguồn: CreateVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/CreateVcnRequest.Builder.html).

Điểm cần kiểm soát nằm ở cách ứng dụng tạo token:

```text
Đúng:
    tạo token một lần cho operation
    lưu bền vững operation và payload
    mọi lần gửi lại lấy token đã lưu

Sai:
    mỗi lần nhận timeout lại sinh UUID mới rồi tạo tài nguyên
```

Nếu hai worker cùng xử lý một công việc nhưng tự sinh hai token, cơ chế phía dịch vụ không tự biết chúng là cùng ý định nghiệp vụ. Ứng dụng cần ánh xạ công việc đó đến một bản ghi thao tác duy nhất.

### 3.2. Token phải đi cùng ý định và payload ổn định

Một token nên gắn với các thông tin do ứng dụng lưu:

| Trường ứng dụng | Mục đích |
| --- | --- |
| `operationId` | Khóa của thao tác logic |
| `businessKey` | Liên hệ đến yêu cầu nghiệp vụ gốc |
| `operationType` | Phân biệt `CREATE_VCN`, `CREATE_SUBNET` và các thao tác khác |
| `targetTenancy`, `region`, `compartmentId` | Xác định đúng ngữ cảnh gửi request |
| `retryToken` | Giá trị dùng lại cho cùng thao tác |
| Payload đã chốt hoặc fingerprint của payload | Phát hiện việc vô tình đổi nội dung khi gửi lại |
| `state`, `firstSentAt`, `lastAttemptAt` | Điều phối retry và xử lý kết quả chưa rõ |
| Resource OCID, request ID, work request ID nếu có | Phục vụ tiếp tục công việc và điều tra |

Đây là mô hình lưu trạng thái được đề xuất cho ứng dụng, không phải danh sách field OCI bắt buộc nhận trong request.

Ví dụ, nếu lần đầu tạo VCN ở compartment A với CIDR `10.90.0.0/16`, không dùng lại token đó để tạo một VCN khác ở compartment B hoặc đổi CIDR. Nếu yêu cầu nghiệp vụ thay đổi, ứng dụng cần quyết định rõ đó là sửa một tài nguyên đã có hay một thao tác tạo mới; không coi token cũ như nút “thử lại với tham số khác”.

Fingerprint là cơ chế kiểm tra nội bộ. Nếu hash JSON, cần thống nhất cách biểu diễn để việc đổi thứ tự key không làm ứng dụng hiểu nhầm thành ý định khác. Fingerprint này không thay thế chữ ký HTTP và cũng không phải ETag của OCI.

### 3.3. Lưu trước khi gửi để phục hồi sau restart

Quy trình đề xuất với một bảng công việc bền vững:

```text
1. Tìm hoặc tạo operation theo khóa nghiệp vụ có ràng buộc duy nhất.
2. Trong giao dịch database:
       lưu payload đã chốt, retryToken, trạng thái PREPARED
   COMMIT.
3. Gửi request OCI bằng payload và token đã lưu.
4. Nhận phản hồi xác định:
       lưu resource OCID và trạng thái tương ứng.
5. Nếu timeout hoặc mất kết nối:
       lưu kết quả UNKNOWN nếu còn ghi được database;
       worker phục hồi đọc lại cùng operation, không sinh token mới.
```

Ràng buộc duy nhất nên phản ánh ý định nghiệp vụ, chẳng hạn tổ hợp môi trường và loại thao tác. Cơ chế lease hoặc claim công việc giúp giảm hai worker gửi đồng thời, nhưng không thay thế token: worker có thể mất lease sau khi request đã tới OCI.

Nếu tiến trình chết sau bước 3 nhưng trước bước 4, database vẫn có operation cùng token để tiếp tục điều tra hoặc retry. Nếu chỉ giữ token trong RAM, việc khởi động lại có thể làm ứng dụng đánh mất mối liên hệ đó.

### 3.4. Thời hạn và token bị vô hiệu hóa

Theo hợp đồng retry token của OCI, token hết hạn sau 24 giờ và có thể bị vô hiệu hóa sớm bởi thao tác xung đột, ví dụ tài nguyên đã được tạo rồi bị xóa khỏi hệ thống. Đây không phải cơ chế chống trùng vĩnh viễn. [Nguồn: Retry Token trong REST APIs](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

Khi đã quá thời hạn bảo đảm hoặc gặp token bị vô hiệu hóa, không tự động đổi token rồi gửi lại chỉ để vượt lỗi. Trước tiên xác định:

- Tài nguyên của lần tạo trước có còn tồn tại không?
- Ứng dụng đã từng lưu OCID hoặc kết quả thành công chưa?
- Ý định nghiệp vụ hiện tại là khôi phục theo dõi tài nguyên cũ hay thực sự tạo lại?
- Có thao tác xóa hoặc can thiệp vận hành nào làm token mất hiệu lực không?

Sau khi xác nhận cần thực hiện lại một tác dụng mới, ứng dụng mới cấp token mới theo quy trình của mình. Với các công việc tồn tại nhiều ngày, giữ thêm ánh xạ bền vững từ khóa nghiệp vụ đến resource OCID thay vì chỉ dựa vào thời hạn token.

## 4. Ví dụ Java: tạo VCN bằng token đã lưu

### 4.1. Điều kiện sử dụng mã

Ví dụ dùng OCI Java SDK 3.x với module `oci-java-sdk-core` và một HTTP implementation đã chọn. Trong project đã import OCI BOM, dependency dịch vụ có dạng:

```xml
<dependency>
    <groupId>com.oracle.oci.sdk</groupId>
    <artifactId>oci-java-sdk-core</artifactId>
</dependency>
```

Client cần authentication provider, region và quyền IAM phù hợp. Đoạn khởi tạo minh họa dùng profile cục bộ:

```java
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.core.VirtualNetworkClient;

ConfigFileAuthenticationDetailsProvider auth =
        new ConfigFileAuthenticationDetailsProvider("DEFAULT");

try (VirtualNetworkClient client = VirtualNetworkClient.builder().build(auth)) {
    client.setRegion(auth.getRegion());
    // Gọi phương thức tạo hoặc cập nhật được trình bày bên dưới.
}
```

Client này phục vụ API Networking của OCI. Phần lưu operation trong database thuộc ứng dụng, được thực hiện trước lời gọi tạo tài nguyên.

### 4.2. Phương thức gửi không tự sinh token

```java
import java.util.Objects;

import com.oracle.bmc.core.VirtualNetworkClient;
import com.oracle.bmc.core.model.CreateVcnDetails;
import com.oracle.bmc.core.requests.CreateVcnRequest;
import com.oracle.bmc.core.responses.CreateVcnResponse;
import com.oracle.bmc.retrier.RetryConfiguration;

public final class IdempotentVcnCreate {
    private IdempotentVcnCreate() {}

    public static CreateVcnResponse submit(
            VirtualNetworkClient client,
            CreateVcnDetails savedIntent,
            String savedRetryToken) {

        Objects.requireNonNull(client, "client");
        Objects.requireNonNull(savedIntent, "savedIntent");
        if (savedRetryToken == null || savedRetryToken.isBlank()) {
            throw new IllegalArgumentException("Can retry token da luu");
        }

        CreateVcnRequest request = CreateVcnRequest.builder()
                .createVcnDetails(savedIntent)
                .opcRetryToken(savedRetryToken)
                .retryConfiguration(
                        RetryConfiguration.SDK_DEFAULT_RETRY_CONFIGURATION)
                .build();

        return client.createVcn(request);
    }
}
```

`savedIntent` phải được dựng từ payload đã chốt của operation. Ví dụ payload để tạo một VCN học tập:

```java
CreateVcnDetails intent = CreateVcnDetails.builder()
        .compartmentId(compartmentId)
        .displayName("learning-env-1042")
        .cidrBlocks(java.util.List.of("10.90.0.0/16"))
        .freeformTags(java.util.Map.of("environment", "learning"))
        .build();
```

`cidrBlocks` là field danh sách CIDR trong builder hiện hành; chọn CIDR phù hợp quy hoạch mạng của môi trường thực hành. [Nguồn: CreateVcnDetails.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/CreateVcnDetails.Builder.html).

Giá trị UUID có thể dùng để sinh token lần đầu, nhưng phần sinh đó phải nằm ở bước tạo operation bền vững. Khi cùng operation được gửi lại, lấy lại token và payload cũ, không thực hiện lại bước sinh UUID trong `submit`.

SDK hỗ trợ cấu hình retry ở cấp request. Ví dụ trên chọn cấu hình retry của SDK cho request tạo VCN; không suy ra rằng mọi API Java SDK đều tự retry giống nhau khi chưa cấu hình. Retry của SDK cũng không lưu operation thay cho ứng dụng sau khi tiến trình chết. [Nguồn: Java SDK Concepts — Retries](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm).

Sau khi nhận `CreateVcnResponse`, lưu OCID từ `getVcn().getId()` cùng request ID của phản hồi. Nếu việc lưu database thất bại sau khi OCI đã tạo tài nguyên, lần phục hồi vẫn phải sử dụng operation cũ. Không kết luận request OCI thất bại chỉ vì giao dịch ghi nhận kết quả của ứng dụng thất bại.

## 5. ETag và bài toán lost update

### 5.1. Hai worker cùng đọc một phiên bản

Giả sử VCN đang có hai tag:

```json
{
  "environment": "learning",
  "owner": "team-a"
}
```

Worker A muốn thêm `costCenter=training`; worker B muốn đổi `owner=team-b`. Cả hai đều đọc cùng snapshot ban đầu và tạo map tags mới từ snapshot đó.

| Thời điểm | Worker A | Worker B | Trạng thái tài nguyên |
| --- | --- | --- | --- |
| t1 | Đọc tags và ETag E1 | | Bản ban đầu |
| t2 | | Đọc tags và ETag E1 | Bản ban đầu |
| t3 | Ghi map có `costCenter` | | Bản mới E2 |
| t4 | | Ghi map cũ đã đổi `owner` | Có nguy cơ mất `costCenter` nếu không kiểm tra phiên bản |

Chỉ đọc lại ngay trước khi ghi vẫn chưa loại bỏ khoảng trống cạnh tranh: tài nguyên có thể đổi giữa hai request. Điều kiện phải được kiểm tra tại dịch vụ khi chấp nhận cập nhật.

### 5.2. Đọc ETag rồi gửi `If-Match`

`GetVcnResponse` cung cấp cả tài nguyên và ETag qua `getVcn()` và `getEtag()`. `UpdateVcnRequest.Builder.ifMatch(...)` truyền điều kiện để chỉ cập nhật khi ETag còn khớp. [Nguồn: GetVcnResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/responses/GetVcnResponse.html), [UpdateVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/UpdateVcnRequest.Builder.html).

Luồng ứng dụng:

```text
GET tài nguyên -> snapshot S1, ETag E1
tính bản cập nhật U1 từ S1
UPDATE U1 với If-Match: E1

nếu thành công:
    nhận snapshot/ETag mới nếu API trả về
nếu ETag không khớp:
    không gửi lại mù U1 với ETag mới
    đọc lại và quyết định có thể tính lại ý định hay cần báo xung đột
```

Trong ví dụ hai worker, nếu A cập nhật thành công trước, B gửi `If-Match: E1` sẽ bị từ chối do phiên bản không còn khớp. `412 NoEtagMatch` là kết quả xung đột ETag được OCI mô tả. [Nguồn: OCI API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm).

ETag được dùng như giá trị opaque: không tự tăng, không so sánh lớn/nhỏ, không suy ra thời gian hoặc số lần cập nhật. Giữ nguyên giá trị mà SDK/API trả về khi đưa vào điều kiện tiếp theo.

### 5.3. Có ETag chưa đủ nếu bỏ điều kiện khi ghi

ETag không giữ khóa trên tài nguyên trong khoảng thời gian ứng dụng đang tính toán. Một bên vẫn có thể thay đổi tài nguyên; điều kiện giúp phát hiện snapshot đã cũ ở lần ghi có điều kiện tiếp theo.

Nếu một writer cố tình bỏ `If-Match`, cơ chế phía writer khác không ngăn được mọi ghi đè do writer đó gây ra. Trong một hệ thống nhiều công cụ quản trị, cần thống nhất cách dùng cập nhật có điều kiện hoặc quy định rõ công cụ nào sở hữu từng phần cấu hình.

`synchronized` trong Java chỉ phối hợp các thread sử dụng cùng cơ chế khóa trong một tiến trình. Nó không bao phủ pod khác, Console, CLI hoặc một bộ điều khiển hạ tầng độc lập đang cập nhật cùng VCN.

## 6. Biểu diễn trên REST API

Các đoạn HTTP sau chỉ minh họa vị trí header và payload; chưa bao gồm toàn bộ header/chữ ký để gửi request thực tế. Khi gọi REST trực tiếp, vẫn phải ký request theo hợp đồng OCI. [Nguồn: Request Signatures](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/signingrequests.htm).

Tạo VCN với token:

```http
POST /20160918/vcns HTTP/1.1
Host: iaas.ap-singapore-1.oraclecloud.com
Content-Type: application/json
opc-retry-token: 92bb936d-cdaf-4509-8090-f349ff8f9adc
Authorization: <chu-ky-hop-le>

{
  "compartmentId": "<compartment_ocid>",
  "displayName": "learning-env-1042",
  "cidrBlocks": ["10.90.0.0/16"]
}
```

Cập nhật có điều kiện sau khi đọc ETag:

```http
PUT /20160918/vcns/<vcn_ocid> HTTP/1.1
Host: iaas.ap-singapore-1.oraclecloud.com
Content-Type: application/json
If-Match: "example-etag-e1"
Authorization: <chu-ky-hop-le>

{
  "displayName": "learning-env-1042-ready"
}
```

`example-etag-e1` là giá trị minh họa, không phải định dạng phải tự xây dựng. Trong Java SDK, dùng `.ifMatch(getResponse.getEtag())` để truyền giá trị dịch vụ đã trả.

Theo HTTP, `If-Match: *` kiểm tra sự tồn tại của representation thay vì đối chiếu một ETag cụ thể. Vì vậy nó không thay thế điều kiện “tài nguyên vẫn đúng phiên bản tôi đã đọc”. Chỉ dùng các biến thể conditional request mà API đích hỗ trợ. [Nguồn: RFC 9110 — If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.1).

Không tự thêm `opc-retry-token` vào mọi API và cho rằng dịch vụ sẽ bảo đảm chống lặp. Trong hai builder được dùng ở bài, `CreateVcnRequest` có `opcRetryToken`, còn ví dụ `UpdateVcnRequest` dùng `ifMatch`; cần kiểm tra hợp đồng từng operation trước khi áp dụng.

## 7. Ví dụ Java: cập nhật tag theo điều kiện nghiệp vụ

### 7.1. Xác định ý định trước khi viết vòng retry

Thay vì yêu cầu chung chung “ghi map tags này”, ứng dụng xác định rõ:

> Đổi tag `owner` từ giá trị đã biết `team-a` thành `team-b`, đồng thời giữ các tag khác trong snapshot mới nhất.

Với ý định này:

- Nếu tag khác thay đổi, có thể đọc lại và xây lại map để bảo toàn thay đổi đó.
- Nếu `owner` đã là `team-b`, mục tiêu trạng thái đã được đáp ứng, không cần ghi thêm.
- Nếu `owner` đã thành `team-c`, phải báo xung đột nghiệp vụ thay vì tự ghi đè.

Đây là chính sách ứng dụng của ví dụ, không phải chính sách tự động của OCI. Một controller có quyền sở hữu tuyệt đối tag `owner` có thể chọn quy tắc khác, nhưng phải quyết định rõ trước khi retry.

### 7.2. Mã minh họa

Ví dụ dùng Java 17, `VirtualNetworkClient` đã có authentication provider và region. Phương thức trả `Vcn` mà nó quan sát được hoặc nhận về sau cập nhật. `expectedValue=null` biểu diễn kỳ vọng tag chưa tồn tại; `desiredValue` phải khác null.

```java
import java.util.ConcurrentModificationException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

import com.oracle.bmc.core.VirtualNetworkClient;
import com.oracle.bmc.core.model.UpdateVcnDetails;
import com.oracle.bmc.core.model.Vcn;
import com.oracle.bmc.core.requests.GetVcnRequest;
import com.oracle.bmc.core.requests.UpdateVcnRequest;
import com.oracle.bmc.core.responses.GetVcnResponse;
import com.oracle.bmc.model.BmcException;
import com.oracle.bmc.retrier.RetryConfiguration;
import com.oracle.bmc.waiter.MaxAttemptsTerminationStrategy;

public final class ConditionalVcnTags {
    private ConditionalVcnTags() {}

    public static Vcn compareAndSetTag(
            VirtualNetworkClient client,
            String vcnId,
            String key,
            String expectedValue,
            String desiredValue) throws InterruptedException {

        Objects.requireNonNull(client, "client");
        Objects.requireNonNull(vcnId, "vcnId");
        Objects.requireNonNull(desiredValue, "desiredValue");
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Tag key khong duoc rong");
        }

        RetryConfiguration oneUpdateAttempt = RetryConfiguration.builder()
                .terminationStrategy(new MaxAttemptsTerminationStrategy(1))
                .build();

        int maxConflictAttempts = 3;
        for (int attempt = 1; attempt <= maxConflictAttempts; attempt++) {
            GetVcnResponse snapshot = client.getVcn(
                    GetVcnRequest.builder().vcnId(vcnId).build());

            Map<String, String> current = snapshot.getVcn().getFreeformTags();
            Map<String, String> next = current == null
                    ? new HashMap<>() : new HashMap<>(current);
            String actualValue = next.get(key);

            if (Objects.equals(actualValue, desiredValue)) {
                return snapshot.getVcn();
            }

            if (!Objects.equals(actualValue, expectedValue)) {
                throw new ConcurrentModificationException(
                        "Tag muc tieu da thay doi; can danh gia lai y dinh");
            }

            String etag = snapshot.getEtag();
            if (etag == null || etag.isBlank()) {
                throw new IllegalStateException(
                        "Khong co ETag; khong gui cap nhat vo dieu kien");
            }

            next.put(key, desiredValue);
            UpdateVcnRequest request = UpdateVcnRequest.builder()
                    .vcnId(vcnId)
                    .ifMatch(etag)
                    .updateVcnDetails(UpdateVcnDetails.builder()
                            .freeformTags(next)
                            .build())
                    .retryConfiguration(oneUpdateAttempt)
                    .build();

            try {
                return client.updateVcn(request).getVcn();
            } catch (BmcException error) {
                boolean etagConflict = error.getStatusCode() == 412
                        && "NoEtagMatch".equals(error.getServiceCode());

                if (!etagConflict || attempt == maxConflictAttempts) {
                    throw error;
                }

                // Luot sau phai GET lai va tinh lai payload.
                Thread.sleep(ThreadLocalRandom.current().nextLong(100, 401));
            }
        }

        throw new IllegalStateException("Vuot gioi han xu ly xung dot");
    }
}
```

Ví dụ cách gọi trong khối đang quản lý vòng đời client:

```java
Vcn result = ConditionalVcnTags.compareAndSetTag(
        client,
        vcnId,
        "owner",
        "team-a",
        "team-b");
```

Mỗi lượt xung đột đều GET lại và tính lại map từ snapshot mới. Mã không giữ nguyên map cũ rồi chỉ thay ETag mới, vì cách đó vẫn có thể làm mất phần thay đổi của worker khác.

`UpdateVcnDetails` dùng builder và phân biệt field chưa được gán với field được gán rõ ràng là null. Vì vậy ví dụ chỉ gán `freeformTags`; không chuyển toàn bộ đối tượng đọc về thành một payload cập nhật chứa mọi field. [Nguồn: UpdateVcnDetails](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/model/UpdateVcnDetails.html).

### 7.3. Giới hạn và ý nghĩa kết quả

Các điều kiện cần hiểu khi sử dụng phương thức:

- Đây là thao tác hướng đến trạng thái mong muốn. Nếu tag đã có giá trị đích, phương thức thành công về trạng thái quan sát được; nó không chứng minh chính caller đã tạo ra giá trị đó.
- Chỉ lỗi `412 NoEtagMatch` được xử lý bằng vòng đọc–tính lại trong ví dụ. Lỗi quyền, timeout hoặc lỗi khác được chuyển cho lớp điều phối bên ngoài.
- Retry của request cập nhật được giới hạn một attempt trong retrier để vòng xử lý xung đột dễ quan sát. `GetVcn` vẫn có chính sách riêng của client/SDK.
- Ba lượt là giới hạn minh họa. Trong sản xuất còn cần deadline tổng, cancellation và metric cho mức tranh chấp.
- Phương thức không ghi lại operation vào database. Lớp ứng dụng chịu trách nhiệm lưu ý định và kết quả nếu cần phục hồi qua restart.

`RetryConfiguration` cho phép điều khiển chiến lược dừng và retry ở SDK; giới hạn attempt của request không đồng nghĩa đã có đầy đủ chính sách phục hồi nghiệp vụ. [Nguồn: RetryConfiguration Java API](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/RetryConfiguration.html).

## 8. Xử lý xung đột: khi nào được tính lại?

### 8.1. Thay đổi ở các field độc lập

Nếu A thêm `costCenter` còn B đổi `owner`, B có thể đọc lại snapshot sau cập nhật của A, giữ `costCenter` và áp dụng thay đổi `owner` nếu điều kiện nghiệp vụ vẫn đúng. Việc tính lại an toàn phụ thuộc vào quy tắc hợp nhất, không chỉ phụ thuộc ETag.

Map và collection cần được xem kỹ. Khi một API nhận cả một tập giá trị để cập nhật, không giả định nó chỉ thêm những mục xuất hiện trong payload. Với ví dụ tags, xây map từ snapshot mới nhất giúp tránh chủ động bỏ các key không thuộc ý định đang xử lý.

Nếu yêu cầu là xóa một key, ý định nên ghi rõ key cần xóa. Sau khi đọc lại, áp dụng thao tác xóa trên map hiện hành, thay vì gửi lại một map cũ thiếu nhiều key khác.

### 8.2. Cùng sửa một giá trị có ý nghĩa nghiệp vụ

Nếu A đổi `owner` sang `team-c`, B vẫn muốn đổi từ `team-a` sang `team-b`, B cần đánh giá lại vì tiền điều kiện nghiệp vụ không còn đúng. Lấy ETag mới rồi ghi `team-b` sẽ biến một xung đột được phát hiện thành hành vi ghi đè có chủ đích nhưng chưa được quyết định đúng.

Tùy loại cấu hình, ứng dụng có thể chọn:

| Loại ý định | Chính sách phù hợp có thể áp dụng |
| --- | --- |
| Đặt một tag do controller sở hữu về giá trị mong muốn | Đọc lại và hội tụ có giới hạn |
| Đổi một field chỉ khi nó còn giá trị đã được duyệt | Kiểm tra giá trị cũ, báo xung đột nếu thay đổi |
| Chỉnh route hoặc security rule ảnh hưởng nhiều thành phần | Tính lại từ cấu hình hiện hành và xác minh các điều kiện liên quan |
| Chỉnh cấu hình từ một biểu mẫu quản trị đã mở lâu | Hiển thị bản mới để người dùng quyết định cách hợp nhất |

ETag cung cấp tín hiệu phiên bản đã đổi. Quyết định “thay đổi đó có cho phép áp dụng lại ý định không” thuộc về nghiệp vụ hoặc controller.

### 8.3. Tranh chấp liên tục

Nếu hai controller liên tục đặt một field về hai giá trị khác nhau, thêm retry sẽ làm tăng request mà không giải quyết được bất đồng. Cần xác định quyền sở hữu cấu hình, hợp nhất nguồn mong muốn hoặc đưa các công việc cùng tài nguyên qua một bộ điều phối.

Hàng đợi theo resource ID hoặc lease có thể giảm cạnh tranh giữa các worker do ứng dụng quản lý. Vẫn nên giữ `If-Match` để phát hiện thay đổi từ Console, CLI hoặc công cụ ngoài cơ chế điều phối đó.

## 9. Timeout khi cập nhật có điều kiện

Một tình huống quan trọng là lần cập nhật đầu dùng ETag E1 đã được dịch vụ chấp nhận và tạo E2, nhưng phản hồi bị mất. Ứng dụng gửi lại request với E1 rồi nhận `412`.

```text
GET -> trạng thái S1, ETag E1
UPDATE theo E1 -> đã áp dụng thành S2, phản hồi mất
gửi lại UPDATE theo E1 -> có thể nhận 412
```

`412` ở lần gửi sau cho biết tiền điều kiện ETag không khớp ở lần đó. Nó không chứng minh lần đầu chưa từng thành công, cũng không cho biết chắc thay đổi mới do ai tạo ra.

Lớp điều phối cần:

1. Giữ nguyên ý định ban đầu và ghi nhận kết quả chưa rõ.
2. GET lại đúng tài nguyên, region và ngữ cảnh cần kiểm tra.
3. So sánh trạng thái hiện tại với mục tiêu cùng các điều kiện nghiệp vụ.
4. Nếu mục tiêu đã được đáp ứng, ghi nhận thành công theo **chính sách hội tụ trạng thái** nếu chính sách cho phép.
5. Nếu mục tiêu chưa đạt và tiền điều kiện nghiệp vụ vẫn đúng, xây request mới từ snapshot/ETag mới.
6. Nếu tiền điều kiện đã thay đổi hoặc không thể xác định an toàn, chuyển sang đối soát hoặc báo xung đột.

Với yêu cầu cần biết chính xác “operation này đã tạo tác dụng nào”, so sánh trạng thái cuối cùng có thể chưa đủ. Ví dụ hai tác nhân cùng đặt tag về một giá trị thì trạng thái không thể xác nhận tác nhân nào đã ghi. Cần thêm lịch sử thao tác, kết quả đã lưu và thông tin truy vết phù hợp.

Không bỏ `If-Match` sau timeout để bảo đảm request cuối cùng “chắc chắn chạy được”. Hành vi đó loại bỏ hàng rào phát hiện cập nhật trên snapshot cũ.

## 10. Retry lỗi tạm thời và giới hạn tổng công việc

### 10.1. Không retry mọi lỗi theo cùng một cách

| Kết quả | Hành vi ứng dụng nên cân nhắc |
| --- | --- |
| Timeout/mất kết nối sau khi có khả năng đã gửi request | Kết quả chưa rõ; giữ danh tính thao tác, dùng token hoặc đối soát trạng thái theo API |
| `429 TooManyRequests` hoặc lỗi server được phép retry | Backoff có jitter, giữ token và ý định của cùng thao tác |
| `412 NoEtagMatch` | Đọc lại và đánh giá lại điều kiện; không chỉ gửi lại payload cũ |
| `409 IncorrectState` | Xem tài nguyên đang ở trạng thái nào, chỉ retry theo hợp đồng operation |
| `409 InvalidatedRetryToken` | Điều tra thao tác trước và ý định hiện tại trước khi cấp token mới |
| Lỗi tham số, xác thực, phân quyền | Sửa nguyên nhân; không tạo vòng retry vô hạn |

OCI phân biệt các mã lỗi cùng HTTP status; ví dụ `409 IncorrectState` có hướng retry khác `409 Conflict` hoặc `409 InvalidatedRetryToken`. Cần đọc service error code cùng status thay vì chỉ kiểm tra `status >= 400`. [Nguồn: OCI API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm).

### 10.2. Kiểm soát retry nhiều tầng

Một lần gọi Java có thể được retrier của SDK gửi lại nhiều lần. Nếu ngoài nó còn có retry của job runner và hàng đợi, số request có thể lớn hơn dự kiến.

Ví dụ giả định mỗi tầng cho phép tối đa ba attempt:

```text
3 attempt của job
    × 3 attempt của ứng dụng trong mỗi job
    × 3 attempt của SDK trong mỗi lần gọi
    = tối đa 27 attempt HTTP cho phần lời gọi được retry như vậy
```

Đây là phép tính minh họa, không phải số attempt mặc định của SDK. Nó cho thấy cần quản lý ngân sách chung thay vì cấu hình từng lớp độc lập.

Với mỗi loại operation, xác định:

- Deadline tổng và số lượt tối đa ở từng tầng.
- Lỗi nào thuộc retry truyền tải, lỗi nào cần tính lại nghiệp vụ.
- Token/payload nào phải giữ nguyên qua các tầng và qua restart.
- Cách dừng khi hết thời hạn, bị hủy hoặc tài nguyên đã ở trạng thái cuối.
- Cách giới hạn polling và ghi nhận metric khi phải đối soát.

Backoff có jitter giảm nhiều worker cùng gửi lại tại một thời điểm. Nó không sửa được payload sai, mất quyền IAM hoặc hai controller có mục tiêu cấu hình trái ngược nhau.

## 11. Phạm vi bảo đảm: một request không phải cả giao dịch hạ tầng

### 11.1. Nhiều tài nguyên cần trạng thái workflow riêng

Một quy trình tạo VCN, subnet, instance và cấu hình database có thể hoàn thành từng phần. Token của bước tạo VCN không làm ba bước còn lại trở thành một giao dịch nguyên tử. ETag của VCN cũng không kiểm tra phiên bản subnet hoặc tài nguyên database.

Ứng dụng cần lưu trạng thái từng bước, các OCID đã tạo và kế hoạch phục hồi. Nếu bước tạo instance thất bại, có thể tiếp tục sửa bước đó hoặc thực hiện bù trừ theo chính sách đã định; không tự động xóa tất cả tài nguyên chỉ vì một response bị mất.

Các ví dụ áp dụng trong module OCI:

- Khi tạo Compute hoặc tài nguyên database, xem operation tương ứng có retry token không và ghi nhận tài nguyên đã được chấp nhận.
- Khi cập nhật tài nguyên lưu trữ, kiểm tra ETag/conditional header mà API cụ thể hỗ trợ; không coi ETag của mọi dịch vụ đều có cùng ý nghĩa nội bộ.
- Khi thay đổi cấu hình mạng phụ thuộc nhiều tài nguyên, xác minh điều kiện của từng tài nguyên và điều phối workflow thay vì dùng một ETag như khóa toàn VCN.

### 11.2. Tác vụ bất đồng bộ cần theo dõi hoàn tất

Một số API OCI trả về trước khi thao tác dài hoàn thành. Khi operation có work request, phản hồi có thể cung cấp `opc-work-request-id` để theo dõi tiến độ bằng API tương ứng của dịch vụ. Mã này khác `opc-request-id` và retry token. [Nguồn: Asynchronous Work Requests](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/workrequests.htm).

Không suy ra tác vụ đã hoàn tất chỉ vì lần gửi lại với token đã nhận được phản hồi hợp lệ. Ứng dụng cần phân biệt:

```text
ý định đã được lưu
    -> API đã chấp nhận thao tác
    -> tài nguyên/tác vụ đang tiến hành
    -> hoàn tất thành công hoặc thất bại xác định
```

Không phải mọi operation đều trả work request ID; ví dụ mã tạo VCN trong bài không đọc một header work request không được hợp đồng phản hồi đó công bố. Chọn cách theo dõi lifecycle hoặc work request đúng với API đang gọi.

### 11.3. Xóa có điều kiện

Một số API xóa cũng hỗ trợ `If-Match`; `DeleteVcnRequest` có trường này. Cơ chế giúp tránh xóa tài nguyên dựa trên một phiên bản đã cũ, nhưng không tự xác minh rằng người dùng thực sự còn muốn xóa tài nguyên đó. [Nguồn: DeleteVcnRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/core/requests/DeleteVcnRequest.Builder.html).

Sau timeout của thao tác xóa, việc GET không tìm thấy tài nguyên cần được diễn giải cùng mã lỗi, quyền và mục tiêu nghiệp vụ. Không coi mọi `404` là bằng chứng đã xóa thành công vì OCI có thể dùng mã lỗi không phân biệt rõ tài nguyên không tồn tại và không được phép truy cập.

## 12. Thực hành quan sát token và ETag

### 12.1. Chuẩn bị môi trường

Chọn một compartment học tập, VCN thử nghiệm và danh tính có quyền đọc/cập nhật VCN. Phần tạo mới cần quyền tạo tương ứng. Không chạy các cập nhật minh họa trên VCN đang phục vụ ứng dụng thật.

Chuẩn bị project Java có `oci-java-sdk-core`, authentication provider, region và HTTP implementation. Log thực hành nên có operation ID, VCN OCID, attempt, ETag đã đọc, mã kết quả và request ID; không ghi private key hoặc Authorization header.

### 12.2. Quan sát một xung đột ETag xác định

Để tạo cạnh tranh có kiểm soát, đọc hai snapshot trước khi thực hiện cập nhật đầu tiên. Đoạn sau là các câu lệnh trong một phương thức đã có `client` và `vcnId`; các import request/model/response như trong ví dụ Java ở trên.

```java
GetVcnResponse a = client.getVcn(
        GetVcnRequest.builder().vcnId(vcnId).build());
GetVcnResponse b = client.getVcn(
        GetVcnRequest.builder().vcnId(vcnId).build());

client.updateVcn(UpdateVcnRequest.builder()
        .vcnId(vcnId)
        .ifMatch(a.getEtag())
        .updateVcnDetails(UpdateVcnDetails.builder()
                .displayName("learning-writer-a")
                .build())
        .build());

client.updateVcn(UpdateVcnRequest.builder()
        .vcnId(vcnId)
        .ifMatch(b.getEtag())
        .updateVcnDetails(UpdateVcnDetails.builder()
                .displayName("learning-writer-b")
                .build())
        .build());
```

Khi hai lần đọc có cùng ETag và cập nhật A làm đổi ETag trước cập nhật B, B phải bị từ chối do điều kiện không còn khớp. Đọc lại tài nguyên để quan sát tên/ETag hiện tại. VCN cho phép cập nhật display name và tags qua API. [Nguồn: Updating a VCN](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/update-vcn.htm).

Sau đó thực hành với tags: một worker đổi key không liên quan, worker còn lại dùng `compareAndSetTag`. Quan sát việc đọc lại, giữ tag mới của worker trước và áp dụng thay đổi mục tiêu khi giá trị kỳ vọng còn đúng. Thử thêm trường hợp key mục tiêu đã được đổi sang một giá trị thứ ba để quan sát xung đột nghiệp vụ.

### 12.3. Quan sát cùng token qua hai lần gửi

Tạo một operation thử nghiệm, lưu payload và token trước khi gửi. Gửi `CreateVcn`, ghi nhận OCID rồi gọi lại với đúng payload/token trong thời gian token còn hợp lệ. Đối chiếu kết quả theo hợp đồng API và xác minh không phát sinh một VCN độc lập thứ hai do lần gửi lại đó.

Để mô phỏng phản hồi thất lạc, có thể để chương trình thử nghiệm bỏ qua kết quả lần đầu sau khi lời gọi đã trả về rồi chạy lại từ operation đã lưu. Đây là mô phỏng cửa sổ lỗi ứng dụng, không khẳng định đã tái hiện mọi tình huống lỗi mạng. Dùng đúng token cũ để quan sát hành vi phục hồi.

Không tạo token mới ở lần gửi thứ hai trong lượt này. Nếu muốn minh họa tác hại của token khác, dùng mô hình hoặc mock trước để tránh tạo tài nguyên dư ngoài mục đích buổi thực hành.

### 12.4. Tiêu chí quan sát

| Tình huống | Kết quả mong đợi theo thiết kế |
| --- | --- |
| Cùng operation tạo, cùng payload/token | Lần gửi lại được xử lý theo hợp đồng idempotency của API |
| Worker restart sau khi request đã gửi | Lấy lại token từ bản ghi operation |
| Cập nhật dựa trên ETag cũ | Phát hiện xung đột thay vì ghi đè vô điều kiện |
| Thay đổi một tag không liên quan | Có thể đọc lại và tính lại map theo chính sách |
| Tag mục tiêu thay đổi ngoài kỳ vọng | Dừng và báo xung đột nghiệp vụ |
| Timeout sau update có khả năng thành công | Đối soát trạng thái, không khẳng định thất bại chỉ từ timeout |
| Hết ngân sách retry | Giữ trạng thái rõ ràng để điều tra hoặc tiếp tục có điều phối |

## 13. IAM, quan sát và tính sẵn sàng

Idempotency và optimistic concurrency không thay thế phân quyền. Danh tính Java cần quyền cho các operation cụ thể trong compartment mục tiêu. Việc cập nhật free-form tags đòi hỏi quyền cập nhật tài nguyên; với VCN cần kiểm tra quyền `VCN_UPDATE` theo policy reference, không mặc định mọi `use` permission đều bao gồm cập nhật tags. [Nguồn: Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

Các tín hiệu nên được ứng dụng ghi nhận:

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Tỷ lệ `412` theo loại tài nguyên | Phát hiện nhiều writer cạnh tranh hoặc snapshot giữ quá lâu |
| Số operation ở trạng thái `UNKNOWN` | Các tác vụ cần đối soát trước khi tiếp tục |
| Tuổi operation chưa có kết quả xác định | Phát hiện công việc tiến gần/vượt cửa sổ retry token |
| Số lần đổi token cho cùng khóa nghiệp vụ | Phát hiện thiết kế tạo thao tác mới không đúng chủ đích |
| Attempt và tổng thời gian xử lý | Quan sát retry nhiều tầng hoặc deadline quá dài |
| Chênh lệch số operation với số tài nguyên đã tạo | Hỗ trợ điều tra tài nguyên dư và nguy cơ chi phí |

Không tăng số worker chỉ để giải quyết hàng đợi đang chậm nếu chúng đều tranh chấp cùng một tài nguyên. Khi tỷ lệ xung đột tăng, ưu tiên giảm cạnh tranh trên tài nguyên đó hoặc sửa quyền sở hữu cấu hình.

Sổ operation bền vững, token giữ ổn định và ETag có điều kiện giúp ứng dụng tiếp tục công việc sau lỗi tiến trình. Kết hợp chúng với giới hạn retry và giám sát sẽ tránh việc một lỗi truyền tải nhỏ biến thành tài nguyên trùng hoặc một vòng ghi đè cấu hình kéo dài.

## 14. Nguyên tắc áp dụng

Với thao tác tạo có hỗ trợ retry token, **một ý định API có một token ổn định qua các lần gửi lại**, được lưu cùng payload và ngữ cảnh mục tiêu. Với cập nhật có hỗ trợ ETag, **đọc snapshot, tính thay đổi rồi ghi với `If-Match` của snapshot đó**; khi xung đột, quyết định lại dựa trên dữ liệu mới và tiền điều kiện nghiệp vụ.

Trong dịch vụ Java quản lý OCI, hai cơ chế này cần nằm trong cùng thiết kế điều phối: phân biệt kết quả chưa rõ với thất bại xác định, lưu OCID/trạng thái tác vụ, giới hạn retry và theo dõi tài nguyên thực tế. Nhờ vậy, việc tự động hóa VCN, Compute, lưu trữ hoặc dịch vụ database có cơ sở để phục hồi sau sự cố và kiểm soát cập nhật đồng thời.
