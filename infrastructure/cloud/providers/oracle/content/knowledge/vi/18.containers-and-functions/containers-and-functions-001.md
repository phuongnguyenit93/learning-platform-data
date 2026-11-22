# Container Registry và quản lý repositories trong OCIR

## 1. Mục tiêu và bối cảnh

Trong chương **Containers và Functions** của module **CLOUD_PROVIDERS_ORACLE**, Container Registry là nơi lưu bản đóng gói ứng dụng trước khi đưa vào môi trường chạy. Một quy trình triển khai OCI cần xác định được image thuộc tenancy nào, repository ở region và compartment nào, ai được phát hành, ai được tải xuống và phiên bản nào còn được giữ để phục hồi.

Sau bài này, người học có thể:

- Phân biệt registry, repository, image, tag, digest và tenancy namespace.
- Thiết kế repository phù hợp với ranh giới phân quyền của nhóm và môi trường.
- Tạo repository private, đăng nhập, push và pull image bằng Docker CLI.
- Tách quyền quản trị repository, quyền phát hành và quyền sử dụng image.
- Lập phương án quét lỗ hổng, lưu giữ, theo dõi và kiểm soát dung lượng.

Bài học tập trung vào quản lý image trong OCIR. OKE, Compute, Container Instances và OCI Functions được nhắc đến ở vai trò nơi sử dụng image; việc cấu hình các môi trường chạy đó cần quy trình triển khai riêng.

## 2. OCIR nằm ở đâu trong quy trình triển khai?

**Oracle Cloud Infrastructure Registry**, thường viết là **OCIR** hoặc gọi là **Container Registry**, là registry do Oracle quản lý. Dịch vụ hỗ trợ lưu trữ và phân phối container image qua giao thức registry và Docker CLI. OCIR cũng hỗ trợ các artifact theo chuẩn Open Container Initiative như manifest list cho nhiều kiến trúc và Helm chart. Tham khảo [tổng quan Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm).

~~~mermaid
flowchart LR
    SRC["Mã nguồn và Dockerfile"] --> BUILD["Máy phát triển hoặc CI build image"]
    BUILD -->|Push bằng danh tính phát hành| REG["OCIR: repository private"]
    REG --> SEC["Quét và xét điều kiện phát hành"]
    SEC --> RELEASE["Ghi nhận image digest được duyệt"]
    REG -->|Pull image được duyệt| RUN["Môi trường chạy ứng dụng"]
    RELEASE --> RUN
~~~

Sơ đồ thể hiện một **quy trình đề xuất**: bước xét điều kiện phát hành do tổ chức triển khai bằng CI/CD. Việc image đã nằm trong OCIR chưa thể hiện image đã được kiểm thử hoặc được chấp thuận đưa vào production.

Registry lưu artifact; tài nguyên chạy ứng dụng cung cấp CPU, bộ nhớ và kết nối tới cơ sở dữ liệu. Vì vậy, thay đổi repository hoặc quyền pull có thể ảnh hưởng trực tiếp đến lần khởi động, mở rộng hay triển khai tiếp theo của ứng dụng.

## 3. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ trong bài |
| --- | --- | --- |
| Registry | Dịch vụ tiếp nhận và phân phối image | OCIR tại một region |
| Repository | Tài nguyên tập hợp các image liên quan | `learning/orders-api` |
| Image | Bản đóng gói ứng dụng và các thành phần cần để chạy | Bản build của ứng dụng orders |
| Image tag | Tên phiên bản dùng khi tham chiếu image | `1.0.0`, `git-a1b2c3d` |
| Image digest | Định danh nội dung dạng băm | `sha256:...` |
| Tenancy namespace | Namespace của tenancy sở hữu repository | Lấy từ thông tin tenancy |
| Compartment | Phạm vi tổ chức tài nguyên và áp dụng IAM | `AppDev` |
| Repository OCID | Định danh tài nguyên repository qua OCI API | `ocid1.containerrepo...` |

Image gồm các thành phần đóng gói để tạo container. Một image có thể được dùng để khởi tạo nhiều container; vòng đời container đang chạy và vòng đời image trong registry là hai vấn đề cần quản lý riêng. Xem [khái niệm container của Docker](https://docs.docker.com/learn/content/what-is-a-container/).

### 3.1. Image tag và resource tag

`1.0.0` trong `orders-api:1.0.0` là **image tag**, dùng để chọn phiên bản image.

Các nhãn như `Owner=platform` hoặc `Environment=dev` gắn lên tài nguyên OCI là **resource tag**, dùng để mô tả và tổ chức tài nguyên. Hai loại tag phục vụ hai mục đích khác nhau. Việc chỉnh resource tag không phát hành thêm một phiên bản ứng dụng. Các thao tác cấu hình repository và resource tag được mô tả trong [Editing a Repository](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/edit-repository.htm).

### 3.2. Tag thuận tiện, digest cố định nội dung

Giả sử hôm nay `orders-api:1.0.0` trỏ tới image A. Nếu quy trình cho phép ghi đè tag, ngày mai cùng tham chiếu đó có thể trỏ tới image B. Tên phiên bản có vẻ cố định nhưng chưa đủ chứng minh nội dung không đổi.

Digest giúp tham chiếu nội dung cụ thể:

~~~text
<registry-domain>/<tenancy-namespace>/<repository>@sha256:<digest>
~~~

Quy ước đề xuất là dùng tag để con người nhận diện bản phát hành, đồng thời lưu digest vào hồ sơ triển khai. Khi cần tái triển khai hoặc rollback, lấy lại digest đã được duyệt. Docker hỗ trợ pull theo digest; xem [docker image pull](https://docs.docker.com/reference/cli/docker/image/pull/).

Digest không ngăn image bị xóa và không chứng minh image an toàn. Cần kết hợp digest với quyền truy cập, chính sách lưu giữ và kiểm tra bảo mật.

## 4. Địa chỉ image, region và compartment

Với repository thông thường không bật top-level capability, tham chiếu image có dạng:

~~~text
<registry-domain>/<tenancy-namespace>/<repository-name>:<image-tag>
~~~

Ví dụ minh họa:

~~~text
ocir.us-ashburn-1.oci.oraclecloud.com/demo_namespace/learning/orders-api:1.0.0
~~~

`demo_namespace` là chỗ giữ chỗ trong bài; khi thực hành phải thay bằng namespace thật.

| Thành phần | Cần kiểm tra |
| --- | --- |
| `ocir.us-ashburn-1.oci.oraclecloud.com` | Endpoint registry của region được chọn |
| `demo_namespace` | Namespace của tenancy sở hữu repository |
| `learning/orders-api` | Tên repository trong mô hình thực hành |
| `1.0.0` | Tag image sẽ push hoặc pull |

Tài liệu Oracle mô tả dạng endpoint `ocir.<region-identifier>.oci.oraclecloud.com`; các dạng `<region-key>.ocir.io` và `<region-identifier>.ocir.io` cũng được hỗ trợ trong OC1 realm. Cần đối chiếu endpoint phù hợp với region và realm thực tế trong [Preparing for Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryprerequisites.htm).

**Compartment không xuất hiện thành một thành phần riêng trong địa chỉ image.** Repository vẫn thuộc một compartment để áp dụng quyền. Không chèn compartment OCID vào đường dẫn Docker.

Tên repository phải duy nhất giữa các compartment trong registry của cùng tenancy và region. Vì thế, muốn tách dev và prod thành hai repository thì nên dùng hai tên khác nhau, chẳng hạn `dev/orders-api` và `prod/orders-api`. Tham khảo [Creating a Resource in Container Registry](https://docs.oracle.com/en-us/iaas/Content/Marketplace/container-registry.htm).

Namespace dùng trong địa chỉ là Object Storage namespace của tenancy, không phải tên compartment hoặc tenancy OCID. Có thể xem trong thông tin tenancy trên Console; cách sử dụng namespace cũng được giải thích trong [Pulling Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypullingimagesusingthedockercli.htm).

## 5. Thiết kế repositories

### 5.1. Chọn ranh giới theo quyền và vòng đời

Một cách thiết kế cho nhóm phát triển dịch vụ orders:

| Repository đề xuất | Mục đích | Chủ thể được push | Định hướng lưu giữ |
| --- | --- | --- | --- |
| `dev/orders-api` | Build phục vụ phát triển | CI của nhóm orders | Ngắn, loại dần build bỏ đi |
| `staging/orders-api` | Bản đang kiểm thử tích hợp | Pipeline được giao quyền | Giữ đủ để tái hiện kiểm thử |
| `prod/orders-api` | Bản phát hành đã duyệt | Pipeline phát hành | Giữ bản đang chạy và bản rollback |

Đây là lựa chọn thiết kế, không phải cấu trúc bắt buộc của OCIR. Nếu một repository chứa cả tag `dev` và `prod`, cần đánh giá việc cùng một ranh giới quyền repository bao phủ các image đó có đáp ứng yêu cầu tổ chức hay không.

Ví dụ, nhóm phát triển cần phát hành build hằng ngày, còn nhóm vận hành chỉ muốn nhận các bản đã duyệt. Tách repository giúp trình bày rõ quyền phát hành và chính sách lưu giữ của mỗi bên.

### 5.2. Dấu gạch chéo và top-level capability

OCIR hỗ trợ hai mô hình cần phân biệt:

- **Không bật top-level capability:** `team/orders` và `team/payments` là hai repository độc lập. Tiền tố `team/` chỉ là một phần tên.
- **Bật top-level capability trên repository `team`:** `team/orders:v1` và `team/payments:v1` có thể là các đường dẫn image thuộc cùng repository `team`. Các đường dẫn con không có quyền repository độc lập.

Do đó, dấu `/` trong đường dẫn không đủ để xác định ranh giới IAM. Phải kiểm tra cấu hình repository thực tế. Xem [Container Registry Concepts](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryconcepts.htm).

Bài thực hành sử dụng **standard repository, private, không bật top-level capability**, tên `learning/orders-api`.

### 5.3. Standard và pull-through cache

Standard repository nhận image do client push. Pull-through cache repository lấy và lưu đệm image được yêu cầu từ upstream OCIR được hỗ trợ ở region khác trong cùng realm; client không push image vào repository cache.

Repository type và top-level capability được chọn khi tạo và không đổi được sau đó. Cần chốt mô hình trước khi gắn pipeline. Với lab này, tạo trước repository trong compartment đích giúp tránh phụ thuộc vào cơ chế tự tạo repository ở root compartment khi push lần đầu. Xem [Creating a Repository](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrycreatingarepository.htm).

## 6. IAM: ai được xem, pull, push và quản trị?

### 6.1. Hiểu đúng resource type `repos`

Các quyền truy cập OCIR dùng resource type `repos`:

| Verb | Ý nghĩa chính trong phạm vi bài |
| --- | --- |
| `inspect` | Liệt kê thông tin tài nguyên |
| `read` | Đọc và pull image |
| `use` | Với `repos`, không bổ sung permission so với `read` |
| `manage` | Bao gồm các quyền tạo, cập nhật, xóa và quản trị |

Điểm dễ nhầm là cấp `use repos` rồi kỳ vọng có thể push. Push cần `REPOSITORY_READ` và `REPOSITORY_UPDATE`; cần dùng permission thực tế thay vì suy từ tên verb. Tham khảo [Details for Container Registry](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/registrypolicyreference.htm).

### 6.2. Ví dụ tách ba vai trò

Giả định compartment `AppDev` và các nhóm sau đã tồn tại trong identity domain `Default`. Thay tên domain, nhóm và compartment cho đúng môi trường:

~~~text
Allow group 'Default'/'RegistryAdmins' to manage repos in compartment AppDev

Allow group 'Default'/'RegistryReaders' to read repos in compartment AppDev

Allow group 'Default'/'RegistryPublishers' to manage repos in compartment AppDev where all { target.repo.name = 'learning/orders-api', any { request.permission = 'REPOSITORY_READ', request.permission = 'REPOSITORY_UPDATE' } }
~~~

Nhóm quản trị tạo repository trước. Nhóm đọc được pull trong compartment. Nhóm phát hành được đọc và cập nhật image trong repository đã chỉ định, không được cấp thêm quyền tạo, xóa hay đổi visibility qua policy này.

Đây là ví dụ thu hẹp quyền theo [Policies to Control Repository Access](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registrypolicyrepoaccess.htm). Phải xét cả các policy khác đang cấp cho người dùng: một policy hẹp không thu hồi quyền đã được cấp bởi policy rộng.

### 6.3. Authentication và authorization

`docker login` kiểm tra danh tính và credential cho registry. Push và pull còn phải đáp ứng IAM cho repository tương ứng.

Ví dụ: một tài khoản đăng nhập thành công nhưng chỉ thuộc `RegistryReaders` sẽ chưa thể push. Cách xử lý là cấp đúng quyền phát hành cho đúng repository sau khi xác nhận nhu cầu.

Auth token đại diện cho người dùng; bản thân token không phải một policy chỉ dành cho một repository. Muốn giảm phạm vi ảnh hưởng khi credential bị lộ, cần giảm quyền của danh tính sở hữu token và quản lý credential phù hợp với CI/CD.

## 7. Thực hành: tạo repository private và push image

### 7.1. Chuẩn bị

Các lệnh dưới đây là **ví dụ để người học thực thi trong Bash**, chẳng hạn WSL hoặc máy Linux có Docker. Chúng cần:

- Tenancy đã đăng ký region dự định sử dụng.
- Docker CLI và Docker daemon hoạt động.
- OCI CLI đã được cấu hình xác thực và có quyền phù hợp.
- Compartment lab và IAM đã được người quản trị chuẩn bị.
- Kết nối tới OCIR; khi build ví dụ còn cần tải base image từ Docker Hub.

Đăng nhập OCI CLI và đăng nhập Docker registry là hai cấu hình xác thực riêng.

Khai báo thông tin lab:

~~~bash
export OCI_REGION='us-ashburn-1'
export REGISTRY='ocir.us-ashburn-1.oci.oraclecloud.com'
export TENANCY_NAMESPACE='REPLACE_WITH_REAL_NAMESPACE'
export COMPARTMENT_OCID='REPLACE_WITH_REAL_COMPARTMENT_OCID'
export REPOSITORY='learning/orders-api'
export IMAGE_TAG='1.0.0'
export IMAGE_PATH="$REGISTRY/$TENANCY_NAMESPACE/$REPOSITORY"
export IMAGE_REF="$IMAGE_PATH":"$IMAGE_TAG"
~~~

Thay các giá trị `REPLACE_WITH_...` trước khi chạy. Nếu chọn region khác, phải đổi cả `OCI_REGION` và `REGISTRY` tương ứng.

### 7.2. Tạo repository trong đúng compartment

Trong Console, tìm **Container Registry**, chọn đúng region, chọn compartment lab rồi tạo repository với:

| Thuộc tính | Giá trị của lab |
| --- | --- |
| Repository type | Standard |
| Repository name | `learning/orders-api` |
| Access/visibility | Private |
| Top-level capability | Disabled |
| Compartment | Compartment lab đã chuẩn bị |

Có thể dùng OCI CLI để tạo private container repository:

~~~bash
oci artifacts container repository create \
  --region "$OCI_REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --display-name "$REPOSITORY" \
  --is-public false
~~~

**Chọn một cách tạo**, Console hoặc CLI, để tránh tạo lặp. Nếu dùng CLI, kiểm tra lại trên Console rằng type và top-level capability đúng với mô hình của bài. Cú pháp CLI được mô tả trong [container repository create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/create.html).

Liệt kê để kiểm tra tài nguyên đã nằm đúng chỗ:

~~~bash
oci artifacts container repository list \
  --region "$OCI_REGION" \
  --compartment-id "$COMPARTMENT_OCID" \
  --display-name "$REPOSITORY" \
  --all
~~~

Lưu repository OCID từ kết quả để phục vụ quản lý. `--all` lấy tất cả các trang kết quả; `--display-name` lọc theo tên chính xác. Xem [container repository list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/repository/list.html).

### 7.3. Tạo auth token và đăng nhập

Tại thông tin người dùng OCI, mở phần **Auth Tokens**, tạo token và lưu bằng hệ thống quản lý bí mật phù hợp. Khi Docker hỏi password, nhập **auth token**, không nhập mật khẩu Console.

Định dạng username:

~~~text
<tenancy-namespace>/<username>

Hoặc với cấu hình danh tính liên kết tương ứng:
<tenancy-namespace>/<domain-name>/<username>
~~~

Phải lấy domain thực tế từ cấu hình tài khoản, không tự mặc định mọi tenancy đều dùng `oracleidentitycloudservice`.

Đăng nhập tương tác:

~~~bash
export OCIR_USERNAME='REPLACE_WITH_FULL_OCIR_USERNAME'
docker login "$REGISTRY" --username "$OCIR_USERNAME"
~~~

Cách tạo token và định dạng đăng nhập được trình bày trong [Pushing Images Using the Docker CLI](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrypushingimagesusingthedockercli.htm).

Với CI đã cấp secret vào biến môi trường `OCIR_AUTH_TOKEN`, dùng stdin:

~~~bash
printf '%s' "$OCIR_AUTH_TOKEN" \
  | docker login "$REGISTRY" \
      --username "$OCIR_USERNAME" \
      --password-stdin
~~~

Không bật shell tracing khi thao tác secret. Dùng credential helper hoặc cơ chế lưu credential phù hợp cho runner. `--password-stdin` giúp tránh truyền token trực tiếp trong đối số; xem [docker login](https://docs.docker.com/reference/cli/docker/login/).

### 7.4. Build một image nhỏ

Trong thư mục lab của người học, tạo Dockerfile:

~~~dockerfile
FROM nginx:stable-alpine
RUN printf '%s\n' 'Orders API - OCIR learning image' > /usr/share/nginx/html/index.html
EXPOSE 80
~~~

Image này chỉ phục vụ kiểm tra đường đi của artifact. Nó trả nội dung tĩnh để dễ nhận diện bản đã tải về.

~~~bash
docker build -t orders-api-local:1.0.0 .
docker tag orders-api-local:1.0.0 "$IMAGE_REF"
docker image ls "$IMAGE_PATH"
docker push "$IMAGE_REF"
~~~

`docker tag` thêm tham chiếu cho image đã build; bước này chưa gửi dữ liệu lên registry. `docker push` mới chuyển artifact đến đích. Sau push, giữ lại digest trong kết quả và mở Console để kiểm tra image.

Base image `nginx:stable-alpine` được dùng cho lab để dễ bắt đầu. Quy trình phát hành cần có quyết định riêng về phiên bản base image và digest đã được duyệt nhằm tái tạo bản build.

### 7.5. Xác minh bằng pull theo digest

Lấy **manifest digest của image trên registry** từ kết quả push hoặc thông tin image. Không lấy Docker image ID cục bộ để thay thế digest này.

~~~bash
export IMAGE_DIGEST='sha256:REPLACE_WITH_REAL_MANIFEST_DIGEST'
export PINNED_IMAGE="$IMAGE_PATH@$IMAGE_DIGEST"

docker pull "$PINNED_IMAGE"
docker image inspect "$PINNED_IMAGE" --format '{{json .RepoDigests}}'
~~~

Trong Console có thể xem thông tin image, thời điểm push, người push, kích thước và các phiên bản. Dùng các dữ liệu này để đối chiếu với lần build; xem [Getting an Image's Details](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryviewingimagedetails.htm).

Để xác minh thêm nội dung của image vừa pull:

~~~bash
docker run --rm --name ocir-orders-lab \
  -p 127.0.0.1:8080:80 "$PINNED_IMAGE"
~~~

Ở terminal khác:

~~~bash
curl http://127.0.0.1:8080
~~~

Kết quả mong đợi là `Orders API - OCIR learning image`. Dừng container bằng Ctrl+C; `--rm` dọn container khi nó kết thúc.

### 7.6. Kết quả cần thu được

Lab hoàn tất khi xác nhận đủ:

1. Repository private tồn tại trong region và compartment đã chọn.
2. Danh tính phát hành push được image; danh tính chỉ đọc pull được nhưng không push được.
3. Console hiển thị image tag, digest và thông tin lần push phù hợp.
4. Pull theo digest thành công và container trả về nội dung nhận diện.
5. Hồ sơ triển khai ghi được repository, tag, digest và mã build hoặc commit liên quan.

Kiểm tra quyền bằng danh tính riêng, chẳng hạn profile máy thử hoặc runner thử riêng, để tránh dùng nhầm credential quản trị còn lưu trên máy.

## 8. Sử dụng repository private từ hạ tầng OCI

### 8.1. Kiểm tra hai đường đi độc lập

Một tài nguyên chạy ứng dụng cần đồng thời có:

- **Đường mạng:** phân giải DNS và kết nối HTTPS tới endpoint registry.
- **Đường truy cập:** credential hoặc cơ chế xác thực được hỗ trợ cùng quyền đọc image.

Kết nối mạng thành công chưa bảo đảm pull thành công. Tương tự, danh tính có quyền đọc vẫn không tải được image khi đường mạng bị chặn.

OCIR hỗ trợ truy cập từ tài nguyên trong VCN cùng region qua **Service Gateway**, giúp tài nguyên trong private subnet truy cập dịch vụ mà không cần public IP. Thiết kế còn cần route và quy tắc mạng phù hợp. Xem [Overview of Container Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm).

Trong lab, Docker build tải base image từ Docker Hub. Đường truy cập riêng tới OCIR không tự cung cấp kết nối tới registry bên ngoài đó; cần tính riêng đường mạng cho build.

### 8.2. Chuẩn bị cho OKE, Compute và Functions

Trước khi một môi trường sử dụng image, nên bàn giao:

| Thông tin | Ví dụ cần ghi nhận |
| --- | --- |
| Tham chiếu artifact | Đường dẫn image kèm digest đã duyệt |
| Quyền sử dụng | Danh tính cần quyền đọc repository nào |
| Kiến trúc | Image dành cho AMD64, ARM64 hay nhiều kiến trúc |
| Mạng | Endpoint cần truy cập và đường ra phù hợp |
| Phục hồi | Digest bản trước và thời hạn còn được giữ |

Cơ chế đưa credential tới từng runtime cần theo tài liệu của runtime đó. Không dùng kết quả `docker login` trên laptop để kết luận worker node hoặc dịch vụ Functions đã có quyền pull.

## 9. Bảo mật chuỗi cung ứng image

### 9.1. Quét lỗ hổng

Có thể thêm image scanner cho repository; OCIR tích hợp với **OCI Vulnerability Scanning**. Dịch vụ quét cần được cấp quyền đọc cần thiết. Xem [Scanning Images for Vulnerabilities](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryscanningimagesforvulnerabilities.htm).

Quy trình phát hành đề xuất:

1. CI push image vào repository phục vụ xét duyệt.
2. Chờ kết quả quét của đúng digest.
3. Áp dụng tiêu chí chấp nhận rủi ro đã thống nhất.
4. Ghi digest được duyệt vào bản ghi phát hành.
5. Theo dõi lại khi thông tin lỗ hổng thay đổi.

Ví dụ, nhóm có thể yêu cầu xử lý mọi lỗ hổng Critical có bản vá trước khi phát hành. Đây là tiêu chí tổ chức cần triển khai trong pipeline; việc bật scanner chưa tự tạo ra cổng kiểm soát triển khai.

### 9.2. Ký image

OCIR hỗ trợ tạo chữ ký cho image với khóa từ **OCI Vault**; xem [Signing Images for Security](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrysigningimages_topic.htm).

Khi thiết kế quy trình, phân công rõ người hoặc pipeline được dùng khóa ký, digest nào được ký và nơi xác minh chữ ký. Chữ ký đã tồn tại cần được bên sử dụng kiểm tra để có ý nghĩa kiểm soát.

Quét lỗ hổng giúp đánh giá nội dung đã biết là có rủi ro; chữ ký giúp kiểm tra nguồn phát hành và tính toàn vẹn theo cơ chế tin cậy đã chọn. Cần xác định rõ cả hai trước khi dùng image cho hệ thống xử lý dữ liệu quan trọng.

### 9.3. Credential và visibility

Mặc định thiết kế lab sử dụng private repository. Chỉ chuyển public khi chủ sở hữu đã xác nhận artifact được phép phân phối công khai.

Tách danh tính phát hành khỏi danh tính chỉ pull; đặt credential trong secret store của pipeline, có người sở hữu và quy trình xoay vòng. Khi nghi token bị lộ, cần thu hồi credential liên quan và xem lại các hành động trong phạm vi danh tính đó.

Không đưa credential cơ sở dữ liệu, khóa riêng hoặc token vào Dockerfile hay image layer. Ứng dụng nên nhận secret khi chạy qua cơ chế quản lý secret của nền tảng.

## 10. Quản lý vòng đời, lưu giữ và dung lượng

### 10.1. Ba thao tác dọn dẹp khác nhau

| Thao tác | Đối tượng tác động | Cần chú ý |
| --- | --- | --- |
| Xóa image cục bộ | Bản trên máy Docker | Không dọn image trong OCIR |
| Unversion image | Bỏ một version identifier trên registry | Không đồng nghĩa xóa nội dung image |
| Xóa image trong OCIR | Artifact trên registry | Có thể ảnh hưởng lần pull sau |

Oracle gọi thao tác bỏ version identifier là **unversioning**. Sau thao tác này cần xem xét image còn cần giữ bằng digest hay thuộc diện dọn dẹp; xem [Unversioning an Image](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registryuntaggingimages.htm).

### 10.2. Retention policy theo region

OCIR có global image retention policy riêng cho mỗi region; mặc định giữ toàn bộ image. Có thể áp custom policy cho repository để thay global policy. Một repository chỉ thuộc một custom policy tại một thời điểm.

Các tiêu chí gồm thời gian chưa được pull, thời gian chưa được gắn version và version identifier được miễn xóa. Policy được xử lý bất đồng bộ, có khoảng chờ sau khi tạo hoặc cập nhật. Chi tiết tại [Retaining and Deleting Images Using Retention Policies](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrymanagingimageretention.htm).

Thiết kế đề xuất:

| Nhóm image | Hướng xử lý |
| --- | --- |
| Build thử nghiệm không còn sử dụng | Chọn thời hạn ngắn sau khi đánh giá nhu cầu |
| Bản đang chạy | Đảm bảo nằm trong phạm vi được giữ |
| Bản rollback đã duyệt | Giữ theo mục tiêu phục hồi của hệ thống |
| Image chưa có tag nhưng còn được triển khai bằng digest | Kiểm tra tham chiếu trước khi dọn |

Một bản production chạy ổn định lâu ngày có thể ít được pull. Do đó, tiêu chí “không được pull gần đây” cần được đối chiếu với danh sách digest đang sử dụng.

### 10.3. Dung lượng không giảm ngay sau thao tác xóa

Oracle lưu ý việc xóa image và giải phóng dung lượng có thể mất đến 48 giờ; xem [Deleting an Image](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrydeletingimages.htm).

Về vận hành, nên theo dõi xu hướng dung lượng thay vì chờ gần hết hạn mức mới dọn. Kết hợp giảm thành phần không cần thiết trong image, kiểm soát số bản build giữ lại và tránh phát hành lại các artifact không phục vụ nhu cầu rõ ràng.

Chi phí cần đánh giá theo dung lượng, số bản được giữ và lưu lượng của kiến trúc thực tế. Khi lập ngân sách, đối chiếu bảng giá và điều kiện tenancy tại thời điểm triển khai; bài này không giả định một mức giá cố định.

## 11. Thay đổi compartment và chuẩn bị phục hồi

Có thể chuyển repository sang compartment khác. Sau khi chuyển, quyền truy cập cần phù hợp với compartment đích; xem [Moving a Repository Between Compartments](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrymovingrepos.htm).

Ví dụ, repository được chuyển từ compartment thử nghiệm sang compartment do nhóm nền tảng quản lý. Trước thay đổi, cần xác định danh tính CI vẫn được push và danh tính runtime vẫn được pull sau khi chuyển. Sau thay đổi, kiểm tra lại cả hai luồng.

**Chuyển compartment** và **chuẩn bị image ở region khác** là hai việc khác nhau. Với yêu cầu phục hồi ở region dự phòng, cần lập quy trình đưa hoặc làm sẵn artifact tại đó, chuẩn bị quyền và kiểm tra khả năng pull khi region chính không sẵn sàng.

Danh sách phục hồi nên ghi:

- Repository và endpoint tại region dự phòng.
- Digest được duyệt cùng cách xác minh artifact ở đích.
- Credential hoặc cơ chế xác thực của môi trường dự phòng.
- Chính sách giữ image và bước kiểm tra định kỳ.

Mục tiêu thực tế là chứng minh có thể khởi tạo lại ứng dụng từ artifact còn truy cập được trong điều kiện phục hồi đã đặt ra.

## 12. Theo dõi và xử lý sự cố

### 12.1. Dữ liệu nên ghi nhận

Với mỗi lần phát hành, lưu thời điểm, danh tính pipeline, commit hoặc mã build, đường dẫn repository, image tag, manifest digest và kết quả kiểm tra được dùng để duyệt.

Với repository, ghi chủ sở hữu, compartment, visibility, nhóm có quyền quản trị và chính sách lưu giữ. Đây là thông tin giúp trả lời nhanh khi cần thu hồi một bản hoặc tìm nguyên nhân mất quyền pull.

### 12.2. Chẩn đoán theo bước lỗi

| Triệu chứng | Hướng kiểm tra đầu tiên | Bằng chứng cần thu thập |
| --- | --- | --- |
| `docker login` báo unauthorized | Username đầy đủ, domain, auth token | Registry host và định dạng username, không ghi token |
| Login được nhưng push bị denied | Quyền phát hành và repository đích | Danh tính, compartment, permission đã cấp |
| Không tìm thấy repository | Region, namespace, tên chính xác | Kết quả list trong region và compartment dự kiến |
| `manifest unknown` | Tag hoặc digest có tồn tại không | Tham chiếu đầy đủ và image còn trên registry |
| DNS lỗi hoặc timeout | Đường mạng tới endpoint | Phân giải DNS, kết nối HTTPS, route và egress |
| Runtime pull lỗi nhưng laptop pull được | Credential và mạng của runtime | Cấu hình tại nơi thực sự pull image |
| Không có manifest cho kiến trúc máy | Kiến trúc image và máy chạy | Platform của image hoặc manifest list |
| Dung lượng chưa giảm sau xóa | Tiến trình xóa bất đồng bộ | Thời điểm xóa và số liệu dung lượng sau đó |

Đây là các hướng khoanh vùng, không phải kết luận từ riêng chuỗi thông báo. Quy trình nên đi từ **endpoint → mạng → danh tính → quyền → tham chiếu image**.

Khi gửi log cho người hỗ trợ, giữ lại lệnh đã che thông tin bí mật, thời điểm và lỗi đầy đủ; loại bỏ token, credential và nội dung secret.

## 13. Kết thúc lab và nguyên tắc áp dụng

Sau khi hoàn tất, dừng container thử nghiệm và đăng xuất khỏi registry nếu môi trường lab không còn cần credential:

~~~bash
docker logout "$REGISTRY"
~~~

`docker logout` không xóa image hoặc repository trên OCI. Việc dọn artifact lab cần thực hiện trong đúng repository sau khi xác nhận chúng không còn được sử dụng. Không áp policy xóa rộng ở cấp region chỉ để dọn một bài thực hành.

Khi áp dụng vào dự án, một repository nên có chủ sở hữu, ranh giới quyền và mục đích rõ ràng. Hồ sơ phát hành cần giữ digest; chính sách lưu giữ cần bảo vệ bản đang chạy và bản rollback. Khả năng triển khai ổn định phụ thuộc đồng thời vào artifact còn tồn tại, danh tính có quyền và đường mạng hoạt động.
