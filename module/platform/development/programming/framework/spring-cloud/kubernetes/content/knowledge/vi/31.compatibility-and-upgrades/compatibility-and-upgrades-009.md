# Rà soát tính năng bị thay thế hoặc ngừng hỗ trợ trong bản phát hành

## Mục tiêu và phạm vi

Một lần nâng cấp Spring Cloud Kubernetes có thể làm thay đổi cách nạp ConfigMap, kích hoạt auto-configuration hoặc gửi thông báo refresh, ngay cả khi ứng dụng vẫn build và Pod vẫn Ready. Rà soát bản phát hành cần trả lời: **ứng dụng đang phụ thuộc hành vi nào, hành vi đó còn được hỗ trợ ở phiên bản đích không và phải thay đổi gì để giữ đúng yêu cầu triển khai?**

Trong module **SPRING_CLOUD_KUBERNETES**, phạm vi gồm DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer, Configuration Watcher và các tích hợp Kubernetes đang được sử dụng. Các tính năng không dùng cần được xác định rõ để tránh mở rộng dependency, quyền RBAC hoặc số thành phần vận hành khi nâng cấp.

Sau bài học, bạn có thể:

- Phân biệt deprecated, removed, thay đổi mặc định và kết thúc hỗ trợ một dòng phiên bản.
- Lập danh mục ảnh hưởng từ release notes, tài liệu theo phiên bản và artifact thực tế.
- Chuyển một số cấu hình cũ sang cơ chế thay thế đúng ngữ nghĩa.
- Thiết kế phép kiểm chứng hành vi và kế hoạch triển khai/quay lại.
- Hoàn tất hồ sơ rà soát có bằng chứng, thay vì chỉ xóa hết cảnh báo.

Bài không giả định phiên bản nguồn hoặc phiên bản đích của hệ thống bạn. Các mốc lịch sử bên dưới là ví dụ có nguồn để học cách phân loại; chúng không tạo thành khuyến nghị chọn một phiên bản cụ thể.

## 1. Đọc đúng ý nghĩa của từng loại thay đổi

| Loại thay đổi | Ý nghĩa | Hành động phù hợp |
| --- | --- | --- |
| Deprecated | Cơ chế cũ đã được khuyến cáo thay thế; có thể vẫn hoạt động trong bản đang xét | Ghi phạm vi sử dụng, cơ chế thay thế và kế hoạch chuyển |
| Marked for removal | Có ý định loại bỏ, có thể kèm mốc hoặc chỉ ghi “future release” | Kiểm tra bản đích; không tự suy ra thời điểm loại bỏ |
| Removed | API, property, module hoặc hành vi cũ đã bị bỏ trong phiên bản xác định | Loại bỏ phụ thuộc hoặc chuyển trước khi dùng bản đó |
| Đổi tên/cách cấu hình | Có key, API hoặc cơ chế cấu hình khác | Kiểm tra alias, kiểu dữ liệu, giai đoạn nạp và thứ tự ưu tiên |
| Đổi mặc định/hành vi | Cấu hình vẫn hợp lệ nhưng kết quả khi bỏ trống hoặc khi chạy có thể khác | Đặt rõ yêu cầu cần giữ và kiểm thử ngữ nghĩa |
| Hết hỗ trợ một dòng phiên bản | Chính sách bảo trì không còn bao phủ dòng phiên bản theo loại hỗ trợ tương ứng | Chọn lộ trình nâng cấp; không đồng nhất với việc mọi tính năng đã bị xóa |

Ba suy luận thường sai:

1. “Vẫn có trang tài liệu nên tính năng chưa bị deprecated.”
2. “Không còn xuất hiện trong trang tổng hợp property nên chắc chắn đã bị xóa.”
3. “Có cơ chế mới nên cơ chế cũ đã bị loại ngay ở bản này.”

Một property có thể còn trong metadata để IDE thông báo cơ chế thay thế, dù runtime không còn bind nó. Một API nội bộ bị xóa cũng không đồng nghĩa cả tính năng sản phẩm bị xóa.

Tình trạng hỗ trợ phiên bản và khả năng hoạt động kỹ thuật là hai câu hỏi khác nhau. Khi đánh giá vòng đời, kiểm tra [trang hỗ trợ Spring Cloud](https://spring.io/projects/spring-cloud#support) và [ánh xạ các thế hệ Spring](https://spring.io/projects/generations/); ghi rõ ngày tra cứu và phân biệt OSS với Enterprise support nếu có liên quan. Không dùng một bảng lịch sử làm bằng chứng rằng hiện tại một phiên bản vẫn được hỗ trợ.

## 2. Chốt bộ phiên bản và các thành phần phải rà soát

### 2.1. Ghi nhận trạng thái nguồn và trạng thái đích

Trước khi sửa code hoặc YAML, lập bảng:

| Thành phần | Đang chạy | Dự kiến nâng cấp |
| --- | --- | --- |
| JDK | Phiên bản thực tế của image | Phiên bản dự kiến |
| Spring Boot | Phiên bản đã đóng gói | Phiên bản đích |
| Spring Cloud release train/BOM | Giá trị đã resolve | Giá trị đích |
| Spring Cloud Kubernetes | Phiên bản từng artifact | Phiên bản đích |
| Java client | Fabric8 hoặc Kubernetes Java Client và version | Client do bộ dependency đích chọn |
| Thành phần triển khai riêng | DiscoveryServer, Configuration Watcher nếu có | Image/tag/digest dự kiến |
| Kubernetes | Phiên bản và bản phân phối cluster | Môi trường sẽ triển khai |
| Cấu hình triển khai | Profile, ConfigMap/Secret, Helm values, RBAC | Các thay đổi dự kiến |

Dùng image digest hoặc thông tin artifact đã đóng gói để gắn bằng chứng với đúng workload. POM của nhánh đang phát triển có thể khác image đang chạy.

Trong dự án Maven cần rà soát, lệnh minh họa:

~~~powershell
mvn dependency:tree "-Dincludes=org.springframework.cloud:*,io.fabric8:*,io.kubernetes:*"
~~~

Đọc dependency được chọn cuối cùng, gồm cả dependency bắc cầu. Khi dùng BOM, không override riêng một client mới chỉ để làm mất cảnh báo mà chưa đối chiếu cách Spring Cloud Kubernetes gọi client đó.

### 2.2. Phân biệt release train với phiên bản project

`2020.0`, `2022.0` là cách đặt phiên bản của Spring Cloud release train. Chúng không phải phiên bản artifact `spring-cloud-kubernetes-*` cùng số.

Ví dụ, thông báo “deprecated in the 2020.0 release” trong tài liệu reload cần được hiểu trong ngữ cảnh release train. Khi lập hồ sơ, ghi cả release train và phiên bản Spring Cloud Kubernetes tương ứng.

Nếu đi qua nhiều thế hệ, đọc các breaking changes ở những mốc trung gian. Chỉ đọc ghi chú patch cuối cùng có thể bỏ sót thay đổi đã xuất hiện ở đầu dòng major.

### 2.3. Kiểm kê tính năng theo nơi thực thi

| Tính năng đang dùng | Nơi chạy | Những ràng buộc cần ghi |
| --- | --- | --- |
| DiscoveryClient trực tiếp | Ứng dụng | Loại client, namespace, resource, selector |
| HTTP DiscoveryClient | Ứng dụng và DiscoveryServer | Phiên bản hai phía và quyền của server |
| ConfigMap/Secret PropertySource | Ứng dụng | Nạp qua API hay file, bootstrap hay Config Data |
| Reload trong ứng dụng | Từng replica ứng dụng | Mode, strategy, đối tượng được refresh |
| Configuration Watcher | Workload riêng | Namespace, bộ lọc, HTTP/Bus, ứng dụng đích |
| Spring Cloud LoadBalancer | Ứng dụng | Mode, cách lấy instance và chọn port |
| Leader election nếu có | Workload tham gia bầu | Implementation, loại khóa, listener và vòng đời |

Một ứng dụng không trực tiếp gọi Kubernetes API vẫn có thể phụ thuộc API thông qua DiscoveryServer. Một lần nâng image ứng dụng cũng không tự nâng image watcher hoặc server đang triển khai riêng.

## 3. Thu thập bằng chứng từ đúng nguồn

### 3.1. Thứ tự đọc tài liệu

Với từng bản đích:

1. Đọc release notes của Spring Cloud để biết thay đổi liên project.
2. Đọc release/changelog của Spring Cloud Kubernetes tại đúng tag.
3. Đọc tài liệu của phiên bản nguồn và phiên bản đích cho tính năng đang dùng.
4. Kiểm tra configuration metadata, Javadoc và source ở tag tương ứng khi cần làm rõ.
5. Xác minh dependency/runtime rồi kiểm thử hành vi ứng dụng.

Điểm bắt đầu chính thức là [các bản phát hành Spring Cloud Kubernetes](https://github.com/spring-cloud/spring-cloud-kubernetes/releases). Khi lập báo cáo thật, lưu liên kết tới tag hoặc mục release cụ thể đã đọc; đường dẫn danh sách release có thể thay đổi theo thời gian.

Không lấy code của nhánh `main` làm bằng chứng rằng một thay đổi đã nằm trong bản GA đã chọn. PR đã merge cũng phải được đối chiếu với tag phát hành.

### 3.2. Đọc phạm vi thay đổi, không chỉ tiêu đề

Một ghi chú có từ “remove” có thể nói về test, dependency build hoặc method nội bộ. Cần đọc đối tượng bị thay đổi, tính công khai của API và người dùng nào bị ảnh hưởng.

Ví dụ, [PR #2229 của Spring Cloud Kubernetes](https://github.com/spring-cloud/spring-cloud-kubernetes/pull/2229) có tiêu đề nhắc đến deprecation liên quan ConfigMap/Secret, nhưng phần thảo luận phân biệt sửa method nội bộ và các field được đánh dấu deprecated. Không thể suy từ tiêu đề đó rằng toàn bộ khả năng đọc ConfigMap/Secret đã ngừng hỗ trợ. Đây là cách diễn giải phạm vi từ nội dung PR; vẫn phải kiểm tra release chứa thay đổi trước khi áp dụng.

Nếu nguồn ghi “will be removed in a future release”, hồ sơ nên ghi **chưa xác định mốc removal từ nguồn này**. Không tự thay bằng “bị loại ở major kế tiếp” trừ khi có bằng chứng rõ ràng.

### 3.3. Giữ phân loại chưa xác minh

Mỗi phát hiện cần có tối thiểu:

~~~text
Đối tượng: property/API/module/hành vi cụ thể
Đang sử dụng tại: file cấu hình, lớp Java hoặc workload
Phiên bản nguồn:
Phiên bản đích:
Loại thay đổi:
Nguồn và vị trí bằng chứng:
Cơ chế thay thế:
Khác biệt hành vi cần kiểm tra:
Quyết định và người phụ trách:
Bằng chứng xác minh:
~~~

Khi chưa đủ dữ liệu, đánh dấu `CHƯA XÁC MINH`. Trạng thái này hữu ích hơn việc gán deprecated hoặc removed theo phỏng đoán.

## 4. Tìm điểm sử dụng trong code, cấu hình và artifact

### 4.1. Tìm cả cấu hình triển khai

Những nơi cần rà soát:

- `application*.yml`, `application*.properties` và `bootstrap*` nếu có.
- Biến môi trường, tham số JVM, command-line arguments.
- ConfigMap, Secret tham chiếu, Helm values và manifest đã render.
- Lớp tự cấu hình client, listener, bean mở rộng hoặc custom implementation.
- Image/tag của DiscoveryServer và Configuration Watcher.
- RBAC, probe, Service port và đường management endpoint.

Trong checkout của ứng dụng cần kiểm tra, có thể dùng ripgrep để tìm tên tệp liên quan:

~~~powershell
rg -l -i --glob '*.yml' --glob '*.yaml' --glob '*.properties' --glob '*.xml' --glob '*.java' --glob 'Dockerfile*' 'kubernetes|spring[.]cloud[.]bootstrap|spring[.]config[.]import|OnGrantedEvent|OnRevokedEvent'
~~~

Lệnh này chỉ là cách thu hẹp nơi đọc. YAML có cấu trúc lồng nhau, template và biến môi trường không thể được phân tích đầy đủ chỉ bằng một regex.

Đặc biệt, tìm cả dạng property và biến môi trường như `spring.cloud.kubernetes.enabled` và `SPRING_CLOUD_KUBERNETES_ENABLED`. Quy tắc relaxed binding không có nghĩa một tên cũ đã bị bỏ sẽ tự được ánh xạ sang một property mới khác ngữ nghĩa.

Không xuất giá trị Secret hoặc toàn bộ môi trường Pod để phục vụ rà soát. Chỉ ghi tên key và phần cấu hình không nhạy cảm cần thiết.

### 4.2. Đọc metadata trong đúng JAR

Spring Boot mô tả configuration metadata tại `META-INF/spring-configuration-metadata.json` trong JAR. Metadata có thể chứa `deprecation.level`, `reason`, `replacement` và `since`; xem [Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html).

Ví dụ PowerShell đọc metadata trực tiếp, không cần giải nén ra thư mục:

~~~powershell
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Get-KubernetesPropertyMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JarPath
    )

    $resolvedJarPath = (Resolve-Path -LiteralPath $JarPath).Path
    $archive = [System.IO.Compression.ZipFile]::OpenRead($resolvedJarPath)

    try {
        $entry = $archive.GetEntry(
            "META-INF/spring-configuration-metadata.json"
        )
        if ($null -eq $entry) {
            throw "JAR khong co configuration metadata tai duong dan mong doi"
        }

        $reader = New-Object System.IO.StreamReader($entry.Open())
        try {
            $metadata = $reader.ReadToEnd() | ConvertFrom-Json
        }
        finally {
            $reader.Dispose()
        }

        $metadata.properties |
            Where-Object {
                $_.name -like "spring.cloud.kubernetes.*"
            } |
            ForEach-Object {
                [pscustomobject]@{
                    Name = $_.name
                    Type = $_.type
                    DefaultValue = (
                        ConvertTo-Json -InputObject $_.defaultValue -Compress -Depth 10
                    )
                    DeprecationLevel = $_.deprecation.level
                    Since = $_.deprecation.since
                    Replacement = $_.deprecation.replacement
                }
            }
    }
    finally {
        $archive.Dispose()
    }
}

Get-KubernetesPropertyMetadata -JarPath "C:\lab\artifact-can-kiem-tra.jar" |
    Sort-Object Name |
    Format-Table -AutoSize
~~~

Đường dẫn JAR là chỗ thay bằng artifact thật. Chạy cho các JAR liên quan ở cả bộ nguồn và bộ đích; một JAR commons không nhất thiết chứa toàn bộ metadata của mọi starter.

Khi đọc kết quả:

- `warning` thể hiện deprecation ở mức cảnh báo.
- `error` được dùng cho property không còn được quản lý/bind theo mô tả metadata.
- Không có metadata hoặc không có entry tương ứng chưa đủ chứng minh runtime không hỗ trợ.
- Có tên property trong metadata chưa đủ chứng minh property còn có tác dụng.

Metadata hỗ trợ tìm hiểu, không tự viết lại cấu hình và không thay thế kiểm tra auto-configuration hoặc hành vi runtime.

### 4.3. Phát hiện phụ thuộc API Java

Bật cảnh báo deprecation trong lượt compile của dự án cần rà soát, đọc Javadoc của API ứng dụng trực tiếp dùng và kiểm tra các custom bean.

Build không lỗi vẫn có thể bỏ sót:

- Property cũ bị bỏ qua mà không có lỗi bind.
- Dependency chạy riêng như watcher chưa được nâng.
- Method có mặt nhưng không còn được gọi ở nhánh cấu hình hiện tại.
- Thay đổi mặc định chỉ xuất hiện khi có nhiều replica hoặc nhiều namespace.
- Điều kiện kích hoạt bean đã thay đổi.

## 5. Ví dụ một property đã bị loại: nhận diện môi trường Kubernetes

### 5.1. Phát hiện và phân loại

Một cấu hình cũ có thể chứa:

~~~properties
spring.cloud.kubernetes.enabled=false
~~~

[Spring Cloud 2022.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2022.0-Release-Notes) ghi nhận thay đổi nhận diện Kubernetes từ mốc 3.0.0-M1: property trên bị loại và không còn được hỗ trợ cho cơ chế awareness. [Tài liệu Kubernetes Awareness nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/kubernetes-awareness.html) cũng mô tả breaking change trong dòng 3.0.x.

Kết luận đúng cho hồ sơ là: **property nhận diện cũ đã bị loại trong dòng được tài liệu chỉ rõ**. Không kết luận rằng toàn bộ Spring Cloud Kubernetes đã mất khả năng chạy ngoài cluster.

### 5.2. Chuyển theo ý định của cấu hình

Cơ chế được tài liệu nêu thay thế dựa trên Spring Boot `ConditionalOnCloudPlatform` và thuộc tính `spring.main.cloud-platform`.

Ví dụ ép nhận diện cho một lượt kiểm thử đã chuẩn bị:

~~~yaml
spring:
  main:
    cloud-platform: KUBERNETES
~~~

Hoặc ép không nhận diện cloud platform khi đó là ý định cần kiểm tra:

~~~yaml
spring:
  main:
    cloud-platform: NONE
~~~

Đây là hai lựa chọn riêng, không ghép thành một cấu hình. Không đổi mọi giá trị của property cũ theo một phép tìm-thay máy móc.

Phải làm rõ mục đích ban đầu:

| Mục đích thật | Việc cần xác minh |
| --- | --- |
| Chọn môi trường để auto-configuration xét điều kiện | Cloud platform được nhận diện đúng |
| Tắt riêng discovery trong test | Cờ discovery của đúng phiên bản và bean thực tế |
| Tắt đọc ConfigMap/Secret qua API | Cơ chế nạp nguồn, cờ tương ứng, request thực tế |
| Tránh dùng credential/mạng Kubernetes trên máy phát triển | Không còn thành phần ngoài ý muốn gọi API |
| Tạo profile chạy trong cluster | Profile và điều kiện được kích hoạt đúng giai đoạn |

`spring.main.cloud-platform` ảnh hưởng nhận diện nền tảng. Không xem nó như bảo đảm rằng mọi client bean do người dùng tự khai báo sẽ bị tắt.

Thuộc tính phục vụ quyết định khởi động phải có mặt đủ sớm. Nếu vẫn sử dụng bootstrap, kiểm tra vị trí cấu hình theo hướng dẫn của nhánh đó; không đặt thuộc tính cần để quyết định nạp nguồn ở chính nguồn chưa được nạp.

### 5.3. Bằng chứng hoàn tất

Trong môi trường local/test và trong Pod lab, đối chiếu:

- Báo cáo condition evaluation hoặc bean liên quan.
- Tính năng nào được bật/tắt đúng yêu cầu.
- Có request Kubernetes API ngoài ý muốn hay không.
- Cấu hình cũ và biến môi trường tương ứng đã được loại khỏi mọi lớp ghi đè.

Một lần khởi động không có exception chưa đủ chứng minh đã thay thế property thành công.

## 6. Ví dụ deprecated: đọc file mount qua config.paths

### 6.1. Phạm vi thông báo

Tài liệu ConfigMap của nhánh 3.3 đánh dấu cơ chế `spring.cloud.kubernetes.config.paths` là deprecated và hướng sang `spring.config.import`. Nguồn ghi sẽ bị loại trong tương lai, không chỉ định trong câu thông báo đó một bản removal cụ thể. Xem [ConfigMap PropertySource nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Điều bị thay thế ở ví dụ này là **cơ chế cấu hình đọc file bằng property đó**, không phải khả năng mount ConfigMap/Secret của Kubernetes.

Cấu hình cũ minh họa:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        paths:
          - /etc/catalog/application.yaml
~~~

### 6.2. Chọn import phù hợp dữ liệu đã mount

Nếu `/etc/catalog/application.yaml` là một tệp YAML chứa toàn bộ cấu hình:

~~~yaml
spring:
  config:
    import: "file:/etc/catalog/application.yaml"
~~~

Nếu cấu trúc mount là mỗi tệp chứa giá trị của một key, có thể đánh giá `configtree:` theo cơ chế Config Data của Spring Boot. Ví dụ một thư mục chứa các file `demo.message` và `demo.region`:

~~~yaml
spring:
  config:
    import: "configtree:/etc/catalog/keys/"
~~~

`file:` và `configtree:` là hai cách diễn giải nội dung khác nhau. Không đổi giữa chúng chỉ vì đều trỏ tới một volume. `optional:` chỉ thích hợp khi nguồn thực sự được phép vắng mặt; không thêm để che lỗi mount trong lượt migration. Xem [Externalized Configuration của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Mặt khác:

~~~yaml
spring:
  config:
    import: "kubernetes:"
~~~

là đường nạp nguồn qua tích hợp Spring Cloud Kubernetes phù hợp với dependency đang chọn, không phải cách viết mới của một đường dẫn file mount.

Đọc file bằng Config Data cũng không tự chứng minh ứng dụng sẽ ngừng mọi request Kubernetes. Discovery, watcher hoặc các starter khác vẫn phải được đánh giá riêng.

### 6.3. Giữ ngữ nghĩa sau khi đổi

Kiểm tra ba trạng thái bằng một thuộc tính lab không nhạy cảm:

| Trạng thái | Điều cần quan sát |
| --- | --- |
| Tệp tồn tại lúc khởi động | Giá trị được nạp từ đúng nguồn |
| Tệp bắt buộc bị thiếu | Ứng dụng phản ứng theo chính sách mong muốn |
| Có giá trị cùng key ở nguồn khác | Giá trị hiệu lực và thứ tự ưu tiên đúng thiết kế |

Thử thêm việc thay đổi file sau khi Pod chạy. Nạp Config Data lúc khởi động và refresh bean khi file thay đổi là hai khả năng cần xác minh riêng.

Không coi việc tên property mới xuất hiện trong Environment là bằng chứng tất cả bean đã dùng giá trị mới. Một bean có thể đã chụp giá trị lúc khởi tạo hoặc không thuộc phạm vi refresh.

## 7. Ví dụ thay đổi cơ chế nạp: bootstrap và Config Data

Tài liệu Spring Cloud Kubernetes nhánh 3.3 mô tả nạp nguồn bằng `spring.config.import: "kubernetes:"` và vẫn nêu cách dùng bootstrap thông qua `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` ở môi trường. Tài liệu cũng yêu cầu chọn một phương thức, không nạp cùng nguồn Kubernetes bằng cả hai. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config.html).

Vì vậy, phát hiện “ứng dụng dùng bootstrap” không tự động được phân loại là “bootstrap đã bị loại”. Cần đối chiếu bản đích và kế hoạch nạp cấu hình của hệ thống.

Khi chọn chuyển sang Config Data:

1. Xác định nguồn nào đang được bootstrap nạp và các thuộc tính cần có từ sớm.
2. Chọn dependency phù hợp với cơ chế nạp mới.
3. Khai báo import và tên/namespace nguồn theo phiên bản đích.
4. Loại đường bootstrap cũ trong cùng kế hoạch thay đổi.
5. Kiểm tra thứ tự ưu tiên, profile, fail-fast và hành vi khi thiếu nguồn.
6. Xác minh mỗi nguồn được nạp đúng một lần theo thiết kế.

Không giữ cả hai chỉ để “dự phòng” nếu tài liệu của nhánh đang xét không hỗ trợ cách đó. Hai đường nạp có thể làm kết quả khác nhau giữa local và cluster.

Đừng xóa starter bootstrap trước khi biết một tích hợp khác trong ứng dụng có đang phụ thuộc nó hay không. Quyết định cần dựa trên dependency và nguồn cấu hình thực tế.

## 8. Ví dụ deprecated: reload trong ứng dụng và cơ chế thay thế

### 8.1. Phát hiện cơ chế reload cũ

Cấu hình kiểu sau là dấu hiệu cần đưa vào hồ sơ:

~~~yaml
spring:
  cloud:
    kubernetes:
      reload:
        enabled: true
        mode: event
        strategy: refresh
~~~

Tài liệu `PropertySource Reload` của nhánh 3.3 ghi cơ chế này deprecated từ release train 2020.0 và chỉ tới Configuration Watcher như một phương án thay thế. Điều đó không tự chứng minh nó đã bị xóa khỏi mọi phiên bản sau đó. Xem [PropertySource Reload](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/propertysource-reload.html).

Trước khi thay, ghi chính xác hợp đồng hiện tại:

| Thuộc tính hành vi | Câu hỏi cần trả lời |
| --- | --- |
| Nguồn | ConfigMap, Secret hay file mount nào? |
| Phạm vi | Namespace, tên hoặc label nào? |
| Cách phát hiện | Event hay polling? |
| Cách áp dụng | Refresh bean, restart context hay shutdown ứng dụng? |
| Thời gian | Bao lâu sau thay đổi thì nghiệp vụ thấy giá trị mới? |
| Số replica | Mỗi replica có nhận và áp dụng thay đổi không? |

Strategy `refresh`, `restart_context` và `shutdown` không có cùng ngữ nghĩa. Đặc biệt, chuyển một thiết kế restart/shutdown sang gọi refresh có thể giữ lại tài nguyên hoặc trạng thái trước đây được tạo lại.

### 8.2. Hiểu thay đổi kiến trúc khi dùng Configuration Watcher

~~~mermaid
flowchart LR
    A[ConfigMap hoặc Secret thay đổi] --> B[Configuration Watcher]
    B --> C[Thông báo HTTP hoặc Spring Cloud Bus]
    C --> D[Ứng dụng nhận yêu cầu]
    D --> E[Đọc lại cấu hình và áp dụng theo khả năng refresh]
~~~

Trong cơ chế reload bên trong ứng dụng, mỗi ứng dụng có đường phát hiện thay đổi của mình. Với watcher triển khai riêng, cần đánh giá workload watcher, danh tính, quyền, nguồn được theo dõi và đường thông báo đến ứng dụng.

Tài liệu watcher nhánh 3.3 mô tả nguồn có label phù hợp và hai cách thông báo qua HTTP hoặc Spring Cloud Bus. Với HTTP, endpoint refresh của ứng dụng phải được cấu hình và truy cập được từ watcher. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Đây là thay đổi kiến trúc, không phải đổi `reload.enabled` thành một property mới rồi giữ nguyên mọi thứ còn lại.

### 8.3. Một nguồn lab để kiểm chứng

Ví dụ ConfigMap phục vụ bài kiểm tra theo nhánh watcher 3.3:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-service
  namespace: upgrade-lab
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  application.yaml: |-
    demo:
      migration-marker: before
~~~

Cần cấu hình ứng dụng đọc đúng nguồn và watcher theo dõi đúng namespace. Khi đổi sang bản đích khác, kiểm tra lại label selector và cấu hình watcher của bản đó, không mặc định ví dụ lịch sử vẫn nguyên vẹn.

Thiết lập đường quan sát nội bộ cho `demo.migration-marker`. Sau khi cập nhật nguồn thành `after`, ghi riêng các thời điểm:

~~~text
t0: Kubernetes chấp nhận cập nhật nguồn
t1: watcher nhận hoặc phát hiện thay đổi
t2: ứng dụng nhận thông báo
t3: hành vi/bean được kiểm tra nhìn thấy giá trị mới
~~~

`t3 - t0` mới là độ trễ áp dụng mà người vận hành cần đánh giá. Log của watcher tại `t1` chưa chứng minh các replica đã áp dụng thành công.

### 8.4. Những việc phải hoàn tất khi chuyển cơ chế

- Chọn HTTP hoặc Bus theo thiết kế đã kiểm chứng; không tự thêm broker chỉ vì có phương án Bus.
- Cấp RBAC cho watcher theo nguồn và namespace thực sự theo dõi.
- Phân biệt quyền đọc nguồn của watcher với quyền của ứng dụng đọc lại nguồn.
- Bảo vệ endpoint quản trị, đồng thời cho phép đường gọi hợp lệ từ watcher.
- Kiểm tra mọi replica, không chỉ một lần gọi qua Service cân bằng tải.
- Tránh để hai cơ chế phát thông báo trùng nhau ngoài ý muốn trong giai đoạn chuyển tiếp.
- Sau khi chứng minh cơ chế mới, loại cấu hình/dependency/quyền cũ không còn dùng.

Nếu yêu cầu chỉ là áp dụng cấu hình qua rollout được kiểm soát, có thể chọn quy trình đó thay vì thêm watcher. Cần ghi rõ sự thay đổi kỳ vọng vận hành; không gọi đó là thay thế tương đương cho nhu cầu refresh tức thời.

## 9. Những phát hiện không được phân loại quá mức

### 9.1. Có lựa chọn mới chưa phải cơ chế cũ đã bị xóa

Tài liệu leader election hiển thị phiên bản 5.1.0 mô tả lựa chọn native với nhóm `spring.cloud.kubernetes.leader.election.*`, cùng định hướng thay thế implementation cũ trong tương lai. Tài liệu đó vẫn trình bày implementation cũ. Vì vậy chỉ thông tin định hướng không đủ để đánh dấu “removed trong 5.1.0”. Xem [Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html).

Nếu ứng dụng có dùng leader election, việc đổi implementation cần kiểm tra lock, RBAC và loại sự kiện listener. Đừng đưa migration này vào một lần nâng cấp chỉ vì nó xuất hiện trong danh sách tính năng mới.

### 9.2. Đổi mode không phải đổi tên property tương đương

Spring Cloud LoadBalancer có các mode được tài liệu mô tả với đường lấy instance khác nhau. Chuyển từ mode dựa vào DiscoveryClient sang mode Service là quyết định hành vi, không mặc định là bản thay thế bắt buộc. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

Khi rà soát, phải giữ mục tiêu gọi đúng backend, namespace và port. Một thay đổi làm hệ thống hết cảnh báo nhưng chuyển cách định tuyến cần được ghi và kiểm thử rõ ràng.

### 9.3. Các client khác nhau cần được đánh giá độc lập

Fabric8, Kubernetes Java Client và HTTP DiscoveryClient là những lựa chọn khác nhau được [tài liệu DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html) mô tả. Không tự phân loại một lựa chọn là “ngừng hỗ trợ” chỉ vì release thêm hoặc cải tiến lựa chọn còn lại.

Tương tự, đổi từ ConfigMap đọc qua API sang file mount không chứng minh rằng ứng dụng đã không còn cần Kubernetes API: discovery hoặc thành phần khác có thể vẫn sử dụng.

## 10. Biến phát hiện thành kế hoạch thay đổi có thể kiểm chứng

### 10.1. Lập bảng ảnh hưởng

Ví dụ hồ sơ cho một ứng dụng giả định:

| ID | Điểm sử dụng | Phân loại có bằng chứng | Hành động dự kiến | Bằng chứng hoàn tất |
| --- | --- | --- | --- | --- |
| M01 | `spring.cloud.kubernetes.enabled` | Removed trong dòng 3.0.x đã dẫn nguồn | Thay theo ý định nhận diện/tắt tính năng | Bean và request đúng ở local/cluster |
| M02 | `config.paths` | Deprecated trong tài liệu 3.3; chưa suy mốc removal | Chuyển file mount sang Config Data phù hợp | Giá trị, precedence và thiếu nguồn đúng kỳ vọng |
| M03 | Reload trong ứng dụng | Deprecated; cơ chế cũ đang dùng refresh | Chọn watcher hoặc quy trình rollout đáp ứng yêu cầu | Thay đổi nguồn có hiệu lực trên mọi replica |
| M04 | Bootstrap | Cần quyết định cách nạp, chưa kết luận removed | Chọn một đường nạp theo bản đích | Không nạp trùng, profile và nguồn đúng |
| M05 | Tính năng chưa được ứng dụng dùng | Không áp dụng sau khi xác minh | Không thêm dependency/quyền để xử lý mục này | Không có kích hoạt ngoài ý muốn |

Đây là ví dụ phân loại, không phải danh sách cần áp dụng nguyên trạng cho mọi lần nâng cấp.

Ưu tiên xử lý theo ảnh hưởng:

1. Tính năng đã bị loại trong bản đích và đang nằm trên đường khởi động/đường nghiệp vụ.
2. Cấu hình có thể bị bỏ qua mà vẫn làm ứng dụng khởi động.
3. Thay đổi quyền, cơ chế nạp, điều kiện kích hoạt và hành vi đa replica.
4. Deprecation còn hoạt động nhưng cần lộ trình loại bỏ.
5. Dọn dependency hoặc API không được ứng dụng sử dụng.

### 10.2. Kiểm thử theo hợp đồng hành vi

| Phạm vi | Phép thử có ý nghĩa |
| --- | --- |
| Nạp cấu hình | Khởi động với nguồn đúng, thiếu nguồn bắt buộc và giá trị ghi đè |
| Discovery | Lấy đúng service/instance rồi quan sát backend thêm hoặc mất readiness |
| LoadBalancer | Gọi được đúng backend và port trước/sau thay đổi tập instance |
| Refresh | Đổi marker lab, quan sát từng chặng và từng replica |
| Secret | Nạp/đổi credential lab theo thiết kế, không lộ giá trị |
| RBAC | Chỉ thành phần đúng danh tính truy cập được nguồn cần thiết |
| Probe | Trạng thái health phản ánh yêu cầu vận hành đã đặt |
| Quay lại | Image và cấu hình cũ còn hoạt động trong trạng thái hạ tầng dự kiến |

Việc kiểm tra RBAC phải dùng resource, verb và namespace đúng request. Quyền Kubernetes dựa trên các thuộc tính đó; xem [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/). Không cấp quyền toàn cluster như cách mặc định để vượt một lỗi sau migration.

Khi ứng dụng không sử dụng một tính năng, vẫn kiểm tra cấu hình/dependency không vô tình bật tính năng đó. Không áp dụng không có nghĩa bỏ qua dấu hiệu auto-configuration đang tạo request.

### 10.3. Kiểm tra cả chiều lỗi

Một kế hoạch migration cần biết hệ thống phản ứng thế nào khi:

- Không có file hoặc ConfigMap bắt buộc.
- Watcher đọc được nguồn nhưng không gửi được refresh.
- Ứng dụng đọc được nguồn nhưng một bean không được refresh.
- Một replica vẫn chạy image/cấu hình cũ.
- ConfigMap được cập nhật trong khi rollout chưa xong.
- Nguồn cũ còn tồn tại và ghi đè lên nguồn mới ngoài ý muốn.

Kết quả mong đợi có thể là fail-fast, tiếp tục với giá trị cũ có quan sát hoặc yêu cầu rollout. Chọn rõ theo yêu cầu sản phẩm, không chỉ làm cho health trả UP.

## 11. Triển khai và quay lại phải bao gồm cấu hình

Gọi `A0`, `C0` là image và cấu hình cũ; `A1`, `C1` là bộ mới:

| Tổ hợp | Ý nghĩa |
| --- | --- |
| `A0 + C0` | Đường cơ sở trước migration |
| `A1 + C1` | Trạng thái đích cần chứng minh |
| `A1 + C0` | Cần kiểm tra nếu rollout có thời gian image mới dùng config cũ |
| `A0 + C1` | Cần kiểm tra nếu kế hoạch rollback có thể giữ config mới |

Không mặc định các tổ hợp chuyển tiếp đều được hỗ trợ. Nếu property mới không tồn tại ở image cũ, rollback image đơn thuần có thể không khôi phục được hành vi.

Một kế hoạch khả thi cần ghi:

- Cấu hình được version hóa và tham chiếu bằng cách nào.
- Khi nào đổi label/selector hoặc nguồn mount.
- Khi nào bật watcher mới và tắt cơ chế cũ.
- Phiên bản của DiscoveryServer/watcher phối hợp với ứng dụng.
- Thời điểm thu hồi quyền hoặc gỡ dependency cũ.
- Điều kiện dừng rollout và bộ image/cấu hình dùng để quay lại.

Canary nhiều phiên bản có thể dùng chung ConfigMap. Thay đổi key hoặc label trên nguồn chung có thể ảnh hưởng cả replica cũ lẫn mới, nên phải đánh giá trước.

Với migration liên quan refresh, việc khôi phục nội dung ConfigMap không luôn đồng nghĩa mọi bean đã quay về trạng thái ban đầu. Phương án quay lại cần có hành động refresh hoặc restart phù hợp với thiết kế đã thử.

## 12. Bài thực hành và tiêu chí kết thúc rà soát

### 12.1. Tình huống thực hành

Ứng dụng `catalog-service` trong namespace `upgrade-lab` có hai replica, đọc một file YAML mount từ ConfigMap và đang dùng reload bên trong ứng dụng. Nhóm dự kiến nâng sang một bộ dependency mới đã chọn.

Thực hiện trên bản sao lab:

1. Ghi bộ phiên bản nguồn/đích và cách triển khai watcher/server nếu có.
2. Tìm mọi chỗ dùng property nhận diện cũ, bootstrap, `config.paths` và `reload.*`.
3. Đọc release notes, tài liệu đúng phiên bản và metadata của các JAR liên quan.
4. Lập bảng phân loại; để `CHƯA XÁC MINH` nếu chưa có nguồn đủ rõ.
5. Chọn cách nạp file và cách áp dụng cập nhật đáp ứng nhu cầu thật.
6. Tạo marker không nhạy cảm, kiểm tra khởi động và cập nhật trên cả hai replica.
7. Thử một tình huống lỗi và xác minh cách phát hiện/phục hồi.
8. Diễn tập quay lại bộ image/cấu hình đã chuẩn bị.

Không cố hoàn tất mọi migration trong một thay đổi duy nhất. Có thể tách những thay đổi độc lập, miễn trạng thái chuyển tiếp được ghi rõ và bản đích không còn phụ thuộc một cơ chế đã bị loại.

### 12.2. Hồ sơ đầu ra

Một lần rà soát hoàn chỉnh nên bàn giao được:

- Bộ phiên bản nguồn/đích, image digest và cấu hình thực tế.
- Danh sách tính năng đang dùng và thành phần chịu trách nhiệm.
- Mỗi phát hiện gắn với loại thay đổi, phiên bản và nguồn bằng chứng.
- Quyết định chuyển đổi, giữ có thời hạn hoặc không áp dụng kèm lý do.
- Kết quả kiểm chứng hành vi, gồm tình huống lỗi và đa replica cần thiết.
- Kế hoạch rollout/quay lại và việc dọn cấu hình, dependency, RBAC cũ.
- Các điểm chưa xác minh, người phụ trách và điều kiện phải hoàn tất.

Có thể kết thúc rà soát khi mọi phụ thuộc bị loại trong bản đích đã có cách xử lý được chứng minh, các thay đổi ngữ nghĩa đã được kiểm tra và trạng thái chuyển tiếp có phương án vận hành rõ ràng. Không cần đạt “không còn một dòng cảnh báo nào” bằng cách tắt tính năng hoặc che lỗi mà chưa đáp ứng yêu cầu triển khai.
