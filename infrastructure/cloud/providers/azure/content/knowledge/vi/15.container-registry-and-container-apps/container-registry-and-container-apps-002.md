# Azure Container Registry, repository và image tag

## 1. Bối cảnh: ứng dụng container được lưu và triển khai như thế nào?

Trong Azure, một ứng dụng Java, Node.js hoặc Python có thể được đóng gói thành **container image** rồi chạy trên Azure Container Apps, Azure Kubernetes Service (AKS) hoặc một môi trường container phù hợp. Nhưng image không nên chỉ tồn tại trong laptop của lập trình viên: hệ thống CI/CD cần nơi đẩy image lên, môi trường staging cần tải đúng phiên bản đã kiểm thử và production cần biết chính xác artifact nào đang chạy.

**Azure Container Registry (ACR)** là dịch vụ registry được quản lý trên Azure, dùng để lưu trữ và phân phối container images và một số loại artifact theo chuẩn OCI. Trong module về hệ sinh thái Azure, ACR kết nối quy trình phát triển với subscription, resource group, Microsoft Entra ID, mạng, triển khai ứng dụng, giám sát, bảo mật và kiểm soát chi phí.

Ví dụ, đội phát triển có một API Java tên **orders-api**:

1. Build ứng dụng thành một file JAR.
2. Build Docker image từ JAR.
3. Đẩy image đến Azure Container Registry.
4. Gắn một tag phiên bản, ví dụ **1.4.0**.
5. Cấu hình Azure Container Apps dùng image đã được kiểm thử.
6. Khi cần sửa lỗi, tạo phiên bản mới hoặc quay lại đúng image đã triển khai trước đó.

Những bước này có vẻ đơn giản nhưng chứa nhiều khái niệm dễ nhầm: **registry**, **repository**, **tag**, **manifest**, **digest**, quyền push/pull và việc tag có thể thay đổi đích.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích vai trò của Azure Container Registry trong quy trình triển khai ứng dụng.
- Phân biệt registry, repository, image, layer, manifest, tag và digest.
- Đọc đúng một image reference có hostname, repository path và version.
- Tạo ACR, đăng nhập, build, tag, push, pull và xem image bằng Docker và Azure CLI.
- Hiểu vì sao dùng tag **latest** hoặc tag bị ghi đè có thể gây sai khác giữa các môi trường.
- Thiết kế quy trình phát hành dựa trên image digest để tăng khả năng tái lập và rollback.
- Phân quyền người hoặc workload bằng Microsoft Entra ID, managed identity và cơ chế RBAC phù hợp.
- Kết nối ACR với Azure Container Apps, AKS hoặc dịch vụ chạy container mà không lộ credential.
- Xử lý lỗi authentication, image name/tag, DNS, network và platform.
- Tính đến quản lý vòng đời image, quét bảo mật, logging và chi phí registry.

## 2. Registry, repository và image khác nhau ở đâu?

Có ba cấp độ cần phân biệt:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **Registry** | Dịch vụ lưu trữ nhiều repository và artifact | **acrlabexample.azurecr.io** |
| **Repository** | Tên logic gom nhiều phiên bản image cùng một sản phẩm hoặc thành phần | **apps/orders-api** |
| **Image** | Artifact chứa filesystem layers, cấu hình runtime và metadata để tạo container | Image của orders-api |
| **Tag** | Tên tham chiếu dễ đọc trỏ tới một image manifest | **1.4.0**, **staging**, **latest** |
| **Digest** | Định danh dựa trên hash nội dung của manifest hoặc image index | **sha256:...** |

Một registry có thể chứa các repository:

~~~text
acrlabexample.azurecr.io
├── apps/orders-api
│   ├── 1.3.0
│   ├── 1.4.0
│   └── release-2026-11
├── apps/customer-api
│   ├── 2.0.0
│   └── 2.1.0
└── workers/image-processor
    ├── 0.8.1
    └── 0.9.0
~~~

Các dòng **1.3.0**, **1.4.0** hay **0.9.0** biểu diễn **tags**, không phải những thư mục độc lập chứa bản sao đầy đủ của toàn bộ image. Nhiều tag có thể cùng trỏ tới một manifest, và các image có thể dùng chung những layers giống nhau.

**Repository không phải Azure resource group hoặc thư mục hệ điều hành.** Tên như **apps/orders-api** tạo một đường dẫn logic bên trong registry, không tự sinh các resource group hoặc một ranh giới phân quyền mới. Quyền repository-scoped chỉ có khi sử dụng mô hình phân quyền và tính năng mà ACR hỗ trợ.

## 3. Cấu trúc đầy đủ của một image reference

Một image được tham chiếu thông qua hostname registry, repository name và tag hoặc digest:

~~~text
<registry-login-server>/<repository>:<tag>
~~~

Ví dụ:

~~~text
acrlabexample.azurecr.io/apps/orders-api:1.4.0
~~~

Diễn giải:

| Đoạn | Giá trị ví dụ | Vai trò |
|---|---|---|
| Registry login server | acrlabexample.azurecr.io | Registry chứa artifact |
| Repository path | apps/orders-api | Tên logic của ứng dụng |
| Tag | 1.4.0 | Nhãn phiên bản có thể đọc được |

Một image cũng có thể được tham chiếu theo **digest**:

~~~text
acrlabexample.azurecr.io/apps/orders-api@sha256:<manifest-digest>
~~~

Trong image reference theo digest, phần **sha256:** phải là chuỗi hash thực tế do registry cung cấp. Không sử dụng placeholder khi triển khai.

### 3.1. Nếu không ghi tag thì sao?

Theo hành vi thường gặp của Docker, image reference không có tag có thể được diễn giải theo tag mặc định **latest**. Điều này tiện khi thử nghiệm nhưng tạo rủi ro: **latest không chứng minh đó là bản mới nhất theo ngày build, commit hay phiên bản nghiệp vụ**. Nó chỉ là một tên tag có thể được người có quyền thay đổi.

Đối với staging và production, nên **ghi tag rõ ràng** hoặc tốt hơn, triển khai theo **digest** nếu công cụ đích hỗ trợ.

### 3.2. Registry name và login server

Khi tạo ACR, bạn chọn một tên registry đáp ứng quy tắc đặt tên và tính duy nhất của Azure. Azure cung cấp login server thường có dạng:

~~~text
<registry-name>.azurecr.io
~~~

Tuy nhiên, trong môi trường có cấu hình domain hoặc DNS đặc biệt, luôn lấy **loginServer** từ tài nguyên registry thay vì tự ghép tên khi triển khai.

## 4. Container image được cấu tạo như thế nào?

Container image thường gồm nhiều **filesystem layers**, cấu hình runtime và một **manifest** mô tả những thành phần cần thiết để runtime tải image.

~~~mermaid
flowchart TD
    SRC[Source code và Dockerfile] --> BUILD[Container build]
    BUILD --> L[Filesystem layers]
    BUILD --> CFG[Image configuration]
    L --> MAN[Image manifest]
    CFG --> MAN
    MAN --> REG[Azure Container Registry]
    REG --> TAG[Tag: 1.4.0]
    REG --> DIGEST[Digest: sha256...]
    TAG --> DEPLOY[Container App / AKS]
    DIGEST --> DEPLOY
~~~

Một image có thể được build bằng Dockerfile, BuildKit, các công cụ OCI builder hoặc dịch vụ build trên Azure. Khi push, client truyền những layers và manifest cần thiết đến registry; các layers đã có có thể không cần tải lại.

**Container image không phải container đang chạy.** Image là artifact được lưu trong registry; container là tiến trình được tạo từ image trong môi trường runtime. Xóa image trên một registry không đồng nghĩa các container đang chạy bị dừng tức thì; tuy nhiên, lần pull, scale-out hoặc redeploy tiếp theo có thể lỗi nếu image không còn tồn tại.

### 4.1. Multi-platform image

Một số image hỗ trợ nhiều kiến trúc, ví dụ **linux/amd64** và **linux/arm64**. Khi đó một tham chiếu có thể trỏ đến **image index/manifest list** chứa nhiều manifest con cho từng platform.

Do đó, cần phân biệt:

- Digest của **image index** dùng cho tập platform.
- Digest của **manifest cụ thể** cho một platform.
- Kiến trúc CPU và hệ điều hành của máy chạy container.

Trong deployment, hãy kiểm tra image hỗ trợ đúng platform mà Azure Container Apps, AKS node pool hoặc máy đích sử dụng. Một tag tồn tại trong registry nhưng chỉ có image **arm64** có thể không chạy trên môi trường chỉ hỗ trợ **amd64**.

## 5. Tag: tên dễ đọc nhưng không tự bất biến

**Tag** giúp con người phân biệt các bản image:

~~~text
apps/orders-api:1.4.0
apps/orders-api:1.4.1
apps/orders-api:main-4f2c91a
apps/orders-api:latest
~~~

Tuy nhiên, theo mô hình registry phổ biến, một tag có thể được **trỏ lại** sang manifest khác khi người có quyền push cùng tên tag.

Ví dụ:

~~~text
Thứ Hai:
  apps/orders-api:1.4.0 -> digest AAA...

Thứ Tư (ai đó ghi đè cùng tag):
  apps/orders-api:1.4.0 -> digest BBB...
~~~

Nếu staging đã pull digest AAA, còn production pull tag 1.4.0 vào thứ Tư, hai môi trường có thể chạy **hai nội dung khác nhau dù hiển thị cùng tag**. Đây là một vấn đề nghiêm trọng về truy xuất nguồn gốc và khả năng rollback.

### 5.1. Tag không phải bản sao image

Gắn thêm một tag thường chỉ tạo một tham chiếu mới. Nó không tự động nhân đôi toàn bộ layers.

### 5.2. Tránh dùng latest làm bằng chứng phát hành

Tag **latest** không có quy tắc bắt buộc rằng nó phải trỏ đến build mới nhất. Nếu muốn dùng trong dev, cần hiểu rõ ai cập nhật và thời điểm cập nhật. Đối với production, không dựa vào latest để chứng minh phiên bản đang chạy.

### 5.3. Khi nào dùng tag phiên bản?

Tag kiểu **1.4.0** hữu ích để đọc và đối chiếu với release notes. Tag có commit SHA giúp truy vết từ image về mã nguồn. Có thể kết hợp cả hai miễn không ghi đè tùy tiện và vẫn lưu digest.

## 6. Digest: tham chiếu chính xác nội dung image

**Digest** là hash nội dung của manifest hoặc image index theo cơ chế OCI/Docker distribution, thường hiển thị với tiền tố **sha256:**.

Ví dụ:

~~~text
acrlabexample.azurecr.io/apps/orders-api@sha256:<64-hex-character-value>
~~~

Khi tham chiếu bằng một digest thực, runtime yêu cầu đúng manifest/index mang hash đó. Nếu tag được chuyển sang manifest khác, digest cũ **không thay đổi**.

| So sánh | Tag | Digest |
|---|---|---|
| Dễ đọc cho con người | Cao | Thấp |
| Có thể được gán lại | Có, nếu không bị khóa hoặc kiểm soát | Nội dung được định danh theo hash |
| Thích hợp ghi release version | Có | Nên lưu kèm |
| Hỗ trợ deploy tái lập | Chưa đủ nếu tag có thể đổi | Mạnh hơn, khi artifact còn tồn tại |
| Có thể trỏ đến nhiều platform | Có | Có, nếu digest là image index |
| Bảo đảm artifact không bao giờ bị xóa | Không | Không |

**Digest bất biến về định danh nội dung, không có nghĩa artifact tồn tại vĩnh viễn.** Nếu manifest và layers bị xóa theo chính sách lưu trữ, deployment theo digest cũng không thể pull thành công.

**Khuyến nghị:** pipeline build ra image một lần, lấy digest sau push, dùng chính digest đó để promotion qua test, staging và production. Đừng build lại từ source ở từng môi trường rồi mặc định kết quả giống nhau.

## 7. Chọn cấu trúc repository và chiến lược tag

Ví dụ tổ chức có ba dịch vụ Java:

~~~text
acrlabexample.azurecr.io/commerce/orders-api:1.4.0
acrlabexample.azurecr.io/commerce/payments-api:2.2.1
acrlabexample.azurecr.io/workers/invoice-exporter:0.9.3
~~~

Cách đặt tên tốt nên có:

- Tên ứng dụng nhất quán giữa repository, source code và deployment.
- Repository path có ý nghĩa theo nhóm/sản phẩm.
- Tag version rõ ràng, có thể gắn commit hash hoặc build ID.
- Quy tắc đặt tên tương thích Docker/OCI registry.
- Cơ chế phân quyền và vòng đời riêng nếu các nhóm có mức nhạy cảm khác nhau.

### 7.1. Một repository cho nhiều phiên bản cùng ứng dụng

Đây là mô hình thường dễ vận hành:

~~~text
commerce/orders-api
  1.4.0
  1.4.1
  1.5.0
~~~

### 7.2. Có nên tạo repository riêng cho dev/prod?

Không có câu trả lời chung. Có thể:

- Dùng một repository, build một image rồi **promotion theo digest** qua nhiều môi trường.
- Dùng registry riêng cho production và non-production để tách ranh giới quyền/mạng và chi phí.
- Dùng repository riêng theo nhóm nếu có yêu cầu phân quyền thực sự và tính năng được hỗ trợ.

Không nên nhân bản image hoặc build lại chỉ để đặt tên khác nếu mục tiêu là xác nhận cùng artifact. Khi cần tách registry, có thể sao chép/import artifact theo cơ chế ACR phù hợp và đối chiếu digest/manifest.

## 8. Các SKU Azure Container Registry

ACR có những cấp dịch vụ phổ biến như **Basic**, **Standard** và **Premium**. Chúng khác nhau về giới hạn, hiệu năng, dung lượng, tính năng mạng và khả năng phục hồi.

| SKU | Định hướng chung | Điểm cần cân nhắc |
|---|---|---|
| **Basic** | Học tập và workload có nhu cầu registry nhỏ | Ít năng lực hoặc tính năng nâng cao hơn |
| **Standard** | Nhu cầu registry cao hơn về quy mô và thông lượng | Phù hợp nhiều workflow CI/CD thông thường |
| **Premium** | Tổ chức cần một số tính năng nâng cao | Cân nhắc private endpoint, geo-replication và những tính năng tùy thời điểm hỗ trợ |

Thông số chi tiết như storage, thông lượng pull/push, webhook, retention, network restriction, geo-replication hoặc bảo mật có thể thay đổi theo SKU và khu vực. Trước khi chọn, phải đối chiếu bảng feature support và bảng giá Azure hiện hành.

### 8.1. Khi nào cần geo-replication?

Một tổ chức có ứng dụng chạy ở nhiều Azure region có thể muốn các image được phân phối gần nơi chạy để giảm độ trễ pull và có phương án khả dụng cao hơn. **ACR geo-replication** là tính năng cần xem xét ở SKU hỗ trợ, thường gắn với Premium.

Nhưng nhân bản registry **không tự triển khai hoặc chuyển traffic ứng dụng đa region**. Cần thiết kế riêng Azure Container Apps/AKS, networking, dữ liệu và cơ chế failover.

### 8.2. Khi nào cần private endpoint?

Nếu chính sách yêu cầu registry được truy cập qua mạng riêng, cần kiểm tra tính năng **Private Link/private endpoint** của SKU và khả năng DNS/route tại mọi nơi push/pull image, bao gồm CI runner, AKS node và Container Apps environment. Private endpoint không tự tạo đường mạng cho một máy nằm ngoài VNet.

## 9. Chuẩn bị một môi trường thử nghiệm ACR

Các ví dụ sử dụng Bash với Azure CLI và Docker. Chúng chỉ là hướng dẫn thực hành; không thực thi trực tiếp trong bài học.

Điều kiện:

1. Có Azure subscription được phép tạo tài nguyên.
2. Có quyền tạo Azure Container Registry trong resource group thử nghiệm.
3. Đã cài Azure CLI và Docker CLI/engine hoặc có công cụ build tương đương.
4. Đăng nhập bằng danh tính có quyền push/pull thích hợp.
5. Có tên ACR duy nhất và hiểu chi phí của registry.
6. Có source code và Dockerfile thử nghiệm; không dùng secret/dữ liệu khách hàng thật.
7. Biết cách kiểm tra và xóa đúng tài nguyên lab sau khi hoàn thành.

Ví dụ dùng:

~~~text
Resource group: rg-acr-lab
Registry name: acrlabunique12345
Repository: apps/orders-api
Tag: 1.0.0
~~~

**Tên registry là ví dụ**, không bảo đảm còn khả dụng. Thay **acrlabunique12345** bằng tên duy nhất bạn sở hữu. Tên registry có các quy tắc ký tự và độ dài riêng; không tự ghép dấu gạch ngang rồi giả định Azure chấp nhận.

## 10. Tạo Azure Container Registry bằng Azure CLI

Đăng nhập Azure và chọn subscription:

~~~bash
az login
az account set --subscription "<subscription-id>"
~~~

Tạo resource group và registry:

~~~bash
az group create \
  --name rg-acr-lab \
  --location southeastasia

az acr create \
  --resource-group rg-acr-lab \
  --name acrlabunique12345 \
  --sku Basic \
  --admin-enabled false
~~~

Trong ví dụ, **admin-enabled false** thể hiện chủ đích không sử dụng tài khoản administrator chia sẻ của registry làm phương thức mặc định.

Xem thông tin registry:

~~~bash
az acr show \
  --name acrlabunique12345 \
  --query "{name:name,loginServer:loginServer,sku:sku.name,adminUserEnabled:adminUserEnabled}" \
  --output json
~~~

Lấy login server:

~~~bash
ACR_NAME="acrlabunique12345"
ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer --output tsv)"
echo "$ACR_LOGIN_SERVER"
~~~

Kết quả mong đợi có dạng:

~~~text
acrlabunique12345.azurecr.io
~~~

Registry là Azure resource có thể được quản lý bằng Azure RBAC và chính sách tổ chức. **Tạo registry không tự động tạo repository**. Repository thường xuất hiện khi image được push/import thành công.

## 11. Đăng nhập registry và phân biệt Azure login với Docker login

Có hai hệ thống liên quan:

- **az login**: xác thực Azure CLI với Microsoft Entra ID.
- **az acr login**: lấy thông tin/token phù hợp để Docker client làm việc với Azure Container Registry bằng danh tính và quyền đang dùng.

Ví dụ:

~~~bash
az acr login --name "$ACR_NAME"
~~~

Lệnh trên thường tích hợp với Docker CLI/daemon trên máy phát triển. Nếu Docker engine chưa chạy, quá trình đăng nhập kiểu thông thường có thể thất bại dù Azure CLI đã đăng nhập hợp lệ.

Khi không có Docker daemon nhưng cần lấy token cho một công cụ tương thích, Azure CLI có tùy chọn phù hợp:

~~~bash
az acr login --name "$ACR_NAME" --expose-token
~~~

Tùy chọn này trả về token và thông tin liên quan; **token vẫn là credential nhạy cảm**. Không đưa nội dung token vào log CI công khai, tài liệu hay chat. Hãy dùng phương án xác thực do công cụ build/deploy hỗ trợ.

**Đăng nhập thành công không chứng minh tài khoản có quyền push.** Danh tính có thể chỉ được cấp quyền pull hoặc thiếu quyền data-plane của repository. Khi bị từ chối, phải kiểm tra authorization và chế độ quyền của registry.

## 12. Ví dụ Dockerfile đóng gói ứng dụng Java

Giả sử Maven đã tạo file **target/orders-api.jar** và ứng dụng lắng nghe HTTP trên cổng 8080. Một Dockerfile đơn giản:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY target/orders-api.jar /app/orders-api.jar

USER 10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

Giải thích:

- **FROM** chọn runtime image nền có Java.
- **WORKDIR** tạo ngữ cảnh làm việc.
- **COPY** đưa artifact đã build vào image.
- **USER 10001** chạy process bằng UID không phải root, nếu permission của ứng dụng cho phép.
- **EXPOSE 8080** mô tả cổng ứng dụng sử dụng; nó không tự mở cổng public.
- **ENTRYPOINT** khai báo tiến trình khi container chạy.

Đây là ví dụ học tập. Trong production nên:

- Pin base image theo phiên bản hoặc digest đã kiểm thử.
- Sử dụng multi-stage build nếu phù hợp.
- Giảm số package không cần thiết.
- Chạy dưới non-root user, kiểm tra quyền ghi log/temp.
- Không đưa file **.env**, credential hoặc khóa riêng vào image context.
- Dùng **.dockerignore** để loại thư mục không cần, file bí mật và dữ liệu build thừa.
- Quét dependency và image trước khi phát hành.

Nếu JAR chưa được tạo hoặc tên file khác, lệnh Docker build sẽ lỗi ở bước COPY; phải build ứng dụng trước.

## 13. Build image cục bộ

Từ thư mục có Dockerfile và artifact JAR:

~~~bash
docker build \
  -t orders-api:1.0.0 \
  .
~~~

Kiểm tra danh sách image:

~~~bash
docker image ls
~~~

Chạy thử container ở môi trường local:

~~~bash
docker run --rm \
  --name orders-api-test \
  -p 8080:8080 \
  orders-api:1.0.0
~~~

Mở một terminal khác để kiểm tra API thật, ví dụ:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Đường dẫn **/health** chỉ tồn tại nếu ứng dụng đã triển khai endpoint đó. Nếu không, hãy kiểm tra bằng endpoint mà ứng dụng thực sự cung cấp.

Kiểm tra chức năng trước khi push giúp tránh lưu một image không khởi động được vào registry, nhưng **kiểm thử local không thay thế test trên Container Apps/AKS** vì cấu hình mạng, danh tính, kiến trúc CPU và resource limits có thể khác.

## 14. Docker tag: đặt tên image để push vào ACR

Image local ban đầu có tên:

~~~text
orders-api:1.0.0
~~~

Để push vào registry, gắn thêm tên đầy đủ:

~~~bash
docker tag \
  orders-api:1.0.0 \
  "$ACR_LOGIN_SERVER/apps/orders-api:1.0.0"
~~~

Kiểm tra:

~~~bash
docker image ls
~~~

**docker tag không upload image.** Nó chỉ tạo thêm một image reference local. Sau thao tác này, image có thể xuất hiện dưới cả tên **orders-api:1.0.0** và **acrlabunique12345.azurecr.io/apps/orders-api:1.0.0** trong danh sách image local.

Khi người dùng thấy Docker tag mới được tạo mà Azure Portal chưa có repository, nguyên nhân thường là vì **chưa chạy push**.

## 15. Docker push: đưa image và manifest lên ACR

Khi đã đăng nhập ACR bằng danh tính có quyền push:

~~~bash
docker push "$ACR_LOGIN_SERVER/apps/orders-api:1.0.0"
~~~

Docker/OCI client kiểm tra layers cần tải, đẩy những phần chưa tồn tại và ghi manifest/tag lên registry.

Sau khi push thành công:

- Registry có repository **apps/orders-api**.
- Tag **1.0.0** được gắn cho manifest tương ứng.
- Azure Container Apps/AKS hoặc Docker client khác có thể pull nếu có quyền và kết nối mạng phù hợp.
- Registry có thể dùng chung các layers trùng nhau, nên không nhất thiết lưu bản sao đầy đủ cho mỗi tag.

Nếu báo **denied / unauthorized**, đừng bật tài khoản admin của registry ngay. Kiểm tra Azure login, RBAC data-plane, chế độ phân quyền repository, đúng registry name và quyền push.

Nếu báo lỗi mạng, kiểm tra DNS, proxy/firewall, cấu hình private endpoint và endpoint của registry; authorization và networking là hai nhóm lỗi khác nhau.

## 16. Kiểm tra repository và image tag bằng Azure CLI

Liệt kê repositories:

~~~bash
az acr repository list \
  --name "$ACR_NAME" \
  --output table
~~~

Liệt kê tags của một repository:

~~~bash
az acr repository show-tags \
  --name "$ACR_NAME" \
  --repository apps/orders-api \
  --orderby time_desc \
  --detail \
  --output table
~~~

Xem metadata một image theo tag:

~~~bash
az acr repository show \
  --name "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  --output json
~~~

Lấy digest từ metadata nếu trường này có sẵn theo CLI/API đang sử dụng:

~~~bash
az acr repository show \
  --name "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  --query digest \
  --output tsv
~~~

**Lưu ý:** CLI và ACR API có thể thay đổi lệnh/trường metadata theo phiên bản. Nếu một lệnh bị đánh dấu deprecated hoặc không hiển thị dữ liệu mong đợi, dùng lệnh manifest/repository được Azure CLI hiện hành hỗ trợ. Không tự đoán digest từ Docker image ID, vì image ID, manifest digest và multi-platform index digest có thể khác nhau.

Kiểm tra trong Portal: vào **Azure Container Registry → Repositories**, chọn **apps/orders-api** để xem tag, digest và thông tin có sẵn.

## 17. Pull image từ máy hoặc môi trường khác

Ở một máy được quyền truy cập:

~~~bash
az login
az acr login --name acrlabunique12345

docker pull \
  acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

Chạy image bằng cấu hình môi trường phù hợp nếu cần:

~~~bash
docker run --rm \
  -p 8080:8080 \
  acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

Khi pull, Docker client xác định manifest từ tag và tải layers cần thiết. Nếu image đã có trong cache local, hành vi sử dụng cache và refresh phụ thuộc lệnh/runtime. Vì vậy đừng giả định việc đổi nội dung của một tag sẽ cập nhật mọi container đang chạy.

Một deployment phải **chủ động cập nhật revision/pod/container** theo cơ chế dịch vụ. Việc push thêm image mới vào ACR không tự khởi động lại tất cả container sử dụng tag đó.

## 18. Build trên Azure bằng ACR Tasks

Ngoài Docker build trên laptop, ACR hỗ trợ khả năng build image ở môi trường được quản lý, thường qua **ACR Tasks**. Với source và Dockerfile hợp lệ:

~~~bash
az acr build \
  --registry "$ACR_NAME" \
  --image apps/orders-api:1.0.0 \
  .
~~~

Lệnh này gửi build context thích hợp để build trên Azure, giảm phụ thuộc Docker daemon local cho quá trình build theo cơ chế của dịch vụ.

Cần hiểu:

- Build context có thể chứa file không mong muốn nếu thiếu **.dockerignore**.
- Nếu Dockerfile cần file **target/orders-api.jar**, phải tạo JAR trong context trước hoặc sử dụng Dockerfile multi-stage có bước build.
- Build vẫn tiêu thụ tài nguyên và có thể phát sinh chi phí theo cấu hình/tính năng của ACR.
- Một build thành công không thay thế kiểm thử ứng dụng hoặc image scanning.
- Nếu nguồn chứa secret hoặc dữ liệu nhạy cảm, đừng gửi chúng trong build context.

ACR Tasks còn có những khả năng tự động hóa build/triggers trong phạm vi hỗ trợ của SKU và cấu hình. Đối với dự án lớn, chọn rõ một hệ thống chịu trách nhiệm build artifact để tránh hai pipeline cùng ghi đè một release tag.

## 19. Authentication và authorization với Azure Container Registry

Một hệ thống an toàn cần tách ba vai trò:

1. **Build pipeline**: được phép push image của sản phẩm.
2. **Runtime** (Container Apps, AKS, VM): chỉ cần quyền pull image.
3. **Administrator**: quản lý cấu hình registry, mạng và chính sách.

### 19.1. Microsoft Entra ID và Azure RBAC

ACR có cơ chế tích hợp Microsoft Entra ID và Azure role assignments. Với registry dùng mô hình RBAC thông thường, các vai trò quen thuộc là:

- **AcrPull**: đọc/pull artifact theo phạm vi quyền được cấp.
- **AcrPush**: push và các thao tác dữ liệu liên quan theo quyền được cấp.
- Các quyền quản trị registry cần vai trò quản lý riêng theo nhiệm vụ.

Khi dùng chế độ **repository permissions/ABAC** được ACR hỗ trợ, mô hình và tên vai trò phù hợp có thể khác, chẳng hạn quyền reader/writer theo repository. **Không mặc định AcrPull/AcrPush hoạt động y hệt trên mọi kiểu registry authorization**. Trước khi cấp quyền, hãy kiểm tra chế độ permission và các role được hỗ trợ của registry.

### 19.2. Dùng managed identity để pull

Với Azure Container Apps, AKS hoặc workload Azure hỗ trợ, nên cân nhắc **managed identity** để tránh hardcode Docker password hoặc admin credentials.

Quy trình khái niệm:

1. Tạo hoặc bật identity cho workload.
2. Xác định identity principal ID và đúng registry scope.
3. Cấp quyền **pull** theo mô hình RBAC hoặc repository authorization mà registry đang dùng.
4. Cấu hình workload sử dụng identity để xác thực với ACR.
5. Kiểm tra network/DNS và pull image bằng đúng identity.
6. Theo dõi khi role assignment cần thời gian lan truyền.

Một ví dụ tạo role assignment cho registry dùng RBAC thông thường, sau khi đã có các giá trị thật:

~~~bash
az role assignment create \
  --assignee-object-id "<workload-principal-object-id>" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "<acr-resource-id>"
~~~

**Ví dụ trên không áp dụng nguyên xi cho mọi chế độ repository ABAC.** Cần chọn role và scope đúng theo cấu hình registry.

### 19.3. Có nên bật ACR admin user?

Admin account của ACR là thông tin xác thực chia sẻ với phạm vi quyền rộng và không gắn trách nhiệm với một workload riêng. Chỉ bật khi có nhu cầu đặc biệt, được phê duyệt và có biện pháp bảo vệ thích hợp. Không sử dụng nó làm phương án mặc định chỉ để xử lý một lỗi quyền tạm thời.

Nếu phải sử dụng credential, lưu trong secret manager, không đặt trong Dockerfile/source code và có quy trình rotation.

## 20. Kết nối ACR với Azure Container Apps

**Azure Container Apps** có thể chạy container image được lưu trong ACR. Tư duy kết nối:

~~~mermaid
flowchart LR
    DEV[Developer commit] --> CI[CI build/test]
    CI --> REG[Azure Container Registry]
    REG --> REPO[apps/orders-api:1.0.0]
    REPO --> APP[Azure Container App revision]
    ID[Managed identity và quyền pull] --> APP
    APP --> MON[Logs và metrics]
~~~

### 20.1. Các điều kiện cần có

- Azure Container App hoặc Container Apps environment được triển khai và cấu hình đúng.
- Image đã push thành công vào registry.
- Runtime identity/credential có quyền pull.
- Runtime có đường mạng và DNS đến login server/endpoints ACR.
- Image có architecture/OS hỗ trợ.
- Cổng ứng dụng và ingress phù hợp.
- Secrets/connection strings của ứng dụng được truyền qua cơ chế cấu hình an toàn.

### 20.2. Cập nhật image

Khi ứng dụng đã được cấu hình registry authentication, có thể cập nhật image bằng lệnh tham khảo:

~~~bash
az containerapp update \
  --name orders-api \
  --resource-group rg-containerapps \
  --image acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
~~~

Lệnh minh họa **chỉ thay image** và giả định Container App đã tồn tại cùng cấu hình pull authentication hợp lệ. Đừng dùng nó như quy trình tạo đầy đủ registry/identity/Container Apps environment.

Sau cập nhật:

1. Xem revision và trạng thái triển khai.
2. Kiểm tra app logs.
3. Kiểm tra readiness/startup và endpoint nghiệp vụ.
4. Xác nhận image thực tế/digest dùng trong revision nếu môi trường cung cấp thông tin.
5. Giữ phương án rollback về release đã kiểm thử.

**ACR push không đồng nghĩa Container Apps tự cập nhật.** Dịch vụ cần một quy trình deployment rõ ràng, có phiên bản và kiểm thử.

## 21. Kết nối ACR với Azure Kubernetes Service và VM

Ở AKS, mỗi node cần lấy container image theo cấu hình pod. Nếu ACR private, cụm phải được cấu hình quyền pull thích hợp theo phương thức hỗ trợ.

Ví dụ một phần cấu hình Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: acrlabunique12345.azurecr.io/apps/orders-api:1.0.0
          ports:
            - containerPort: 8080
~~~

Đây là ví dụ cấu trúc manifest, **không tự cấp quyền pull**. AKS node/kubelet identity hoặc một cơ chế registry authentication được hỗ trợ phải truy cập được ACR. Với registry có repository ABAC, cần xem lại cách tích hợp và role assignment phù hợp.

Ở VM Docker thông thường, Docker client/daemon có thể đăng nhập và pull bằng thông tin xác thực được cấp. Nhưng lưu credential lâu dài trên VM làm tăng rủi ro; cần một giải pháp quản lý danh tính và secret phù hợp.

## 22. CI/CD: build một lần, triển khai cùng một artifact

Một pipeline sản xuất cần bảo đảm image được kiểm thử ở staging chính là image dùng trong production.

~~~mermaid
flowchart TD
    GIT[Source commit] --> TEST[Unit tests và static checks]
    TEST --> BUILD[Build image]
    BUILD --> SCAN[Scan, SBOM, policy checks]
    SCAN --> PUSH[Push ACR]
    PUSH --> DIGEST[Đọc digest]
    DIGEST --> STAGE[Deploy staging theo digest]
    STAGE --> VERIFY[Integration/E2E test]
    VERIFY --> APPROVE{Approval?}
    APPROVE -->|Có| PROD[Promote chính digest vào production]
    APPROVE -->|Không| STOP[Không phát hành]
    PROD --> OBS[Monitoring và rollback plan]
~~~

### 22.1. Tại sao không build lại ở production?

Hai lần build cùng source code vẫn có thể khác nhau vì:

- Base image tag đã thay đổi.
- Dependency không được khóa phiên bản.
- Timestamps hoặc metadata build khác.
- Build tool sử dụng nguồn tài nguyên không ổn định.
- Compiler/package repository có bản mới.

Vì vậy, **build một lần**, push một artifact, ghi lại digest và deploy lại artifact đó. Nếu cần hai registry khác nhau, thực hiện promotion/copy có kiểm chứng thay vì rebuild.

### 22.2. Gợi ý metadata release

| Thông tin | Ví dụ |
|---|---|
| Git commit | 4f2c91a... |
| Build ID | ci-20261120-142 |
| Repository | apps/orders-api |
| Human-readable tag | 1.4.0 |
| Immutable reference | sha256:... |
| Base image digest | sha256:... |
| SBOM/scan status | Passed theo policy |
| Deployed environment | staging rồi production |
| Approval | Change request hoặc release review |

Đảm bảo có thể truy ngược **từ một container đang chạy về image digest, pipeline run và source commit**.

## 23. Chiến lược image tag cho môi trường

Một số nhóm dùng tag **dev**, **staging**, **prod** như một con trỏ di chuyển theo release. Cách này tiện nhưng có rủi ro nếu tag bị ghi đè mà deployment không cập nhật rõ.

### Phương án A — Immutable release tags

~~~text
apps/orders-api:1.4.0
apps/orders-api:1.4.1
apps/orders-api:1.5.0
~~~

Mỗi release tag chỉ gắn với một nội dung đã phê duyệt. Có thể kiểm soát bằng quy trình pipeline và khả năng khóa tag/manifest được registry hỗ trợ.

### Phương án B — Commit tags

~~~text
apps/orders-api:git-4f2c91a
apps/orders-api:git-a3b9d20
~~~

Hữu ích để tra nguồn code. Nhưng chỉ dùng một SHA rút gọn có thể chưa đủ để chứng minh artifact duy nhất nếu pipeline rebuild nhiều lần; vẫn ghi digest.

### Phương án C — Environment pointer tags

~~~text
apps/orders-api:dev
apps/orders-api:staging
apps/orders-api:prod
~~~

Đây là những tag **có thể di chuyển**. Nếu dùng, cần kiểm soát rõ ai cập nhật, khi nào, và lưu release manifest/digest. Không dùng chúng làm nguồn chứng cứ duy nhất cho nội dung production.

### Lựa chọn

**Ưu tiên một release tag không bị ghi đè + digest được ghi nhận.** Với workload nhạy cảm, triển khai theo digest và dùng tag để giao tiếp giữa con người.

## 24. Khóa tag và bảo vệ image phát hành

Một số khả năng ACR hỗ trợ cấu hình thuộc tính của manifest/tag, chẳng hạn hạn chế ghi đè hoặc xóa. Tuy nhiên, chi tiết và phạm vi khóa phụ thuộc tính năng/CLI version.

Khái niệm cần phân biệt:

- **Không cho ghi đè**: giúp giữ tag/manifest đã phát hành không bị thay đổi ngoài ý muốn.
- **Không cho xóa**: giúp tránh xóa một artifact còn được production tham chiếu.
- **Retention**: dọn artifact không còn cần theo chính sách.
- **RBAC/ABAC**: giới hạn ai được tạo, ghi, xóa hoặc đọc trong registry.

Khóa không thay thế kiểm soát identity hoặc nguồn image. Nếu build pipeline có quyền quá rộng, nó vẫn có thể gây rủi ro ở những repository khác.

Trước khi xóa/khóa một manifest, phải kiểm tra:

1. Có revision/pod nào đang tham chiếu image/tag/digest không?
2. Hệ thống DR hoặc rollback có cần artifact này không?
3. Registry khác đã có bản copy kiểm chứng chưa?
4. Có tag khác trỏ cùng digest không?
5. Chính sách retention và audit yêu cầu lưu bao lâu?

## 25. Cleanup: quản lý vòng đời repository và image

Khi pipeline tạo hàng trăm tags mỗi tuần, registry có thể tích lũy image manifests và layers không còn được dùng.

Một quy trình dọn dẹp an toàn:

1. Phân loại **release**, **rollback**, **dev/test** và **untagged artifacts**.
2. Xác định thời hạn giữ riêng cho từng nhóm.
3. Đối chiếu các version đang triển khai trên staging/production và DR.
4. Chỉ xóa image thật sự không còn tham chiếu.
5. Kiểm tra khả năng khôi phục một release cũ sau cleanup.
6. Giám sát storage usage và chi phí trước/sau.
7. Ghi log những thao tác xóa theo quy trình tổ chức.

ACR cung cấp các cơ chế hỗ trợ cleanup/retention trong những cấu hình và SKU nhất định. Không giả định mọi chính sách tự động dọn artifact có cùng hành vi đối với **tagged**, **untagged**, **locked** hoặc **multi-platform images**.

**Cảnh báo:** xóa tag hoặc manifest từ ACR có thể khiến lần triển khai tiếp theo lỗi **manifest unknown** hoặc **not found**. Không thử lệnh xóa trên registry đang dùng production nếu chưa kiểm chứng.

## 26. Bảo mật chuỗi cung ứng container

Registry là điểm phân phối artifact, nên cần coi đây là một phần của **software supply chain security**.

### 26.1. Chỉ đưa image tin cậy vào registry

- Pin base image theo phiên bản/digest đã kiểm thử.
- Kiểm tra provenance của image nền.
- Quét dependency và các lỗ hổng đã biết.
- Giảm image layers và phần mềm không cần.
- Sử dụng SBOM (Software Bill of Materials) khi có yêu cầu.
- Cân nhắc signing/attestation và xác minh trước deploy khi nền tảng hỗ trợ.
- Không upload secret, private key hoặc file .env vào image.

**Xóa secret trong một layer sau đó không bảo đảm secret biến mất khỏi lịch sử layers**. Phải loại secret khỏi build context và dùng secret mechanism đúng của build pipeline.

### 26.2. Phân quyền push và pull

Build identity thường cần quyền ghi đúng phạm vi; runtime identity chỉ cần đọc. Một pipeline của đội orders-api không nên mặc nhiên được ghi đè images của payments-api nếu tổ chức có chính sách phân quyền theo repository.

### 26.3. Bảo vệ network

Với private registry access:

- Kiểm tra DNS resolve đúng.
- Bảo đảm CI runner có đường mạng đến registry.
- Kiểm tra node/Container Apps environment có route đến ACR và những endpoints cần thiết để tải layers.
- Đánh giá firewall, proxy và private endpoint.
- Tránh bật public network rộng chỉ để xử lý sự cố mà không có đánh giá rủi ro.

### 26.4. Monitoring và incident response

Theo dõi:

- Sự kiện push/delete hoặc thay đổi quyền registry.
- Các lỗi xác thực bất thường.
- Thay đổi network restriction.
- Image scan findings.
- Artifact digest được triển khai.
- Các deploy ngoài quy trình phê duyệt.

Khả năng log/metrics và hình thức export phụ thuộc Azure Monitor, diagnostic settings và các tính năng ACR/Defender đang sử dụng.

## 27. Xử lý lỗi ACR thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| **unauthorized / denied** khi push | Thiếu quyền push, nhầm registry, token không hợp lệ | Kiểm tra danh tính, quyền và chế độ authorization |
| **unauthorized** khi pull từ Container Apps/AKS | Runtime identity thiếu quyền hoặc chưa cấu hình | Kiểm tra identity, role/scope và registry config |
| **manifest unknown** | Tag/digest không tồn tại hoặc đã bị xóa | Kiểm tra repository/tags/digest thực |
| **repository not found** | Sai path, image chưa push, khác registry | Kiểm tra login server và repository name |
| **Docker daemon unavailable** | Docker engine chưa chạy | Chạy Docker hoặc dùng ACR Tasks/công cụ phù hợp |
| **TLS/timeout/DNS failure** | Network, DNS, proxy, private endpoint | Kiểm tra phân giải tên và đường mạng của client |
| **exec format error** | Image không hỗ trợ OS/CPU architecture | Kiểm tra platform và manifest |
| **ImagePullBackOff** trong Kubernetes | Pull, auth, network hoặc image reference thất bại | Xem events/logs pod và kiểm tra ACR |
| Container chạy nhưng ứng dụng không phục vụ | Sai port, config, thiếu secret, startup lỗi | Xem runtime logs, readiness và app settings |
| Tag trùng nhưng hành vi khác | Tag được ghi đè hoặc local cache khác | Đối chiếu digest thực trên từng môi trường |

### 27.1. Điều tra theo thứ tự

1. Ghi lại **full image reference** gồm registry, repository và tag/digest.
2. Kiểm tra registry/repository/tag có tồn tại.
3. Kiểm tra role và identity thực sự dùng để pull/push.
4. Kiểm tra DNS và network từ đúng nơi chạy workload.
5. Kiểm tra platform và manifest.
6. Kiểm tra runtime startup logs nếu pull thành công nhưng container lỗi.
7. Đối chiếu digest với release manifest của pipeline.

Một lỗi **ImagePullBackOff** không nhất thiết là lỗi ACR; có thể do tên tag, quyền AKS, private networking hoặc platform. Không nên bật admin user rồi thử lại như bước mặc định.

## 28. Thiết kế chi phí và vận hành Registry

ACR có các khoản chi phí có thể bao gồm:

- SKU/tier của registry.
- Storage dùng cho layers/manifests.
- Các thao tác build hoặc tính năng nâng cao theo mô hình tính phí áp dụng.
- Geo-replication, network/data transfer nếu sử dụng.
- Những dịch vụ phụ trợ như Azure Monitor, CI runner, image scanning hoặc private networking.

Các nguyên tắc tối ưu:

1. Không tạo registry mới cho mỗi build hoặc feature branch.
2. Phân tách registry theo ranh giới bảo mật/đơn vị vận hành có lý do rõ ràng.
3. Giới hạn artifact cũ theo retention được kiểm soát.
4. Dùng image layers hợp lý để tận dụng cache và giảm kích thước tải.
5. Kiểm tra chi phí xây dựng/nhân bản image giữa region.
6. Đặt Azure Cost Management budgets và tags phù hợp.
7. Không xóa image mà rollback hoặc một môi trường DR còn cần.

**ACR không phải runtime compute.** Registry giữ artifact; compute cost của Container Apps, AKS hoặc VM được tính riêng theo dịch vụ chạy ứng dụng.

## 29. Bài thực hành end-to-end

**Bối cảnh:** đội phát triển có API Java sẵn JAR và muốn dùng Azure Container Registry làm nguồn image cho môi trường thử nghiệm.

### Phần A — Tạo registry

1. Đăng nhập Azure và chọn subscription thử nghiệm.
2. Tạo resource group **rg-acr-lab**.
3. Tạo ACR với tên duy nhất, SKU phù hợp ngân sách, không bật admin user.
4. Đọc lại **loginServer** từ Azure CLI.
5. Kiểm tra quyền của danh tính thực hiện push.

### Phần B — Build và push

1. Build JAR thử nghiệm.
2. Tạo Dockerfile không chứa secret.
3. Build **orders-api:1.0.0** và chạy local.
4. Dùng **docker tag** tạo full image reference trỏ đến ACR.
5. Đăng nhập bằng **az acr login**.
6. **docker push** image lên registry.
7. Kiểm tra repository/tags trên CLI hoặc Portal.

### Phần C — Xác minh digest

1. Đọc metadata của image **apps/orders-api:1.0.0**.
2. Ghi lại digest thực tế.
3. Gắn thêm một tag mô tả release hoặc commit nếu quy trình yêu cầu.
4. Đối chiếu các tag có cùng digest hay khác digest.
5. Giải thích vì sao tag có thể đổi nhưng digest định danh một manifest cụ thể.

### Phần D — Thử triển khai

1. Chuẩn bị Container App hoặc môi trường runtime thử nghiệm đã được phép.
2. Cấp identity quyền pull phù hợp với chế độ authorization của registry.
3. Cấu hình image đầy đủ và cổng ứng dụng.
4. Triển khai, kiểm tra logs, readiness và HTTP endpoint.
5. Ghi lại image reference/digest của bản đang chạy.

### Phần E — Thử phiên bản mới và rollback

1. Sửa một thay đổi nhỏ trong ứng dụng.
2. Build image **1.0.1**, push dưới tag mới.
3. Kiểm thử và ghi digest.
4. Chuyển ứng dụng thử nghiệm sang phiên bản mới.
5. Nếu có lỗi, redeploy **1.0.0** hoặc đúng digest đã lưu.
6. Đánh giá vì sao việc ghi đè một tag cũ có thể làm rollback khó dự đoán.

### Phần F — Cleanup

1. Liệt kê tài nguyên đã tạo riêng cho bài lab.
2. Kiểm tra Container Apps hoặc workload khác có còn sử dụng image không.
3. Xóa đúng resource thử nghiệm theo quyền cho phép và quy trình.
4. Xem chi phí ACR, Container Apps và các tài nguyên liên quan.
5. Không xóa registry dùng chung hoặc image còn cần cho production/rollback.

**Tiêu chí hoàn thành:** bạn có thể đọc chính xác full image reference, chứng minh image đã được push vào ACR, xác định digest, giải thích quyền pull/push và thực hiện deploy/rollback mà không dùng admin credential chia sẻ.

## 30. Checklist trước khi dùng ACR trong production

- [ ] Registry và SKU phù hợp nhu cầu lưu trữ, hiệu năng, mạng và availability.
- [ ] Repository naming rõ ràng, có owner và convention thống nhất.
- [ ] Image tag của release không bị ghi đè tùy tiện.
- [ ] Release manifest ghi image digest, commit và build provenance.
- [ ] Image được build/test/scan theo pipeline có kiểm soát.
- [ ] Không có secret hoặc khóa riêng trong image/build context.
- [ ] CI identity chỉ có quyền push cần thiết.
- [ ] Runtime identity chỉ có quyền pull cần thiết.
- [ ] Kiểm tra chế độ RBAC/ABAC của registry trước khi cấp quyền.
- [ ] Nếu dùng private access, CI runner và runtime có DNS/network phù hợp.
- [ ] Artifact có platform phù hợp với môi trường chạy.
- [ ] Container Apps/AKS có cấu hình deployment và health độc lập với ACR.
- [ ] Có policy retention/cleanup nhưng vẫn giữ artifact rollback.
- [ ] Có audit/monitoring và cảnh báo thay đổi nhạy cảm.
- [ ] Có kế hoạch dự phòng/geo-replication khi yêu cầu HA/DR phù hợp.
- [ ] Theo dõi storage usage, build usage và chi phí tổng thể.
- [ ] Quy trình xóa/tag lock/rotate credentials được ghi nhận rõ.

## 31. Câu hỏi tự kiểm tra

1. Registry và repository khác nhau ở đâu? Repository có phải một Azure Resource Group không?
2. Trong **acrlabexample.azurecr.io/apps/orders-api:1.4.0**, đoạn nào là hostname, repository và tag?
3. Vì sao **docker tag** không đủ để image xuất hiện trong Azure Portal?
4. Sự khác nhau giữa Docker image, container đang chạy, filesystem layer và image manifest là gì?
5. Một tag **1.4.0** có thể được trỏ lại sang nội dung khác không? Cần kiểm soát bằng cách nào?
6. Vì sao digest hỗ trợ triển khai tái lập tốt hơn một tag có thể di chuyển?
7. Nếu image có nhiều kiến trúc CPU, digest của image index và manifest theo platform có thể khác nhau không?
8. Tại sao không nên dùng ACR admin user làm credential mặc định cho CI/CD?
9. **AcrPull** và **AcrPush** có vai trò gì trong registry dùng mô hình RBAC thông thường?
10. Khi dùng repository ABAC, tại sao phải kiểm tra mô hình role riêng?
11. Vì sao push image mới lên ACR không làm Azure Container App tự cập nhật?
12. Khi gặp lỗi **manifest unknown** hoặc **ImagePullBackOff**, nên kiểm tra những yếu tố nào?
13. Tại sao production nên deploy cùng digest đã kiểm thử ở staging thay vì build lại?
14. Nếu một artifact bị xóa khỏi registry, điều gì có thể xảy ra với lần scale-out/rollback tiếp theo?
15. Khi muốn hạn chế mạng bằng private endpoint, tại sao cần quan tâm CI runner, DNS và đường pull của runtime?

## 32. Tổng kết

**Azure Container Registry** là nền tảng lưu trữ và phân phối container images/artifacts trong Azure. **Registry** chứa nhiều **repository**; mỗi repository có thể có nhiều **image tags**; tag là tên dễ đọc có thể được gán lại, còn **digest** định danh nội dung manifest/index cụ thể. Khi vận hành, hãy đọc đúng cấu trúc image reference, phân biệt **build → tag → push → pull → deploy** và ghi lại digest cho từng bản phát hành.

Với ứng dụng production, quy trình đáng tin cậy là **build một lần, kiểm thử/quét image, push ACR, ghi digest, deploy đúng artifact qua các môi trường**, sử dụng managed identity và quyền pull/push tối thiểu, quản lý image retention và khả năng rollback. Kết hợp ACR với Azure Container Apps/AKS, Microsoft Entra ID, networking, Azure Monitor và Cost Management sẽ tạo nên một chuỗi triển khai container an toàn, có thể truy xuất và kiểm soát được chi phí.
