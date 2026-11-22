# Kiến trúc OCI Functions và Fn Project

## 1. Mục tiêu và vị trí trong OCI

Trong chương **Containers và Functions** của module **CLOUD_PROVIDERS_ORACLE**, OCI Functions giúp triển khai logic ứng dụng theo từng hàm và thực thi khi có yêu cầu. Để vận hành được trên OCI, cần hiểu cả mã nguồn, artifact triển khai, tenancy, compartment, IAM, VCN, quan sát hệ thống và tài nguyên đích như Object Storage hoặc cơ sở dữ liệu Oracle.

Sau bài học, người học có thể:

- Giải thích quan hệ giữa OCI Functions, Fn Project, Fn Server, Fn CLI và FDK.
- Phân biệt application, function, invocation và trigger.
- Mô tả luồng build, deploy và invoke của hàm dùng container image.
- Phân biệt đường gọi hàm với đường hàm truy cập tài nguyên trong VCN.
- Thiết kế phân quyền, quản lý trạng thái, khả năng mở rộng và quan sát.
- Thực hành một hàm Java qua Fn Server cục bộ rồi xác định cấu hình cần khi triển khai lên OCI.

## 2. OCI Functions và Fn Project có quan hệ gì?

**OCI Functions** là nền tảng Functions as a Service do Oracle quản lý, được xây dựng dựa trên engine mã nguồn mở **Fn Project**. Người phát triển cung cấp logic và cấu hình; dịch vụ quản lý hạ tầng thực thi, tiếp nhận yêu cầu và mở rộng môi trường chạy. Xem [Overview of Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm).

Phân biệt các thành phần:

| Thành phần | Vai trò | Người học tương tác như thế nào? |
| --- | --- | --- |
| OCI Functions | Dịch vụ chạy hàm được quản lý trên OCI | Console, API, SDK, OCI CLI hoặc Fn CLI |
| Fn Project | Nền tảng serverless mã nguồn mở | Mô hình phát triển và bộ công cụ |
| Fn Server | Engine quản lý và thực thi hàm trong môi trường Fn | Chạy cục bộ để phát triển hàm dùng image |
| Fn CLI | Công cụ dòng lệnh `fn` | Khởi tạo, build, deploy, quản lý context và invoke |
| FDK | Function Development Kit cho một ngôn ngữ | Chuyển dữ liệu invocation tới handler và trả kết quả |
| Handler | Hàm hoặc phương thức chứa logic nghiệp vụ | Mã Java, Python hoặc ngôn ngữ được hỗ trợ |

Fn Server có thể chạy trong môi trường do người dùng quản lý. Với OCI Functions, người học sử dụng dịch vụ thay vì tự triển khai một cụm Fn Server để vận hành dịch vụ đó. Các khác biệt về endpoint, xác thực OCI và tính năng riêng được mô tả trong [Differences between OCI Functions and Fn Project](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsdiffswithfn.htm).

### 2.1. Hai mô hình artifact cần phân biệt

OCI Functions hiện hỗ trợ hai hướng triển khai:

| Khía cạnh | Hàm dùng container image | Hàm code-only |
| --- | --- | --- |
| Artifact người phát triển cung cấp | Container image | Archive chứa mã và dependency |
| Runtime | Được đóng trong image | Chọn managed runtime được hỗ trợ |
| Quy trình registry | Build và publish image lên OCIR | Không yêu cầu người phát triển tự publish image |
| Trách nhiệm cập nhật | Quản lý mã, dependency và các thành phần trong image | Quản lý mã, dependency và lựa chọn cập nhật runtime |
| Mục đích phù hợp | Cần kiểm soát base image, thư viện hệ thống, chuỗi build | Muốn triển khai với managed runtime phù hợp |

Bài học dùng **mô hình container image** để giải thích quan hệ với Fn Project và thực hành Java. Không nên suy rằng mọi workflow của OCI Functions đều yêu cầu người học tự viết Dockerfile hoặc push image. Xem [About Code-only Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functions-codeonly-about.htm).

## 3. Application, function, invocation và trigger

### 3.1. Application là phạm vi cấu hình chung

Một **application** nhóm các function liên quan và cung cấp ngữ cảnh cấu hình chung. Trong OCI Functions, application gắn với lựa chọn subnet, cấu hình và phạm vi cô lập runtime giữa các application. Xem [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

Ví dụ, application `order-events` có thể chứa `validate-order` và `create-order-summary`. Nên nhóm các hàm có nhu cầu cấu hình và quản trị tương thích; việc cùng thuộc một nhóm nghiệp vụ chưa đủ để bỏ qua khác biệt về quyền hoặc mạng.

### 3.2. Function là định nghĩa có thể triển khai

Một **function** có mã thực thi và metadata như nguồn artifact, memory và timeout. Tên function, function OCID và image version là các định danh phục vụ những mục đích khác nhau.

Ví dụ, function `create-order-summary` có thể được cập nhật sang một image mới nhưng vẫn giữ vai trò nghiệp vụ đó. Hồ sơ phát hành cần ghi cả định danh function lẫn artifact đã được duyệt.

### 3.3. Invocation là một lần gọi

**Invocation** là một yêu cầu thực thi function. Một function có thể nhận nhiều invocation theo thời gian hoặc đồng thời. Payload của invocation là dữ liệu từng lần gọi; cấu hình function là dữ liệu vận hành dùng cho nhiều lần gọi.

### 3.4. Trigger là nguồn phát sinh yêu cầu

**Trigger** là tác động khiến yêu cầu gọi hàm được gửi đi. Function có thể được gọi trực tiếp hoặc được tích hợp với các nguồn sự kiện phù hợp.

Quan hệ giữa bốn khái niệm được mô tả trong [OCI Functions Concepts](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsconcepts.htm).

Ví dụ thiết kế:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Application | `order-events` |
| Function | `create-order-summary` |
| Trigger | Sự kiện object mới cần xử lý |
| Payload | Namespace, bucket, object name và mã sự kiện |
| Kết quả | Bản tóm tắt được ghi vào nơi lưu trữ quy định |

Payload nên mang tham chiếu tới dữ liệu lớn. Một function nhận “địa chỉ object cần xử lý” có thể tải đúng dữ liệu khi cần, thay vì mọi tầng trung gian đều phải mang toàn bộ nội dung object.

## 4. Kiến trúc tổng thể: từ mã nguồn tới môi trường chạy

Sơ đồ dưới đây mô tả **luồng dùng container image**. Các hộp biểu diễn trách nhiệm logic, không phải một thiết kế máy chủ nội bộ mà người dùng phải tự xây dựng.

~~~mermaid
flowchart TB
    subgraph DEV["Môi trường phát triển hoặc CI"]
        CODE["Mã Java và func.yaml"] --> CLI["Fn CLI và context"]
        CLI --> BUILD["Build bằng FDK"]
    end

    BUILD -->|Push image| OCIR["OCIR"]
    CLI -->|Tạo hoặc cập nhật metadata| META["Application và function trên OCI"]

    CALL["Caller hoặc dịch vụ tích hợp"] -->|Yêu cầu gọi đã xác thực| INVOKE["Invoke endpoint"]
    INVOKE --> EXEC["Môi trường thực thi do OCI quản lý"]
    META --> EXEC
    OCIR -->|Chuẩn bị image khi cần| EXEC
    EXEC --> FDK["FDK → handler Java"]

    FDK --> PRIVATE["Tài nguyên trong VCN"]
    FDK --> SERVICE["Dịch vụ OCI được cấp quyền"]
    EXEC --> OBS["Logs, metrics và tracing khi cấu hình"]
~~~

Có thể đọc kiến trúc theo ba luồng:

1. **Luồng phát hành:** build artifact, publish artifact, tạo hoặc cập nhật định nghĩa function.
2. **Luồng thực thi:** xác thực yêu cầu, chuẩn bị hoặc sử dụng lại môi trường chạy, gọi handler, xử lý kết quả.
3. **Luồng truy cập phụ thuộc:** mã trong function kết nối tới dịch vụ khác bằng đường mạng và danh tính phù hợp.

Ví dụ, CI có thể deploy thành công nhưng function vẫn không đọc được Object Storage. Khi đó cần kiểm tra quyền của function và đường truy cập tới Object Storage; kết quả deploy chỉ xác nhận một phần của kiến trúc.

### 4.1. Control plane và luồng invocation

Trong bài, **control plane** chỉ nhóm thao tác quản lý tài nguyên: tạo application, đặt subnet, cập nhật function, cấu hình memory và timeout.

Luồng invocation dùng endpoint của function để gửi dữ liệu thực thi. Endpoint API quản lý theo region và invoke endpoint của function phục vụ hai mục đích khác nhau. Khi tích hợp, lấy endpoint từ metadata hoặc công cụ được hỗ trợ, tránh tự ghép từ tên function. Oracle mô tả cách lấy thông tin bằng `fn inspect function` trong [Differences between OCI Functions and Fn Project](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsdiffswithfn.htm).

### 4.2. Trách nhiệm của người dùng và dịch vụ

| Vấn đề | Trách nhiệm chính |
| --- | --- |
| Cấp phát và vận hành máy chủ thực thi của dịch vụ | OCI Functions |
| Logic nghiệp vụ và kiểm tra đầu vào | Nhóm phát triển |
| Dependency và base image do nhóm đóng gói | Nhóm sở hữu image |
| IAM, compartment, subnet và route | Nhóm triển khai OCI |
| Giữ artifact, phát hành và phương án rollback | Nhóm vận hành và CI/CD |
| Mục tiêu độ trễ, chi phí, mức tải và cảnh báo | Nhóm sở hữu ứng dụng |

Serverless giảm việc quản lý máy chủ. Các quyết định về dữ liệu, quyền, kết nối và hành vi khi lỗi vẫn cần được thiết kế.

## 5. FDK làm gì khi chạy một hàm Java?

FDK cung cấp phần tích hợp giữa giao thức thực thi của Fn và mã viết theo ngôn ngữ. Với hàm dùng image, bộ công cụ có base image dành cho build, base image dành cho runtime và thư viện hỗ trợ handler. Xem [Function Development Kits](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionssupportedlanguageversions.htm).

Một luồng Java có thể được hiểu như sau:

~~~text
Payload invocation
    → FDK nhận và chuyển đổi đầu vào
    → gọi phương thức handler đã khai báo
    → nhận giá trị trả về hoặc lỗi
    → tạo phản hồi theo cơ chế của nền tảng
~~~

Ví dụ handler đơn giản:

~~~java
package com.example.fn;

public class HelloFunction {
    public String handleRequest(String input) {
        String name = (input == null || input.isEmpty()) ? "world" : input;
        return "Hello, " + name + "!";
    }
}
~~~

Điểm vào tương ứng:

~~~yaml
cmd: com.example.fn.HelloFunction::handleRequest
~~~

Đây là mô hình handler, không cần tự viết vòng lặp nhận yêu cầu hay khởi động một web server trong ví dụ. Một container chạy được độc lập chưa tự chứng minh nó đáp ứng cơ chế gọi hàm của Fn; với custom image cần bảo đảm tương thích theo yêu cầu nền tảng.

Ví dụ Java và cấu trúc project được giới thiệu trong [Introduction to Fn with Java](https://fnproject.io/tutorials/JavaFDKIntroduction/).

## 6. Vòng đời thực thi, cold start và khả năng mở rộng

### 6.1. Chuẩn bị môi trường và tái sử dụng

Ở lần gọi cần chuẩn bị môi trường mới, nền tảng phải dành tài nguyên thực thi và khởi tạo runtime. Với Java, quá trình khởi tạo còn liên quan tới JVM và các thành phần ứng dụng. Lần gọi có thể tận dụng môi trường còn sẵn thường tránh được một phần chi phí khởi tạo.

Oracle gọi việc chuẩn bị ban đầu là **cold start** và việc tận dụng hạ tầng còn sẵn là **hot start**. **Provisioned concurrency** giúp giữ sẵn năng lực thực thi cho mức đồng thời cấu hình. Xem [Reducing Initial Latency Using Provisioned Concurrency](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingprovisionedconcurrency.htm).

Hệ quả thiết kế:

- Không giả định mỗi invocation luôn có một môi trường mới.
- Không giả định cùng một môi trường sẽ tồn tại mãi.
- Không dùng biến tĩnh hoặc dữ liệu trong container làm bản ghi nghiệp vụ duy nhất.
- Chỉ tái sử dụng client hoặc cache khi việc đó an toàn và không làm rò dữ liệu giữa các lần gọi.

Ví dụ, một cache danh mục chỉ nên giúp tăng tốc; ứng dụng vẫn cần hoạt động đúng khi cache biến mất. Ngược lại, trạng thái “đơn hàng đã được thanh toán” phải nằm trong kho dữ liệu bền vững phù hợp.

### 6.2. Concurrency tác động tới cả hệ thống phía sau

**Concurrency** là số lần thực thi cùng lúc. Một function được mở rộng có thể tạo thêm nhiều kết nối tới cơ sở dữ liệu, nhiều yêu cầu tới API ngoài hoặc nhiều thao tác Object Storage.

Ví dụ ước lượng:

~~~text
Tốc độ đến:                    40 yêu cầu/giây
Thời gian xử lý trung bình:     0,5 giây
Mức đồng thời trung bình:       khoảng 40 × 0,5 = 20
~~~

Đây là phép ước lượng ở trạng thái ổn định, không phải cam kết cấp phát. Burst, độ biến động thời gian xử lý và retry có thể làm mức đồng thời thực tế tăng cao.

Nếu mỗi lần thực thi giữ nhiều connection, tổng số connection của toàn hệ thống có thể lớn hơn nhiều dự đoán từ một lần thử. Cần giới hạn tài nguyên phụ thuộc, đặt timeout cho từng thao tác và kiểm tra tải.

OCI Functions có giới hạn theo region về application, function, memory cho thực thi đồng thời và provisioned concurrency. Giá trị hiệu lực phụ thuộc tenancy; xem [Viewing Current Limit Values for OCI Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsviewinglimits.htm).

### 6.3. Memory và timeout

Memory ảnh hưởng khả năng xử lý của function và là một yếu tố khi đánh giá tài nguyên tiêu thụ. Timeout giới hạn thời gian thực thi; timeout ở caller hoặc tầng tích hợp còn có thể ngắn hơn.

Theo tài liệu hiện hành:

| Tham số | Giá trị cần biết |
| --- | --- |
| Timeout Sync mặc định | 30 giây |
| Timeout Sync tối đa | 300 giây |
| Timeout Detached tối đa | 3.600 giây |
| Memory cho ví dụ Java trong bài | Chọn 256 MB để bắt đầu đo |

Oracle khuyến nghị Java function có memory tối thiểu 256 MB. Khi đổi `func.yaml` phải redeploy để cấu hình có hiệu lực trên dịch vụ; cũng cần đối chiếu định nghĩa function đang triển khai. Xem [Changing Default Memory and Timeout Settings](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscustomizing.htm).

Trong dự án, nên đo thời gian khởi tạo, thời gian nghiệp vụ và bộ nhớ rồi chọn cấu hình. Việc tăng timeout không giải quyết được một truy vấn bị treo hoặc đường mạng cấu hình sai.

## 7. Sync, Detached và hợp đồng kết quả

OCI Functions hỗ trợ hai kiểu invocation:

| Kiểu | Hành vi phía caller | Cách quản lý kết quả |
| --- | --- | --- |
| Sync | Chờ function kết thúc và nhận phản hồi | Kết quả được trả cho caller |
| Detached | Nhận quyền điều khiển lại khi xử lý bắt đầu | Function xử lý kết quả; có thể cấu hình destination phù hợp |

Với Detached, HTTP `202` không có nghĩa nghiệp vụ đã hoàn tất. Cần định nghĩa nơi lưu trạng thái, kết quả và cách theo dõi lỗi. Fn CLI phù hợp phát triển; Oracle không khuyến nghị dùng công cụ này để invoke trong production. Xem [Invoking Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsinvokingfunctions.htm).

Ví dụ:

- Kiểm tra một giá trị rồi trả kết quả ngay có thể dùng Sync.
- Xử lý dữ liệu lâu hơn có thể xem xét Detached nếu giới hạn và cách nhận kết quả phù hợp.
- Một workflow nhiều bước cần trạng thái rõ ràng, cơ chế phục hồi và điều phối phù hợp.

Không nên xem Detached là cam kết “xử lý đúng một lần”. Caller hoặc dịch vụ tích hợp có thể thử lại sau lỗi; thiết kế nghiệp vụ phải chịu được các lần gọi lặp khi chúng xảy ra.

## 8. VCN: đường gọi hàm và đường hàm đi ra

### 8.1. Subnet của application phục vụ môi trường thực thi

Khi tạo application, người triển khai chọn VCN, subnet và kiến trúc tính toán. Image phải tương thích với kiến trúc application; ví dụ image dành cho AMD64 không đủ để chạy trên application chỉ dùng ARM.

Regional subnet là lựa chọn được Oracle khuyến nghị để thuận tiện hơn cho yêu cầu sẵn sàng giữa các availability domain. Xem [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

Ví dụ các đường kết nối cần thiết:

| Đích mà function truy cập | Các yếu tố phải xác định |
| --- | --- |
| Cơ sở dữ liệu có private endpoint | DNS, route, NSG/security list, cổng kết nối và xác thực DB |
| Dịch vụ OCI qua đường riêng phù hợp | Service Gateway, route và IAM |
| API công khai bên ngoài | Đường egress phù hợp, DNS, HTTPS và timeout |
| Artifact của hàm dùng image | Khả năng dịch vụ truy cập image hợp lệ |

Đây là danh sách để thiết kế kết nối. Mỗi đường cần đối chiếu tài liệu mạng của dịch vụ đích và cấu hình thật trong tenancy.

### 8.2. Private subnet không tự khóa invoke endpoint

Điểm quan trọng: **đặt application trong private subnet không tự ngăn việc truy cập invoke endpoint từ Internet**. Oracle yêu cầu dùng IAM để kiểm soát quyền invoke; có thể xem thêm điều kiện nguồn mạng khi phù hợp. Xem [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm).

Cần phân biệt:

~~~text
Caller → invoke endpoint:
    Kiểm tra danh tính caller, quyền invoke và kiến trúc điểm vào.

Function → tài nguyên đích:
    Kiểm tra mạng của môi trường chạy và quyền truy cập tài nguyên đó.
~~~

Nếu dùng API Gateway làm điểm vào cho ứng dụng, cần thiết kế riêng xác thực client, quyền Gateway gọi function và hợp đồng HTTP. Việc có Gateway không thay thế quyền function đọc bucket hoặc kết nối cơ sở dữ liệu.

## 9. IAM: ba danh tính, ba phạm vi quyền

### 9.1. Danh tính triển khai, danh tính gọi và danh tính thực thi

| Chủ thể | Nhu cầu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Developer hoặc CI | Tạo/cập nhật application, function và artifact | Có được deploy trong compartment này không? |
| Caller | Gửi invocation | Có được gọi function này không? |
| Function đang chạy | Gọi dịch vụ khác | Có được đọc object hoặc secret đích không? |

Không suy từ quyền quản trị của developer sang quyền runtime. Người deploy có thể đọc bucket nhưng function chưa có quyền đọc; người invoke cũng không tự nhận được quyền quản lý function.

Các quyền của workflow còn liên quan tới mạng, OCIR hoặc quan sát. Nên lập policy theo tài nguyên cần dùng và phạm vi compartment, thay vì mặc định cấp quyền rộng trên tenancy. Xem [Creating Policies to Control Access to Network and Function-Related Resources](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingpolicies.htm).

### 9.2. Ví dụ quyền invoke một function

Giả định nhóm `FunctionCallers` thuộc domain `Default` và function nằm trong compartment `AppDev`:

~~~text
Allow group 'Default'/'FunctionCallers' to use fn-invocation in compartment AppDev where target.function.id = '<FUNCTION_OCID>'
~~~

Thay `<FUNCTION_OCID>` bằng giá trị thật. Nếu dùng Fn CLI để tra cứu tài nguyên theo tên, caller còn có thể cần quyền đọc metadata tương ứng; quyền thực thi và quyền tra cứu phục vụ các thao tác khác nhau.

Phải xét tổng các policy đang cấp. Một policy giới hạn một function không làm mất quyền đã được cấp bởi policy khác rộng hơn. Các mẫu kiểm soát theo function hoặc application nằm trong [Controlling Access to Invoke and Manage Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsrestrictinguseraccess.htm).

### 9.3. Resource principal cho function gọi dịch vụ OCI

Một function chạy trên OCI có thể dùng **resource principal** qua OCI SDK. Dynamic group xác định function thuộc nhóm nào; policy cấp quyền trên tài nguyên đích.

Ví dụ rule cho một function cụ thể:

~~~text
ALL {resource.type = 'fnfunc', resource.id = '<FUNCTION_OCID>'}
~~~

Ví dụ policy cho dynamic group `OrderFunctions` đọc object trong bucket đã chỉ định:

~~~text
Allow dynamic-group 'Default'/'OrderFunctions' to read objects in compartment AppData where target.bucket.name = 'order-input'
~~~

Đây là quyền đọc object; nếu nghiệp vụ cần ghi kết quả thì phải thiết kế thêm quyền ghi phù hợp. Không mở rộng quyền khi chưa xác định thao tác cần thiết.

Resource principal giúp mã trên OCI xác thực theo danh tính tài nguyên, tránh đóng gói API private key của developer vào image. SDK cần được cấu hình dùng resource principal provider. Xem [Accessing Other Oracle Cloud Infrastructure Resources from Running Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm).

## 10. Thực hành Fn Project với Java trên máy cục bộ

Mục tiêu phần này là quan sát các thành phần Fn CLI, Fn Server, FDK và handler trong một luồng hoàn chỉnh. Các lệnh là hướng dẫn để người học thực thi, không phải kết quả đã chạy trên tenancy.

### 10.1. Điều kiện chuẩn bị

Dùng môi trường Linux hoặc WSL phù hợp, đã có:

- Container engine tương thích và hoạt động.
- Fn CLI phù hợp với runtime Java định sử dụng.
- Kết nối tải base image và dependency của project.
- Cổng `8080` cục bộ chưa bị dịch vụ khác chiếm.

Trên terminal thứ nhất, khởi động Fn Server:

~~~bash
fn start
~~~

Giữ terminal này chạy. Fn Server cục bộ cung cấp endpoint phát triển tại `http://localhost:8080`. Xem [Using Fn Server to Develop Functions Locally](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingwithfnserverlocally.htm).

### 10.2. Tạo context cục bộ riêng

Ở terminal thứ hai:

~~~bash
fn create context fn-architecture-local --provider default
fn use context fn-architecture-local
fn update context api-url http://localhost:8080
fn update context registry fnlocal
fn list contexts
~~~

Context xác định CLI sẽ gọi endpoint nào và dùng registry prefix nào. Trước deploy, kiểm tra dấu hiệu context hiện tại để tránh chạy nhầm lệnh lên một môi trường khác. Tham khảo [Fn Development with Multiple Contexts](https://fnproject.io/tutorials/basics/UsingContexts/).

### 10.3. Khởi tạo Java function

Trong thư mục lab mới:

~~~bash
fn init --help
fn init --runtime java17 hello-java
cd hello-java
~~~

`java17` là ví dụ runtime; đối chiếu các lựa chọn mà phiên bản CLI đang dùng hỗ trợ. Dùng project do CLI sinh để giữ đồng bộ các phiên bản FDK và base image. Hướng dẫn xác định runtime nằm trong [Function Development Kits](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionssupportedlanguageversions.htm).

Các thành phần chính của project:

~~~text
hello-java/
├── func.yaml
├── pom.xml
└── src/
    ├── main/java/com/example/fn/HelloFunction.java
    └── test/java/com/example/fn/HelloFunctionTest.java
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `func.yaml` | Metadata phát triển và cấu hình function |
| `pom.xml` | Dependency, build Java và hỗ trợ kiểm thử |
| `HelloFunction.java` | Handler chứa logic |
| `HelloFunctionTest.java` | Kiểm thử được skeleton tạo để bắt đầu |

Có thể dùng handler ở mục 5. Nếu sửa hành vi trả về, cần cập nhật kiểm thử tương ứng trong project thực hành.

Trong `func.yaml`, kiểm tra các field sau và đặt memory, timeout cho lab:

~~~yaml
schema_version: 20180708
name: hello-java
version: 0.0.1
runtime: java17
memory: 256
timeout: 30
cmd: com.example.fn.HelloFunction::handleRequest
~~~

Đây là **trích đoạn field**, không phải yêu cầu thay toàn bộ file. Giữ các giá trị `build_image`, `run_image` và cấu hình dependency phù hợp do CLI tạo. Không sao chép cố định một tag FDK cũ từ bài học vào mọi project mới.

### 10.4. Deploy và invoke cục bộ

~~~bash
fn create app fn-architecture-local
fn deploy --app fn-architecture-local --local
printf '%s' 'OCI' | fn invoke fn-architecture-local hello-java
~~~

Với handler mục 5, kết quả mong đợi:

~~~text
Hello, OCI!
~~~

Thử đầu vào rỗng:

~~~bash
printf '%s' '' | fn invoke fn-architecture-local hello-java
~~~

Kết quả mong đợi:

~~~text
Hello, world!
~~~

Ở bước deploy, CLI build image và đăng ký function với Fn Server cục bộ. Invocation đi qua Fn Server và FDK tới handler. Workflow Java được giới thiệu trong [Introduction to Fn with Java](https://fnproject.io/tutorials/JavaFDKIntroduction/).

### 10.5. Giới hạn của kết quả local

Thành công cục bộ giúp kiểm tra handler và đóng gói. Nó chưa xác minh IAM, VCN, hạn mức hoặc kết nối database trên OCI.

Resource principal của function trên OCI không được kiểm chứng bằng một lần gọi Fn Server local. Với phần code gọi OCI SDK, có thể dùng mock hoặc cấu hình xác thực phát triển riêng phù hợp; không nhúng khóa cá nhân vào artifact đưa lên cloud. Giới hạn này được nêu trong [Using Fn Server to Develop Functions Locally](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsusingwithfnserverlocally.htm).

## 11. Chuyển luồng phát triển sang OCI Functions

### 11.1. Chuẩn bị tài nguyên cloud

Trước khi deploy, cần có:

| Tài nguyên hoặc cấu hình | Nội dung cần xác nhận |
| --- | --- |
| Region và compartment | Nơi tạo application, function |
| VCN và subnet | Phù hợp với tài nguyên mà function sẽ truy cập |
| Application | Đã tạo trên OCI, có kiến trúc tương thích image |
| IAM cho developer/CI | Đủ thao tác function, mạng và artifact cần thiết |
| OCIR | Registry và repository nhận image |
| Xác thực công cụ | OCI profile và credential đăng nhập registry |
| Logging | Có nơi lưu log để xem lần invoke đầu |

Trong lab, tạo application `fn-architecture-oci` qua Console, chọn VCN và subnet đã chuẩn bị. Nếu image được build cho AMD64, chọn kiến trúc application tương thích; khi dùng multi-architecture application phải chuẩn bị artifact tương ứng.

Cách tạo application và lựa chọn kiến trúc được mô tả trong [Creating an Application](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatingapps-task.htm).

### 11.2. Tạo context OCI riêng

Ví dụ Bash cho region Ashburn:

~~~bash
export FUNCTIONS_COMPARTMENT_OCID='REPLACE_WITH_FUNCTIONS_COMPARTMENT_OCID'
export IMAGE_COMPARTMENT_OCID='REPLACE_WITH_IMAGE_COMPARTMENT_OCID'
export TENANCY_NAMESPACE='REPLACE_WITH_REAL_NAMESPACE'
export REGISTRY='ocir.us-ashburn-1.oci.oraclecloud.com'

fn create context fn-architecture-oci --provider oracle
fn use context fn-architecture-oci
fn update context api-url https://functions.us-ashburn-1.oci.oraclecloud.com
fn update context oracle.compartment-id "$FUNCTIONS_COMPARTMENT_OCID"
fn update context oracle.image-compartment-id "$IMAGE_COMPARTMENT_OCID"
fn update context oracle.profile DEFAULT
fn update context registry "$REGISTRY/$TENANCY_NAMESPACE/learning"
fn list contexts
~~~

Thay các placeholder và bảo đảm profile `DEFAULT` được cấu hình cho đúng tenancy, người dùng và region. `oracle.compartment-id` là nơi chứa function; `oracle.image-compartment-id` là nơi chứa repository image. Xem [Creating an Fn Project CLI Context to Connect to Oracle Cloud Infrastructure](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionscreatefncontext.htm).

Với function `hello-java` và registry prefix như trên, dự kiến repository là `learning/hello-java`. Kiểm tra tên và compartment thực tế mà workflow sử dụng, đặc biệt khi repository cùng tên đã tồn tại.

### 11.3. Xác thực OCIR và deploy

Đăng nhập registry theo username đầy đủ của tenancy và auth token:

~~~bash
export OCIR_USERNAME='REPLACE_WITH_FULL_OCIR_USERNAME'
docker login "$REGISTRY" --username "$OCIR_USERNAME"
~~~

Khi được hỏi password, nhập OCI auth token. Đăng nhập registry phục vụ push image; provider `oracle` và OCI profile phục vụ các API của OCI. Hai phần xác thực cần được chuẩn bị riêng. Có thể làm theo [Functions QuickStart on Cloud Shell Using Container Images](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsquickstartcloudshell.htm).

Từ thư mục `hello-java`, với context OCI đã được kiểm tra:

~~~bash
fn deploy --app fn-architecture-oci
fn inspect function fn-architecture-oci hello-java
printf '%s' 'OCI' | fn invoke fn-architecture-oci hello-java
~~~

Kết quả mong đợi vẫn là `Hello, OCI!`. Tuy nhiên, lần gọi này kiểm tra thêm đường tích hợp cloud: API, artifact, application và môi trường chạy trên OCI.

Nên ghi lại function OCID, region, application, image reference/digest của bản triển khai, mã commit và kết quả invoke. Các thông tin đó giúp đối chiếu khi phát hành lại hoặc điều tra thay đổi.

### 11.4. Đọc kết quả theo từng tầng

| Kết quả quan sát | Phần đã có bằng chứng | Phần vẫn cần kiểm tra nếu nghiệp vụ yêu cầu |
| --- | --- | --- |
| Build thành công | Mã và dependency đóng gói được | IAM và mạng trên OCI |
| Push thành công | Danh tính phát hành đưa được image lên OCIR | Khả năng thực thi function |
| Deploy thành công | Định nghĩa function được tạo/cập nhật | Đường kết nối tới dữ liệu nghiệp vụ |
| Invoke trả đúng lời chào | Đường gọi và handler hoạt động | Quyền đọc bucket, secret hoặc database |
| Gọi dịch vụ đích thành công | Luồng tích hợp cụ thể hoạt động | Tải đồng thời, lỗi và phục hồi |

Bảng này giúp tránh kết luận một bài thử “Hello World” đã xác minh toàn bộ hệ thống production.

## 12. Cấu hình, secret và trạng thái

### 12.1. Cấu hình dùng chung và cấu hình từng hàm

Có thể đặt custom configuration ở application hoặc function. Cấu hình function ghi đè giá trị cùng tên ở application; các giá trị cũng được cung cấp dưới dạng biến môi trường. Xem [Passing Custom Configuration Parameters to Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionspassingconfigparams-about.htm).

Ví dụ:

~~~bash
fn config app fn-architecture-oci APP_ENV dev
fn config function fn-architecture-oci hello-java MESSAGE_PREFIX Hello
~~~

Các lệnh cấu hình được mô tả trong [Specifying Custom Configuration Parameters](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionspassingconfigparams.htm). Việc đặt `MESSAGE_PREFIX` không tự làm thay đổi handler mẫu; mã phải đọc giá trị đó nếu cần sử dụng.

Nên tách giá trị vận hành khỏi dữ liệu của từng invocation:

| Loại | Ví dụ |
| --- | --- |
| Cấu hình vận hành | Tên bucket đích, mức log, endpoint dịch vụ |
| Dữ liệu từng lần gọi | Order ID, object name, mã sự kiện |
| Secret | Mật khẩu DB, token API bên ngoài |
| Trạng thái bền vững | Kết quả xử lý, khóa chống lặp, tiến độ workflow |

Secret nên được quản lý qua cơ chế như OCI Vault phù hợp với kiến trúc. Không đưa secret vào mã nguồn, image hoặc log; function chỉ lấy giá trị khi được cấp quyền và có nhu cầu.

### 12.2. Stateless và idempotency

**Stateless** nghĩa là tính đúng của invocation không phụ thuộc vào việc lần gọi trước còn giữ dữ liệu trong cùng môi trường chạy.

**Idempotency** nghĩa là xử lý lặp cùng một yêu cầu không tạo thêm tác động nghiệp vụ ngoài ý muốn.

Ví dụ thiết kế xử lý đơn hàng:

~~~text
Nhận event có eventId
    → xác định khóa nghiệp vụ
    → ghi nhận hoặc kiểm tra khóa bằng thao tác nhất quán
    → nếu đã hoàn tất: trả kết quả đã có
    → nếu chưa: thực hiện và lưu kết quả
~~~

Đây là mô hình khái niệm. Nếu tách bước “kiểm tra” và “ghi nhận” thiếu tính nguyên tử, hai invocation đồng thời vẫn có thể tạo bản ghi trùng.

Với Oracle Database, có thể dùng unique constraint và transaction phù hợp cho khóa nghiệp vụ. Khi tác động nằm ở một API bên ngoài, cần xét thêm khóa idempotency của API hoặc cơ chế phối hợp; một transaction cục bộ không tự bảo đảm tính nguyên tử xuyên hai hệ thống.

## 13. Quan sát: logs, metrics và tracing

### 13.1. Log để giải thích một lần xử lý

Bật OCI Logging cho application và xác định log group phù hợp. Log nên chứa dữ liệu giúp nối invocation với nghiệp vụ, chẳng hạn mã yêu cầu hoặc mã sự kiện, bước xử lý và thời gian thao tác.

Ví dụ cấu trúc log do ứng dụng chủ động thiết kế:

~~~json
{
  "eventId": "evt-order-001",
  "operation": "create-summary",
  "status": "completed",
  "durationMs": 84
}
~~~

Không cần ghi toàn bộ payload để điều tra mọi vấn đề. Nên chọn các trường cần thiết và kiểm soát dữ liệu nhạy cảm.

OCI Functions hỗ trợ cấu hình định dạng dòng log; để khai thác các trường JSON, cần phát log hợp lệ và chọn định dạng phù hợp. Xem [Storing and Viewing Function Logs](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsexportingfunctionlogfiles.htm).

### 13.2. Metrics để nhìn xu hướng

Namespace metrics của Functions là `oci_faas`. Các chỉ số cho biết số invocation, thời gian thực thi, phản hồi lỗi và hiện tượng throttling. Xem [Function Metrics](https://docs.oracle.com/en-us/iaas/Content/Functions/Reference/functionsmetrics.htm).

| Quan sát | Câu hỏi vận hành |
| --- | --- |
| Invocation tăng | Đây là tải thật, retry hay vòng lặp sự kiện? |
| Thời gian thực thi tăng | Chậm trong handler, khởi tạo hay dịch vụ đích? |
| Tỷ lệ lỗi tăng | Lỗi đầu vào, quyền, tài nguyên hay lỗi nghiệp vụ? |
| Phản hồi `429` tăng | Có vượt năng lực hoặc hạn mức hiệu lực không? |
| Tải DB tăng cùng mức đồng thời | Có cần giới hạn connection và tốc độ nhận việc không? |

Nên đặt cảnh báo theo mục tiêu dịch vụ, kết hợp số lượng mẫu và độ dài cửa sổ quan sát. Một lỗi đơn lẻ và một tỷ lệ lỗi tăng kéo dài cần cách phản ứng khác nhau.

### 13.3. Tracing để tìm đoạn chậm

Khi bật tracing ở application và function phù hợp, có thể dùng APM để quan sát các bước thực thi. Tracing hữu ích khi tổng thời gian tăng nhưng log chưa cho biết tác vụ nào chiếm thời gian. Xem [Troubleshooting OCI Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionstroubleshooting.htm).

Khi đo hệ thống, tách ít nhất:

~~~text
Thời gian caller quan sát
    = thời gian các tầng trung gian
    + chờ và khởi tạo nếu có
    + thời gian xử lý function
    + truyền kết quả
~~~

Đây là cách phân rã để điều tra. Không coi thời gian handler đo bằng một đồng hồ trong code là toàn bộ độ trễ mà người dùng nhận thấy.

## 14. Chi phí, tính sẵn sàng và phục hồi

### 14.1. Ước lượng từ workload

Một mô hình sơ bộ cho khối lượng tài nguyên là:

~~~text
Khối lượng GB-giây
    ≈ số invocation × thời gian thực thi trung bình × memory tính theo GB
~~~

Ví dụ giả định có 100.000 lần gọi, mỗi lần chạy 0,2 giây và dùng mức memory 1 GB thì khối lượng tham khảo là 20.000 GB-giây. Đây là phép ước lượng kỹ thuật trước các quy tắc tính phí, không phải báo giá.

Khi lập ngân sách cần tính thêm các thành phần thật sự sử dụng: artifact, log, truy cập mạng, dịch vụ phụ thuộc và provisioned concurrency nếu bật. Tra bảng giá, điều kiện miễn phí và quy tắc tính phí có hiệu lực khi triển khai.

Các biện pháp kiểm soát nên gắn với nguyên nhân:

- Giảm thời gian chờ không cần thiết bằng timeout và tối ưu truy cập dữ liệu.
- Đo memory và độ trễ trước khi chọn cấu hình.
- Tránh phát log quá nhiều ở lưu lượng lớn.
- Giới hạn retry và phát hiện vòng lặp gọi hàm.
- Theo dõi tải vào database hoặc API có tính phí riêng.

Provisioned concurrency là một lựa chọn để xử lý yêu cầu độ trễ ban đầu. Cần đo mục tiêu p95/p99 và nhu cầu mức đồng thời trước khi quyết định cấu hình; không lấy một lần gọi “ấm” làm đại diện cho mọi trạng thái tải.

### 14.2. Sẵn sàng của function và của toàn luồng

Dịch vụ chạy hàm được quản lý không tự bảo đảm mọi phụ thuộc của ứng dụng đều sẵn sàng.

Ví dụ, function còn chạy nhưng database tạm không truy cập được. Thiết kế cần xác định timeout, cách trả lỗi, nơi ghi trạng thái chưa xử lý và điều kiện retry. Việc retry cần tôn trọng idempotency và giới hạn tải của database.

Nên đánh giá cả:

| Phạm vi | Nội dung cần chuẩn bị |
| --- | --- |
| Runtime | Memory, timeout, kiến trúc và hạn mức |
| Mạng | Subnet, route, DNS và kết nối tới đích |
| Dữ liệu | Tính nhất quán, sao lưu và khả năng phục hồi |
| Artifact | Bản phát hành còn truy cập được và có thể triển khai lại |
| Quan sát | Có log, metrics và cảnh báo đúng nơi |
| Region dự phòng nếu yêu cầu | Tài nguyên, artifact, cấu hình, quyền và dữ liệu tương ứng |

Một bản phục hồi cần đầy đủ hơn một file mã nguồn. Nên quản lý cấu hình bằng quy trình có thể tái lập và kiểm tra triển khai tại môi trường dự phòng theo mục tiêu của hệ thống.

## 15. Chẩn đoán theo tầng kiến trúc

| Triệu chứng | Tầng cần kiểm tra trước | Bằng chứng nên thu thập |
| --- | --- | --- |
| Local chạy, deploy OCI lỗi | Context, profile và quyền triển khai | Context hiện tại, region, compartment và thông báo lỗi |
| Push image lỗi | OCIR và credential phát hành | Repository đích, danh tính và lỗi push |
| Invoke bị từ chối | Danh tính caller và quyền invoke | Function OCID, policy áp dụng và mã yêu cầu |
| Khởi tạo runtime lỗi | Artifact, handler hoặc kiến trúc | Image đang dùng, `cmd`, dependency và log |
| Chỉ lần đầu chậm | Khởi tạo và cold start | Mẫu đo qua nhiều trạng thái, không chỉ một lần gọi |
| Gọi DB timeout | Mạng, DNS và dịch vụ DB | Điểm kết nối, thời gian chờ và cấu hình kết nối |
| Đọc bucket bị từ chối | Resource principal và quyền dữ liệu | Dynamic group, policy và bucket đích |
| Chạy lặp làm trùng dữ liệu | Hợp đồng nghiệp vụ | Event ID, khóa idempotency và transaction |
| Lưu lượng tăng kéo theo lỗi | Đồng thời và phụ thuộc | Metrics Functions, connection DB và tốc độ retry |

Bảng đưa ra hướng khoanh vùng, không thay thế việc đọc lỗi thực tế. Khi điều tra, ghi lại thời điểm, function OCID, bản triển khai và mã tương quan; loại bỏ secret trước khi chia sẻ log.

## 16. Khi nào nên chọn OCI Functions?

OCI Functions phù hợp khi có một đơn vị xử lý rõ ràng, được kích hoạt theo yêu cầu hoặc sự kiện, có thể hoàn tất trong giới hạn của nền tảng và quản lý trạng thái bền vững ở bên ngoài.

Cần đánh giá kỹ hơn với workload đòi hỏi tiến trình sống lâu, kết nối kéo dài, quyền điều khiển hệ điều hành sâu hoặc thời gian chạy vượt giới hạn. Khi đó có thể cân nhắc nền tảng container hay compute phù hợp theo yêu cầu cụ thể.

Với một thiết kế đã chọn Functions, các câu hỏi cốt lõi cần trả lời là:

1. Artifact là image hay archive, và ai chịu trách nhiệm cập nhật runtime?
2. Function thuộc application, compartment và region nào?
3. Ai deploy, ai invoke, function được phép truy cập dữ liệu nào?
4. Payload và kết quả được biểu diễn thế nào; có xử lý gọi lặp không?
5. Tải đồng thời tác động gì tới database, API và ngân sách?
6. Có đủ thông tin để phát hiện lỗi và triển khai lại bản đã được duyệt không?

Kiến trúc hoàn chỉnh nối được các quyết định đó với cùng một luồng nghiệp vụ. Fn Project cung cấp mô hình và công cụ phát triển; OCI Functions bổ sung môi trường thực thi được quản lý cùng các tích hợp OCI cần thiết để đưa hàm vào hệ thống.
