# Cloud Build configs, build steps và substitutions

Cloud Build tự động hóa quá trình lấy mã nguồn, kiểm thử, đóng gói và tạo artifact để phát hành ứng dụng. Một build config mô tả các bước cần thực hiện, container image dùng cho từng bước, thứ tự chạy, biến cấu hình và artifact đầu ra. Khi hiểu rõ cấu trúc này, nhóm phát triển có thể tạo pipeline dễ đọc, tái lập, kiểm soát quyền và điều chỉnh theo từng môi trường mà không phải sao chép nhiều tệp cấu hình.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài này, chúng ta tập trung vào cấu hình Cloud Build, build steps, thứ tự thực thi, substitutions và cách đưa một ứng dụng Java vào quy trình build.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của Cloud Build và build config.
- Nhận diện các trường chính của một tệp cloudbuild.yaml.
- Tổ chức build steps, container image, args, env, dir, id và waitFor.
- Chạy các bước tuần tự hoặc song song và chia sẻ artifact qua workspace.
- Phân biệt built-in substitutions với user-defined substitutions.
- Sử dụng substitutions cho project, region, repository, image tag và trigger.
- Chọn cách xử lý substitution không tồn tại và escape ký tự dollar.
- Chạy build thủ công, cấu hình trigger và kiểm tra kết quả.
- Áp dụng nguyên tắc IAM, quản lý secret và bảo vệ chuỗi cung ứng phần mềm.

## 1. Cloud Build trong quy trình CI/CD

Cloud Build là dịch vụ thực thi build trên Google Cloud. Một build có thể được khởi chạy thủ công từ máy phát triển, qua Cloud Build trigger khi có thay đổi trong repository hoặc thông qua API. Cloud Build thực hiện các bước đã khai báo, lưu kết quả và cung cấp trạng thái cùng log để nhóm kiểm tra.

Một quy trình phổ biến cho ứng dụng Java:

~~~mermaid
flowchart TD
    A["Commit mã nguồn"]
    B["Cloud Build trigger"]
    C["Checkout source"]
    D["Compile và unit tests"]
    E["Build container image"]
    F["Push Artifact Registry"]
    G["Deploy Cloud Run / GKE"]
    H["Kiểm tra sau deploy"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Cloud Build tập trung vào việc thực thi các bước build. Repository chứa mã nguồn và build config; Artifact Registry lưu container image hoặc package; Cloud Run, GKE hoặc Compute Engine chạy artifact sau khi phát hành. Có thể dùng thêm các dịch vụ kiểm thử, phê duyệt, quản lý secret và giám sát tùy kiến trúc.

### Build config là gì?

Build config là tệp YAML hoặc JSON mô tả một build. Tên thường dùng là cloudbuild.yaml hoặc cloudbuild.yml. Tệp này khai báo:

- **steps:** danh sách các bước build và container image thực thi từng bước.
- **substitutions:** các biến dùng để tùy chỉnh build.
- **options:** tùy chọn chung như logging, machine type và cách xử lý substitutions.
- **timeout:** thời gian tối đa cho toàn bộ build.
- **images:** container image Cloud Build cần lưu/push sau khi build.
- **artifacts:** artifact khác, ví dụ tệp được đưa lên Cloud Storage.
- **availableSecrets:** secret được cấp cho build step qua Secret Manager.
- **serviceAccount:** danh tính thực thi build nếu dùng user-specified service account.

Không phải mọi trường đều bắt buộc. Một build tối thiểu có thể chỉ cần steps; build production nên khai báo rõ những tùy chọn ảnh hưởng đến quyền, logging, timeout và artifact.

## 2. Cấu trúc một build step

Mỗi phần tử trong mảng **steps** mô tả một container được Cloud Build chạy. Container image cung cấp công cụ cho bước đó, chẳng hạn Maven, Docker, gcloud hoặc một image do nhóm tự xây dựng.

Các trường thường dùng:

| Trường | Vai trò | Ví dụ |
|---|---|---|
| name | Container image thực thi step | maven:3.9-eclipse-temurin-21 |
| id | Tên định danh của step | unit-tests |
| entrypoint | Chương trình chạy bên trong container | mvn, bash |
| args | Đối số truyền cho entrypoint hoặc command mặc định | -B test package |
| env | Biến môi trường thông thường | APP_ENV=staging |
| secretEnv | Biến môi trường lấy từ availableSecrets | PAYMENT_API_TOKEN |
| dir | Thư mục làm việc của step | services/orders |
| waitFor | Các step cần hoàn thành trước step hiện tại | unit-tests, package |
| timeout | Thời gian tối đa của step | 300s |
| allowFailure | Cho phép build tiếp tục khi step thất bại | true |
| allowExitCodes | Các exit code được chấp nhận | 1, 2 |
| volumes | Mount volume dùng chung giữa các step | cache-volume |

### Container image và lệnh

Trường name xác định image có sẵn trên registry. Khi step bắt đầu, Cloud Build tạo container từ image đó rồi chạy entrypoint cùng args. Nếu không chỉ định entrypoint, Cloud Build dùng entrypoint mặc định của image.

Ví dụ chạy Maven:

~~~yaml
steps:
  - name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test
      - package
~~~

Trong ví dụ, Maven image cung cấp JDK và Maven; entrypoint là mvn; args yêu cầu chạy test và package ở chế độ batch. Với dự án thực tế, nên chọn phiên bản builder cụ thể đã được kiểm tra. Có thể pin image theo digest để giảm nguy cơ tag thay đổi ngoài ý muốn.

### entrypoint và args

Nếu cần shell để nối nhiều lệnh, có thể dùng image có bash và chỉ định entrypoint:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/gcloud
    entrypoint: bash
    args:
      - -ceu
      - |
        echo "Build started"
        gcloud version
        echo "Build checks completed"
~~~

Các tùy chọn -c, -e và -u thuộc bash: -c chạy chuỗi lệnh, -e dừng khi một lệnh thất bại và -u báo lỗi khi dùng biến chưa được định nghĩa. Dùng pipefail nếu script có pipeline shell và cần phát hiện lỗi từ các lệnh đứng trước. Tránh ghép một chuỗi lệnh phức tạp vào một args không rõ cách quote; block nhiều dòng dễ đọc và review hơn.

### env và dir

Trường env truyền các biến cấu hình không bí mật vào container của step. Trường dir thay đổi thư mục làm việc. Nếu dir là đường dẫn tương đối, đường dẫn được tính từ /workspace.

~~~yaml
steps:
  - name: maven:3.9.9-eclipse-temurin-21
    dir: services/orders
    env:
      - APP_ENV=ci
    entrypoint: mvn
    args:
      - -B
      - test
~~~

Không đặt mật khẩu hoặc token trong env trực tiếp của build config. Giá trị này có thể xuất hiện trong cấu hình, lịch sử thay đổi hoặc log nếu được in ra.

## 3. Workspace và chia sẻ dữ liệu giữa các step

Mỗi build step chạy trong container riêng. Các tệp trong filesystem riêng của container không tự động được chia sẻ với container của step tiếp theo. Cloud Build cung cấp thư mục **/workspace** được chia sẻ giữa các bước trong cùng build. Source được đặt trong workspace và các step có thể ghi hoặc đọc artifact ở đây.

Ví dụ:

~~~yaml
steps:
  - id: compile
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - package

  - id: inspect-artifact
    name: gcr.io/cloud-builders/gcloud
    entrypoint: bash
    args:
      - -ceu
      - |
        test -f /workspace/target/app.jar
        ls -lh /workspace/target/app.jar
    waitFor:
      - compile
~~~

Ví dụ giả định Maven được cấu hình để tạo file target/app.jar. Nếu artifact có tên khác, hãy điều chỉnh đường dẫn hoặc cấu hình finalName trong Maven.

Nếu cần chia sẻ dữ liệu ngoài /workspace, khai báo volume dùng chung cho các step cần nó. Volume phải có cùng name và mount path phù hợp ở các step tham gia. Không giả định rằng /tmp hoặc thư mục home của container này sẽ tồn tại trong container khác.

### Tránh ghi đè artifact

Khi nhiều step chạy song song, mỗi step nên ghi ra file hoặc thư mục riêng. Nếu hai step cùng ghi một file, kết quả có thể phụ thuộc thứ tự hoàn tất. Chỉ ghép hoặc đóng gói artifact sau khi các step tạo dữ liệu đã hoàn thành.

## 4. Thứ tự thực thi: id và waitFor

Cloud Build thực thi các step theo thứ tự mặc định. Một step thường chờ các step đứng trước hoàn thành. Trường **id** đặt tên cho step; **waitFor** khai báo rõ các step mà step hiện tại cần chờ.

Ví dụ pipeline có hai bước kiểm tra độc lập và một bước package:

~~~yaml
steps:
  - id: unit-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test

  - id: static-checks
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -ceu
      - |
        echo "Run project static checks here"
    waitFor:
      - "-"

  - id: package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - package
      - -DskipTests
    waitFor:
      - unit-tests
      - static-checks
~~~

Giá trị đặc biệt **-** trong waitFor có nghĩa step có thể bắt đầu ngay khi build bắt đầu, không cần chờ step nào khác. Trong ví dụ, unit-tests và static-checks chạy song song; package chờ cả hai. Nếu một bước kiểm tra bắt buộc thất bại, build dừng và package không được chạy.

Hãy chỉ chạy song song các bước độc lập. Nếu package cần output của compile, hoặc integration test cần database đã khởi tạo, hãy khai báo dependency bằng waitFor để build có thứ tự xác định.

### allowFailure và allowExitCodes

Một số bước có thể mang tính bổ trợ, chẳng hạn thu thập báo cáo tùy chọn. **allowFailure: true** cho phép build tiếp tục khi step đó thất bại. **allowExitCodes** cho phép chỉ định những exit code cụ thể được chấp nhận. Khi dùng allowExitCodes, danh sách exit code được ưu tiên hơn allowFailure.

Không bật allowFailure cho compile, test bắt buộc, scan bảo mật hoặc bước tạo artifact cần phát hành. Một build xanh trong khi kiểm thử quan trọng đã thất bại sẽ làm mất ý nghĩa của trạng thái CI.

## 5. Built-in substitutions

Substitution là biến được Cloud Build thay bằng giá trị trước khi thực thi build step. Built-in substitutions cung cấp thông tin về build, project hoặc nguồn kích hoạt.

Một số built-in substitutions thường gặp:

| Substitution | Ý nghĩa |
|---|---|
| PROJECT_ID | Project ID của build |
| PROJECT_NUMBER | Project number |
| BUILD_ID | ID duy nhất của build |
| LOCATION | Vị trí Cloud Build |
| TRIGGER_NAME | Tên trigger đã khởi chạy build |
| REPO_NAME | Tên repository nguồn |
| REPO_FULL_NAME | Tên repository đầy đủ nếu nguồn hỗ trợ |
| BRANCH_NAME | Tên branch khi build từ branch |
| TAG_NAME | Tên tag khi build từ tag |
| COMMIT_SHA | Commit SHA |
| SHORT_SHA | Phiên bản rút gọn của commit SHA |
| REVISION_ID | Revision ID |
| REF_NAME | Tên ref nguồn |

Các giá trị phụ thuộc cách build được khởi chạy và nguồn repository. Ví dụ, TRIGGER_NAME hoặc BRANCH_NAME có thể không có giá trị trong build thủ công không gắn với trigger. Hãy tránh giả định rằng mọi built-in substitution luôn có giá trị trong mọi loại build.

### Dùng built-in substitutions

Ví dụ đặt tag container image theo build ID:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/containers/orders-api:$BUILD_ID
      - .
~~~

Khi build chạy, Cloud Build thay PROJECT_ID và BUILD_ID bằng giá trị tương ứng. Tag chứa build ID giúp nhận diện artifact của một lần build cụ thể. Với build từ source control, có thể dùng SHORT_SHA để liên kết image với commit.

## 6. User-defined substitutions

Khi cần truyền tên service, region, repository hoặc môi trường, hãy khai báo custom substitutions trong trường **substitutions**. Tên custom substitution phải bắt đầu bằng dấu gạch dưới, sau đó dùng chữ hoa, số hoặc dấu gạch dưới. Ví dụ: _SERVICE, _REGION, _AR_REPOSITORY.

~~~yaml
substitutions:
  _SERVICE: orders-api
  _REGION: asia-southeast1
  _AR_REPOSITORY: containers

steps:
  - name: gcr.io/cloud-builders/gcloud
    args:
      - run
      - services
      - describe
      - $_SERVICE
      - --region=$_REGION
~~~

Cloud Build hỗ trợ cách viết $_SERVICE hoặc dạng có ngoặc nhọn tương đương. Dạng có ngoặc nhọn hữu ích khi nối substitution với ký tự khác mà ranh giới tên biến có thể không rõ. Hãy dùng một quy ước nhất quán trong repository.

### Giá trị mặc định và ghi đè khi chạy build

Substitution có thể được đặt mặc định trong build config và ghi đè khi chạy build thủ công hoặc cấu hình trigger. Ví dụ:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _SERVICE: orders-api
  _ENVIRONMENT: staging
~~~

Khi chạy build, có thể truyền giá trị khác cho các custom substitutions. Điều này cho phép cùng một build config phục vụ nhiều môi trường mà không phải sao chép toàn bộ tệp YAML. Tuy nhiên, các môi trường production nên có trigger, quyền và phê duyệt phù hợp; không để một tham số tùy ý biến build staging thành build production mà bỏ qua kiểm soát.

### SubstitutionOption: MUST_MATCH và ALLOW_LOOSE

Build config có thể dùng **options.substitutionOption** để quy định cách xử lý substitution không được cung cấp:

- **MUST_MATCH:** build thất bại nếu substitution được tham chiếu nhưng không có giá trị.
- **ALLOW_LOOSE:** substitution không có giá trị được thay bằng chuỗi rỗng.

Với build thủ công, mặc định thường là MUST_MATCH. Với build được trigger, Cloud Build mặc định sử dụng ALLOW_LOOSE. Có thể khai báo rõ trong options để người đọc hiểu hành vi mong muốn.

ALLOW_LOOSE có thể tiện khi một build config dùng chung cho nhiều trigger có bộ built-in substitutions khác nhau. Tuy nhiên, biến thiếu bị thay bằng chuỗi rỗng có thể tạo ra tên image, đường dẫn hoặc lệnh sai mà không báo lỗi sớm. Với giá trị bắt buộc như region, repository hoặc service name, nên xác thực đầu vào trong step trước khi dùng.

### Dynamic substitutions

**dynamicSubstitutions** cho phép một substitution tham chiếu đến substitution khác. Ví dụ, một custom substitution có thể dựa trên PROJECT_ID hoặc một custom value khác. Với build được khởi chạy bởi trigger, Cloud Build bật dynamic substitutions tự động; với build thủ công, cần bật rõ trong options nếu cấu hình sử dụng tính năng này.

~~~yaml
substitutions:
  _IMAGE_NAME: orders-api
  _IMAGE_PATH: asia-southeast1-docker.pkg.dev/$PROJECT_ID/containers/$_IMAGE_NAME

options:
  dynamicSubstitutions: true
~~~

Hãy dùng dynamic substitutions khi thật sự cần tạo giá trị dẫn xuất. Với cấu hình đơn giản, khai báo từng giá trị trực tiếp thường dễ đọc và dễ kiểm tra hơn.

## 7. Escape ký tự dollar và dùng biến shell

Cloud Build xử lý substitutions trước khi shell chạy. Vì vậy, nếu một script cần dùng cú pháp biến của shell, cần tránh để Cloud Build coi đó là substitution của nó.

Cloud Build dùng **$$** để escape dấu dollar và truyền một dấu dollar xuống bước thực thi. Ví dụ:

~~~yaml
steps:
  - name: bash
    entrypoint: bash
    env:
      - APP_ENV=staging
    args:
      - -ceu
      - |
        echo "Build environment: $$APP_ENV"
        echo "Working directory: $$PWD"
~~~

Sau bước xử lý substitutions, bash nhận được biến APP_ENV và PWD để mở rộng. Nếu viết một dấu dollar trực tiếp trước tên biến không phải built-in hoặc custom substitution, Cloud Build có thể báo lỗi substitution không hợp lệ hoặc thay giá trị ngoài ý muốn.

Không nhầm lẫn giữa:

- **$_REGION:** custom substitution do Cloud Build thay trước khi chạy step.
- **$$APP_ENV:** dấu dollar được escape để shell mở rộng biến môi trường APP_ENV.
- **$BUILD_ID:** built-in substitution do Cloud Build thay trước khi chạy step.

Đối với script nhiều dòng, hãy kiểm tra chuỗi sau khi substitution và quote shell cẩn thận. Không dùng substitution để ghép dữ liệu không đáng tin cậy vào lệnh shell; truyền giá trị qua env hoặc args và kiểm tra đầu vào phù hợp.

## 8. Ví dụ hoàn chỉnh: build và đóng gói ứng dụng Java

Giả sử repository chứa ứng dụng Java dùng Maven, có Dockerfile tại thư mục gốc. Maven được cấu hình tạo file **target/app.jar**. Mục tiêu là chạy test, build container image và push image lên Artifact Registry.

### Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ Dockerfile sử dụng JRE Java 21. Với production, nên pin base image theo version hoặc digest, cập nhật định kỳ và quét lỗ hổng trước khi phát hành.

### cloudbuild.yaml

~~~yaml
steps:
  - id: unit-tests-and-package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test
      - package

  - id: build-container
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_AR_HOST/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - .
    waitFor:
      - unit-tests-and-package

images:
  - $_AR_HOST/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID

substitutions:
  _AR_HOST: asia-southeast1-docker.pkg.dev
  _AR_REPOSITORY: containers
  _IMAGE: orders-api

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

Giải thích:

1. Step unit-tests-and-package dùng Maven để chạy test và tạo artifact.
2. Step build-container chờ bước Maven thành công, sau đó dùng Docker builder tạo image từ Dockerfile.
3. Image được tag theo project, Artifact Registry host, repository, image name và BUILD_ID.
4. Trường images khai báo image đầu ra để Cloud Build push sau khi các step hoàn tất.
5. Substitutions cung cấp host, repository và tên image mặc định.
6. logging chọn Cloud Logging làm nơi lưu log build; timeout giới hạn thời gian tối đa của build.

Để ví dụ hoạt động, cần tạo Artifact Registry Docker repository tương ứng, bật các API cần thiết và cấp quyền ghi cho build service account. Maven project phải tạo đúng file target/app.jar. Nếu tên file khác, hãy điều chỉnh Dockerfile hoặc Maven finalName.

### Tạo Artifact Registry repository

Ví dụ lệnh tạo Docker repository:

~~~bash
gcloud artifacts repositories create containers \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Container images for application builds"
~~~

Project và region phải đúng với nơi triển khai. Nếu repository đã tồn tại, không cần tạo lại. Quyền tạo repository thuộc nhóm quản trị hạ tầng; build service account chỉ cần quyền ghi image vào repository.

### Chạy build thủ công

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

Lệnh gửi source hiện tại cùng build config lên Cloud Build. Có thể truyền custom substitutions khi cần:

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1 \
  --substitutions=_AR_HOST=asia-southeast1-docker.pkg.dev,_AR_REPOSITORY=containers,_IMAGE=orders-api
~~~

Không đưa mật khẩu, token hoặc khóa vào --substitutions. Substitution là dữ liệu cấu hình, không phải kênh lưu secret.

### Kiểm tra kết quả

Sau khi build kết thúc:

1. Mở Cloud Build History và chọn build ID.
2. Xem log từng step để xác nhận Maven test và Docker build thành công.
3. Kiểm tra trạng thái image trong Artifact Registry.
4. Ghi lại image URI và digest để phát hành đúng artifact đã được build.
5. Nếu build thất bại, xác định step đầu tiên lỗi và đọc log của step đó; tránh chỉ sửa bước cuối mà bỏ qua lỗi nguồn.

## 9. Build triggers và substitutions theo nguồn

Build trigger tự động khởi chạy build khi có sự kiện từ repository hoặc nguồn được cấu hình. Trigger thường liên kết với branch, tag hoặc pull request. Khi trigger chạy, Cloud Build có thể cung cấp built-in substitutions như BRANCH_NAME, TAG_NAME, COMMIT_SHA, SHORT_SHA và TRIGGER_NAME.

Một quy trình trigger điển hình:

1. Kết nối repository với Cloud Build.
2. Tạo trigger và chọn event, ví dụ push lên branch main.
3. Chọn build config trong repository.
4. Chọn region của trigger và cấu hình substitutions riêng nếu cần.
5. Chỉ định service account của build với quyền tối thiểu.
6. Thử trigger bằng một commit không ảnh hưởng production.
7. Kiểm tra log, artifact và trạng thái build.

### Phân biệt trigger cho pull request và branch chính

Một tổ chức có thể dùng trigger riêng:

- Pull request: chạy lint, unit tests, dependency checks và build thử; không cấp quyền deploy production hoặc secret không cần thiết.
- Branch main: chạy kiểm thử đầy đủ, tạo image và phát hành vào môi trường kiểm thử.
- Tag release: tạo artifact release, gắn version rõ ràng và có thể yêu cầu phê duyệt trước deploy.

Substitutions theo branch hoặc tag có thể dùng để gắn metadata cho artifact. Tuy nhiên, không dùng tên branch làm ranh giới bảo mật. Quyền deploy phải được kiểm soát bằng IAM, trigger policy, approval và service account phù hợp.

### Trigger substitutions và giá trị thiếu

Trigger có thể cung cấp các built-in substitutions phụ thuộc event. Nếu build config dùng chung cho manual build và trigger build, cần xem xét giá trị nào không có trong từng ngữ cảnh. Có thể đặt default cho custom substitutions và kiểm tra những trường bắt buộc trước khi thực hiện deploy.

## 10. Dùng Secret Manager trong build step

Build đôi khi cần token để truy cập package registry riêng, chạy scan hoặc gọi dịch vụ kiểm thử. Không ghi secret vào build config, substitutions, Dockerfile hoặc câu lệnh echo. Hãy lấy secret từ Secret Manager và chỉ cấp cho step cần sử dụng.

Ví dụ cấu hình secret:

~~~yaml
availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/SONAR_TOKEN/versions/latest
      env: SONAR_TOKEN

steps:
  - name: bash
    entrypoint: bash
    secretEnv:
      - SONAR_TOKEN
    args:
      - -ceu
      - |
        test -n "$$SONAR_TOKEN"
        echo "Scanner credential is available"
~~~

Build service account cần quyền truy cập secret tương ứng, thường là roles/secretmanager.secretAccessor ở cấp secret. Secret chỉ được ánh xạ vào step khai báo secretEnv. Không in giá trị secret ra log và không truyền nó vào command line nếu công cụ có thể nhận qua environment hoặc cơ chế an toàn khác.

Không cung cấp secret cho build từ pull request không đáng tin cậy. Một script trong repository có thể đọc biến môi trường và gửi ra ngoài. Hãy tách trigger, service account và secret scope theo mức độ tin cậy của nguồn code.

## 11. Build service account và IAM

Cloud Build sử dụng danh tính để truy cập source, ghi log, đọc secret, push image hoặc deploy. Cần phân biệt Cloud Build service agent do Google quản lý với build service account mà các step sử dụng để thực thi thao tác.

Trong production, nên chỉ định user-specified service account phù hợp với workload và cấp quyền tối thiểu. Ví dụ:

| Nhiệm vụ | Quyền thường cần |
|---|---|
| Ghi log vào Cloud Logging | roles/logging.logWriter |
| Push image lên Artifact Registry | roles/artifactregistry.writer trên repository cần dùng |
| Đọc secret trong build step | roles/secretmanager.secretAccessor trên secret cần dùng |
| Ghi custom metrics nếu build có nhu cầu | Quyền Monitoring phù hợp với tác vụ |
| Deploy Cloud Run | Quyền deploy service và quyền iam.serviceAccounts.actAs trên runtime service account phù hợp |

Danh sách chính xác phụ thuộc cấu hình, API và dịch vụ đích. Không cấp Owner hoặc Editor cho build service account chỉ để xử lý lỗi quyền. Hãy kiểm tra permission bị thiếu và cấp role nhỏ nhất ở phạm vi tài nguyên nhỏ nhất.

Build service account và runtime service account là hai danh tính khác nhau. Build cần quyền tạo và phát hành artifact; ứng dụng khi chạy chỉ nên có quyền truy cập dữ liệu và dịch vụ mà workload cần. Không dùng build service account làm runtime identity cho ứng dụng.

## 12. Build options, timeout và logging

Trường **options** điều khiển cách Cloud Build thực thi build:

- **logging:** chọn nơi lưu log, ví dụ CLOUD_LOGGING_ONLY.
- **machineType:** chọn loại máy build khi workload cần tài nguyên khác mặc định.
- **diskSizeGb:** cấu hình dung lượng đĩa build khi cần.
- **substitutionOption:** MUST_MATCH hoặc ALLOW_LOOSE.
- **dynamicSubstitutions:** bật substitution dẫn xuất khi cần.
- **pool:** chọn private pool nếu build cần môi trường mạng riêng.

Trường **timeout** ở cấp build giới hạn tổng thời gian build. Có thể khai báo timeout ở cấp step để giới hạn một bước riêng. Hãy đặt giới hạn phù hợp với thời gian kiểm thử và tải thực tế; timeout quá dài làm chậm phát hiện pipeline bị treo, timeout quá ngắn gây fail giả.

### Private pools

Private pools hữu ích khi build cần truy cập tài nguyên trong mạng riêng hoặc cần kiểm soát môi trường build. Khi sử dụng, cần thiết kế network, region, IAM và kết nối đến source/artifact phù hợp. Không đưa thông tin xác thực mạng hoặc secret vào substitutions.

### Logs và chẩn đoán

Cloud Build có thể ghi log vào Cloud Logging hoặc vị trí lưu trữ được cấu hình. Khi build thất bại, hãy kiểm tra:

1. Build status và step đầu tiên thất bại.
2. Exit code và command thực tế đã chạy.
3. Image builder có tồn tại và pull được không.
4. Source có chứa tệp hoặc đường dẫn mà step mong đợi không.
5. Substitution có được thay đúng và có giá trị không.
6. Build service account có quyền với API, repository hoặc secret không.
7. Timeout, quota, private pool và network có gây gián đoạn không.

Không xử lý mọi lỗi bằng cách tăng quyền hoặc tăng timeout. Hãy xác định nguyên nhân từ log và chỉ thay đổi cấu hình liên quan.

## 13. Bảo vệ chuỗi cung ứng phần mềm trong Cloud Build

Build pipeline là một phần quan trọng của software supply chain. Nếu build config hoặc builder image bị thay đổi trái phép, artifact phát hành có thể bị ảnh hưởng ngay cả khi mã nguồn ứng dụng không có lỗi.

Các biện pháp nên áp dụng:

- Review thay đổi cloudbuild.yaml như review mã nguồn ứng dụng.
- Dùng builder image từ nguồn tin cậy và pin phiên bản hoặc digest.
- Quản lý dependency có lockfile hoặc version cố định khi hệ sinh thái hỗ trợ.
- Giới hạn quyền của build service account theo nhiệm vụ.
- Tách build từ pull request không tin cậy khỏi build có secret hoặc quyền deploy.
- Dùng approval hoặc cơ chế kiểm soát riêng cho production release.
- Lưu image theo digest và liên kết artifact với commit, build ID và provenance.
- Quét dependency, container image và artifact theo chính sách bảo mật.
- Không để log build lộ token, password, private key hoặc dữ liệu khách hàng.
- Theo dõi thay đổi trigger, service account, repository và build config.

Substitutions giúp tái sử dụng cấu hình nhưng không phải cơ chế bảo mật. Giá trị custom substitution có thể được xem trong build config hoặc thông tin build; chỉ truyền tên môi trường, region, repository, version và các giá trị không nhạy cảm.

## 14. Lỗi cấu hình thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Build báo invalid substitution | Tên biến sai định dạng hoặc biến chưa có giá trị | Kiểm tra built-in và custom substitutions |
| Lệnh shell nhận chuỗi rỗng | ALLOW_LOOSE thay biến thiếu bằng rỗng | Xác thực biến bắt buộc trước khi dùng |
| Shell báo bad substitution | Cloud Build và shell cùng xử lý ký tự dollar | Escape bằng $$ khi cần shell mở rộng biến |
| Step không thấy artifact | Artifact nằm trong filesystem riêng của container | Ghi artifact vào /workspace hoặc volume dùng chung |
| Step chạy quá sớm | waitFor không khai báo dependency | Dùng id và waitFor rõ ràng |
| Image không push được | Sai registry path hoặc thiếu quyền | Kiểm tra repository, location và Artifact Registry IAM |
| Build không đọc được secret | Thiếu secret accessor hoặc secretEnv sai | Cấp quyền ở secret cần thiết và kiểm tra tên env |
| Build trigger không chạy | Event, branch, repository hoặc region cấu hình sai | Kiểm tra trigger configuration và event |
| Build xanh dù kiểm tra thất bại | Step bắt buộc được đặt allowFailure | Bỏ allowFailure hoặc điều chỉnh allowExitCodes |
| Artifact không tái lập | Builder/dependency tag thay đổi hoặc source không cố định | Pin version/digest và ghi lại commit |

## 15. Bài tập thực hành: tạo Cloud Build pipeline cho Java service

Giả sử repository chứa service Java tên orders-api, dùng Maven và triển khai lên Cloud Run. Hãy tạo pipeline có thể chạy thủ công và qua trigger.

Thực hiện:

1. Tạo cloudbuild.yaml với step chạy Maven unit tests và package.
2. Tạo step Docker build image từ Dockerfile.
3. Đặt image tag theo BUILD_ID hoặc SHORT_SHA để liên kết artifact với build.
4. Dùng custom substitutions cho Artifact Registry host, repository, image name và region.
5. Đảm bảo build step phụ thuộc vào bước kiểm thử bằng waitFor.
6. Bật Cloud Logging cho build và đặt timeout phù hợp.
7. Tạo Artifact Registry repository và cấp quyền writer cho build service account.
8. Chạy build thủ công bằng gcloud builds submit.
9. Kiểm tra log, trạng thái build, image URI và digest trong Artifact Registry.
10. Tạo trigger cho pull request hoặc branch thử nghiệm.
11. Xác nhận trigger không có quyền production và không nhận secret không cần thiết.
12. Thử thay đổi một substitution không hợp lệ và quan sát lỗi; sau đó sửa và chạy lại.
13. Thêm bước kiểm tra container hoặc dependency, nhưng không để một kiểm tra bắt buộc thất bại mà build vẫn báo thành công.

### Tiêu chí hoàn thành

- Build config hợp lệ và dễ đọc.
- Các bước chạy theo dependency đã khai báo.
- Artifact được tạo và push đúng repository.
- Build ID hoặc commit SHA có thể truy ngược từ image tag.
- Không có secret trong YAML hoặc substitutions.
- Build service account chỉ có quyền cần thiết.
- Trigger chạy đúng sự kiện và không vượt phạm vi quyền.

## Checklist trước khi đưa Cloud Build config vào production

- [ ] Tệp cloudbuild.yaml được review và quản lý trong repository.
- [ ] Mỗi step dùng builder image tin cậy và phiên bản được kiểm soát.
- [ ] entrypoint, args, env và dir được khai báo rõ.
- [ ] Artifact cần chia sẻ được ghi vào /workspace hoặc volume dùng chung.
- [ ] id và waitFor thể hiện dependency chính xác.
- [ ] allowFailure chỉ dùng cho bước không bắt buộc.
- [ ] Built-in substitutions và custom substitutions được dùng đúng ngữ cảnh.
- [ ] Biến bắt buộc được kiểm tra trước khi sử dụng.
- [ ] Shell variable được escape bằng $$ khi cần.
- [ ] Secret lấy từ Secret Manager và chỉ cấp cho step cần dùng.
- [ ] Build service account có quyền tối thiểu.
- [ ] Trigger cho PR, branch và release có ranh giới quyền phù hợp.
- [ ] Timeout, logging và private pool được cấu hình theo nhu cầu.
- [ ] Artifact được liên kết với build ID, commit và digest.
- [ ] Build log không chứa secret hoặc dữ liệu nhạy cảm.

## Câu hỏi tự kiểm tra

**1. Cloud Build config dùng để làm gì?**

Nó mô tả các build step, thứ tự thực thi, container image, substitutions, options, timeout và artifact đầu ra.

**2. Mỗi build step chạy trong môi trường nào?**

Mỗi step chạy trong container riêng từ image được khai báo. Các step có thể chia sẻ dữ liệu qua /workspace hoặc volume được cấu hình.

**3. waitFor có tác dụng gì?**

Nó khai báo step hiện tại phải chờ những step nào. Giá trị đặc biệt dấu gạch ngang cho phép step bắt đầu ngay khi build bắt đầu.

**4. User-defined substitution phải có định dạng ra sao?**

Tên custom substitution phải bắt đầu bằng dấu gạch dưới, ví dụ _REGION hoặc _SERVICE.

**5. Khi nào cần dùng $$ trong build config?**

Khi muốn escape dấu dollar để Cloud Build truyền biến xuống shell, nơi shell sẽ mở rộng biến môi trường.

**6. Vì sao không lưu token trong substitutions?**

Substitutions là dữ liệu cấu hình có thể xuất hiện trong build config hoặc thông tin build; chúng không phải kho bí mật và không bảo đảm bảo vệ giá trị nhạy cảm.

**7. Build service account khác runtime service account như thế nào?**

Build service account thực hiện các thao tác trong pipeline như đọc secret hoặc push image. Runtime service account là danh tính ứng dụng dùng khi chạy và cần quyền riêng phù hợp với workload.

## Tài liệu tham khảo

- [Cloud Build overview](https://cloud.google.com/build/docs/overview)
- [Build config file schema](https://cloud.google.com/build/docs/build-config-file-schema)
- [Build steps](https://cloud.google.com/build/docs/configuring-builds/create-basic-configuration)
- [Substituting variable values](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Build request and built-in substitutions](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values#using_default_substitutions)
- [Configure user-specified service accounts](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Accessing private data in build steps](https://cloud.google.com/build/docs/securing-builds/use-secrets)
- [Cloud Build triggers](https://cloud.google.com/build/docs/triggers)
- [Cloud Build locations](https://cloud.google.com/build/docs/locations)

## Kết luận

Cloud Build config mô tả cách một artifact được tạo ra từ source code thông qua các build steps. Mỗi step chạy trong container image riêng, có thể dùng entrypoint, args, env và dir; các step phối hợp qua id, waitFor và workspace. Built-in substitutions cung cấp ngữ cảnh của build, còn custom substitutions giúp tái sử dụng cấu hình cho nhiều project hoặc môi trường. Khi kiểm soát substitutionOption, dynamicSubstitutions và ký tự dollar, pipeline sẽ dễ dự đoán hơn. Kết hợp IAM tối thiểu, Secret Manager, builder image tin cậy và artifact có thể truy vết giúp Cloud Build trở thành nền tảng CI/CD an toàn và có thể vận hành lâu dài.
