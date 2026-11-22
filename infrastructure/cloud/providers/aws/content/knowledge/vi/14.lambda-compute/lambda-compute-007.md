# Cold start, Java SnapStart và tối ưu khởi tạo

Một hàm **AWS Lambda** có thể phản hồi nhanh khi môi trường thực thi đã sẵn sàng, nhưng yêu cầu đầu tiên sau khi Lambda tạo một môi trường mới có thể phải chờ khởi động runtime và mã ứng dụng. Hiện tượng này được gọi là **cold start**. Với **Java**, việc khởi động JVM, nạp class, khởi tạo framework và các thư viện có thể chiếm một phần đáng kể trong độ trễ đầu-cuối.

**AWS Lambda SnapStart** giảm chi phí khởi tạo bằng cách chuẩn bị môi trường của một **function version đã publish**, lưu snapshot trạng thái đã khởi tạo và khôi phục khi cần thêm execution environment. SnapStart giúp giảm phần init lặp lại, nhưng **restore vẫn có độ trễ**, kết nối hoặc credentials có thể hết hạn, và **không thể kết hợp SnapStart với Provisioned Concurrency trên cùng phiên bản hàm**.

Bài thuộc chương **Điện toán Lambda** trong mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn với hạ tầng Region/AZ, IAM, VPC, compute, storage, database, tích hợp và serverless nhằm giúp người học chọn kiến trúc, triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **cold start**, **warm invocation**, **Init**, **Restore**, **Invoke** và latency đầu-cuối.
2. Xác định các nguyên nhân khiến Java Lambda khởi tạo chậm và cách đo tác động lên p95/p99.
3. Mô tả lifecycle **publish → checkpoint → snapshot → restore → invoke** của Lambda SnapStart.
4. Phân biệt **published version**, **alias**, **$LATEST**, SnapStart và Provisioned Concurrency.
5. Tránh nhân bản giá trị phải duy nhất hoặc giữ connections, secrets và credentials hết hạn trong snapshot.
6. Áp dụng **CRaC hooks** beforeCheckpoint/afterRestore khi cần khởi tạo lại tài nguyên.
7. Bật, publish, kiểm tra version và chuyển alias bằng AWS CLI theo quy trình có rollback.
8. So sánh giải pháp tối ưu Java init, memory/CPU, concurrency, quan sát và chi phí thực tế.

## 2. Lambda execution lifecycle: cold và warm

Lambda quản lý các **execution environments**. Một môi trường có thể phục vụ nhiều invocation tuần tự trong thời gian tồn tại của nó, nhưng AWS **không bảo đảm** môi trường luôn được giữ lại.

~~~mermaid
flowchart TD
    REQ["Event / HTTP request"] --> CHECK{"Có execution environment<br/>sẵn sàng?"}
    CHECK -->|"Không"| SETUP["Environment setup"]
    SETUP --> INIT["INIT<br/>Extensions + Runtime + Function"]
    INIT --> INV["INVOKE<br/>Handler xử lý event"]
    CHECK -->|"Có"| INV
    INV --> RESULT["Response / kết quả"]
    INV --> REUSE["Có thể reuse environment"]
    REUSE -. "Nếu vẫn được giữ" .-> CHECK
~~~

| Giai đoạn | Chuyện gì xảy ra? | Điều cần đo |
|---|---|---|
| **Environment setup** | Lambda chuẩn bị execution environment | Thời gian trước khi runtime sẵn sàng |
| **Extension Init** | Extensions được khởi động | Mức overhead của monitoring/security extensions |
| **Runtime Init** | Khởi chạy runtime, ví dụ JVM | Startup/class loading |
| **Function Init** | Nạp handler, chạy static initializer, dựng framework/SDK clients | Thời gian framework và I/O lúc init |
| **Invoke** | Thực thi handler và nghiệp vụ | Duration, error, downstream latency |
| **Restore (SnapStart)** | Phục hồi trạng thái sau init đã snapshot | Restore Duration và afterRestore hooks |

**Cold start** thường xuất hiện khi concurrency tăng cần thêm môi trường, môi trường cũ bị thu hồi, code/version đổi hoặc runtime phải khởi tạo lại sau sự cố. **Warm invocation** tránh nhiều bước init nhưng vẫn phải chạy handler và gọi dependency.

### 2.1. Concurrency khác request rate

Nếu cùng có 100 request/giây, handler xử lý 50 ms sẽ cần concurrency ít hơn handler xử lý 2 giây. Do đó, một database timeout có thể làm tăng số môi trường Lambda đồng thời, rồi làm tăng số cold starts khi scale-out. **Giảm dependency latency và số connection** đôi khi quan trọng hơn vài chục mili giây Init.

### 2.2. Không đồng nhất cold start với API latency

Với luồng **client → API Gateway → Lambda → RDS**, độ trễ quan sát còn có DNS/TLS, API Gateway, authorization, Lambda Init/Restore/Invoke, database, mạng và serialization. Cần dùng log/trace để chứng minh phần nào gây p99 cao, thay vì tự kết luận mọi request chậm đều do JVM.

## 3. Vì sao Java cold start thường tốn thời gian?

| Thành phần | Ví dụ gây chậm | Phương án phân tích |
|---|---|---|
| **JVM và class loading** | Khởi động runtime, nạp nhiều classes | So sánh runtime/memory, profiling |
| **Classpath** | JAR lớn, dependency không sử dụng | Giảm số module, kiểm tra build artifacts |
| **Framework startup** | Spring context, dependency injection, annotation scanning | Tối ưu auto-configuration, bean initialization |
| **Static initialization** | Tạo serializer/SDK client, nạp cấu hình, build cache | Giữ phần bất biến, tránh I/O dư thừa |
| **External I/O** | Fetch Secrets Manager, RDS, HTTP API ngay lúc init | Timeout, cache TTL, lazy initialization hợp lý |
| **Extensions** | Agent observability/bảo mật nặng | Đo từng extension |
| **Memory/CPU** | Memory thấp kéo theo ít CPU hơn | Benchmark nhiều mức memory |
| **Network** | DNS, TLS handshake, VPC dependencies | Kiểm tra đường mạng, NAT/endpoint, SG |

**Lazy initialization không phải luôn tốt hơn:** chuyển nhiều việc từ Init sang handler có thể khiến nhãn Init Duration nhỏ đi nhưng **request đầu tiên vẫn chậm**. Mục tiêu cần đo là **end-to-end latency** và tỷ lệ lỗi, không chỉ số milliseconds trong một nhãn log.

### 3.1. Tối ưu Java trước khi bật tính năng đặc biệt

- Dùng dependency cần thiết, loại những module AWS SDK không dùng và thư viện trùng lặp.
- Không dựng cả web server/framework chỉ để xử lý một event đơn giản nếu handler gọn đáp ứng yêu cầu.
- Hạn chế auto-configuration và component scanning không phục vụ chức năng.
- Cache **object bất biến** như JSON serializer hoặc schema đã phân tích để reuse execution environment.
- Không lưu request-specific state trong static fields.
- Tránh gọi API bên ngoài từ Init nếu dependency đó không bắt buộc trước request đầu tiên.
- Đo thời gian startup riêng cho code, framework, extensions và external calls.

## 4. Thiết lập baseline và benchmark công bằng

Trước khi thay đổi, ghi lại:

1. **Latency client/API:** p50/p95/p99 với workload đã định nghĩa.
2. **Init/Restore/Invoke duration:** dữ liệu platform logs, CloudWatch Logs/X-Ray hoặc công cụ quan sát.
3. **Errors, timeouts, throttles và concurrency** khi traffic tăng.
4. **Memory và chi phí:** cấu hình MB, thực dùng, billed duration, log và backend.

| Metric | Ý nghĩa |
|---|---|
| **Duration** | Thời gian handler thực thi được Lambda đo |
| **Init Duration** | Thời gian khởi tạo ở giai đoạn có Init |
| **Restore Duration** | Thời gian phục hồi environment từ SnapStart |
| **ConcurrentExecutions** | Số invocation đồng thời |
| **Errors / Throttles** | Tính đúng và khả năng đáp ứng tải |
| **Max Memory Used** | Năng lực bộ nhớ thực dùng |
| **API latency p95/p99** | Chất lượng thực tế người dùng cảm nhận |

Không phải Init/Restore Duration đều là **CloudWatch metrics mặc định** trong mọi cấu hình; có thể phải đọc **platform log**, X-Ray hoặc xuất metric riêng. Hãy ghi rõ nguồn và công thức khi làm báo cáo.

### 4.1. Tránh các phép so sánh sai

- Không so sánh một function **mới triển khai** với function **đã warm** mà không kiểm soát concurrency.
- Giữ cùng payload, memory, architecture, Region, VPC, runtime, dependencies và tỷ lệ request.
- Đo đủ số lượng samples để có p95/p99 đáng tin, không chỉ một request duy nhất.
- Đo cả thời gian publish và lỗi sau restore; tối ưu latency nhưng làm deployment thường xuyên thất bại không phải cải tiến thực.
- Nếu bật/tắt SnapStart ở cấp function cho những version tiếp theo, so sánh bằng **hai functions tương đương** hoặc thí nghiệm version được kiểm soát. Published version đã tạo là bất biến.

## 5. SnapStart: từ checkpoint tới restore

SnapStart được bật cho **published versions** của những Lambda functions có runtime/package tương thích. Khi publish, Lambda:

1. Khởi tạo runtime, extensions và **function init code**.
2. Chạy những **beforeCheckpoint hooks** đã đăng ký.
3. Tạo snapshot của execution environment đã khởi tạo.
4. Lưu/quản lý snapshot theo cơ chế của dịch vụ.
5. Khi có invocation cần môi trường mới, **restore** từ snapshot.
6. Chạy **afterRestore hooks**, rồi gọi handler như bình thường.

~~~mermaid
flowchart LR
    CODE["Code / config"] --> PUBLISH["Publish version 7"]
    PUBLISH --> INIT["INIT<br/>JVM / framework"]
    INIT --> BEFORE["beforeCheckpoint"]
    BEFORE --> SNAP["Lambda-managed snapshot"]
    SNAP --> RESTORE["RESTORE khi cần<br/>môi trường mới"]
    RESTORE --> AFTER["afterRestore"]
    AFTER --> HANDLER["INVOKE handler"]
    HANDLER --> WARM["Warm reuse nếu còn"]
~~~

### 5.1. Lợi ích và giới hạn

| Tình huống | Lợi ích | Điều SnapStart không giải quyết |
|---|---|---|
| Java framework bootstrap lâu | Chuyển phần lớn init sang khi publish | Vẫn có restore overhead |
| Scale-out theo burst | Restore nhanh hơn việc init mới toàn bộ trong điều kiện phù hợp | Quota, concurrency và latency backend |
| SDK/HTTP clients | Có thể snapshot cấu hình an toàn | TCP connections và credentials sau restore có thể hết hạn |
| Static immutable config | Tận dụng kết quả khởi tạo | Config thay đổi sau checkpoint không tự xuất hiện |
| Dữ liệu nghiệp vụ | Không trực tiếp | Backup, DB HA và idempotency |

SnapStart không đồng nghĩa “container luôn warm” và không bảo đảm mọi cold invocation có cùng latency. **afterRestore** có thể là nút cổ chai mới nếu phải làm quá nhiều việc hoặc gọi mạng bên ngoài.

### 5.2. Published version, alias và $LATEST

Một function có mã/cấu hình **$LATEST**, có thể publish thành những version bất biến như **7** và **8**. Alias **prod** hoặc **canary** có thể trỏ tới version phù hợp.

| Tài nguyên | Hành vi |
|---|---|
| **$LATEST** | Có thể cập nhật code/config; không trực tiếp được SnapStart tối ưu như published version |
| **Published version** | Code/config bất biến và có snapshot nếu được bật hợp lệ |
| **Alias** | Tên ổn định tham chiếu version; có thể hỗ trợ weighted routing |

SnapStart version có thể chuyển trạng thái như **Pending, Active, Inactive, Failed**. Khi một version lâu không được gọi, snapshot có thể bị loại khỏi cache theo lifecycle của AWS; invocation tới **Inactive version** có thể gặp **SnapStartNotReadyException** trong lúc snapshot được tạo lại. Vì vậy, hệ thống ít traffic cần kế hoạch retry và kiểm tra version state trước những đợt sử dụng quan trọng.

## 6. Điều kiện và những bất tương thích cần nhớ

Trước khi bật, kiểm tra **runtime/Region/architecture và package type** theo tài liệu AWS tại thời điểm triển khai:

| Yếu tố | Điều kiện/cân nhắc |
|---|---|
| **Runtime Java** | AWS Lambda **managed Java runtime** nằm trong danh sách SnapStart hỗ trợ, chẳng hạn các thế hệ Java 11/17/21 |
| **Packaging** | Cần function triển khai dạng **ZIP** tương thích; SnapStart không hỗ trợ **container-image functions** |
| **Version** | Chỉ áp dụng cho **published versions**, không bật trực tiếp cho **$LATEST** |
| **Provisioned Concurrency** | **Không được kết hợp với SnapStart trên cùng function version** |
| **Amazon EFS** | SnapStart không hỗ trợ function cấu hình **EFS** |
| **Ephemeral storage** | Không hỗ trợ cấu hình **/tmp lớn hơn 512 MB** trong phạm vi giới hạn của SnapStart |
| **Hooks và extensions** | Phải tương thích checkpoint/restore và tuân thủ timeout |
| **VPC/IAM/KMS** | Vẫn phải cấu hình network/permission như Lambda thông thường |
| **Lifecycle** | Kiểm tra snapshot/version **Active** trước khi chuyển traffic |

**Không suy rằng mọi Lambda function viết bằng Java đều dùng được SnapStart.** Java chạy trong **container image**, custom runtime hoặc một architecture chưa được AWS hỗ trợ có thể không đáp ứng yêu cầu; kiểm tra đúng runtime, hình thức triển khai và Region.

### 6.1. SnapStart không sửa lỗi VPC

Nếu Lambda cần RDS trong private subnet, vẫn phải có VPC configuration, SG, route, DNS, IAM và secret phù hợp. SnapStart không tự mở cổng database, cấp quyền KMS, tạo VPC endpoint hoặc giải quyết network timeout. Đặt timeout/retry hợp lý để chức năng phục hồi không kéo dài vô hạn khi dependency gặp sự cố.

## 7. Snapshot state: rủi ro về uniqueness, secrets và connections

Snapshot lưu **bộ nhớ sau Initialization**. Nhiều execution environments được restore có thể bắt đầu từ **trạng thái giống nhau**. Đây là điểm cần xem kỹ khi dùng Java static fields và dependency injection singletons.

### 7.1. Đừng tạo sẵn giá trị cần duy nhất theo request

**Ví dụ sai:**

~~~java
public final class BadRequestIds {
    // Tính một lần khi class được khởi tạo; có thể nằm trong snapshot.
    static final String OPERATION_ID =
            java.util.UUID.randomUUID().toString();
}
~~~

Nếu OPERATION_ID được dùng cho từng order/request, nhiều environments có thể tái sử dụng **cùng ID** sau restore. Lỗi nằm ở việc tạo ID trước snapshot nhưng dùng như ID **per-invocation**, không phải do UUID không an toàn.

**Ví dụ đúng:**

~~~java
import java.util.UUID;

public final class RequestIds {
    public static String createOperationId() {
        return UUID.randomUUID().toString();
    }
}
~~~

Áp dụng cùng nguyên tắc với **nonce, transactionId, token tự tạo, sequence counter, temporary file names**. Java managed runtime có biện pháp hỗ trợ sinh số ngẫu nhiên phù hợp, nhưng không thể sửa thiết kế lưu lại một giá trị phải duy nhất trong static state rồi tái sử dụng.

### 7.2. Secrets, credentials và timestamps có thể cũ

Không tạo một static credential hoặc token ngắn hạn trước checkpoint rồi dùng vô thời hạn. Token có thể hết hạn/rotate trong thời gian snapshot không được invoke. Nếu cần Secrets Manager/SSM:

- Dùng **Lambda execution role** và **AWS SDK default credential provider chain**, tránh hard-code AWS access key.
- Cache secret có **TTL/refresh policy** phù hợp; có thể refresh ở **afterRestore** khi bắt buộc.
- Xử lý expiration và rotation, không in dữ liệu nhạy cảm vào log.
- Không dùng một **Instant.now()** được tính ở Init như thời gian của các request tương lai.
- Nếu feature flags hoặc service endpoint thường đổi, cần refresh sau restore hoặc lúc invoke.

### 7.3. Network connections và DNS cache

**TCP sockets, HTTP connection pools, database sessions, DNS cache** có thể không còn hợp lệ sau restore. Với RDS/Redis/API bên ngoài:

1. Không cho rằng kết nối được mở khi Init chắc chắn sống sau snapshot.
2. Xác minh hoặc tạo lại connection trong **afterRestore** hoặc khi dùng lần đầu.
3. Đặt **connect/read timeout**, retry có giới hạn, exponential backoff kèm jitter.
4. Khi dùng RDS, kiểm soát **connection storms** và cân nhắc **RDS Proxy** khi phù hợp.
5. Kiểm tra DNS TTL/refresh trong Java khi backend failover.

Nhiều SDK hiện đại tự làm mới credentials và kết nối. Dù vậy, **kiểm chứng thư viện và phiên bản cụ thể**; đừng coi tính năng tự phục hồi là bảo đảm cho mọi client tự xây.

## 8. Java CRaC hooks: beforeCheckpoint và afterRestore

**Coordinated Restore at Checkpoint (CRaC)** là cơ chế hooks để Java chuẩn bị tài nguyên trước snapshot và phục hồi sau restore. Hook phải **được đăng ký trong Init**, trước checkpoint.

| Hook | Thời điểm | Công việc phù hợp |
|---|---|---|
| **beforeCheckpoint** | Trước snapshot của published version | Kết thúc công việc khởi tạo, đóng tài nguyên không nên snapshot |
| **afterRestore** | Sau restore, trước handler invoke | Refresh kết nối/credentials, kiểm tra cấu hình động |

### 8.1. Mã Java minh họa

Ví dụ dùng **org.crac.Resource** và **java.net.http.HttpClient**. Dự án cần thư viện CRaC tương thích; đây là mẫu lifecycle để học, không phải ứng dụng hoàn chỉnh:

~~~java
package example.lambda;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.net.http.HttpClient;
import java.time.Duration;

public final class ClientLifecycle implements Resource {
    private volatile HttpClient client;

    public ClientLifecycle() {
        // Tạo object trong Lambda handler constructor / Init.
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        // Không giữ trạng thái connection cũ làm điều kiện đúng.
        client = null;
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        // Tạo lại sau snapshot restore.
        client = createClient();
    }

    public synchronized HttpClient getClient() {
        // Fallback nếu chạy không có SnapStart.
        if (client == null) {
            client = createClient();
        }
        return client;
    }

    private HttpClient createClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }
}
~~~

Handler phải tạo **ClientLifecycle** trong constructor/init để callback đã được đăng ký khi Lambda checkpoint, rồi sử dụng **getClient()** khi cần. Nếu thay bằng database pool/SDK client thực tế, phải xử lý đồng bộ, close/reconnect và provider chain theo thư viện đó.

**Giới hạn vận hành:** beforeCheckpoint hoặc afterRestore thất bại có thể làm publish/restore thất bại. Hook quá chậm làm giảm hiệu quả SnapStart và có thể vượt timeout. Tránh gọi giao dịch nghiệp vụ hoặc side effects không idempotent trong hook. Chỉ khởi tạo lại tài nguyên cần thiết, có timeout và log ngắn gọn không chứa secret.

## 9. Quy tắc chọn phần việc để khởi tạo

| Thành phần | Đặt tại Init? | Điều kiện an toàn |
|---|---|---|
| Serializer, regex, schema bất biến | Thường có | Có thể tái dùng, không phụ thuộc event |
| Tập cấu hình không đổi theo version | Có | Publish version mới khi cấu hình thay đổi |
| AWS SDK clients | Có thể | Default credential provider, connection recovery |
| TCP/DB connection mở sẵn | Cẩn trọng | Có cách reconnect và validation sau restore |
| Secrets/token từ dịch vụ ngoài | Cẩn trọng | TTL, refresh, KMS/IAM phù hợp |
| Request ID, nonce, transaction ID | **Không** | Sinh cho mỗi operation |
| Request body hoặc dữ liệu cá nhân | **Không** | Không lưu xuyên invocation |
| Feature flags, discovery kết quả thường đổi | Cân nhắc | Refresh tại restore hoặc invocation |

**Priming** những code paths không có side effects trong Init có thể giúp JVM/framework chuẩn bị sẵn, nhưng phải đo trước/sau. Không gọi handler “giả” mà vô tình ghi database, gửi notification hoặc tạo đơn hàng. Khởi tạo càng phức tạp tại thời điểm publish càng dễ bị ảnh hưởng bởi dependency không sẵn sàng.

## 10. Bật SnapStart, publish version và chuyển alias bằng AWS CLI

Các lệnh sau là **ví dụ thao tác có thể thay đổi tài nguyên AWS thật**, không tự thực thi. Chỉ sử dụng trong lab hoặc tài khoản được phép, với một Lambda **ZIP Java** đã tồn tại trong Region/runtime được hỗ trợ. Thay các tên và phiên bản minh họa bằng giá trị thực tế. Cần kiểm tra các bất tương thích trong phần 6 trước khi bật.

### 10.1. Kiểm tra cấu hình hiện tại

~~~bash
# Chỉ đọc cấu hình function và trạng thái SnapStart.
aws lambda get-function-configuration \
  --region ap-southeast-1 \
  --function-name orders-api \
  --query '{Name:FunctionName,Runtime:Runtime,PackageType:PackageType,Memory:MemorySize,Timeout:Timeout,SnapStart:SnapStart,LastUpdateStatus:LastUpdateStatus}' \
  --output json

# Danh sách aliases đang được sử dụng.
aws lambda list-aliases \
  --region ap-southeast-1 \
  --function-name orders-api \
  --output json
~~~

Đối chiếu **Runtime**, **PackageType**, **MemorySize**, **EphemeralStorage**, **FileSystemConfigs**, **VpcConfig**, function extensions và trạng thái các published versions. Nếu đang dùng Provisioned Concurrency tại phiên bản mục tiêu, cần thiết kế một hướng triển khai khác.

### 10.2. Bật SnapStart cho những version publish tiếp theo

~~~bash
aws lambda update-function-configuration \
  --region ap-southeast-1 \
  --function-name orders-api \
  --snap-start ApplyOn=PublishedVersions

# Đợi cấu hình update hoàn tất trước khi publish.
aws lambda wait function-updated \
  --region ap-southeast-1 \
  --function-name orders-api
~~~

**ApplyOn=PublishedVersions** không biến môi trường **$LATEST** thành một SnapStart environment. Quy trình CI/CD nên đảm bảo không có pipeline khác cùng lúc sửa function configuration hoặc publish version ngoài ý muốn.

### 10.3. Publish một version có snapshot

~~~bash
aws lambda publish-version \
  --region ap-southeast-1 \
  --function-name orders-api \
  --description "snapstart-release"
~~~

AWS trả về số version thực tế. **Giả sử** lần publish này nhận **version 7**; các lệnh tiếp theo chỉ đúng khi thay bằng số đã nhận.

~~~bash
aws lambda get-function-configuration \
  --region ap-southeast-1 \
  --function-name orders-api \
  --qualifier 7 \
  --query '{Version:Version,State:State,SnapStart:SnapStart,LastUpdateStatus:LastUpdateStatus}' \
  --output json

# Đợi version có trạng thái sẵn sàng khi CLI hỗ trợ waiter này.
aws lambda wait published-version-active \
  --region ap-southeast-1 \
  --function-name orders-api \
  --qualifier 7
~~~

Cần kiểm tra **State = Active** và **SnapStart.OptimizationStatus = On** với version tương thích trước khi cho người dùng thật truy cập. Publish trả về thành công **không đồng nghĩa** snapshot đã sẵn sàng ngay lập tức. Nếu version Pending/Failed/Inactive, xem log Init/hook và nguyên nhân cụ thể.

### 10.4. Chuyển alias production có kiểm soát

Nếu alias **prod** đã tồn tại và bản phát hành đã vượt qua canary/smoke tests:

~~~bash
aws lambda update-alias \
  --region ap-southeast-1 \
  --function-name orders-api \
  --name prod \
  --function-version 7
~~~

Nếu alias chưa có, dùng **create-alias** thay vì **update-alias**. Khi cần canary deployment, có thể dùng **weighted alias** hoặc giải pháp rollout/CodeDeploy được hỗ trợ. Cần kiểm tra versions cùng cấu hình external dependencies và có alarms để chủ động rollback khi errors/p99 tăng.

**Rollback bằng alias không đảo ngược database migration hoặc side effects.** Đồng thời, một published version cũ có thể đã **Inactive**, nên trước khi đưa traffic rollback, kiểm tra trạng thái SnapStart và kế hoạch retry/chuyển tiếp.

## 11. Quản lý SnapStart bằng Infrastructure as Code

AWS CloudFormation, SAM, CDK hoặc Terraform có thể khai báo các tài nguyên Lambda và quy trình publish/alias theo khả năng hỗ trợ. Lợi ích là review cấu hình, audit thay đổi và giảm drift giữa môi trường staging/production.

Ví dụ **AWS SAM** minh họa một function Java dạng ZIP:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  OrdersFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: example.lambda.OrdersHandler::handleRequest
      CodeUri: target/orders-lambda.zip
      MemorySize: 1024
      Timeout: 15
      AutoPublishAlias: prod
      SnapStart:
        ApplyOn: PublishedVersions
      Policies:
        - AWSLambdaBasicExecutionRole
~~~

Đây là **mẫu cấu trúc**, chưa phải một ứng dụng có thể triển khai ngay: cần build artifact ZIP, handler có thật, SAM CLI/permissions và những quyền truy cập S3/RDS/Secrets Manager cụ thể. **AWSLambdaBasicExecutionRole** chỉ cung cấp các quyền logging nền tảng liên quan, không cho phép mặc định mọi API nghiệp vụ.

Với production, nên kết hợp version/alias với **canary/linear rollout**, CloudWatch alarms và kiểm tra compatibility của database/schema. **Không gắn quyền AdministratorAccess** để giải quyết một lỗi init hoặc KMS; chỉ cấp action/resource thực sự cần thiết.

## 12. Tối ưu cold start ngoài SnapStart

### 12.1. Giảm chi phí khởi tạo mã nguồn

- Loại dependency thừa, rà soát Spring Boot starters và auto-configurations không dùng.
- Hạn chế scanning diện rộng; xây serializer/validator/schema cache một lần khi hợp lý.
- Không nạp toàn bộ dataset hoặc gọi nhiều services trong Init nếu chỉ một số event cần dùng.
- Dùng environment variables/parameter store đúng mục đích, cache cấu hình có thời hạn phù hợp.
- Theo dõi overhead của Lambda extensions/agent và giảm những thành phần quá nặng.
- Thực hiện profiling để xác định *class loading* hay external I/O mới là bottleneck.

### 12.2. Benchmark memory/CPU

Lambda cấp **CPU tương ứng với cấu hình memory**, vì vậy tăng memory có thể rút ngắn **JVM init**, handler duration hoặc mã hóa/giải mã dữ liệu. Ví dụ có thể thử **512 MB**, **1024 MB** và **2048 MB**, nhưng phải dùng cùng payload và concurrency.

Không kết luận “memory gấp đôi thì chi phí luôn gấp đôi”: tổng GB-second phụ thuộc thời gian thực thi. Khi tăng memory, thời gian xử lý có thể giảm đủ để giữ hoặc giảm chi phí; cũng có trường hợp chi phí tăng nếu bottleneck là database. Đo cùng **p95/p99, Memory Used, Errors và billed duration** trước khi chọn.

### 12.3. External I/O và initialization

Nếu Init phải tải secret, metadata hoặc config:

1. Phân biệt dữ liệu cần trước request đầu tiên với dữ liệu có thể lazy load.
2. Dùng timeout và retry có giới hạn cho HTTP/SDK calls.
3. Cache có TTL và refresh; tránh token hết hạn sau snapshot.
4. Nếu function dùng VPC private subnets, kiểm tra NAT hoặc VPC endpoints phù hợp, routing/SG và KMS.
5. Quan sát cả tốc độ khởi động và ảnh hưởng tới backend khi concurrency tăng nhanh.

**RDS Proxy** có thể hỗ trợ quản lý nhiều database connections khi Lambda scale-out, nhưng không giải quyết query chậm hoặc IAM/DB authentication sai. Việc gom kết nối cũng cần benchmark với transaction patterns thật.

### 12.4. AOT/native image có thay thế SnapStart không?

Các hướng build-time optimization, AOT và native compilation có thể giảm startup ở một số Java workloads nhưng đi kèm thay đổi build, reflection/library compatibility và runtime/package format. Một Java native/custom runtime hoặc container image **không tự có SnapStart**. So sánh dựa trên **end-to-end latency, độ ổn định, khả năng phát triển và chi phí**, không chỉ thời gian JVM khởi động.

## 13. SnapStart so với Provisioned Concurrency

| Phương án | Cơ chế | Khi nên dùng | Giới hạn |
|---|---|---|---|
| **On-demand mặc định** | Khởi tạo khi cần, tái dùng môi trường warm nếu còn | Workload không quá nhạy cold start | Cold start khi scale-out |
| **SnapStart** | Restore snapshot của published version | Java Init nặng, muốn giảm startup overhead | Restore latency, lifecycle/compatibility |
| **Provisioned Concurrency (PC)** | Chuẩn bị sẵn một lượng execution environments đã init | Ứng dụng cần latency ổn định với demand tương đối dự báo được | Phí capacity provisioned, cần quản lý mức cấp |
| **Tối ưu Init/memory** | Giảm thời gian khởi tạo và xử lý | Hầu hết Lambda functions | Cần profiling và regression testing |
| **Gọi định kỳ để “giữ ấm”** | Invoke trước để cố duy trì warm environments | Trường hợp giới hạn/thử nghiệm | Không có bảo đảm, không xử lý burst scale-out |

### 13.1. Reserved Concurrency không giống Provisioned Concurrency

**Reserved Concurrency** giới hạn và bảo đảm phần concurrency quota cho function, **không** giữ những execution environments đã được Init. **Provisioned Concurrency** cung cấp sẵn environments đã được khởi tạo theo năng lực đặt trước. Hai khái niệm khác nhau về tác động latency và chi phí.

**SnapStart và Provisioned Concurrency không được bật cùng lúc trên cùng function version.** Nếu p99 cực nhạy và tải có lịch rõ, PC có thể hợp hơn; cần tính phí capacity kể cả khi ít request và chuẩn bị xử lý traffic vượt provisioned capacity.

### 13.2. Vì sao “warmer cron” không bảo đảm loại bỏ cold start?

Gọi Lambda mỗi vài phút có thể giữ một số môi trường warm trong vài tình huống, nhưng AWS vẫn có thể thu hồi môi trường, khởi tạo môi trường khác hoặc scale-out đồng thời vượt số environment đã được làm nóng. Nó còn tạo thêm request, log và tác dụng phụ nếu handler không tách logic warmup. Đánh giá SnapStart/PC và tối ưu mã thường có căn cứ hơn.

## 14. CloudWatch Logs, X-Ray và phép đo thực tế

### 14.1. Nhận biết Init/Restore trong platform logs

Log Lambda có thể chứa các bản ghi dạng:

~~~text
INIT_REPORT Init Duration: ... ms
START RequestId: ... Version: ...
RESTORE_REPORT Restore Duration: ... ms Status: success
REPORT RequestId: ... Duration: ... ms Billed Duration: ... ms Memory Size: ... MB Max Memory Used: ... MB
~~~

Đây là **mẫu tham khảo**; định dạng và trường xuất hiện phụ thuộc runtime, chế độ SnapStart, thời điểm và định dạng logging. Không nên kết luận “không có cold start” chỉ vì một lần gọi trong một log stream không thấy **INIT_REPORT**. Một số lần init lại sau runtime failure có hành vi log khác với cold start thông thường.

### 14.2. Query CloudWatch Logs Insights

Để xem các record liên quan:

~~~text
fields @timestamp, @logStream, @message
| filter @message like /INIT_REPORT|RESTORE_REPORT|REPORT/
| sort @timestamp desc
| limit 100
~~~

Khi Logs Insights nhận dạng **@type** và **@duration** từ REPORT logs:

~~~text
filter @type = "REPORT"
| stats count(*) as invocations,
        pct(@duration, 50) as p50Ms,
        pct(@duration, 95) as p95Ms,
        pct(@duration, 99) as p99Ms
  by bin(5m)
~~~

**Lưu ý:** report duration không nhất thiết bằng **latency đầu-cuối** khi có API Gateway, Restore và các network dependencies. Hãy xác minh các trường được parse đúng với log format, sau đó liên kết với **API Gateway integration latency**, **AWS X-Ray traces** và backend metrics.

### 14.3. Các nguồn quan sát bổ sung

| Nguồn | Điều cần theo dõi |
|---|---|
| **Lambda CloudWatch metrics** | Invocations, Errors, Throttles, Duration, ConcurrentExecutions |
| **Lambda platform logs** | Init/Restore reports, exception, timeout, memory |
| **AWS X-Ray / tracing** | Function, downstream calls, dấu vết initialization/restore theo cơ chế hỗ trợ |
| **API Gateway/ALB** | Latency đầu-cuối, 4xx/5xx và integration errors |
| **RDS/Database** | Connection count, query latency, CPU, throttling |
| **Cost Explorer** | Chi phí requests, duration, concurrency và dịch vụ liên quan |

Để phát hiện bất thường, quan sát **p95/p99 theo version/alias** trong mỗi đợt rollout thay vì chỉ nhìn p50 toàn function. Một phiên bản có p50 tốt nhưng p99 tệ do reconnect database vẫn có thể vi phạm SLO.

## 15. Quy trình benchmark SnapStart và tối ưu hóa

### Bước 1 — Nêu mục tiêu định lượng

Ví dụ: với luồng API đã định nghĩa, đặt **p95 dưới 300 ms** và **p99 dưới 700 ms** trong một mức concurrency cụ thể. Đây là **SLO minh họa**, không phải SLA mặc định của Lambda. Cần xác định payload, traffic pattern, memory, architecture, Region và sự phụ thuộc vào database/API ngoài.

### Bước 2 — Đo baseline

Đo code hiện tại khi chưa bật SnapStart theo cả cold và warm opportunities; ghi log/trace, metrics và chi phí. Nếu không có đủ dữ liệu cold start, dùng kịch bản thử scale-out có kiểm soát hoặc môi trường mới tương đương, tránh cố thao tác vào production để “ép cold start”.

### Bước 3 — Publish SnapStart version

Bật SnapStart cho published versions, publish, chờ **Active/OptimizationStatus = On**, rồi cho canary traffic qua alias. Ghi lại quá trình snapshot creation, thời gian publish và mọi lỗi beforeCheckpoint.

### Bước 4 — Thử concurrency burst

Tạo nhiều request trong thời gian ngắn để kiểm tra restore song song, errors và throttles. Đo riêng handler duration/restore overhead và quan sát backend connection limits. So sánh cùng số lượng request với baseline.

### Bước 5 — Thử tính đúng sau restore

- Kiểm tra request IDs/nonce/transaction IDs không trùng giữa những môi trường mới.
- Rotate token/secret trong lab và xác minh credential refresh.
- Mô phỏng socket đóng, DNS thay đổi, database failover và timeout.
- Kiểm tra afterRestore hook, logs, state transitions và version/alias rollback.
- Không lưu secret trong log/benchmark reports.

### Bước 6 — Kết luận theo SLO và TCO

So sánh **p95/p99**, Errors, Cold/Restore duration, số lần publish thất bại, DB saturation và tổng chi phí. Một cải tiến chỉ có ý nghĩa nếu **dữ liệu đúng, độ trễ tốt hơn và khả năng vận hành chấp nhận được**.

## 16. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
|---|---|---|
| **OptimizationStatus không phải On** | Runtime/package/config chưa hỗ trợ, version chưa sẵn sàng | GetFunctionConfiguration của đúng qualifier/version |
| Gọi **$LATEST** vẫn cold start | SnapStart áp dụng published version | Dùng alias trỏ version đã publish |
| Version lâu ở **Pending/Failed** | Init hoặc beforeCheckpoint lỗi/timeout | Platform logs, hook logs, VPC/IAM/dependency |
| **SnapStartNotReadyException** | Version đã Inactive, snapshot đang chuẩn bị lại | State/OptimizationStatus, retry có giới hạn |
| **SnapStartTimeoutException** hoặc restore lỗi | afterRestore quá chậm, kết nối/secret timeout | RESTORE_REPORT, hook timeout, network |
| **ExpiredToken/401** sau restore | Static credential/token bị snapshot rồi hết hạn | SDK default provider, refresh policy |
| **Connection reset / SQL error** | Socket/pool từ checkpoint đã không hợp lệ | Connection validation, afterRestore, RDS |
| Trùng operation ID | Sinh ID trước checkpoint | Sinh ID cho mỗi operation/invocation |
| P99 API vẫn cao | Database/query/external API là bottleneck | X-Ray, RDS metrics, concurrency |
| Tăng memory nhưng không giảm latency | Workload bị giới hạn I/O/backend | Benchmark, tracing, profile |
| Publish SnapStart lỗi bất thường | Khởi tạo phụ thuộc external service kém ổn định | Rút gọn init, timeout, retry |
| Có SnapStart nhưng request vẫn lỗi 403 | IAM, bucket policy, KMS hoặc auth không đúng | Principal, resource policy, network |
| Chi phí cao sau tối ưu | More memory, PC, logs, backend calls tăng | Cost Explorer, pricing theo runtime/version |

### 16.1. Không xử lý lỗi restore bằng cách nới toàn bộ quyền IAM

Khi thấy timeout hoặc connection reset, trước tiên phân biệt **network/connection lifecycle** với **IAM AccessDenied**. Nếu SDK trả ExpiredToken, kiểm tra nguồn credentials đang dùng và cách refresh. Khi Lambda version Inactive, xử lý lifecycle/active status; đây không phải lỗi tài khoản không có quyền gọi database.

### 16.2. Hạn chế retry storm

Nếu sau restore hàng trăm instances đồng thời reconnect DB hoặc refresh secret, số kết nối đột ngột có thể làm backend quá tải. Đặt timeout ngắn vừa đủ, exponential backoff + jitter, giới hạn concurrency hoặc dùng proxy khi phù hợp. Không retry vô hạn các thao tác không idempotent; có thể tạo giao dịch hoặc thông báo trùng.

## 17. Bảo mật, phục hồi và chi phí

### 17.1. Bảo mật

- Không chụp static **AWS credentials, JWT, nonce, password** mà không có lifecycle refresh.
- Dùng **Lambda execution role least privilege**, KMS key policy và resource policies đúng phạm vi.
- Không log Authorization/Cookie, access key, connection strings hoặc dữ liệu cá nhân nhạy cảm.
- Kiểm soát quyền **lambda:UpdateFunctionConfiguration**, **lambda:PublishVersion**, **lambda:UpdateAlias** trong CI/CD.
- Kiểm tra VPC route, security group, Secrets Manager/SSM/STS endpoints, TLS và chính sách dữ liệu.
- Có TTL/cache invalidation, timeouts, retry theo mức rủi ro nghiệp vụ.

### 17.2. Chi phí

| Thành phần | Điều cần đưa vào TCO |
|---|---|
| **Requests** | Số Lambda invocations |
| **Duration / memory** | GB-second, billed duration theo cấu hình/runtimes |
| **SnapStart** | Giá snapshot caching/restore có thể khác theo runtime và chính sách giá hiện hành |
| **Provisioned Concurrency** | Phí capacity giữ sẵn và usage |
| **Observability** | CloudWatch Logs ingestion/retention/queries, X-Ray |
| **Network/VPC** | NAT Gateways, endpoints, data transfer |
| **Backends** | RDS connections, capacity, Secrets Manager, S3/API calls |
| **Vận hành** | Build/publish duration, canary tests, rollback và quản lý versions |

Đừng mặc định SnapStart miễn phí ở mọi ngôn ngữ hoặc mọi thời điểm. Đối chiếu **AWS Lambda pricing theo runtime** và AWS Pricing Calculator. TCO phải xét cả thời gian triển khai, chi phí backend khi scale-out, log/metric và số sự cố.

### 17.3. Khả năng phục hồi

Lambda có cơ chế vận hành đa AZ trong phạm vi AWS Region, nhưng **SnapStart không tự đảm bảo data recovery hoặc Multi-Region DR**. Nếu xử lý SQS/S3/EventBridge, thiết kế retry, idempotency, dead-letter queue hoặc destinations phù hợp. Với RDS, cân nhắc Multi-AZ/proxy/backup. Mục tiêu là ứng dụng vẫn xử lý đúng khi environment bị tạo lại, version đổi hoặc database failover.

## 18. Tình huống thực hành

### Tình huống A — Java Spring Boot mất nhiều giây để khởi tạo

Một Lambda Java dựng Spring context lâu, nhưng handler chỉ mất vài chục mili giây. Hệ thống có traffic theo đợt và p99 nhạy cảm.

**Yêu cầu:** đề xuất cải tiến trước và sau khi bật SnapStart.

**Gợi ý:** đo Init/Invoke và end-to-end, giảm dependencies/auto-configuration, benchmark memory, publish SnapStart version, quan sát Restore và hook; không kết luận chỉ bằng handler Duration.

### Tình huống B — Transaction ID trùng giữa các môi trường

Mã Java lưu **static final String TRANSACTION_ID** được tạo một lần bởi UUID.randomUUID() khi Init, rồi dùng như ID của từng giao dịch.

**Yêu cầu:** giải thích sự cố và thiết kế lại.

**Gợi ý:** snapshot có thể nhân bản giá trị; tạo ID mới cho mỗi operation và dùng idempotency key/DB uniqueness phù hợp. Không dùng static initializer làm per-invocation state.

### Tình huống C — Token hết hạn sau restore

Function tạo token của external API ngay tại Init và không kiểm tra expiry. Sau một khoảng thời gian không có traffic, function bị 401 khi gọi lại.

**Yêu cầu:** mô tả vòng đời token an toàn.

**Gợi ý:** refresh trong afterRestore hoặc khi token gần hết hạn; dùng credential provider, cache TTL, timeout, retry có giới hạn và tránh log secrets.

### Tình huống D — SnapStart không hỗ trợ cấu hình hiện tại

Một Lambda dùng managed Java nhưng package là **container image**, có EFS và cần /tmp 2 GB.

**Yêu cầu:** nêu các điểm bất tương thích và giải pháp.

**Gợi ý:** kiểm tra giới hạn SnapStart; cân nhắc đổi packaging/storage hoặc sử dụng Provisioned Concurrency và tối ưu Java init, nhưng không bật PC đồng thời SnapStart trên một version.

### Tình huống E — p99 API vẫn tăng sau bật SnapStart

SnapStart cải thiện cold startup, nhưng khi concurrency tăng lên 300, RDS chậm do quá nhiều connections.

**Yêu cầu:** xác định bottleneck và đề xuất kiểm chứng.

**Gợi ý:** đo RDS connection counts, CPU/query latency, kiểm tra pooling/RDS Proxy, giới hạn concurrency, caching, timeouts và application metrics. Không tăng Max Concurrency thiếu kiểm soát.

### Tình huống F — Rollback trỏ vào version Inactive

Một version SnapStart cũ không có traffic trong thời gian dài. Khi rollback alias production, API có lúc nhận SnapStartNotReadyException.

**Yêu cầu:** sửa quy trình phát hành/rollback.

**Gợi ý:** kiểm tra trạng thái **Active/OptimizationStatus** trước khi đưa traffic, chuẩn bị retry/backoff và fallback tới version đã sẵn sàng, theo dõi version lifecycle.

## 19. Checklist production

- [ ] Đã ghi baseline p50/p95/p99, Init/Restore/Invoke, errors, throttles và concurrency.
- [ ] Đã xác nhận runtime Java, Region, architecture, ZIP package và tính tương thích SnapStart.
- [ ] Đã rà soát bất tương thích **Provisioned Concurrency, EFS và /tmp > 512 MB**.
- [ ] Đã cấu hình **ApplyOn=PublishedVersions**, publish version, đợi trạng thái **Active/OptimizationStatus = On**.
- [ ] Đã dùng alias và có rollout/canary/rollback, không chỉ thử **$LATEST**.
- [ ] Đã rà soát giá trị cần unique: request ID, transaction ID, nonce, random seed ứng dụng.
- [ ] Đã rà soát secrets, AWS credentials, DNS cache, TCP/HTTP/DB clients khi restore.
- [ ] Đã thiết kế CRaC hooks nếu cần, bảo đảm không có side effects nghiệp vụ.
- [ ] Đã benchmark đủ concurrency và môi trường restore mới; kiểm tra connection storm.
- [ ] Đã tối ưu dependency, framework, memory/CPU và external I/O theo dữ liệu.
- [ ] Đã so sánh SnapStart, Provisioned Concurrency và reserved concurrency theo SLO.
- [ ] Đã bật CloudWatch/X-Ray metrics/traces, bảo vệ log khỏi PII/secret.
- [ ] Đã thiết kế retries, idempotency, DB HA và network/security theo least privilege.
- [ ] Đã tính requests, duration, caching/restore pricing, PC, logs, NAT và backend cost.
- [ ] Đã có runbook version Inactive, hook timeout, expired tokens và rollback.

## 20. Ghi nhớ

**Cold start** là phần chi phí khởi tạo môi trường trước khi Lambda handler xử lý. Với **Java**, JVM và framework bootstrap có thể khiến phần này đáng kể. **Lambda SnapStart** chuẩn bị và snapshot môi trường khi **publish version**, sau đó **restore** cho execution environments mới thay vì làm lại phần lớn Init. SnapStart không làm mất hoàn toàn Restore Duration và không sửa các vấn đề về backend hay ứng dụng.

Để dùng SnapStart an toàn, cần thiết kế **unique values theo invocation**, refresh **secrets/credentials**, xử lý **connections/DNS** sau restore, dùng **CRaC hooks** khi cần và triển khai qua **published version + alias**. Quyết định tối ưu dựa trên **p95/p99 đầu-cuối, tỷ lệ lỗi, tính đúng dữ liệu, khả năng phục hồi và tổng chi phí**, không chỉ thời gian khởi động một lần.

### Tài liệu AWS chính thức nên đối chiếu

- [AWS Lambda execution environment](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html) — Init, Invoke và warm reuse.
- [Improving startup performance with Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html) — cơ chế, runtime và giới hạn.
- [Lambda SnapStart runtime hooks for Java](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-runtime-hooks-java.html) — beforeCheckpoint và afterRestore.
- [Handle uniqueness with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-uniqueness.html) — random values, IDs và state.
- [Lambda SnapStart troubleshooting](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-troubleshooting.html) — xử lý lỗi checkpoint/restore.
- [Lambda versions and aliases](https://docs.aws.amazon.com/lambda/latest/dg/configuration-versions.html) — kiểm soát deployment.
- [Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html) — môi trường đã init sẵn.
- [Reserved Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html) — concurrency quota.
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html) — init, caching, idempotency, connections.
- [Configure Lambda memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html) — quan hệ CPU và memory.
- [Monitoring with CloudWatch Logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html) — platform và application logs.
- [Monitoring Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html) — invocations, duration, throttles.
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — giá dịch vụ theo cấu hình hiện hành.

