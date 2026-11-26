# Giới hạn kích thước và phân chia cấu hình hợp lý

Trong chương **ConfigMap** của module **SPRING_CLOUD_KUBERNETES**, giới hạn dung lượng không chỉ là một lỗi cần xử lý khi triển khai. Nó giúp xác định dữ liệu nào phù hợp để làm cấu hình, nên chia theo ranh giới nào và ứng dụng phải nạp, kiểm tra, cập nhật các phần đó ra sao.

Một ConfigMap lớn chứa mọi cấu hình có thể khó kiểm soát quyền và phạm vi cập nhật. Ngược lại, chia mỗi khóa thành một ConfigMap tạo thêm nhiều resource, phụ thuộc và điểm có thể sai. Mục tiêu là giữ các nhóm cấu hình nhỏ, có trách nhiệm rõ ràng và đáp ứng cách ứng dụng Spring sử dụng chúng.

## 1. Giới hạn cơ bản: 1 MiB dữ liệu cho một ConfigMap

Kubernetes quy định dữ liệu trong một ConfigMap không được vượt **1 MiB**, tương đương **1.048.576 byte**. Đây là giới hạn theo resource, không phải dung lượng riêng cho từng khóa hoặc từng file nhúng. ConfigMap dành cho dữ liệu không nhạy cảm; tài liệu cũng khuyến nghị dùng nơi lưu trữ khác nếu dữ liệu cấu hình quá lớn. Xem [ConfigMaps của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/).

Ví dụ minh họa, dùng KiB với quy ước 1 KiB = 1.024 byte:

| Dữ liệu trong một ConfigMap | Tổng | Đánh giá riêng về ngưỡng 1 MiB |
| --- | --- | --- |
| Một giá trị 700 KiB | 700 KiB | Chưa vượt |
| Hai giá trị, mỗi giá trị 600 KiB | 1.200 KiB | Vượt |
| Mười file nhúng, mỗi file 110 KiB | 1.100 KiB | Vượt |
| Ba ConfigMap riêng, mỗi resource 400 KiB | 400 KiB/resource | Từng resource chưa vượt |

Bảng chỉ đánh giá ngưỡng dữ liệu. Một object chưa vượt 1 MiB vẫn có thể bị từ chối vì cấu trúc không hợp lệ, annotation quá lớn, chính sách admission hoặc lỗi khác.

Các thao tác sau không tạo thêm dung lượng cho cùng một ConfigMap:

- Chuyển từ nhiều khóa phẳng sang một khóa `application.yaml`.
- Chia nội dung thành nhiều file nhưng vẫn đưa tất cả vào cùng resource.
- Chuyển sang namespace khác.
- Mount chính ConfigMap đó thành volume.
- Tăng heap JVM, số replica hoặc cấu hình retry của Spring.

Giới hạn được kiểm tra ở Kubernetes API, trước khi Spring có cơ hội đọc phiên bản dữ liệu mới.

## 2. Đo byte của dữ liệu, không đếm ký tự hoặc dòng YAML

Để hiểu cách tính, có thể đối chiếu hàm `ValidateConfigMap` trong mã nguồn Kubernetes v1.34.0. Hàm cộng độ dài byte của các giá trị `data` và `binaryData`, rồi so sánh với giới hạn. Với `binaryData`, đó là dữ liệu nhị phân sau giải mã của biểu diễn API. Xem [mã kiểm tra ConfigMap](https://github.com/kubernetes/kubernetes/blob/v1.34.0/pkg/apis/core/validation/validation.go).

Công thức cho phần dữ liệu theo cách kiểm tra đó:

```text
payloadBytes =
    tổng số byte UTF-8 của các giá trị data
    + tổng số byte nhị phân của các giá trị binaryData
```

Hằng số được dùng trong kiểm tra có giá trị `1 * 1024 * 1024`; xem [định nghĩa giới hạn trong Kubernetes](https://github.com/kubernetes/kubernetes/blob/v1.34.0/pkg/apis/core/types.go). Khi cần phân tích chi tiết hành vi cluster, đối chiếu phiên bản và chính sách đang vận hành.

Tên khóa, metadata và cú pháp bao ngoài của manifest không nằm trong tổng payload của phép kiểm tra trên. Chúng vẫn có quy tắc hợp lệ và chi phí lưu trữ, truyền tải riêng. Vì vậy, kích thước file YAML hoặc JSON đầy đủ là một chỉ số bổ sung, không phải phép đo thay thế chính xác.

### Nội dung nhúng cũng là dữ liệu

Với khai báo:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-core
  namespace: checkout
data:
  application.yaml: |-
    # Ghi chú này là một phần của chuỗi được lưu.
    app:
      client:
        timeout: 2s
```

Comment ở bên trong chuỗi `application.yaml`, khoảng trắng và ký tự xuống dòng của chuỗi đều góp vào dung lượng. Comment YAML bên ngoài dữ liệu thì không trở thành một giá trị trong `data`.

Các chỉ số sau không tương đương:

- Số dòng trong file.
- Số ký tự hiển thị.
- Độ dài chuỗi Java hoặc PowerShell.
- Số byte UTF-8.

Văn bản tiếng Việt có thể dùng nhiều byte cho một ký tự. Trong Java, cần đo bằng cách mã hóa UTF-8, chẳng hạn:

```java
byte[] payload = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int payloadBytes = payload.length;
```

Không dùng `text.length()` làm số byte của chuỗi cấu hình.

### Base64 và nén không tự giải quyết thiết kế

Nếu ghi chuỗi Base64 vào `data`, chuỗi đã mã hóa vẫn chiếm dung lượng. Đổi sang `binaryData` cũng không bỏ qua giới hạn tổng dữ liệu của resource.

Nén rồi lưu một khối dữ liệu có thể yêu cầu mã giải nén và parser riêng. Spring Cloud Kubernetes không tự suy ra mọi chuỗi nén là tài liệu cấu hình để giải nén và bind. Chỉ chọn cách đó khi đã thiết kế rõ định dạng và đường đọc; không coi đây là bước sửa mặc định cho một ConfigMap quá lớn.

## 3. Phân biệt lỗi dữ liệu với lỗi annotation

Một ConfigMap có payload vài trăm KiB có thể bị báo lỗi kiểu:

```text
metadata.annotations: Too long ...
262144 bytes
```

Đây có thể là giới hạn tổng kích thước annotation **256 KiB**, khác với ngưỡng payload 1 MiB. Mã kiểm tra annotation cộng byte của cả tên và giá trị annotation; xem [ValidateAnnotationsSize](https://github.com/kubernetes/kubernetes/blob/v1.34.0/staging/src/k8s.io/apimachinery/pkg/api/validation/objectmeta.go).

Client-side apply có thể ghi bản cấu hình đã áp dụng vào annotation `kubectl.kubernetes.io/last-applied-configuration`. Với ConfigMap chứa nhiều nội dung, bản sao này có thể làm annotation vượt ngưỡng dù dữ liệu chưa đạt 1 MiB. Cơ chế đó được mô tả trong [Declarative Management of Kubernetes Objects](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/).

Cần đọc đúng trường mà API báo lỗi:

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| Tổng dữ liệu vượt 1.048.576 byte | Giảm dữ liệu, chia resource hoặc đổi nơi lưu |
| `metadata.annotations` vượt 262.144 byte | Kiểm tra annotation và cơ chế apply |
| Request quá lớn ở một tầng khác | Kiểm tra kích thước request, công cụ và hạ tầng |
| Dữ liệu hợp lệ nhưng không bind được | Kiểm tra hợp đồng thuộc tính và kiểu Java |

Server-side apply quản lý quyền sở hữu trường qua `managedFields`. Nó không nâng ngưỡng dữ liệu ConfigMap lên trên 1 MiB. Khi chuyển cách apply, cần kiểm tra annotation cũ và hành vi migration của công cụ; không giả định một lệnh mới tự loại bỏ mọi metadata đã có. Xem [Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/).

Không xóa annotation một cách tùy tiện để “làm nhẹ object” nếu chưa hiểu pipeline nào đang dựa vào nó để quản lý thay đổi.

## 4. Đo dung lượng của một ConfigMap thực tế

Đo **kết quả đã render**, không chỉ file nguồn của template. Một giá trị được chèn vào khi render có thể làm manifest cuối khác đáng kể so với template.

Ví dụ PowerShell dưới đọc một ConfigMap đã tồn tại, cộng số byte và chỉ in số liệu tổng hợp. Nó không in nội dung cấu hình:

```powershell
$ErrorActionPreference = 'Stop'

$configMapJson = kubectl -n checkout get configmap checkout-core -o json
if ($LASTEXITCODE -ne 0) {
    throw 'Không đọc được ConfigMap checkout-core'
}

$configMap = ($configMapJson -join [Environment]::NewLine) |
    ConvertFrom-Json

[long]$textBytes = 0
[long]$binaryBytes = 0

if ($null -ne $configMap.data) {
    foreach ($entry in $configMap.data.PSObject.Properties) {
        $textBytes += [System.Text.Encoding]::UTF8.GetByteCount(
            [string]$entry.Value)
    }
}

if ($null -ne $configMap.binaryData) {
    foreach ($entry in $configMap.binaryData.PSObject.Properties) {
        $binaryBytes += [Convert]::FromBase64String(
            [string]$entry.Value).LongLength
    }
}

[long]$payloadBytes = $textBytes + $binaryBytes
[long]$limitBytes = 1048576

[pscustomobject]@{
    Name = $configMap.metadata.name
    TextBytes = $textBytes
    BinaryBytes = $binaryBytes
    PayloadBytes = $payloadBytes
    LimitBytes = $limitBytes
    RemainingBytes = $limitBytes - $payloadBytes
    PayloadPercent = [Math]::Round(
        100.0 * $payloadBytes / $limitBytes, 2)
}
```

Ví dụ giả định terminal nhận JSON Unicode đúng từ `kubectl`. Nếu dữ liệu đã bị lỗi mã hóa trước lúc chuyển thành object thì phép đo UTF-8 không còn phản ánh đúng bản gốc.

Để khảo sát một manifest chưa được tạo, có thể dùng JSON từ bước render hoặc từ:

```bash
kubectl create --dry-run=client -f checkout-core.yaml -o json
```

Sau đó đưa JSON của **một ConfigMap** vào cùng logic tính toán. Nếu đầu vào là `List` hoặc chứa nhiều tài liệu, phải đo từng ConfigMap, không cộng cả tập rồi so sánh với giới hạn của một resource.

Cũng cần kiểm tra với API server trong môi trường phù hợp, chẳng hạn:

```bash
kubectl apply --server-side --field-manager=config-size-check --dry-run=server -f checkout-core.yaml
```

Dry-run có thể bị từ chối vì quyền, conflict hoặc admission; không phải mọi lỗi đều là lỗi dung lượng. Các lệnh trong bài là hướng dẫn thực hành, không phải những lần chạy đã được thực hiện.

## 5. Chọn dữ liệu phù hợp trước khi chia nhỏ

Trước một ConfigMap đang tăng nhanh, hãy hỏi phần nào thực sự là cấu hình khởi động của ứng dụng.

| Nội dung | Nơi lưu phù hợp với mục đích |
| --- | --- |
| URL dịch vụ, timeout, giới hạn kết nối | ConfigMap nếu không nhạy cảm |
| Một nhóm feature flag nhỏ | ConfigMap, với cơ chế cập nhật đã xác định |
| Mật khẩu, token, khóa truy cập | Secret hoặc hệ thống quản lý bí mật phù hợp |
| Danh mục sản phẩm, bảng giá, dữ liệu từng khách hàng | Cơ sở dữ liệu hoặc dịch vụ dữ liệu |
| File quy tắc lớn, nhiều phiên bản | Kho file/object storage, volume hoặc dịch vụ chuyên biệt |
| Model, ảnh, dữ liệu nhị phân lớn | Kho artifact hoặc nơi lưu file phù hợp |
| Giá trị mặc định đi cùng mã ứng dụng | Có thể đóng gói trong artifact nếu vòng đời phù hợp |

Secret không phải một cách “nâng cấp dung lượng” cho dữ liệu lớn. Đổi nơi lưu dựa trên độ nhạy cảm và đường sử dụng, không dựa vào mong muốn tránh lỗi ConfigMap.

Nếu dùng kho bên ngoài, cấu hình nhỏ trong ConfigMap có thể chỉ chứa định danh phiên bản, URI hoặc checksum. Ứng dụng vẫn cần đường tải dữ liệu, xác thực, xử lý lỗi và quy tắc kiểm tra tương ứng; Spring không tự tải và áp dụng mọi URI xuất hiện trong một thuộc tính.

Mount volume cũng cần nói rõ nguồn. Volume tham chiếu ConfigMap vẫn phụ thuộc vào ConfigMap và ngưỡng của nó. Volume chứa file từ nơi lưu trữ khác mới là một kiến trúc khác.

## 6. Chia theo trách nhiệm, quyền sở hữu và nhịp thay đổi

Ranh giới tốt thường được xác định bằng các câu hỏi:

1. Các khóa có phục vụ cùng một thành phần không?
2. Chúng có do cùng nhóm sở hữu không?
3. Chúng có thay đổi cùng lúc không?
4. Ai cần được phép sửa hoặc đọc nhóm này?
5. Có cần cập nhật nguyên khối để giữ tương thích không?

Ví dụ ứng dụng `checkout-service` có ba nhóm:

| ConfigMap | Nội dung chính | Đặc điểm thay đổi |
| --- | --- | --- |
| `checkout-core` | Client URL, timeout, giới hạn retry | Thay đổi cùng cấu hình tích hợp |
| `checkout-features` | Các feature flag nhỏ | Có thể thay đổi độc lập |
| `checkout-observability` | Mức log và tùy chọn quan sát | Do vận hành điều chỉnh |

Đây là một thiết kế minh họa, không phải yêu cầu mọi ứng dụng đều cần ba ConfigMap.

Không nên chia máy móc thành `part-001`, `part-002` chỉ để mỗi phần vừa dưới ngưỡng. Cách chia đó có thể giữ nguyên một khối dữ liệu lớn nhưng thêm công việc ghép, kiểm tra thứ tự và xử lý thiếu phần.

Ngược lại, tách mỗi khóa thành một resource làm tăng số lượng nguồn mà không nhất thiết tạo được ranh giới vận hành có ích. Giữ cùng nhau những khóa phải được hiểu và thay đổi cùng nhau.

## 7. Ví dụ phân chia và nạp bằng Spring Cloud Kubernetes

Các namespace, ServiceAccount và dependency Kubernetes Config tương thích được giả định đã chuẩn bị. Những đoạn manifest dưới dùng dữ liệu nhỏ để thể hiện cách tổ chức.

### Nhóm tích hợp

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-core
  namespace: checkout
data:
  app.client.base-url: "https://payments.example.invalid"
  app.client.timeout: "2s"
  app.client.max-attempts: "3"
```

### Nhóm tính năng

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-features
  namespace: checkout
data:
  app.features.coupon-enabled: "true"
  app.features.express-checkout-enabled: "false"
```

### Nhóm quan sát

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-observability
  namespace: checkout
data:
  logging.level.example.checkout: "INFO"
```

Cấu hình khởi động của ứng dụng:

```yaml
spring:
  application:
    name: checkout-service
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        use-name-as-prefix: false
        include-profile-specific-sources: false
        sources:
          - name: checkout-core
            namespace: checkout
          - name: checkout-features
            namespace: checkout
          - name: checkout-observability
            namespace: checkout
      secrets:
        enabled: false
      discovery:
        enabled: false
```

Danh sách `sources` nạp ba ConfigMap; cơ chế hỗ trợ nhiều nguồn theo tên được mô tả trong [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Ví dụ chủ động dùng các nhóm khóa khác nhau. Tắt prefix giúp giữ đúng hợp đồng tên thuộc tính đang dùng. Nếu hai nguồn vô tình chứa cùng khóa, vẫn cần xét thứ tự ghi đè; việc chia resource không tự tạo namespace cho khóa Spring.

Tên như `checkout-core` hoặc `checkout-features` cũng không tự cho Configuration Watcher biết phải gửi refresh cho ứng dụng `checkout-service`. Nếu cần theo dõi động, phải thiết kế thêm quan hệ từ nguồn đến ứng dụng.

## 8. Chi phí của việc tách thành nhiều ConfigMap

Tách một object thành nhiều object có thể giúp rõ trách nhiệm, nhưng không đảm bảo hệ thống nhẹ hơn.

Có thể dùng mô hình ước lượng:

```text
Dung lượng dữ liệu mà mỗi instance phải xử lý
    ≈ tổng dung lượng các nguồn mà instance thực sự đọc
```

Đây là mô hình phân tích, không phải công thức dự báo chính xác heap hoặc số request. Client có thể cache, đọc theo batch hoặc đọc từng resource; parser và binder cũng tạo cấu trúc trong bộ nhớ.

Những yếu tố cần đo khi tăng số nguồn:

- Thời gian chuẩn bị Environment và khởi động ứng dụng.
- Tổng dữ liệu API trả về, không chỉ số resource được chọn.
- Số nguồn mà mỗi instance thật sự cần.
- Số instance khởi động hoặc refresh cùng lúc.
- Mức độ lan truyền khi một ConfigMap dùng chung thay đổi.
- Lỗi tải thiếu một phần cấu hình.

Một số dòng Spring Cloud Kubernetes hỗ trợ chế độ đọc theo batch hoặc đọc riêng theo tên. Cần đối chiếu phiên bản đang dùng trước khi suy luận rằng “chỉ chọn ba tên thì client chắc chắn chỉ tải đúng ba object”. Tài liệu [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html) trình bày các chế độ đọc và ảnh hưởng đến quyền truy cập.

Cùng một nguyên tắc áp dụng cho DiscoveryClient, LoadBalancer hoặc health indicator: chỉ bật tính năng cần dùng. Không thêm các nhóm cấu hình và quyền truy cập của tính năng khác chỉ vì chúng cùng thuộc Spring Cloud Kubernetes.

## 9. Phân quyền phải đi cùng đường đọc thực tế

Tách ConfigMap theo nhóm sở hữu có thể giúp tổ chức quyền sửa. Tuy nhiên, danh sách `sources` của ứng dụng chỉ chọn dữ liệu, không tự giới hạn quyền Kubernetes của ServiceAccount.

Ví dụ, nếu Role cho phép `list` toàn bộ ConfigMap trong namespace thì ServiceAccount có phạm vi đọc rộng hơn ba tên được liệt kê. Nếu muốn giới hạn theo `resourceNames`, phải bảo đảm request của client tương thích; không thể chỉ thêm giới hạn tên vào Role rồi giả định mọi cơ chế list vẫn hoạt động.

Cần ghi lại cho từng nguồn:

| Điều cần ghi | Ví dụ |
| --- | --- |
| Resource | `checkout/checkout-features` |
| Chủ sở hữu nội dung | Nhóm phụ trách tính năng |
| Danh tính ứng dụng đọc | ServiceAccount của checkout-service |
| Cách đọc | Kubernetes Config Data qua API |
| Quyền cần dùng | Theo chế độ đọc thực tế |
| Cách đưa bản mới vào ứng dụng | Rollout hoặc refresh đã thiết kế |

Nếu dùng ConfigMap chung giữa nhiều dịch vụ, một thay đổi có thể ảnh hưởng nhiều người tiêu thụ. Tách riêng theo trách nhiệm chỉ có ích khi quyền sửa và quy trình triển khai cũng phản ánh ranh giới đó.

## 10. Nhiều ConfigMap không tạo ra một giao dịch cập nhật chung

Giả sử có hai thay đổi phụ thuộc nhau:

```text
checkout-core: dùng giao thức mới với hệ thống thanh toán
checkout-features: bật tính năng yêu cầu giao thức mới
```

Cập nhật cả hai trong một file manifest không biến chúng thành một giao dịch nguyên tử trên nhiều resource. Ứng dụng hoặc watcher có thể quan sát trạng thái trung gian: phần này đã mới, phần kia còn cũ.

Vì vậy:

- Những khóa nhỏ bắt buộc nhất quán có thể nên ở cùng một ConfigMap.
- Những nhóm độc lập có thể cập nhật riêng.
- Một tập dữ liệu lớn cần nhất quán nguyên khối có thể cần nơi lưu và giao thức phiên bản khác.
- Refresh cần được xem như một luồng cập nhật của ứng dụng, không chỉ là sự kiện “resource đã đổi”.

Configuration Watcher hỗ trợ gửi thông báo refresh, nhưng cần cấu hình đúng nguồn theo dõi, ứng dụng đích, quyền truy cập và endpoint hoặc bus. Nó không tự tạo giao dịch cho nhiều ConfigMap. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Ngay cả khi Environment đã được cập nhật, một client tạo sẵn từ cấu hình cũ có thể vẫn cần được tạo lại hoặc cập nhật theo cơ chế phù hợp.

## 11. Dùng phiên bản khi cần triển khai một bộ cấu hình

Một phương án là tạo bộ resource mới có tên theo phiên bản:

```text
checkout-core-r17
checkout-features-r17
checkout-observability-r17
```

Trình tự triển khai có thể là:

1. Tạo và kiểm tra toàn bộ resource của bộ `r17`.
2. Kiểm tra hợp đồng dữ liệu và tính tương thích giữa các nhóm.
3. Đổi cấu hình khởi động của bản triển khai mới sang các tên `r17`.
4. Tạo Pod mới và xác minh cấu hình thực sự được nạp.
5. Giữ bộ cũ đủ thời gian phục vụ rollback.
6. Dọn các phiên bản không còn được tham chiếu theo quy trình của đội.

Có thể khai báo `immutable: true` cho ConfigMap nếu chọn mô hình tạo resource mới thay vì sửa dữ liệu của cùng tên. Đánh dấu immutable không tự đổi tham chiếu trong Deployment hay tự tạo một rollout.

Trong bộ cấu hình, nên có định danh phiên bản riêng cho từng phần và một phiên bản mong đợi do bản triển khai cung cấp. Ứng dụng kiểm tra các phần bắt buộc có mặt và tương thích trước khi nhận lưu lượng.

Ví dụ hợp đồng:

```text
Bản triển khai mong đợi: r17
Nhóm core cung cấp:     r17
Nhóm features cung cấp: r17
```

Nếu thiếu một nhóm hoặc nhận phiên bản khác, ứng dụng cần xử lý theo chính sách đã định, thay vì im lặng lấy mặc định. Một khóa phiên bản bị trùng và ghi đè giữa mọi nguồn sẽ không chứng minh từng phần đã được nạp; cần tên định danh phân biệt cho từng nhóm.

Cách làm này giảm nguy cơ đọc một bộ bị trộn phiên bản, nhưng không biến rollout nhiều Pod thành chuyển đổi đồng thời. Trong rollout, Pod cũ và Pod mới vẫn có thể cùng tồn tại; giao thức và dữ liệu phải chịu được giai đoạn đó.

## 12. Quy trình quyết định khi ConfigMap tăng nhanh

Khi một ConfigMap tiến gần ngưỡng, có thể xử lý theo trình tự:

| Bước | Việc cần làm | Kết quả mong muốn |
| --- | --- | --- |
| 1 | Đo payload đã render và kiểm tra annotation | Biết đúng loại giới hạn |
| 2 | Liệt kê nhóm dữ liệu và người sử dụng | Nhìn thấy dữ liệu thừa hoặc đặt sai chỗ |
| 3 | Chuyển dữ liệu lớn không phù hợp ra nơi lưu khác | ConfigMap giữ vai trò cấu hình |
| 4 | Chia theo trách nhiệm, vòng đời và quyền sở hữu | Có ranh giới vận hành rõ |
| 5 | Khai báo nguồn và chủ động kiểm soát khóa trùng | Giá trị hiệu lực giải thích được |
| 6 | Thiết kế cập nhật, kiểm tra phiên bản và rollback | Tránh bộ cấu hình bị trộn |
| 7 | Đo lại khởi động, đọc API và refresh | Xác nhận thiết kế đáp ứng thực tế |

Nên đặt ngưỡng cảnh báo nội bộ thấp hơn giới hạn cứng, dựa trên tốc độ tăng dữ liệu, công cụ apply và yêu cầu vận hành. Đó là chính sách của đội, không phải một ngưỡng Kubernetes mới; cũng không có một tỷ lệ dự phòng đảm bảo mọi manifest sẽ được chấp nhận.

Nếu cập nhật ConfigMap bị API từ chối vì dung lượng, đừng kết luận cấu hình đang chạy đã thay đổi. Phải xác nhận phiên bản resource còn tồn tại và giá trị ứng dụng đang dùng. Tăng retry hoặc chạy lại refresh không làm một bản cấu hình chưa được lưu thành bản hợp lệ.

Phân chia hợp lý nghĩa là mỗi ConfigMap chứa một nhóm cấu hình có thể giải thích được: **dùng cho ai, do ai sở hữu, lớn bao nhiêu, cập nhật khi nào và cần nhất quán với phần nào**. Số resource và kích thước từng phần là kết quả của thiết kế đó.
