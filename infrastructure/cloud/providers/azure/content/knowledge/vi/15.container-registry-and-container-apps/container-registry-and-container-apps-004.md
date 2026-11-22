# ACR Tasks và tự động hóa quá trình build image

Khi triển khai ứng dụng bằng container trên Microsoft Azure, quy trình phát hành thường bắt đầu bằng việc biến mã nguồn và Dockerfile thành **container image**. Image cần được xây dựng một cách nhất quán, gắn phiên bản để truy vết, kiểm tra bảo mật và lưu trong một registry mà môi trường chạy có thể truy cập. Nếu mỗi lập trình viên tự build và push image từ máy cá nhân, chất lượng và khả năng tái hiện kết quả có thể khác nhau; việc xoay vòng credential, cập nhật base image và ghi nhận lịch sử build cũng trở nên khó quản lý.

**Azure Container Registry (ACR)** là dịch vụ registry do Azure quản lý để lưu và phân phối container images cùng các artifact tương thích. **ACR Tasks** bổ sung khả năng build image trên hạ tầng Azure, chạy quy trình nhiều bước và kích hoạt build dựa trên các sự kiện như cập nhật mã nguồn, cập nhật base image hoặc lịch định kỳ theo các tính năng được hỗ trợ.

Bài học thuộc chương **Container Registry và Container Apps** của mô-đun CLOUD_PROVIDERS_AZURE. Nội dung kết nối ACR với subscription, resource group, Microsoft Entra ID, managed identity, Azure Container Apps, Azure Monitor và kiểm soát chi phí một quy trình triển khai ứng dụng từ mã nguồn tới production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích registry, repository, tag, digest, Dockerfile và vai trò của ACR Tasks trong chuỗi cung ứng phần mềm.
2. Phân biệt **quick task** (build tức thời), **automated task** có trigger và **multi-step task** theo YAML.
3. Thực hiện ví dụ build image từ một thư mục nguồn bằng Azure CLI mà không cần tự chạy Docker daemon tại máy điều khiển.
4. Thiết kế trigger theo commit nguồn, theo thay đổi base image và theo lịch phù hợp.
5. Cấu hình thực hành ACR Task, theo dõi run, đọc log và xác minh image đã được push.
6. Quản lý identity, quyền push/pull, secret, provenance, scan và tính bất biến của artifact.
7. Kết nối pipeline build với quá trình deploy có kiểm soát sang Azure Container Apps hoặc một nền tảng chạy container khác.
8. Chẩn đoán các lỗi như không truy cập được context nguồn, Dockerfile sai, push bị từ chối, trigger không chạy hoặc image mới không được rollout.

Các ví dụ sử dụng Bash và Azure CLI. Tên registry, source repo và image chỉ mang tính minh họa; các thao tác tạo tài nguyên, build hoặc chạy task có thể phát sinh phí và cần quyền Azure phù hợp.

## 2. Những khái niệm cơ bản trước khi tự động hóa

### 2.1. Container image khác container đang chạy

**Container image** là gói dữ liệu gồm các layer, filesystem, metadata và cấu hình cần thiết để một runtime tạo container. **Container** là instance đang chạy từ image; việc push một image mới lên ACR không tự làm container cũ thay đổi.

Một luồng phát hành phổ biến:

~~~mermaid
flowchart LR
    S["Source code + Dockerfile"] --> T["ACR Task build"]
    B["Base image"] --> T
    T --> V["Kiểm thử / xác minh artifact"]
    V --> R["Azure Container Registry"]
    R --> D["CD approval / deployment"]
    D --> C["Azure Container Apps / AKS / App Service"]
    C --> M["Giám sát, rollback, cost"]
~~~

Trong thực tế, bước kiểm thử có thể chạy trước hoặc sau build tùy loại kiểm tra. Sơ đồ chỉ minh họa trách nhiệm của các thành phần, không có nghĩa mọi bước tự động được ACR cung cấp sẵn.

### 2.2. Các thuật ngữ quan trọng

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Registry | Dịch vụ lưu và phân phối image | myacr.azurecr.io |
| Repository | Nhóm image có cùng tên logic trong registry | orders-api |
| Tag | Nhãn trỏ tới một manifest/image cụ thể; có thể được gán lại | orders-api:1.4.2 |
| Digest | Giá trị nội dung giúp định danh manifest bất biến | sha256:... |
| Dockerfile | Chỉ dẫn xây dựng các layer và image | FROM, COPY, RUN, USER, ENTRYPOINT |
| Build context | Tập file đầu vào gửi cho tác vụ build | Thư mục nguồn hoặc Git repository |
| Base image | Image dùng ở lệnh FROM | eclipse-temurin:21-jre |
| Task | Định nghĩa build/automation do ACR quản lý | orders-ci |
| Task run | Một lần thực thi cụ thể, có ID, trạng thái và log | Run ID do ACR cấp |
| Trigger | Điều kiện làm task được lên lịch/chạy | Commit, base image update, cron |
| Service principal/managed identity | Danh tính workload dùng truy cập Azure hoặc dịch vụ ngoài | Identity của pipeline hoặc task |

Một image được đặt tên đầy đủ có dạng:

~~~text
<REGISTRY_NAME>.azurecr.io/orders-api:1.4.2
~~~

Trong đó registry login server, repository và tag là những phần khác nhau. Với môi trường production, nên ghi cả **digest đã triển khai** để tránh mơ hồ khi một tag bị ghi đè.

### 2.3. Vì sao tag chưa đủ để bảo đảm tái hiện?

Một tag như latest hoặc stable có thể được trỏ sang image khác. Nếu pipeline ghi đè cùng tag, hai lần deploy sử dụng cùng chuỗi tên image nhưng lấy content khác nhau.

Chiến lược nên dùng:

- Tag chứa semantic version như 1.4.2 để dễ hiểu.
- Tag chứa Git commit SHA hoặc build run ID để truy vết chính xác.
- Ghi image digest trong release record; khi cần bất biến cao, deploy bằng digest nếu nền tảng hỗ trợ.
- Giữ release artifact và metadata build theo retention policy.
- Không coi việc chỉ dùng tag latest là đủ để rollback production.

## 3. ACR Tasks giải quyết vấn đề gì?

Azure Container Registry lưu image. **ACR Tasks** cho phép thực thi công việc xây dựng trên hạ tầng build của ACR và tự động hóa việc tạo bản mới.

Ví dụ tổ chức phát hành orders-api:

1. Developer push commit lên nhánh main.
2. Hệ thống trigger một ACR Task được cấu hình kết nối tới nguồn.
3. Task lấy build context và Dockerfile, kéo base image rồi build phiên bản mới.
4. Image được tag, push vào ACR và tạo run log để truy vết.
5. Pipeline phát hành kiểm tra image, kết quả kiểm thử/bảo mật và phê duyệt.
6. Hệ thống CD cập nhật Azure Container Apps dùng image mới.
7. Azure Monitor/Log Analytics và ứng dụng xác nhận phiên bản mới hoạt động.

**ACR Tasks không tự động tương đương một hệ thống CI/CD đầy đủ.** ACR thực hiện những bước được cấu hình; quality gates, review, chữ ký, triển khai production, rollback và quản lý release có thể cần Azure DevOps, GitHub Actions hoặc công cụ khác.

### 3.1. Ba nhóm công việc phổ biến

| Loại | Cách bắt đầu | Phù hợp với |
|---|---|---|
| Quick task | Người dùng/CI gọi az acr build hoặc az acr run | Build thử, build một lần, xác minh Dockerfile |
| Automated task | Task đã tạo chạy theo trigger hoặc được gọi thủ công | Tự build khi mã nguồn đổi, base image cập nhật hoặc đến lịch |
| Multi-step task | Task YAML mô tả các bước build, push hoặc command | Quy trình có nhiều image, bước chuẩn bị, kiểm tra hoặc đóng gói liên tiếp |

Một task có thể kết hợp một hoặc nhiều cơ chế trên tùy định nghĩa và tính năng hỗ trợ. Việc chọn loại task phải dựa vào nguồn mã, cơ chế trigger, yêu cầu bảo mật và cách quản lý phát hành.

## 4. Điều kiện chuẩn bị

Để thực hành cần có:

- Azure subscription đã chọn đúng tenant/resource group.
- Quyền tạo ACR hoặc quyền làm việc với một registry có sẵn.
- Azure CLI đã cài đặt, đăng nhập được và hỗ trợ nhóm lệnh az acr.
- Dockerfile và build context hợp lệ.
- Khả năng task runner lấy được base image và dependency cần thiết.
- Quyền registry phù hợp để tạo task/build và lưu image.
- Nếu trigger từ Git: quyền quản lý Git repository và webhook/token phù hợp.
- Nếu triển khai sang Container Apps: quyền deploy, identity có quyền pull và ứng dụng/container environment được cấu hình.

Ví dụ tên:

~~~text
Resource group: rg-container-lab
Azure region: southeastasia
Registry name: acrorderslab123
Registry login server: acrorderslab123.azurecr.io
Repository: orders-api
Task name: orders-ci
~~~

ACR name phải hợp lệ và duy nhất theo phạm vi dịch vụ; hãy thay bằng tên của bạn. Chọn **registry SKU** theo tính năng, nhu cầu lưu trữ, private networking, quota và chi phí. Những giới hạn network, task runs và throughput có thể khác giữa Basic, Standard và Premium.

Kiểm tra subscription:

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Không chạy các lệnh tạo registry trong production chỉ để thử tutorial.

## 5. Thực hành 1: quick task build image trên ACR

### 5.1. Tạo resource group và registry thử nghiệm

Trong Bash:

~~~bash
az group create \
  --name rg-container-lab \
  --location southeastasia

az acr create \
  --resource-group rg-container-lab \
  --name acrorderslab123 \
  --sku Standard \
  --location southeastasia
~~~

Nếu tên đã được sử dụng, chọn tên khác. Trong thực tế có thể dùng registry có sẵn, do đó cần bỏ qua bước tạo để tránh trùng tài nguyên.

Lấy login server:

~~~bash
az acr show \
  --name acrorderslab123 \
  --query loginServer \
  --output tsv
~~~

Cần có quyền phù hợp cho thao tác tạo tài nguyên, build và push. Đăng nhập Azure CLI không đồng nghĩa mọi role đều có quyền tạo ACR Task hoặc push dữ liệu.

### 5.2. Dockerfile ví dụ cho ứng dụng Java

Giả sử ứng dụng Spring Boot có cấu trúc:

~~~text
orders-api/
  Dockerfile
  .dockerignore
  pom.xml
  src/
    main/
      java/
      resources/
~~~

Ví dụ Dockerfile multi-stage:

~~~dockerfile
# Build stage: biên dịch JAR trong quá trình build image.
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp -DskipTests package

# Runtime stage: không đưa Maven và source vào image chạy ứng dụng.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/*.jar /app/app.jar
RUN chown -R 10001:10001 /app
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đoạn ví dụ giả định Maven tạo **một JAR chạy được** ở target. Nếu build tạo nhiều file JAR (ví dụ bản gốc và bản repackaged), cần chỉ định đường dẫn chính xác để tránh copy thất bại. Cũng cần cấu hình Spring Boot lắng nghe đúng port và runtime theo môi trường Container Apps.

Nên có .dockerignore để loại bỏ thư mục .git, file tạm, artifact không cần thiết, credentials, thư mục .idea, target và những file không nằm trong build context mong muốn. Tuy nhiên nếu Dockerfile lấy artifact đã build sẵn từ target thì .dockerignore phải phù hợp với cách build đó; ví dụ ở đây build JAR ngay trong container nên không cần gửi target.

Không dùng COPY toàn bộ thư mục có thể chứa secret hoặc .env từ máy phát triển vào image.

### 5.3. Build từ thư mục local mà không cần Docker daemon cục bộ

Di chuyển đến thư mục dự án chứa Dockerfile. Chạy:

~~~bash
az acr build \
  --registry acrorderslab123 \
  --image orders-api:1.0.0 \
  --file Dockerfile \
  .
~~~

Trong đó:

- --registry chỉ ACR đích.
- --image gán tên repository và tag cho image sau build.
- --file chọn Dockerfile.
- Dấu chấm cuối là build context thư mục hiện tại.

ACR nhận context rồi thực hiện build phía dịch vụ. **Người dùng không cần một Docker daemon local đang chạy chỉ để gọi az acr build**, nhưng vẫn cần Azure CLI, kết nối mạng và quyền upload context/build. Build thật vẫn có thể thất bại do Dockerfile, dependency, network hoặc quota.

Sau khi build thành công, image dự kiến có tên:

~~~text
acrorderslab123.azurecr.io/orders-api:1.0.0
~~~

### 5.4. Kiểm tra image trong registry

~~~bash
az acr repository list \
  --name acrorderslab123 \
  --output table

az acr repository show-tags \
  --name acrorderslab123 \
  --repository orders-api \
  --output table
~~~

Để kiểm tra phiên bản sâu hơn, xem metadata của image/manifest và digest theo khả năng CLI hoặc API hiện hành. Ghi digest từ kết quả xác minh vào release record. Việc thấy tag tồn tại chứng minh có artifact được push, không tự chứng minh nó an toàn hoặc chạy được.

### 5.5. Test container image trước khi phát hành

Một build thành công có thể vẫn chứa lỗi runtime như sai port, thiếu tài nguyên, Java startup error hoặc health endpoint chưa sẵn sàng. Nên:

1. Kiểm tra dependency và build output.
2. Chạy unit/integration tests trong pipeline.
3. Kiểm tra image metadata, kích thước và thành phần phần mềm.
4. Chạy image trong môi trường test có network/secret phù hợp.
5. Xác nhận HTTP readiness/health và cấu hình runtime.
6. Ghi build/run ID, commit SHA, digest và kết quả gate.

Không coi thông báo BUILD SUCCEEDED là tiêu chí chấp nhận duy nhất.

## 6. Tạo ACR Task để chạy lại theo yêu cầu

Quick task phù hợp cho một lần build. Để gọi lại cùng định nghĩa hoặc cài trigger, tạo **named task**.

### 6.1. Nguồn build context

Task có thể sử dụng nhiều dạng context được hỗ trợ, chẳng hạn Git repository hoặc một nguồn được ACR Tasks nhận diện. Cách khai báo URL/ref, private repository credential và file path phải khớp yêu cầu CLI hiện hành.

Ví dụ ý tưởng với Git:

~~~text
Git repo: https://github.com/EXAMPLE_ORG/orders-api
Branch: main
Dockerfile: Dockerfile
Output: orders-api:<run-id>
Task: orders-ci
~~~

Thay EXAMPLE_ORG và repository bằng nguồn mà bạn có quyền quản lý. Khi dùng trigger tự động từ Git, ACR cần quyền liên quan webhook/credential theo nhà cung cấp Git và loại repository; không tự giả định repository public luôn cấu hình trigger được mà không có bước cấp quyền.

### 6.2. Tạo task theo commit Git

Ví dụ Bash với token lấy từ hệ thống quản lý bí mật đã được phê duyệt:

~~~bash
az acr task create \
  --registry acrorderslab123 \
  --name orders-ci \
  --image 'orders-api:{{.Run.ID}}' \
  --context 'https://github.com/EXAMPLE_ORG/orders-api.git#main' \
  --file Dockerfile \
  --git-access-token "$GIT_ACCESS_TOKEN" \
  --commit-trigger-enabled true
~~~

Lưu ý:

- {{.Run.ID}} là một biến của ACR Tasks dùng để đặt tag theo **run**; nó được công cụ task đánh giá, không phải biến Bash.
- Dấu nháy đơn giữ nguyên cú pháp template khi gửi CLI.
- GIT_ACCESS_TOKEN phải được cung cấp từ secret store/pipeline bảo mật, có scope tối thiểu và thời hạn/rotation.
- Không in token bằng echo, không commit token vào source code, không copy giá trị thật vào tài liệu.
- Truyền secret qua tham số CLI có nguy cơ hiện trong process list hoặc log tùy môi trường; trong production nên ưu tiên cơ chế lưu credential được công cụ/pipeline hỗ trợ và tránh shell tracing.

Những tham số Git trigger, loại token và quyền webhook có thể khác theo GitHub/Azure Repos và cập nhật CLI. Trước khi triển khai chính thức, kiểm tra:

~~~bash
az acr task create --help
~~~

Nếu tổ chức hạn chế PAT hoặc webhook từ ACR, có thể để GitHub Actions/Azure DevOps **gọi ACR Task thủ công** bằng danh tính liên kết OIDC, thay vì thiết lập commit trigger trực tiếp qua một token dài hạn.

### 6.3. Chạy và kiểm tra task

~~~bash
az acr task run \
  --registry acrorderslab123 \
  --name orders-ci

az acr task show \
  --registry acrorderslab123 \
  --name orders-ci \
  --output json
~~~

Theo dõi các run:

~~~bash
az acr task list-runs \
  --registry acrorderslab123 \
  --output table
~~~

Xem log của một lần chạy cụ thể:

~~~bash
az acr task logs \
  --registry acrorderslab123 \
  --run-id "<RUN_ID>"
~~~

Lấy RUN_ID từ kết quả task run hoặc list-runs. Log có thể chứa đường dẫn, thông tin build context và output dependency; cần kiểm soát quyền đọc log và tránh in secret ở bước build.

Khi chạy thủ công thành công, cũng cần kiểm tra image tag thực sự đã được tạo và push. Cấu hình task chạy không tự bảo đảm context build hiện tại trùng với commit bạn kỳ vọng.

### 6.4. Tách tạo task và chạy task

- **Task definition:** chứa thông tin nguồn, image output, trigger, tùy chọn chạy và định nghĩa các bước.
- **Task run:** một lần thực thi, có thời gian bắt đầu/kết thúc, trạng thái và log.
- **Image artifact:** sản phẩm của lần build, có tag và digest.
- **Deployment:** quyết định đưa image đã xác minh vào môi trường chạy; đây là bước khác.

Những đối tượng này nên có liên kết ID rõ ràng để kiểm toán chuỗi từ commit → build → image → deploy.

## 7. Các cơ chế trigger tự động

### 7.1. Commit trigger

Khi source repository có commit mới ở nhánh/ref được cấu hình, webhook/tích hợp trigger có thể làm ACR Task chạy. Điều kiện thành công gồm:

1. Repository/branch đúng.
2. Credential hoặc tích hợp webhook còn hiệu lực.
3. Task không bị vô hiệu hóa.
4. Build context và Dockerfile hợp lệ tại commit vừa cập nhật.
5. Registry/task runner có quyền đọc nguồn, kéo base image và push output.
6. Có quota, network access và khả năng kết nối dependency.

Không nên để mọi push trên mọi nhánh tự tạo image có quyền triển khai production. Với code quan trọng, dùng protected branch, review, kiểm thử và gate phê duyệt trước phát hành.

### 7.2. Base image update trigger

Ứng dụng có thể dùng base image chứa hệ điều hành/runtime, ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jre
~~~

Khi publisher cập nhật base image để sửa lỗ hổng, image ứng dụng **không tự thay đổi** chỉ vì tag base được cập nhật. Muốn nhận bản sửa, cần build lại ứng dụng và push artifact mới.

ACR Tasks có khả năng **base image update trigger** trong những kịch bản registry/base image được hỗ trợ. Tác vụ có thể được thực thi lại khi hệ thống phát hiện thay đổi base image phù hợp.

Cần kiểm tra:

- Base image được lấy từ registry và kiểu image mà ACR Tasks có thể theo dõi.
- Task được cấu hình bật trigger liên quan.
- Nền tảng đã xác định dependency giữa Dockerfile và base image như dự kiến.
- Nếu Dockerfile dùng nhiều stage, thay đổi của stage nào phải làm build lại?
- Task đã ghi image output mới, nhưng deployment có được phê duyệt hay chưa?

**Không mặc định ACR theo dõi tức thời mọi image công cộng hoặc mọi kiểu FROM động.** Cơ chế phát hiện và khoảng thời gian phản ứng khác nhau theo registry, nguồn và tính năng. Cần xác minh trên hệ thống thật và có fallback build định kỳ.

### 7.3. Scheduled trigger

Một số image nên được rebuild theo lịch để kéo các thành phần đã cập nhật và nhận diện lỗi bảo mật hoặc dependency drift, ngay cả khi source không đổi.

Ví dụ tạo task theo lịch cron minh họa:

~~~bash
az acr task create \
  --registry acrorderslab123 \
  --name orders-nightly \
  --image 'orders-api:nightly-{{.Run.ID}}' \
  --context 'https://github.com/EXAMPLE_ORG/orders-api.git#main' \
  --file Dockerfile \
  --schedule '0 2 * * *' \
  --git-access-token "$GIT_ACCESS_TOKEN" \
  --commit-trigger-enabled false
~~~

Biểu thức cron ở đây biểu thị thời điểm do scheduler hiểu theo quy tắc hiện hành của ACR Tasks; kiểm tra múi giờ và khả năng cron của dịch vụ trước khi triển khai. Không suy luận lịch chạy từ múi giờ máy phát triển. Khi theo dõi định kỳ, ghi thời gian chạy thực tế và kiểm tra run bị bỏ qua hoặc thất bại.

Một build hằng đêm tạo ra image mới chưa chắc nên triển khai production ngay. Thường cần vulnerability policy, integration tests, review hoặc phê duyệt ở bước CD.

### 7.4. Khi nào chọn trigger nào?

| Trigger | Trường hợp phù hợp | Cạm bẫy |
|---|---|---|
| Commit | Muốn có image mới khi code thay đổi | Build từ nhánh chưa kiểm duyệt, webhook/token hết hạn |
| Base image | Muốn cập nhật image khi nền tảng/runtime được vá | Không phải base source nào cũng theo dõi được; dễ tạo image chưa qua test |
| Schedule | Muốn rebuild có chu kỳ, kiểm tra dependency drift | Chi phí run và image cũ tích lũy |
| Manual/API/pipeline | Muốn gate rõ ràng trong CI/CD | Phụ thuộc pipeline bên ngoài và quyền thực thi task |

Có thể dùng nhiều trigger cho cùng hệ thống nhưng cần có cơ chế kiểm soát **độ trùng lặp**, tránh chạy quá nhiều build đồng thời và tránh tag bị ghi đè ngoài ý muốn.

## 8. Multi-step ACR Task với YAML

Với quy trình đơn giản, Dockerfile và một output image đã đủ. Khi cần build nhiều image, chạy công cụ chuẩn bị hoặc push theo chuỗi, **multi-step task** cho phép định nghĩa các bước trong YAML.

### 8.1. Cấu trúc ví dụ

Giả sử source chứa Dockerfile. Tạo file acr-task.yaml:

~~~yaml
version: v1.1.0
steps:
  - build: -t {{.Run.Registry}}/orders-api:{{.Run.ID}} .
  - push:
      - "{{.Run.Registry}}/orders-api:{{.Run.ID}}"
~~~

Ý nghĩa:

- version: phiên bản cú pháp ACR Task YAML trong ví dụ.
- steps: danh sách bước chạy theo trình tự.
- build: build image có tag chứa run ID.
- push: đẩy image sang registry phù hợp.
- {{.Run.Registry}} và {{.Run.ID}}: các biến runtime được ACR Tasks thay thế trong ngữ cảnh hỗ trợ.

Các bản ACR Tasks có thể thêm cấu trúc steps, command, dependencies, conditional execution và task properties khác. Khi mở rộng, cần bám schema tài liệu chính thức chứ không giả định mọi lệnh shell đều có thể viết trực tiếp dưới build hoặc push.

### 8.2. Chạy multi-step task tức thời

Từ thư mục chứa Dockerfile và acr-task.yaml:

~~~bash
az acr run \
  --registry acrorderslab123 \
  --file acr-task.yaml \
  .
~~~

Lệnh yêu cầu ACR chạy định nghĩa YAML với build context thư mục hiện tại. Đây là một kiểu quick run theo tác vụ YAML; không tự tạo task có trigger lâu dài.

### 8.3. Mở rộng với quality gates

Một multi-step workflow có thể được thiết kế theo logic:

~~~mermaid
flowchart TD
    A["Lấy source và Dockerfile"] --> B["Build image"]
    B --> C["Kiểm tra Dockerfile / image / dependency"]
    C --> D{"Kết quả gate đạt?"}
    D -->|Không| E["Fail task, lưu log"]
    D -->|Có| F["Push image / ghi digest"]
    F --> G["Xuất metadata cho pipeline CD"]
    G --> H["Phê duyệt và deploy riêng"]
~~~

**Không tự khẳng định** các chức năng như vulnerability scanning, SBOM generation, image signing hoặc test framework là những bước tự động có sẵn chỉ vì bạn dùng ACR Tasks. Các khả năng đó thường cần công cụ/step/integration cụ thể, identity và policy tương ứng.

Ví dụ, một bước scan có thể dùng công cụ bên ngoài được hỗ trợ để phân tích package và lỗ hổng của image; khi kết quả vượt ngưỡng, task hoặc release pipeline phải từ chối đưa image vào production. Tổ chức cần định nghĩa ngưỡng, dữ liệu lỗ hổng và cơ chế ngoại lệ có phê duyệt.

### 8.4. Build một lần, triển khai nhiều môi trường

Một nguyên tắc quan trọng:

~~~text
Source commit C
    ↓
ACR build / quality gates
    ↓
Image digest D
    ├── Dev
    ├── Staging
    └── Production (sau approval)
~~~

Tái sử dụng **cùng image digest** ở các môi trường giúp giảm nguy cơ build lại tạo artifact khác, đồng thời làm release và rollback dễ truy vết hơn. Các cấu hình môi trường như DB URL, Key Vault reference, replica count và network nên được đưa vào runtime configuration, không đóng gói secret production trong Dockerfile.

## 9. Bảo mật ACR Tasks và quản lý danh tính

### 9.1. Quyền quản lý task khác quyền truy cập dữ liệu

Cần phân biệt ít nhất ba loại quyền:

| Nhu cầu | Đối tượng | Ví dụ kiểm soát |
|---|---|---|
| Tạo/sửa ACR và task | Admin hoặc automation quản trị Azure | Azure RBAC ở scope registry/resource group, quyền quản lý task |
| Push image vào registry | Build workload hoặc task runner | Quyền ghi repository tương ứng theo mô hình RBAC/ABAC của registry |
| Pull image khi chạy ứng dụng | Azure Container Apps/AKS/App Service | Quyền pull repository thích hợp, thường qua managed identity |

Không nên cấp quyền quản trị registry cho runtime ứng dụng nếu nó chỉ cần pull image. Registry có thể có chế độ permission kiểu registry-level RBAC hoặc repository-scoped ABAC; quyền và tên role cụ thể cần kiểm tra theo cấu hình ACR hiện hành.

### 9.2. Azure RBAC, managed identity và Entra ID

Khi có thể, dùng:

- Danh tính Microsoft Entra cho người quản trị với MFA/PIM theo chính sách.
- Managed identity cho Azure Container Apps khi pull image từ ACR theo kịch bản được hỗ trợ.
- Federated workload identity/OIDC cho GitHub Actions hoặc Azure DevOps khi gọi Azure CLI/ACR API.
- Identity của ACR Task để truy cập tài nguyên Azure như Key Vault theo khả năng Task hỗ trợ, thay cho credential hard-code.

Việc một task có managed identity **không tự cấp** quyền đọc mọi secret hoặc quyền push/pull ở mọi repository. Phải tạo role assignment đúng resource/scope và kiểm tra thực tế bằng build.

### 9.3. Quản lý credential của nguồn Git

ACR task lấy context từ repository private có thể cần quyền đọc source và tạo webhook. Các nguyên tắc:

1. Cấp token có scope tối thiểu và expiration phù hợp.
2. Tách credential của source repository khỏi credential dùng deploy production.
3. Không commit PAT vào Dockerfile, YAML, Makefile hoặc shell script.
4. Kiểm soát ai được xem/chỉnh task definition, logs và credential.
5. Xoay/thu hồi token theo quy trình; kiểm tra trigger sau rotation.
6. Ưu tiên OAuth/OIDC hoặc tích hợp không dùng secret dài hạn khi được hỗ trợ.

### 9.4. Không đưa secret vào image

Những cách nguy hiểm:

- COPY .env chứa credential vào build context.
- Dùng ARG hoặc ENV để chứa secret rồi nghĩ rằng sau build nó sẽ tự biến mất.
- Dùng RUN echo secret để tạo file tạm trong layer.
- In kết quả kết nối hoặc token trong build log.
- Push image lên repository không hạn chế quyền mà bên trong có cấu hình production.

Nếu build cần credential để lấy dependency private, sử dụng cơ chế secret của hệ thống build/task hoặc dịch vụ cung cấp dependency được hỗ trợ, theo quy trình tránh leak vào layer và log. Thử quét image/layers/config sau build để xác nhận không chứa dữ liệu không được phép.

### 9.5. Network isolation của registry và build

ACR có thể cấu hình firewall, private endpoint và mạng riêng tùy SKU. Tuy nhiên, việc chặn public network access hoặc đặt registry chỉ có private endpoint có thể ảnh hưởng khả năng ACR Tasks đọc/ghi registry hoặc lấy source/base image qua hạ tầng thực thi mặc định.

Trước khi chọn kiến trúc mạng riêng:

- Kiểm tra cách task runner truy cập registry, source Git, package feeds và base image.
- Xác minh tính năng dedicated agent pool hoặc phương án network được ACR Tasks hỗ trợ trong SKU/region hiện hành nếu cần.
- Đảm bảo DNS, private endpoint và routing phù hợp.
- Tránh mở registry ra Internet vĩnh viễn chỉ để sửa lỗi build.
- Phân biệt quyền lỗi 401/403 với lỗi DNS, timeout hoặc kết nối bị firewall từ chối.

## 10. Chất lượng và tính toàn vẹn của container image

### 10.1. Chọn base image đáng tin

Base image nên đến từ publisher đáng tin cậy, có chính sách cập nhật, version rõ ràng và kiến trúc CPU phù hợp. Với ứng dụng Java, cần thống nhất JDK cho build và JRE cho runtime (hoặc distro được hỗ trợ).

Ví dụ:

~~~dockerfile
FROM eclipse-temurin:21-jre
~~~

Tag có thể thay đổi khi publisher cập nhật. Để **reproducibility** ở mức cao, có thể pin digest ở Dockerfile theo yêu cầu chuỗi cung ứng. Nhưng pin digest có nghĩa cập nhật bảo mật của base image phải được chủ động quản lý: một task theo dõi tag mới có thể không đủ nếu Dockerfile vẫn khóa digest cũ.

Cần cân bằng giữa hai mục tiêu:

- **Reproducibility:** cùng nguồn, cùng dependency và base digest để build có thể tái hiện.
- **Freshness:** thường xuyên nhận runtime/OS patches và giảm lỗ hổng.

Quy trình có thể dùng bot cập nhật digest, review PR, rebuild, scan và phát hành; không chỉ dựa vào tag latest.

### 10.2. SBOM, scanning, signing và provenance

Một release quan trọng có thể cần:

1. **SBOM:** danh sách thành phần và dependency có trong image.
2. **Vulnerability scan:** tìm lỗ hổng của OS và package theo nguồn dữ liệu được tổ chức phê duyệt.
3. **Image signing:** chữ ký giúp xác minh ai phát hành image/manifest.
4. **Provenance:** bằng chứng build từ source commit, pipeline và builder nào.
5. **Policy enforcement:** môi trường production chỉ nhận image đã đáp ứng điều kiện.

ACR Tasks giúp thực thi các bước đã được định nghĩa nhưng **không thay thế toàn bộ công cụ chuỗi cung ứng**. Có thể kết hợp khả năng của ACR, Microsoft Defender for Cloud và công cụ CI/CD phù hợp. Tính năng scan và coverage phụ thuộc license, cấu hình, loại artifact và khả năng của công cụ.

### 10.3. Multi-architecture images

Image cho linux/amd64 và linux/arm64 không mặc nhiên tương đương. Nếu môi trường chạy yêu cầu nhiều kiến trúc, phải dùng chiến lược build/push manifest list hoặc image index được công cụ và ACR Tasks hỗ trợ. Không suy ra một quick task duy nhất tạo multi-platform image nếu Dockerfile/runner chưa được cấu hình phù hợp.

Kiểm tra kiến trúc image tại từng runtime để tránh lỗi exec format error khi deploy.

## 11. Từ image trong ACR tới Azure Container Apps

ACR Tasks và Azure Container Apps có nhiệm vụ khác nhau:

- **ACR Tasks:** build, tag, push, ghi log và tự động hóa image.
- **Azure Container Apps:** chạy container, cấu hình ingress, scaling, revision, secrets, managed identity và môi trường ứng dụng.

**Push một image mới không tự động đồng nghĩa Container Apps sẽ rollout bản mới.** Cần một deployment action hoặc tính năng continuous deployment được cấu hình chính xác theo mô hình đang dùng.

### 11.1. Mẫu kiến trúc CI/CD

~~~mermaid
flowchart LR
    G["Git repository"] --> A["ACR Task"]
    A --> R["ACR: image + digest"]
    R --> Q["Test, scan và release approval"]
    Q --> D["CD: cập nhật Azure Container App"]
    D --> V["Container App revision"]
    V --> O["Health / log / rollback"]
~~~

Trong production nên phân tách quyền:

- Build identity có quyền cần thiết để chạy task và push image.
- Deploy identity có quyền cập nhật Container App theo scope.
- Runtime identity chỉ cần pull image và truy cập dịch vụ đích được cho phép.
- Người phê duyệt có quyền quyết định phát hành, không nhất thiết nắm credential lâu dài.

### 11.2. Cấu hình runtime pull image

Container App cần quyền pull từ registry. Kịch bản phổ biến dùng **managed identity** được cấp quyền pull phù hợp cho ACR. Quyền cụ thể phụ thuộc mô hình registry (RBAC/ABAC) và phiên bản tính năng.

Ví dụ mô hình cấu hình (không phải một manifest hoàn chỉnh):

~~~text
Container App: orders-api-prod
Registry: acrorderslab123.azurecr.io
Image: acrorderslab123.azurecr.io/orders-api:1.0.0
Identity: user-assigned hoặc system-assigned managed identity
Registry permission: pull đúng phạm vi
Ingress: HTTPS theo chính sách
Secrets: Key Vault / Container Apps secret management
Environment variables: theo từng môi trường
~~~

Không sử dụng admin username/password của registry như giải pháp mặc định cho production khi managed identity phù hợp.

### 11.3. Ví dụ cập nhật Container App có kiểm soát

Sau khi image được kiểm tra và phê duyệt:

~~~bash
az containerapp update \
  --resource-group rg-apps-prod \
  --name orders-api-prod \
  --image acrorderslab123.azurecr.io/orders-api:1.0.0
~~~

Lệnh đòi hỏi Container App đã tồn tại, đã cấu hình registry authentication và quyền pull. Cách Container Apps tạo revision/rollout tùy revision mode và thiết lập của ứng dụng. Sau deploy, xác nhận revision active, endpoint health, logs, error rate và traffic split nếu dùng multiple revisions.

Không lấy việc update CLI trả về thành công làm bằng chứng đủ rằng mọi request đang phục vụ phiên bản mới.

### 11.4. Rollback

Một kế hoạch rollback an toàn cần giữ:

- Image digest của bản production trước.
- Các tham số runtime và secret reference của bản đó.
- Cấu hình revision/traffic routing tương ứng.
- Migrations database có tính tương thích ngược.
- Log, approval và tiêu chí kích hoạt rollback.

Rollback có thể thông qua revision management của Container Apps hoặc cập nhật image đã lưu; chọn cách được nền tảng hỗ trợ và phù hợp mô hình revision đang dùng. Một tag cũ bị ghi đè sẽ làm rollback khó tái hiện, do đó nên lưu digest.

## 12. Lên lịch và lifecycle management cho image

ACR là nơi lưu artifact tích lũy qua nhiều lần build. Nếu tạo image mỗi commit và mỗi đêm, registry có thể tăng dung lượng nhanh.

Nên thiết kế:

- Giữ image production/staging đã được phê duyệt theo retention policy.
- Gắn tag theo run/commit và lưu digest trong release records.
- Dọn dẹp tag hoặc manifest không còn được tham chiếu theo quy trình được kiểm soát.
- Tránh xóa artifact đang được một môi trường dùng hoặc cần cho rollback.
- Theo dõi dung lượng lưu, task runs, băng thông pull và chi phí.
- Kiểm tra các tính năng retention/purge được ACR hỗ trợ ở tier hiện tại.

**Xóa tag không luôn tương đương xóa dữ liệu manifest hoặc thu hồi image khỏi runtime đang chạy.** Cách garbage collection, retention và purging phụ thuộc dịch vụ. Trước khi làm sạch registry, đối chiếu danh sách artifact đang deploy và nhu cầu điều tra bảo mật.

Trong nhiều tổ chức, chỉ các repository production-critical được giữ artifact lâu; artifact thử nghiệm có vòng đời ngắn hơn. Việc này cần thể hiện qua policy, owner và audit.

## 13. Logging, giám sát và kiểm toán build

### 13.1. Những dữ liệu cần ghi

Mỗi task run nên gắn được với:

| Trường | Ý nghĩa |
|---|---|
| Source repository/branch/commit | Mã nào được build |
| ACR task name và run ID | Tác vụ và lần thực thi nào |
| Start/end time (UTC) | Thời gian thực hiện |
| Trigger reason | Commit, base update, schedule hay manual |
| Build context/Dockerfile | Input nào được dùng |
| Base image digest | Nền tảng build từ bản nào |
| Output image tag/digest | Artifact nào được tạo |
| Test/scan/signing results | Những điều kiện kiểm tra nào đạt |
| Builder/identity | Ai thực thi với quyền nào |
| Deployment/revision ID | Artifact đã tới môi trường nào |

Không phải mọi trường đều có sẵn tự động trong ACR Tasks log. Pipeline có thể cần thu thập và gắn metadata bổ sung trong build artifact store hoặc hệ thống quản lý release.

### 13.2. Lệnh theo dõi thông dụng

~~~bash
# Danh sách định nghĩa task
az acr task list \
  --registry acrorderslab123 \
  --output table

# Các lần chạy
az acr task list-runs \
  --registry acrorderslab123 \
  --output table

# Thông tin một task
az acr task show \
  --registry acrorderslab123 \
  --name orders-ci \
  --output json

# Log theo run ID
az acr task logs \
  --registry acrorderslab123 \
  --run-id "<RUN_ID>"
~~~

Để quan sát thay đổi registry và hoạt động Azure management plane, có thể dùng Azure Activity Log cùng các metrics/diagnostics được ACR hỗ trợ. Dữ liệu ở management plane không tự thay thế toàn bộ dữ liệu build output hoặc image provenance.

### 13.3. Alerts nên có

- Build/task thất bại liên tiếp.
- Không có run mới dù source đã có commit/trigger kỳ vọng.
- Scheduled task không chạy trong cửa sổ đã định.
- Thời gian build kéo dài bất thường.
- Base image update chưa được xử lý theo SLA bảo mật.
- Dung lượng registry hoặc chi phí tăng đột biến.
- Access failures hoặc thay đổi quyền quản trị registry.
- Production image digest khác artifact đã được phê duyệt.

Cần phân biệt lỗi build với lỗi deploy. Một image mới được tạo đúng nhưng Container App không khởi động do cổng, memory limit, secret hoặc configuration sẽ cần kiểm tra ở runtime, không chỉ ở ACR.

## 14. Chi phí và hiệu năng build

ACR Tasks có thể phát sinh chi phí theo mô hình registry/task run/tính năng hiện hành. Ngoài ra:

- Registry SKU ảnh hưởng khả năng lưu trữ, throughput, tính năng networking và quota.
- Nhiều commit/schedule dẫn tới nhiều lượt build và nhiều tag/manifest.
- Kéo base image lớn hoặc dependency nhiều làm tăng thời gian build.
- Image lớn làm runtime pull lâu hơn và tăng chi phí truyền tải theo đường mạng.
- Log ingestion, scanner, Key Vault, agent pool hoặc tài nguyên phụ có thể phát sinh phí.
- Giữ nhiều image cũ cần dung lượng registry.

### 14.1. Tối ưu Dockerfile trước khi nâng SKU

Một số biện pháp:

1. Dùng multi-stage build để loại bỏ compiler và công cụ build khỏi runtime image.
2. Sắp xếp COPY/RUN để tận dụng layer cache khi cơ chế builder hỗ trợ.
3. Loại bỏ artifact và dependency không dùng.
4. Dùng .dockerignore để giảm context upload.
5. Pin phiên bản dependency, kiểm tra checksum khi phù hợp.
6. Chỉ dùng runtime base image cần thiết, không làm tăng rủi ro vì image tối giản thiếu cập nhật bảo mật.
7. Tránh thực thi network download không ổn định trong Dockerfile nếu có giải pháp dependency cache có kiểm soát.
8. Theo dõi build duration và image size qua các release.

Không tự giả định mọi builder hoặc ACR Task run luôn giữ layer cache giữa các lần thực thi. Khả năng cache phụ thuộc chế độ build/task và hạ tầng; đánh giá bằng số đo thực tế.

### 14.2. Lựa chọn lịch build

Nếu push 50 commit/ngày và mỗi commit tạo một image production-ready, chi phí và số artifact có thể cao hơn nhu cầu thực tế. Có thể:

- Chỉ build trên protected branch hoặc sau PR merge.
- Chạy test nhanh ở PR, build image release tại điểm hợp nhất.
- Sử dụng scheduled rebuild theo nhu cầu an ninh thay vì quá thường xuyên.
- Kích hoạt base-image rebuild theo quy trình scan và policy.
- Dùng tag/digest để phát hành một artifact qua dev/staging/prod, không build lại từng môi trường.

Các lựa chọn này cần cân bằng tốc độ phản hồi và độ tin cậy bảo mật, không chỉ tối ưu phí.

## 15. Tình huống thực tế: Spring Boot lên Azure Container Apps

Một nhóm phát triển ứng dụng đơn hàng Spring Boot muốn triển khai tự động sau mỗi PR được merge vào main. Mục tiêu là chuẩn hóa build và bảo đảm image có thể rollback.

### 15.1. Quy trình đề xuất

1. Developer tạo PR, CI chạy unit tests, static checks và review.
2. PR được merge vào main theo branch protection.
3. ACR Task được trigger từ commit hoặc pipeline gọi task thủ công bằng danh tính phù hợp.
4. Task build multi-stage Dockerfile và tạo tag theo commit SHA/run ID.
5. Image được đẩy vào registry, hệ thống ghi digest, source commit và task run.
6. Security scan/SBOM và integration test được thực thi theo công cụ đã chọn.
7. Nếu gate đạt, pipeline cập nhật Container App staging đến chính digest được phê duyệt.
8. Nhóm QA xác minh health, authentication, DB, messaging và logs.
9. Approval production cho phép deploy artifact tương tự sang production.
10. Azure Container Apps tạo/điều chỉnh revision theo cấu hình; nhóm quan sát số liệu.
11. Nếu lỗi, rollback revision/image và kiểm tra ảnh hưởng database hoặc tác vụ nền.

### 15.2. Sơ đồ release record

~~~yaml
application: orders-api
source:
  repository: "https://github.com/EXAMPLE_ORG/orders-api"
  branch: main
  commit: "<COMMIT_SHA>"
build:
  registry: acrorderslab123.azurecr.io
  task: orders-ci
  runId: "<ACR_RUN_ID>"
  dockerfile: Dockerfile
  image: "acrorderslab123.azurecr.io/orders-api:<VERSION_OR_RUN_ID>"
  digest: "sha256:<IMAGE_DIGEST>"
qualityGates:
  unitTests: passed
  vulnerabilityPolicy: passed
  sbom: recorded
release:
  environment: production
  approvedBy: "<APPROVER>"
  containerApp: orders-api-prod
  revision: "<REVISION_NAME>"
  deployedAtUtc: "<ISO_UTC_TIME>"
rollback:
  previousDigest: "sha256:<PREVIOUS_DIGEST>"
  procedure: "Use approved Container Apps revision/image rollback"
~~~

YAML này là **mẫu ghi nhận metadata**, không phải schema dành để chạy trực tiếp trong ACR Tasks hay Azure DevOps. Giá trị passed chỉ có ý nghĩa khi có log hoặc artifact kiểm thử tương ứng.

### 15.3. Một số failure scenario

**Build đạt nhưng deploy lỗi:** kiểm tra revision logs, registry pull permissions, port ingress và secret. Không rebuild vội nếu image digest đã được xác minh.

**Image bị phát hiện lỗ hổng:** xác định base image và dependency, cập nhật phiên bản/digest, build lại, scan và phát hành bản mới. Không chỉ đổi tag để che lỗ hổng.

**Commit trigger không chạy:** kiểm tra webhook, branch, token, task disabled và lịch sử runs. Trong lúc khắc phục có thể chạy task thủ công từ một commit đã được phê duyệt và ghi rõ lý do.

**Production đang dùng tag ghi đè:** đối chiếu image digest thực tế, sửa pipeline để deploy artifact bất biến và xác lập retention/rollback.

## 16. Xử lý sự cố ACR Tasks

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| az acr build bị từ chối | Sai subscription, registry, RBAC hoặc quota | az account show, registry show, role assignments, error code |
| Không tìm thấy Dockerfile | --file hoặc build context sai | Kiểm tra tên file, case-sensitive path, .dockerignore |
| COPY không thấy tệp | File ngoài context hoặc bị .dockerignore loại | Kiểm tra context gửi lên ACR |
| Maven/npm build lỗi | Dependency, repo private, certificate hoặc mạng | Task logs, package feed access, phiên bản tool |
| Base image pull lỗi | Registry auth, DNS, rate limit hoặc tag sai | Kiểm tra FROM, registry, credential và network |
| Task tạo được nhưng Git trigger không chạy | Webhook/token/branch/ref hoặc trigger setting sai | Task config, webhook, token scopes, list-runs |
| Base update không kích hoạt build | Registry/base format không được hỗ trợ hoặc tracking không đúng | Xác nhận cơ chế trigger và dùng scheduled fallback |
| Scheduled task không chạy | Cron, timezone, task disabled hoặc quyền | Kiểm tra schedule config và lịch sử runs |
| Push thất bại 401/403 | Identity thiếu quyền push/repository | Kiểm tra role, ABAC scope, login server |
| Build xong nhưng không thấy tag | Task YAML không có push, tag khác dự kiến hoặc run fail | Xem task logs, repositories, tags/digest |
| Image pull thất bại trên Container Apps | Runtime identity thiếu pull, networking hoặc registry config sai | Kiểm tra managed identity, role và Container App logs |
| Container App có image mới nhưng vẫn thấy code cũ | Chưa deploy revision đúng, cache runtime hoặc tag bị ghi đè | Kiểm tra revision và digest thực tế |
| Build quá chậm | Context lớn, dependency download, Dockerfile layer cache kém | Đo size, Dockerfile, network và duration |
| Registry bị đầy hoặc phí tăng | Lưu quá nhiều image, retention chưa rõ | Registry usage, tags/manifests, policy cleanup |
| Security scan không chạy | Chưa cấu hình scanner/gate, thiếu license hoặc task step | Kiểm tra pipeline/gói bảo vệ và job logs |

### 16.1. Cách điều tra theo thứ tự

1. **Azure account:** đúng subscription, tenant và resource group?
2. **Registry:** có tồn tại và hỗ trợ tính năng đang dùng?
3. **Task definition:** đúng context, branch, Dockerfile, image tag và trigger?
4. **Source access:** token/webhook và network đọc repo hoạt động?
5. **Builder:** log có lỗi dependency, base image, CPU/memory hoặc Dockerfile?
6. **Output:** run successful và image manifest/tag/digest có xuất hiện?
7. **Security:** scan/signing/approval có hoàn tất?
8. **Deployment:** Container Apps có được cập nhật image digest/revision chưa?
9. **Runtime:** health, auth, network, database, startup và logs có đạt không?

Nếu build fail, không nên cấp Owner toàn subscription hoặc bật registry admin account làm biện pháp đầu tiên. Phân tích lỗi quyền tại scope cụ thể rồi cấp tối thiểu đúng role.

## 17. Checklist triển khai production

### Trước khi tạo task

- [ ] Registry SKU/region/quota và chính sách network phù hợp.
- [ ] Source repository/branch và Dockerfile được quản lý bằng code review.
- [ ] Có .dockerignore, không đưa secret vào context.
- [ ] Đã quyết định chiến lược tag/digest và retention.
- [ ] Identity quản lý task, push image, pull runtime được tách quyền.
- [ ] Credential Git/webhook được bảo quản và xoay vòng.
- [ ] Có phương án base image update và lịch rebuild phù hợp.
- [ ] Có baseline thời gian build, kích thước image và ngân sách.

### Trong build và kiểm tra

- [ ] Task run ghi ID, commit SHA và trigger reason.
- [ ] Log không để lộ secret.
- [ ] Unit/integration tests đạt.
- [ ] Base image và dependency provenance được ghi nhận.
- [ ] Vulnerability scan/SBOM/signing được chạy nếu policy yêu cầu.
- [ ] Image digest được lưu sau push.
- [ ] Test runtime với image đã build, port và health endpoint đúng.

### Trước và sau deploy

- [ ] CD sử dụng image đã được phê duyệt, không build lại không kiểm soát.
- [ ] Container App hoặc nền tảng chạy có identity pull tối thiểu.
- [ ] Runtime secrets không bị nhúng vào Docker image.
- [ ] Có approval gate khi lên production.
- [ ] Theo dõi revision/image digest, error rate, latency và logs.
- [ ] Có kế hoạch rollback image/revision và dữ liệu.
- [ ] Artifact dùng để rollback chưa bị xóa bởi cleanup policy.

## 18. Câu hỏi tự kiểm tra

1. **ACR và ACR Tasks khác nhau ở đâu?** ACR lưu/phân phối image; ACR Tasks thực hiện và tự động hóa build/steps trên hạ tầng được quản lý.
2. **Quick task có cần Docker daemon local không?** Thông thường không; az acr build gửi context cho dịch vụ build từ Azure CLI.
3. **Named task khác task run như thế nào?** Task là định nghĩa; run là một lần thực thi cụ thể.
4. **Vì sao không chỉ dùng latest tag ở production?** Tag có thể được gán lại; digest giúp định danh artifact chính xác.
5. **Commit trigger phụ thuộc điều kiện nào?** Repository/ref, webhook hoặc tích hợp provider, credential/permissions và task được bật.
6. **Base image update có tự sửa CVE trong container đang chạy không?** Không. Cần rebuild và deploy artifact mới.
7. **Scheduled task có bắt buộc deploy production ngay không?** Không. Build và release là hai quy trình khác nhau.
8. **ACR Tasks có tự scan và ký mọi image không?** Không. Cần cấu hình công cụ, bước và policy tương ứng.
9. **Một Dockerfile có ARG SECRET rồi RUN echo có an toàn không?** Không. Secret có thể lộ qua build logs/layers/metadata.
10. **Phải cấp quyền nào cho Container Apps khi chỉ pull image?** Quyền pull phù hợp với registry/repository qua identity được hỗ trợ, không cấp quyền quản trị rộng.
11. **Ghi image digest giúp gì?** Giúp truy vết, tái triển khai và rollback artifact cụ thể.
12. **Build thành công có đồng nghĩa ứng dụng chạy được không?** Không. Còn kiểm thử runtime, health, cổng mạng, secret và dependencies.
13. **Đổi tag image trong ACR có làm Container App tự rollout?** Không mặc nhiên; cần deploy action hoặc continuous deployment đã cấu hình.
14. **Task không trigger từ Git, nên kiểm tra gì?** Webhook, branch/ref, token, trigger enabled và task run history.
15. **Khi dùng mạng riêng cho registry có cần kiểm tra tác động lên builder không?** Có. Task runner phải có đường kết nối phù hợp tới registry, source và base images.
16. **Lợi ích của build một lần, deploy qua nhiều môi trường?** Giảm drift artifact và tăng khả năng chứng minh cùng image digest đã qua kiểm thử.
17. **Tại sao retention policy cần tính đến rollback?** Xóa image cũ quá sớm có thể làm không thể khôi phục phiên bản trước.

## 19. Tài liệu tham khảo

- [Azure Container Registry documentation](https://learn.microsoft.com/azure/container-registry/) — quản lý registry, repositories, image và bảo mật.
- [ACR Tasks overview](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-overview) — quick tasks, automation và trigger.
- [Build and push images with ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-quickstart-task-cli) — quick build và tác vụ CLI.
- [Automate image builds with ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-tutorial-build-task) — cấu hình task theo nguồn và tự động hóa.
- [Multi-step ACR Tasks](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-multi-step) — cú pháp YAML, steps và task execution.
- [Automated base image updates](https://learn.microsoft.com/azure/container-registry/container-registry-tasks-base-images) — theo dõi base image và build lại.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — các lựa chọn danh tính và quyền truy cập.
- [Azure Container Apps documentation](https://learn.microsoft.com/azure/container-apps/) — chạy image, revisions, ingress, scaling và quản trị.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — theo dõi chi phí theo resource và workload.

**Kết luận:** ACR Tasks giúp chuẩn hóa và tự động hóa khâu build container image bằng quick build, task theo Git, base-image update, lịch và multi-step workflow. Một pipeline đáng tin cậy phải quản lý chặt **source commit → build run → image digest → kiểm thử/bảo mật → approval → deployment/revision**. Muốn triển khai an toàn trên Azure, hãy dùng identity tối thiểu, không đưa secret vào image, tách build khỏi phát hành production, theo dõi log/chi phí và luôn giữ artifact đủ để rollback.
