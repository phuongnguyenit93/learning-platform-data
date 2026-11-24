# SnapStart, cấu hình bộ nhớ và điều kiện tương thích runtime

Một Lambda Java có thể khởi động chậm vì phải tải runtime, khởi tạo Spring ApplicationContext, tạo bean, nạp cấu hình và thiết lập kết nối trước khi xử lý invocation đầu tiên. **AWS Lambda SnapStart** giảm phần khởi tạo lặp lại bằng cách tạo snapshot của execution environment đã được khởi tạo khi bạn publish một function version. Khi cần execution environment mới, Lambda khôi phục snapshot đó thay vì chạy lại toàn bộ quá trình init.

SnapStart không phải một annotation của Spring và cũng không thay đổi programming model của **Spring Cloud Function**. Bean vẫn là **Supplier**, **Function** hoặc **Consumer**; với Java managed runtime, handler vẫn có thể là **FunctionInvoker**. Tuy nhiên, snapshot làm thay đổi cách cần suy nghĩ về dữ liệu khởi tạo, static state, kết nối mạng, random seed và credentials. Đồng thời, cấu hình **MemorySize** ảnh hưởng cả RAM, CPU và hiệu năng mạng, còn **EphemeralStorage** là dung lượng thư mục **/tmp** độc lập với memory.

Bài thuộc chương **AWS Lambda**, hướng dẫn bật SnapStart cho published versions, hiểu vòng đời snapshot/restore, dùng Java **CRaC runtime hooks**, kiểm tra tính tương thích của runtime, tích hợp với Spring Cloud Function, cấu hình AWS SAM/CLI, chọn memory và ephemeral storage, benchmark và xử lý lỗi. Mục tiêu là đưa ra quyết định dựa trên workload và giới hạn runtime thay vì chỉ bật một tùy chọn rồi giả định cold start đã được giải quyết.

## 1. SnapStart giải quyết phần nào của cold start?

Khi một Lambda execution environment mới được tạo, AWS phải chuẩn bị môi trường và chạy phần khởi tạo của ứng dụng. Với Spring Boot, quá trình này có thể bao gồm:

- Khởi động Java runtime/JVM.
- Tải class và dependency.
- Tạo Spring ApplicationContext.
- Khởi tạo bean và cấu hình.
- Tạo serializer, HTTP client, SDK client và connection pool.
- Chạy static initializer hoặc phương thức **@PostConstruct**.
- Đăng ký Function bean trong **FunctionCatalog**.

Với runtime được SnapStart hỗ trợ, Lambda thực hiện init khi bạn **publish một version**, chụp trạng thái memory/disk đã khởi tạo, mã hóa và lưu snapshot. Khi scale ra execution environment mới, Lambda khôi phục snapshot để giảm phần khởi động phải lặp lại.

~~~mermaid
flowchart TD
    A["Publish Lambda version"] --> B["Init: runtime + Spring context + beans"]
    B --> C["beforeCheckpoint hooks"]
    C --> D["Lambda tạo encrypted snapshot"]
    D --> E["Invoke / scale out"]
    E --> F["Restore snapshot"]
    F --> G["afterRestore hooks"]
    G --> H["Invoke Function handler"]
~~~

### SnapStart không bỏ qua mọi chi phí

SnapStart giảm thời gian tạo execution environment từ trạng thái đã khởi tạo. Lambda vẫn cần:

- Khôi phục snapshot.
- Chạy các hook sau restore nếu có.
- Tiếp nhận event và gọi handler.
- Thực hiện business logic và downstream calls.

Vì vậy, SnapStart không thay thế tối ưu Function code, memory tuning, connection management hoặc observability. Với API có yêu cầu latency rất thấp, cần đo cả restore duration và thời gian xử lý request.

### So sánh với Provisioned Concurrency

**Provisioned Concurrency** giữ sẵn execution environments đã khởi tạo để đáp ứng request với latency thấp. SnapStart tạo snapshot để khôi phục environment khi cần. Hai cơ chế này có mục đích gần nhau nhưng **không thể bật đồng thời trên cùng function version**.

| Tiêu chí | SnapStart | Provisioned Concurrency |
| --- | --- | --- |
| Cách chuẩn bị | Snapshot khi publish version | Khởi tạo trước số environment đã cấu hình |
| Scale | Khôi phục environment từ snapshot | Dùng các environment được provision; có thể cần scale theo cấu hình |
| Vận hành | Cần kiểm tra uniqueness, stale state và restore hooks | Cần dự báo concurrency và quản lý số environment sẵn sàng |
| Kết hợp | Không hỗ trợ đồng thời với Provisioned Concurrency | Không dùng cùng SnapStart trên cùng function version |
| Phù hợp | Giảm startup latency mà không giữ sẵn toàn bộ capacity | Workload có yêu cầu latency nghiêm ngặt và dự báo traffic |

Nếu SnapStart chưa đáp ứng SLO latency, hãy đánh giá Provisioned Concurrency như một lựa chọn riêng và tính chi phí/khả năng duy trì capacity.

## 2. Điều kiện tương thích runtime

SnapStart hỗ trợ các **Lambda managed runtimes** thuộc những nhóm được AWS công bố, trong đó có **Java 11 trở lên**. Hỗ trợ tương ứng áp dụng cho ZIP và các Lambda base images được hỗ trợ. Với container image dùng base image tùy chỉnh, cần triển khai các hook/điều kiện tương thích SnapStart theo hướng dẫn AWS.

Một số loại runtime và tính năng không tương thích:

| Runtime/feature | SnapStart |
| --- | --- |
| Java managed runtime từ Java 11 trở lên | Hỗ trợ |
| Python 3.12+ và .NET 8+ | Hỗ trợ theo danh sách runtime AWS |
| OS-only runtime như **provided.al2023** | Không hỗ trợ |
| Custom runtime ZIP tự quản lý | Không hỗ trợ theo nhóm OS-only runtime |
| Native image ZIP chạy trên **provided.al2023** | Không hỗ trợ SnapStart |
| Container image | Có điều kiện; dùng Lambda base image được hỗ trợ hoặc thực hiện hooks theo hướng dẫn cho custom base image |
| Provisioned Concurrency | Không thể kết hợp |
| Amazon EFS | Không hỗ trợ |
| Amazon S3 Files | Không hỗ trợ |
| Ephemeral storage lớn hơn 512 MB | Không hỗ trợ |

**Điểm cần nhớ khi học chuỗi AWS Lambda:** Spring Cloud Function chạy bằng **Java managed runtime** có thể sử dụng SnapStart nếu phiên bản Java/Region được AWS hỗ trợ. Bài custom runtime/native image dùng **provided.al2023** ở phần trước không thể bật SnapStart theo cách này vì OS-only runtime không nằm trong danh sách hỗ trợ.

Danh sách runtime và tính năng có thể thay đổi. Trước khi triển khai, kiểm tra trang SnapStart hiện hành và trạng thái runtime trong Region mục tiêu; không suy luận rằng mọi Java runtime hoặc mọi custom runtime đều tự động tương thích.

AWS hiện công bố SnapStart ở các commercial Regions, với một số ngoại lệ tại Asia Pacific như New Zealand và Taipei. Vì phạm vi Region có thể được mở rộng, kiểm tra danh sách hỗ trợ tại thời điểm triển khai thay vì hard-code một giả định trong pipeline.

## 3. SnapStart chỉ áp dụng cho published version

SnapStart được cấu hình với:

~~~yaml
SnapStart:
  ApplyOn: PublishedVersions
~~~

Lambda tạo snapshot khi publish một function version. Bạn **không thể invoke SnapStart trên $LATEST chưa publish**. Một alias như **live** hoặc **prod** phải trỏ tới version đã publish để traffic thực sự sử dụng snapshot.

~~~mermaid
flowchart LR
    A["$LATEST"] --> B["Publish version 12"]
    B --> C["Init + snapshot"]
    C --> D["Version 12: Active"]
    D --> E["Alias live -> version 12"]
    E --> F["Client invoke alias live"]
~~~

### Trạng thái của version

| State | Ý nghĩa thực tế |
| --- | --- |
| **Pending** | Lambda đang chạy init và tạo snapshot; chưa nên invoke version |
| **Active** | Snapshot đã sẵn sàng để restore/invoke |
| **Inactive** | Snapshot của Java version có thể đã bị xóa sau thời gian không được invoke; Lambda cần tạo lại snapshot |
| **Failed** | Init hoặc snapshot creation thất bại; cần xem CloudWatch logs và trạng thái version |

Với Java SnapStart, nếu version không được invoke trong **14 ngày**, snapshot có thể bị xóa và version chuyển sang **Inactive**. Khi invoke lại, có thể nhận **SnapStartNotReadyException** trong lúc Lambda khởi tạo snapshot mới. Theo dõi state và thử lại sau khi version trở về Active.

### Thay đổi code hoặc cấu hình cần publish version mới

Snapshot gắn với **một published version**. Khi thay đổi code, environment variables, memory hoặc cấu hình SnapStart, hãy đảm bảo một version mới được publish và alias trỏ tới version đó. Chỉnh **$LATEST** không làm thay đổi snapshot đã tạo cho version cũ.

## 4. Bật SnapStart bằng AWS SAM

Ví dụ Spring Cloud Function có bean **uppercase**, dùng Java managed runtime và handler **FunctionInvoker**:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: Spring Cloud Function with Lambda SnapStart

Resources:
  UppercaseFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
      CodeUri: target/function-app-1.0.0-aws.jar
      MemorySize: 1024
      Timeout: 30
      EphemeralStorage:
        Size: 512
      SnapStart:
        ApplyOn: PublishedVersions
      AutoPublishAlias: live
      Environment:
        Variables:
          spring_cloud_function_definition: uppercase
      Policies:
        - AWSLambdaBasicExecutionRole
~~~

Các thuộc tính quan trọng:

- **Runtime: java21**: dùng managed Java runtime; chọn version đang được AWS hỗ trợ tại Region triển khai.
- **Handler**: Spring Cloud Function **FunctionInvoker**, không phải tên bean **uppercase**.
- **CodeUri**: shaded JAR được build theo hướng dẫn của Spring Cloud Function.
- **MemorySize**: ví dụ 1.024 MB, phải benchmark theo workload.
- **EphemeralStorage.Size: 512**: giữ **/tmp** ở mức mặc định tương thích SnapStart.
- **SnapStart.ApplyOn**: yêu cầu Lambda tạo snapshot cho các version được publish.
- **AutoPublishAlias: live**: SAM tạo version và alias trỏ tới version mới.
- **spring_cloud_function_definition**: chọn Function bean mà FunctionInvoker gọi.
- **AWSLambdaBasicExecutionRole**: quyền log cơ bản; thêm quyền nghiệp vụ tối thiểu nếu function gọi dịch vụ AWS khác.

Khi sử dụng **AutoPublishAlias**, SAM tạo tài nguyên version/alias cho function. Thay đổi code và các thuộc tính versioned như **MemorySize**, **Environment** hoặc **SnapStart** có thể kích hoạt publish version mới theo quy tắc của SAM. Kiểm tra CloudFormation change set và alias sau deploy.

### Không dùng template này cho custom runtime/native ZIP

Template trên dùng **managed Java runtime**. Không đổi Runtime thành **provided.al2023** rồi giữ SnapStart với hy vọng snapshot hoạt động. OS-only runtime không hỗ trợ SnapStart. Nếu cần native image hoặc custom runtime, tiếp tục theo mô hình custom runtime ở bài trước và benchmark/tối ưu theo các cơ chế phù hợp với runtime đó.

## 5. Bật và kiểm tra bằng AWS CLI

Nếu function đã tồn tại, bật SnapStart cho published versions:

~~~bash
aws lambda update-function-configuration \
  --function-name spring-function \
  --snap-start ApplyOn=PublishedVersions \
  --memory-size 1024 \
  --ephemeral-storage '{"Size":512}'
~~~

Sau khi cấu hình được cập nhật, publish version mới:

~~~bash
aws lambda publish-version \
  --function-name spring-function
~~~

Lấy version number từ kết quả publish, sau đó kiểm tra cấu hình version cụ thể:

~~~bash
aws lambda get-function-configuration \
  --function-name spring-function \
  --qualifier 12
~~~

Trong output cần kiểm tra:

~~~json
{
  "Version": "12",
  "State": "Active",
  "SnapStart": {
    "ApplyOn": "PublishedVersions",
    "OptimizationStatus": "On"
  }
}
~~~

Các giá trị version/state trong ví dụ là minh họa. Khi version còn **Pending**, đợi Lambda hoàn tất snapshot. Khi **OptimizationStatus** không phải On hoặc state là Failed, xem LastUpdateStatusReason và CloudWatch logs.

Invoke published version:

~~~bash
aws lambda invoke \
  --function-name spring-function:12 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

Hoặc invoke alias đã trỏ đến version:

~~~bash
aws lambda invoke \
  --function-name spring-function:live \
  --cli-binary-format raw-in-base64-out \
  --payload '{"value":"hello lambda"}' \
  response.json
~~~

Không dùng tên function không qualifier để kiểm chứng SnapStart rồi kết luận feature đã hoạt động; invocation cần nhắm tới published version hoặc alias trỏ đến version đó.

## 6. Cấu hình MemorySize: RAM đồng thời điều khiển CPU

Lambda cho phép cấu hình memory từ **128 MB đến 10.240 MB**, tăng theo bước **1 MB**. Memory không chỉ là dung lượng heap cho Java. Đây là mức memory mà Lambda cấp cho execution environment, bao gồm runtime, Spring, extension, heap, metaspace, thread stack, direct buffer và native memory.

Lambda phân bổ CPU theo memory. Ở mức **1.769 MB**, function có lượng CPU tương đương một vCPU; khi tăng memory, CPU được tăng theo tỷ lệ và ở mức tối đa 10.240 MB có thể nhận tới 6 vCPU. Năng lực mạng cũng có thể tăng theo cấu hình tài nguyên. Vì vậy, tăng memory đôi khi làm function nhanh hơn ngay cả khi ứng dụng chưa sử dụng hết RAM.

| Memory cấu hình | Ý nghĩa |
| --- | --- |
| 128 MB | Mức thấp nhất; phù hợp function rất nhẹ |
| 512 MB | Ví dụ cấu hình nhỏ, cần đo với Spring runtime |
| 1.024 MB | Mức minh họa cho ứng dụng Java có dependency |
| 1.769 MB | Xấp xỉ năng lực một vCPU |
| 3.538 MB | Có thể cung cấp nhiều CPU hơn cho workload song song |
| 10.240 MB | Mức tối đa; tối đa khoảng 6 vCPU |

Các dòng giữa là mốc minh họa, không phải profile tối ưu cố định. Workload I/O-bound, CPU-bound và memory-bound sẽ có điểm tối ưu khác nhau.

### Java heap không bằng MemorySize

Không đặt JVM heap bằng toàn bộ MemorySize. JVM còn cần memory cho:

- Metaspace và class metadata.
- Thread stacks.
- JIT/compiler data trên JVM managed runtime.
- Direct ByteBuffer và network buffers.
- Native library, TLS, compression và serialization.
- Spring/agent/extension và phần runtime khác.

Nếu heap chiếm gần toàn bộ MemorySize, process có thể bị out-of-memory dù heap chưa đạt giới hạn bạn dự kiến. Theo dõi **Max Memory Used** trong Lambda REPORT/CloudWatch và kiểm tra heap/native memory khi cần.

### Cấu hình trong AWS SAM

~~~yaml
Properties:
  Runtime: java21
  MemorySize: 1769
  Timeout: 30
  SnapStart:
    ApplyOn: PublishedVersions
~~~

**1769 MB** trong ví dụ là mốc để thử workload CPU-bound; không phải khuyến nghị đặt mọi function ở mức này.

### Cập nhật memory bằng AWS CLI

~~~bash
aws lambda update-function-configuration \
  --function-name spring-function \
  --memory-size 1769
~~~

Thay đổi này cập nhật cấu hình của function. Với SnapStart, cần publish version mới và chuyển alias tới version đó để version đang phục vụ traffic dùng memory setting mới.

## 7. EphemeralStorage và giới hạn /tmp

**EphemeralStorage** là dung lượng ổ đĩa tạm mà Lambda cấp trong thư mục **/tmp**. Nó độc lập với MemorySize:

- MemorySize đo memory của execution environment.
- EphemeralStorage đo dung lượng file tạm trên filesystem.
- Tăng /tmp không làm tăng Java heap hoặc CPU.
- Tăng MemorySize không tự động tăng dung lượng /tmp.

Lambda cho phép cấu hình ephemeral storage từ **512 MB đến 10.240 MB**, theo bước 1 MB. Tuy nhiên, **SnapStart không hỗ trợ ephemeral storage lớn hơn 512 MB**. Nếu cần SnapStart, giữ EphemeralStorage ở mức 512 MB.

Ví dụ cấu hình tương thích:

~~~yaml
EphemeralStorage:
  Size: 512
SnapStart:
  ApplyOn: PublishedVersions
~~~

Ví dụ cần /tmp 2 GB:

~~~yaml
EphemeralStorage:
  Size: 2048
~~~

Cấu hình thứ hai **không tương thích SnapStart**. Nếu workload cần nhiều dung lượng tạm, cân nhắc bỏ SnapStart hoặc thay đổi thiết kế để stream dữ liệu, chia nhỏ file hay dùng storage phù hợp. EFS cũng nằm trong danh sách tính năng không tương thích SnapStart, nên không xem EFS là cách mở rộng trực tiếp cho một function SnapStart.

### /tmp và dữ liệu snapshot

SnapStart lưu trạng thái memory và disk đã khởi tạo. Vì vậy, không dùng file trong /tmp được tạo ở init như một vùng lưu dữ liệu riêng cho từng execution environment sau restore. File có thể chứa trạng thái được copy từ snapshot. Tạo file tạm theo invocation, kiểm tra expiry và không lưu secret/business state cần duy nhất ở đây.

## 8. Quy trình tuning MemorySize và SnapStart

Không chọn memory chỉ dựa vào một lần chạy hoặc cảm giác ứng dụng nhanh/chậm. Hãy xây dựng một quy trình đo lặp lại:

1. **Chọn workload đại diện**: payload nhỏ/lớn, mức concurrency và tần suất invoke gần thực tế.
2. **Đặt baseline**: chạy managed Java runtime chưa bật SnapStart với memory hiện tại.
3. **Đo resource**: Duration, Billed Duration, Max Memory Used, errors, throttles và downstream latency.
4. **Thử nhiều mức memory**: tăng/giảm MemorySize để xem CPU, throughput và duration thay đổi ra sao.
5. **Bật SnapStart trên published version**: publish version mới, chờ Active rồi gọi đúng version/alias.
6. **Đo restore và invoke**: phân biệt Restore Duration, thời gian handler và warm invocation.
7. **Tính cost theo workload**: memory lớn hơn có thể tăng giá mỗi millisecond nhưng giảm thời gian chạy; so sánh tổng chi phí theo số invocation thực tế.
8. **Kiểm tra độ ổn định**: chạy đủ lần cold restore, warm invoke và concurrency để tránh kết luận từ một mẫu.

### Chỉ số cần quan sát

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Init Duration** | Thời gian init trong các log phù hợp |
| **Restore Duration** | Thời gian Lambda khôi phục SnapStart snapshot |
| **Duration** | Thời gian xử lý invocation |
| **Billed Duration** | Thời gian tính phí theo cấu hình runtime |
| **Max Memory Used** | Memory cao nhất đã sử dụng |
| **Memory Size** | Mức memory được cấu hình |
| **Errors/Throttles** | Lỗi và giới hạn concurrency |
| **p50/p95/p99 latency** | Phân phối latency thay vì chỉ nhìn average |

Với SnapStart, log **RESTORE_REPORT** giúp phân tích restore. Đừng gộp restore duration với business handler duration khi so sánh các phương án.

### AWS Lambda Power Tuning

Có thể dùng công cụ mã nguồn mở **AWS Lambda Power Tuning** để chạy workload ở nhiều memory allocation và so sánh thời gian/chi phí. Công cụ có thể gọi code và downstream services thật trong AWS account; dùng function staging và dữ liệu test, không chạy benchmark vô tình ghi dữ liệu production.

### So sánh công bằng

Khi so sánh JVM thường với SnapStart:

- Dùng cùng artifact, Java runtime, Region và architecture.
- Dùng cùng payload, dependency và downstream.
- So sánh cả cold start lẫn warm execution.
- Không chỉ lấy invocation đầu tiên sau publish; chờ version Active.
- Đo đủ lần để có p95/p99 đáng tin cậy.
- Không thay đổi memory đồng thời với nhiều yếu tố khác nếu muốn xác định nguyên nhân cải thiện.

## 9. Cấu hình tương thích tổng hợp cho Spring Cloud Function

Bảng sau giúp kiểm tra nhanh cấu hình triển khai:

| Thành phần | SnapStart Java managed runtime | Custom runtime/native image |
| --- | --- | --- |
| Runtime | Java managed runtime được hỗ trợ | Ví dụ provided.al2023 |
| Handler | FunctionInvoker::handleRequest | Theo custom runtime/RIC integration |
| SnapStart | ApplyOn: PublishedVersions | Không hỗ trợ cho OS-only runtime |
| Function definition | spring_cloud_function_definition | Theo integration/sample runtime |
| MemorySize | 128-10.240 MB | 128-10.240 MB |
| EphemeralStorage | Không vượt 512 MB | Theo quota runtime, không có SnapStart restriction này |
| Version | Publish version và invoke alias/version | Quản lý version theo deployment model |
| Bootstrap | Không cần file bootstrap riêng | Cần với custom runtime ZIP |

Với Spring Cloud Function, hãy xác minh **handler, function definition và runtime** cùng một mô hình. Không lấy Handler của managed Java rồi chuyển sang provided.al2023 mà bỏ qua RIC/bootstrap. Tương tự, không bật SnapStart trên native image ZIP chỉ vì executable được build từ cùng mã nguồn Java.

## 10. SnapStart runtime hooks với Java CRaC

Snapshot lưu trạng thái của memory và disk tại thời điểm checkpoint. Một số trạng thái trong đó có thể không còn đúng sau khi Lambda khôi phục execution environment: socket có thể đã hết hiệu lực, token có thể hết hạn, cache chứa timestamp cũ hoặc dữ liệu cần duy nhất cho từng environment có thể bị nhân bản.

Java runtime hỗ trợ **runtime hooks** dựa trên API **CRaC (Coordinated Restore at Checkpoint)**. Hai callback quan trọng:

- **beforeCheckpoint()**: chạy trước khi Lambda tạo snapshot; dùng để flush, đóng hoặc chuẩn bị các resource không thể khôi phục nguyên trạng.
- **afterRestore()**: chạy sau khi Lambda restore snapshot; dùng để kiểm tra và khôi phục resource cần thiết trước khi handler xử lý invocation.

CRaC có ba thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **Resource** | Đối tượng triển khai beforeCheckpoint/afterRestore |
| **Context** | Đăng ký và điều phối các Resource |
| **Core** | Cung cấp global context qua Core.getGlobalContext() |

### Thêm dependency CRaC

Với Maven:

~~~xml
<dependency>
    <groupId>org.crac</groupId>
    <artifactId>crac</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

Version trên là ví dụ theo hướng dẫn AWS; hãy pin phiên bản tương thích với Java/Spring build của dự án và cập nhật theo dependency policy.

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.crac:crac:1.4.0'
}
~~~

### Ví dụ Spring bean đăng ký lifecycle hooks

Giả sử ứng dụng có một **ConnectionManager** riêng để quản lý connection tới hệ thống downstream. Tên interface và hai method trong ví dụ là hợp đồng minh họa; thay bằng client/pool thực tế của ứng dụng.

Tệp **src/main/java/example/lambda/SnapStartLifecycle.java**:

~~~java
package example.lambda;

import org.crac.Core;
import org.crac.Resource;
import org.springframework.stereotype.Component;

@Component
public final class SnapStartLifecycle implements Resource {

    private final ConnectionManager connectionManager;

    public SnapStartLifecycle(
            ConnectionManager connectionManager) {
        this.connectionManager = connectionManager;

        // Đăng ký resource trong CRaC global context.
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            org.crac.Context<? extends Resource> context)
            throws Exception {

        connectionManager.closeConnectionsThatCannotBeResumed();
    }

    @Override
    public void afterRestore(
            org.crac.Context<? extends Resource> context)
            throws Exception {

        connectionManager.validateOrReconnect();
    }
}
~~~

Vì **SnapStartLifecycle** là Spring singleton bean, Spring ApplicationContext giữ một strong reference tới object này. Điều đó quan trọng: CRaC Context đăng ký Resource bằng **weak reference**. Nếu chỉ đăng ký một object tạm thời rồi không giữ reference mạnh, garbage collector có thể thu hồi object và hook sẽ không được gọi.

### Thứ tự hook và giới hạn thời gian

- **beforeCheckpoint()** được thực thi theo thứ tự ngược với thứ tự đăng ký.
- **afterRestore()** được thực thi theo đúng thứ tự đăng ký.
- Hook phải được import/khởi tạo trong ứng dụng; một class không được load thì hook không được đăng ký.
- **afterRestore()** và việc nạp runtime phải hoàn tất trong giới hạn restore **10 giây**. Nếu quá thời gian, Lambda có thể báo **SnapStartTimeoutException**.
- **beforeCheckpoint()** được tính trong giới hạn thời gian init/checkpoint của Lambda; hook không nên thực hiện migration hoặc tác vụ không giới hạn.
- Init và before-checkpoint có giới hạn thời gian riêng theo Lambda lifecycle; không đặt công việc không giới hạn vào hook.

Không làm migration database, gọi API chậm hoặc tải hàng trăm MB dữ liệu trong **afterRestore()**. Hãy giữ hook ngắn, có timeout và có thể chạy lặp an toàn. Nếu reconnect có thể chậm, đánh dấu client cần refresh rồi thực hiện lazy reconnect ở handler với deadline phù hợp.

## 11. Những dữ liệu không được giả định là duy nhất sau restore

Lambda có thể dùng **một snapshot ban đầu** để tạo nhiều execution environments. Vì vậy, giá trị được sinh trong giai đoạn init có thể được sao chép sang nhiều environment.

Ví dụ nguy hiểm:

~~~java
private static final String INSTANCE_ID =
    java.util.UUID.randomUUID().toString();
~~~

Nếu UUID được tạo khi class khởi tạo trước snapshot, nhiều environment được restore có thể bắt đầu với cùng giá trị. Điều tương tự áp dụng với:

- Random seed hoặc random bytes đã được lưu trong memory.
- Token, secret hoặc credential được tạo trong init.
- Counter in-memory dùng để cấp ID duy nhất.
- Timestamp dùng để đánh dấu thời điểm của từng environment.
- Hostname/process metadata được giả định là định danh duy nhất.
- Cache chứa dữ liệu phải khác nhau giữa các environment.

### Sinh giá trị duy nhất sau restore hoặc trong handler

Nếu ID phục vụ từng business request, sinh nó khi xử lý request:

~~~java
@Bean("createRequestId")
Supplier<String> createRequestId() {
    return () -> java.util.UUID.randomUUID().toString();
}
~~~

Với dữ liệu cần cryptographic randomness, dùng **java.security.SecureRandom** hoặc cơ chế CSPRNG được AWS hỗ trợ. Không tự tạo seed từ current time trong init rồi lưu vào static field.

Nếu cần một ID duy nhất cho từng execution environment, tạo lại sau restore bằng hook và xác minh chiến lược không gây collision khi nhiều environment được tạo đồng thời. Nếu ID phải duy nhất toàn hệ thống hoặc bền vững qua invocation, dùng cơ chế cấp ID bên ngoài như database sequence/conditional write hoặc UUID theo chuẩn ứng dụng; đừng dựa vào static counter.

### Tránh side effect nghiệp vụ trong Spring initialization

Với SnapStart, Spring ApplicationContext và các bean được khởi tạo khi Lambda publish version để tạo snapshot. Vì vậy, các hành động trong static initializer, constructor hoặc **@PostConstruct** có thể chạy trong lúc deploy/publish version, trước khi có request thật.

Không nên:

- Tạo một đơn hàng thật trong @PostConstruct.
- Gửi email hoặc phát event nghiệp vụ khi Spring context khởi động.
- Chạy migration không idempotent khi publish version.
- Cấp business ID một lần rồi giả định mỗi environment sẽ có giá trị khác nhau.

Initialization nên tạo cấu trúc dùng chung, cấu hình và client có thể tái sử dụng. Business side effects phải diễn ra trong Function handler và có idempotency phù hợp.

## 12. Kết nối mạng, credentials và dữ liệu tạm

### Network connections

Trạng thái connection được tạo trong init **không được bảo đảm** còn hợp lệ sau khi Lambda restore snapshot. TCP connection, TLS session, DNS cache hoặc connection pool có thể đã stale.

Các cách xử lý:

1. Ưu tiên client/pool có khả năng phát hiện connection lỗi và tự reconnect.
2. Validate connection trước khi dùng hoặc tạo lại khi cần.
3. Dùng **afterRestore()** cho việc reset/reinitialize ngắn và có thể dự đoán.
4. Nếu kết nối cần thời gian dài, thực hiện lazy reconnect trong handler với timeout/deadline.
5. Đặt timeout cho downstream nhỏ hơn thời gian Lambda còn lại.

AWS SDK thường tự khôi phục phần lớn kết nối theo cơ chế của SDK; không vì thế mà giả định mọi custom socket hoặc JDBC connection đều còn sống.

### Credentials

Không đọc một temporary credential lúc init rồi giữ access key/secret/session token trong static field. Credential có thể hết hạn trước khi environment được restore.

Khi dùng AWS SDK, ưu tiên **default credential provider chain** hoặc provider được AWS khuyến nghị cho runtime. Khi SnapStart được bật, Lambda dùng container credential endpoint để SDK lấy credentials mới sau restore. Không hard-code credentials vào code hoặc snapshot.

Lambda cung cấp các biến container credential endpoint như **AWS_CONTAINER_CREDENTIALS_FULL_URI** và **AWS_CONTAINER_AUTHORIZATION_TOKEN** khi SnapStart hoạt động. AWS SDK credential provider chain có thể sử dụng cơ chế này; tránh tự đọc access key/session token trong init rồi giữ chúng trong static field.

### Temporary data và /tmp

**/tmp** là ephemeral storage của từng execution environment. SnapStart có thể khôi phục trạng thái disk đã snapshot, vì vậy dữ liệu được ghi vào /tmp trong init không nên được coi là dữ liệu riêng cho một invocation hoặc một environment sau restore.

- Không lưu secret hoặc token duy nhất trong file được tạo lúc init.
- Không dựa vào file tạm để lưu business state bền vững.
- Xóa/recreate file tạm theo nhu cầu invocation.
- Kiểm tra timestamp/expiry trước khi dùng cache hoặc file được tạo trước snapshot.

Nếu dữ liệu cần sống qua nhiều invocation hoặc phải chia sẻ giữa các execution environments, dùng storage bên ngoài phù hợp.

## 13. Tích hợp với Spring Cloud Function

Với Java managed runtime, Spring Cloud Function tiếp tục dùng AWS adapter:

~~~text
Handler:
  org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest

spring_cloud_function_definition:
  uppercase
~~~

Ví dụ Function bean:

~~~java
package example.lambda;

import java.util.Locale;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SnapStartFunctionApplication {

    public static void main(String[] args) {
        SpringApplication.run(SnapStartFunctionApplication.class, args);
    }

    public record TextRequest(String value) {}

    public record TextResponse(String value) {}

    @Bean("uppercase")
    Function<TextRequest, TextResponse> uppercase() {
        return request -> {
            if (request == null || request.value() == null) {
                throw new IllegalArgumentException(
                    "value is required");
            }

            return new TextResponse(
                request.value().toUpperCase(Locale.ROOT));
        };
    }
}
~~~

SnapStart hoạt động ở tầng **Lambda runtime/execution environment**. FunctionInvoker và FunctionCatalog vẫn chịu trách nhiệm định tuyến event tới bean. Không cần thay Function thành một AWS-specific handler chỉ để bật SnapStart.

### Điều cần rà soát trong Spring Boot

- Bean khởi tạo ở startup có tạo side effect không?
- HTTP/DB client có giữ connection qua snapshot không?
- Cache có chứa timestamp, token hoặc ID cần duy nhất không?
- Có static field mutable hoặc random seed được tạo trong init không?
- Có component nào tạo thread/background task rồi tiếp tục chạy sau khi init không?
- Resource hook có được Spring component scan khởi tạo không?
- CRaC Resource có strong reference trong suốt vòng đời không?
- Hook restore có hoàn tất trong 10 giây không?

Nếu không có resource đặc biệt, không cần thêm CRaC hook chỉ để có hook. Hãy bắt đầu bằng kiểm tra uniqueness, connection, credentials và side effects; chỉ thêm hook khi cần thao tác cụ thể trước checkpoint hoặc sau restore.
## 14. Kiểm thử SnapStart cho Spring Cloud Function

Nên chia kiểm thử thành các tầng vì mỗi tầng xác minh một hợp đồng khác nhau:

| Tầng kiểm thử | Mục tiêu |
| --- | --- |
| Unit test | Logic Function, idempotency và cách sinh ID |
| Spring integration test | ApplicationContext, FunctionCatalog, bean lifecycle và component scan |
| CRaC hook test | beforeCheckpoint/afterRestore gọi đúng thao tác quản lý resource |
| Publish-version test | Lambda tạo snapshot và version chuyển sang Active |
| Restore test | Environment được khôi phục, hooks chạy và connection được làm mới |
| Load/latency test | p50/p95/p99, restore duration, memory, concurrency và downstream latency |

### Unit test cho Function bean

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SnapStartFunctionTest {

    @Test
    void uppercasesRequest() {
        var app = new SnapStartFunctionApplication();

        var result = app.uppercase().apply(
            new SnapStartFunctionApplication.TextRequest(
                "hello lambda"));

        assertEquals("HELLO LAMBDA", result.value());
    }
}
~~~

Test này kiểm tra business function trực tiếp. Nó không xác minh SnapStart, CRaC runtime hoặc Lambda version.

### Test CRaC hook với mock collaborator

Có thể inject một **ConnectionManager** giả và gọi hai callback để xác minh thứ tự thao tác:

~~~java
package example.lambda;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.crac.Context;
import org.junit.jupiter.api.Test;

class SnapStartLifecycleTest {

    @Test
    void closesBeforeCheckpointAndReconnectsAfterRestore()
            throws Exception {

        ConnectionManager manager =
            mock(ConnectionManager.class);

        SnapStartLifecycle lifecycle =
            new SnapStartLifecycle(manager);

        Context context = mock(Context.class);

        lifecycle.beforeCheckpoint(context);
        lifecycle.afterRestore(context);

        verify(manager).closeConnectionsThatCannotBeResumed();
        verify(manager).validateOrReconnect();
    }
}
~~~

Test này kiểm tra class lifecycle và collaborator. Khi khởi tạo class trong unit test, nó cũng đăng ký resource với CRaC global context của test JVM; với test suite thực tế, cân nhắc tách registration khỏi constructor hoặc dùng Spring test context để tránh đăng ký nhiều lần. Integration test trên Lambda staging mới chứng minh Lambda runtime thực sự gọi hook.

### Spring FunctionCatalog integration test

~~~java
package example.lambda;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = SnapStartFunctionApplication.class)
class SnapStartCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void registersUppercaseFunction() {
        assertNotNull(catalog.lookup("uppercase"));
    }
}
~~~

Nếu lifecycle bean là một phần của component scan, kiểm tra nó cũng được tạo trong Spring context. Chỉ kiểm tra FunctionCatalog chưa chứng minh CRaC Resource được đăng ký và giữ strong reference; có thể bổ sung test riêng cho bean lifecycle.

### Kiểm thử uniqueness và connection recovery

Trên staging, tạo đủ concurrency để Lambda khởi tạo nhiều execution environments từ cùng snapshot. Ghi lại:

- Request ID của Lambda.
- Business event ID.
- ID của execution environment nếu ứng dụng có cơ chế định danh an toàn.
- Kết quả tạo token/UUID.
- Connection reset/reconnect và lỗi downstream.

Kiểm tra không có business ID hoặc secret bị lặp do được sinh ở init. Với connection pool, xác minh request đầu sau restore không dùng socket stale và việc reconnect không vượt thời gian restore.

## 15. Troubleshooting SnapStart và memory

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **SnapStartNotReadyException** | Java version ở trạng thái Inactive hoặc snapshot đang được tạo lại | Kiểm tra State, chờ Active rồi retry |
| **SnapStartTimeoutException** | afterRestore hook hoặc runtime restore quá 10 giây | Rút ngắn hook, reconnect lazy và đặt timeout |
| Version ở **Pending** lâu | Init, beforeCheckpoint hoặc VPC/network setup chậm | Xem logs, dependency startup và resource hooks |
| **OptimizationStatus** không phải On | Runtime/feature không tương thích hoặc snapshot chưa sẵn sàng | Kiểm tra runtime, Region, State và SnapStart config |
| Invoke $LATEST không thấy SnapStart | SnapStart chỉ áp dụng published versions | Publish version và invoke qualifier/alias |
| Alias vẫn dùng behavior cũ | Alias chưa trỏ tới version mới | Kiểm tra alias routing và published version |
| **Runtime.Unsupported** hoặc cấu hình bị từ chối | Dùng OS-only runtime như provided.al2023 | Chuyển sang managed Java runtime nếu cần SnapStart |
| EFS attach thất bại khi bật SnapStart | EFS không tương thích | Bỏ SnapStart hoặc thay đổi storage design |
| Cấu hình /tmp lớn hơn 512 MB không tương thích | SnapStart giới hạn ephemeral storage | Giảm về 512 MB hoặc bỏ SnapStart |
| ID/secret bị trùng giữa environments | Giá trị unique được tạo trong init và snapshot bị nhân bản | Sinh sau restore/trong handler, dùng CSPRNG hoặc ID service |
| DB/HTTP connection lỗi sau restore | Socket hoặc pool state đã stale | Validate/reconnect trong hook hoặc lazy trong handler |
| Credentials hết hạn | Cached temporary credentials được tạo trong init | Dùng AWS SDK default credential provider chain |
| CRaC hook không chạy | Resource không được import/register hoặc bị garbage collected | Kiểm tra component scan, registration và strong reference |
| Restore hook chạy chậm | Gọi mạng hoặc khởi tạo lớn trong afterRestore | Làm hook ngắn, trì hoãn công việc tới handler |
| Lambda OOM | MemorySize thấp hoặc heap/native memory tăng | Kiểm tra Max Memory Used, heap và native buffers |
| CPU-bound function chậm | Memory thấp làm CPU allocation thấp | Thử mức memory cao hơn và đo duration/cost |
| Tốn thời gian dù memory còn dư | Workload I/O/downstream-bound hoặc cold start | Đo network/downstream latency và restore riêng |
| /tmp hết chỗ | File tạm không được dọn hoặc workload cần storage lớn | Dọn file, stream dữ liệu hoặc thiết kế lại storage |
| Build SnapStart thành công nhưng latency không đổi | Đang gọi alias/version sai hoặc init không phải bottleneck | Kiểm tra qualifier, restore logs và phân tích latency |

### Phân tích log

Khi SnapStart được sử dụng, xem các log lifecycle như **RESTORE_REPORT** và log init/report. Tách ba phần:

1. **Init/snapshot**: chi phí khởi tạo khi publish version.
2. **Restore**: thời gian khôi phục snapshot và chạy afterRestore.
3. **Invoke**: thời gian Function xử lý event và gọi downstream.

Nếu chỉ nhìn Duration của handler, bạn có thể bỏ qua restore latency hoặc thời gian startup xảy ra trong publish workflow.

## 16. Checklist trước khi bật SnapStart

- [ ] Runtime Java nằm trong danh sách managed runtime được SnapStart hỗ trợ.
- [ ] Function không dùng OS-only runtime hoặc custom runtime ZIP không tương thích.
- [ ] Function được publish thành version; traffic gọi alias/version đó.
- [ ] SAM/CloudFormation có SnapStart ApplyOn: PublishedVersions.
- [ ] Không bật Provisioned Concurrency đồng thời trên cùng version.
- [ ] Không gắn EFS hoặc Amazon S3 Files theo cấu hình không tương thích.
- [ ] EphemeralStorage không vượt 512 MB.
- [ ] Không tạo unique ID, secret hoặc random seed trong init rồi dùng lại sau restore.
- [ ] AWS SDK dùng credential provider có khả năng refresh; không cache temporary credentials.
- [ ] Network connections được validate/reconnect sau restore hoặc trong handler.
- [ ] Spring @PostConstruct/static initialization không thực hiện side effect nghiệp vụ.
- [ ] CRaC Resource được register và giữ strong reference nếu có dùng hooks.
- [ ] afterRestore hoàn tất trong 10 giây.
- [ ] MemorySize được benchmark với payload/concurrency đại diện.
- [ ] Đã đo Init/Restore/Duration/Max Memory Used và p95/p99.
- [ ] Alias trỏ đúng version và rollback đã được chuẩn bị.

## 17. Bài tập thực hành

**Bài tập 1 — SnapStart lifecycle.** Vẽ sơ đồ publish version, init, beforeCheckpoint, snapshot, restore, afterRestore và invoke. Chỉ ra giai đoạn nào chạy lúc deploy và giai đoạn nào chạy khi có traffic.

**Bài tập 2 — Runtime compatibility.** Một ứng dụng Spring Cloud Function chạy trên Java 21 managed runtime. Một ứng dụng khác là native image ZIP trên provided.al2023. Xác định ứng dụng nào có thể dùng SnapStart và giải thích vì sao.

**Bài tập 3 — Version và alias.** Bật SnapStart, publish version mới và tạo alias live. Viết các lệnh CLI kiểm tra SnapStart OptimizationStatus và invoke alias. Giải thích vì sao invoke $LATEST không kiểm chứng SnapStart.

**Bài tập 4 — CRaC hooks.** Viết một Resource quản lý JDBC pool. Đóng connection không thể resume trong beforeCheckpoint và validate/reconnect trong afterRestore. Đảm bảo hook sau restore không vượt 10 giây.

**Bài tập 5 — Weak reference.** Giải thích vì sao đăng ký một anonymous Resource rồi bỏ reference có thể khiến hook không chạy. Thiết kế Spring singleton bean giữ strong reference.

**Bài tập 6 — Uniqueness.** Một static UUID được tạo trong @PostConstruct. Mô tả cách nhiều execution environments restore từ cùng snapshot có thể dùng chung UUID. Chuyển việc sinh ID vào handler hoặc một cơ chế cấp ID phù hợp.

**Bài tập 7 — Connection recovery.** Ứng dụng mở JDBC connection trong init rồi snapshot. Thiết kế kiểm tra connection sau restore và chiến lược lazy reconnect nếu database chưa sẵn sàng.

**Bài tập 8 — Memory tuning.** Đo function tại 512, 1.024, 1.769 và 3.538 MB. So sánh duration, memory, throughput và cost. Giải thích vì sao mức memory cao hơn có thể rẻ hơn nếu giảm thời gian chạy đủ nhiều.

**Bài tập 9 — Ephemeral storage.** Một function cần 2 GB /tmp để xử lý file. Giải thích vì sao cấu hình đó không dùng được với SnapStart và đề xuất một thiết kế stream/chia file hoặc storage khác.

**Bài tập 10 — Spring integration.** Viết FunctionInvoker bean, đặt spring_cloud_function_definition và bật SnapStart trong SAM. Xác minh FunctionCatalog, published version và alias.

**Bài tập 11 — Restore timeout.** Một afterRestore hook gọi API ngoài và mất 12 giây. Phân tích lỗi và thiết kế lại để hook hoàn tất trong giới hạn, còn phần việc chậm chạy trong handler.

**Bài tập 12 — Benchmark.** Thiết kế thử nghiệm so sánh managed Java runtime không SnapStart, Java runtime có SnapStart và Provisioned Concurrency. Đo p50/p95/p99, restore, billed duration, memory và chi phí.

### Ghi nhớ

- **SnapStart** tạo snapshot khi publish version và khôi phục execution environment từ snapshot để giảm init lặp lại.
- Chỉ invoke **published version hoặc alias trỏ đến version**; $LATEST không sử dụng SnapStart.
- SnapStart hỗ trợ managed Java runtime từ Java 11 trở lên; **provided.al2023/OS-only custom runtime** không được hỗ trợ.
- Không kết hợp SnapStart với Provisioned Concurrency, EFS, Amazon S3 Files hoặc EphemeralStorage lớn hơn 512 MB.
- Java **CRaC Resource** cung cấp beforeCheckpoint/afterRestore; giữ strong reference và hoàn thành afterRestore trong 10 giây.
- Không tạo unique IDs, secrets hoặc random seed trong init rồi giả định chúng duy nhất sau restore.
- Connection mạng và temporary credentials có thể stale; validate/reconnect và dùng credential provider có khả năng refresh.
- MemorySize từ 128 đến 10.240 MB điều khiển cả memory và CPU; 1.769 MB tương đương một vCPU. EphemeralStorage là /tmp riêng, từ 512 đến 10.240 MB.
- Tuning bằng workload thật, so sánh restore, handler duration, Max Memory Used, p95/p99 và tổng chi phí trước khi quyết định.

### Tài liệu tham khảo

- [AWS Lambda — Improving startup performance with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html): runtime support, published versions, limitations và compatibility.
- [AWS Lambda — Activating and managing SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-activate.html): bật SnapStart bằng console/CLI, version state, snapshot và AWS SAM.
- [AWS Lambda — Runtime hooks for Java](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-runtime-hooks-java.html): CRaC Resource, beforeCheckpoint, afterRestore và registration.
- [AWS Lambda — Handling uniqueness with SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-uniqueness.html): unique values, randomness và execution environment clones.
- [AWS Lambda — SnapStart best practices](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-best-practices.html): networking, credentials và startup optimization.
- [AWS Lambda — Troubleshooting SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart-troubleshooting.html): restore timeout, initialization và snapshot failures.
- [AWS Lambda — Configure function memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html): memory range, CPU allocation và memory tuning.
- [AWS Lambda — Configure ephemeral storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html): /tmp từ 512 MB đến 10.240 MB.
- [AWS SAM — AWS::Serverless::Function](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-resource-function.html): SnapStart, AutoPublishAlias và version publishing.
- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker, FunctionCatalog, routing và deployment.

