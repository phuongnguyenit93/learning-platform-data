# Cloud Build service accounts và quyền tối thiểu

Cloud Build thực thi các bước kiểm thử, đóng gói và triển khai phần mềm trên Google Cloud. Mỗi build cần một danh tính để gọi API, đọc nguồn, đẩy image, ghi log hoặc cập nhật dịch vụ. Nếu build dùng tài khoản có quyền Owner hoặc Editor trên toàn project, bất kỳ lệnh nào chạy trong build cũng có thể sử dụng phạm vi quyền rộng đó. Một script build bị sửa, dependency độc hại hoặc pull request không đáng tin cậy vì thế có thể trở thành đường truy cập vào tài nguyên production.

Thiết kế an toàn cần xác định chính xác service account nào thực thi build, cấp quyền theo từng bước công việc và giới hạn phạm vi tài nguyên. Cloud Build hỗ trợ dùng service account mặc định hoặc service account do tổ chức chỉ định. Với pipeline quan trọng, nên tạo danh tính riêng cho build, tách khỏi danh tính runtime của ứng dụng và kiểm soát ai được phép yêu cầu Cloud Build sử dụng danh tính đó.

## 1. Phân biệt các danh tính trong Cloud Build

Một pipeline có thể liên quan đến nhiều principal. Chúng có trách nhiệm khác nhau và không nên gộp thành một tài khoản dùng chung:

| Danh tính | Vai trò | Quyền cần quan tâm |
| --- | --- | --- |
| Người hoặc hệ thống khởi chạy build | Gọi API tạo build hoặc kích hoạt trigger | Quyền tạo build/trigger và quyền **iam.serviceAccounts.actAs** trên service account được chỉ định |
| Cloud Build service agent | Danh tính Google quản lý để vận hành Cloud Build trong project | Role dịch vụ **roles/cloudbuild.serviceAgent**; thường được cấp khi bật API |
| Build service account | Danh tính mà các bước build sử dụng khi gọi Google Cloud API | Quyền đọc nguồn, đẩy image, ghi log hoặc triển khai đúng theo pipeline |
| Runtime service account | Danh tính mà ứng dụng sử dụng sau khi được triển khai | Quyền truy cập dữ liệu và dịch vụ cần cho hoạt động runtime |
| Service agent của dịch vụ đích | Danh tính Google quản lý để dịch vụ như Cloud Run thực hiện công việc nền | Quyền dịch vụ cần thiết, ví dụ đọc image từ Artifact Registry trong trường hợp liên project |

Cloud Build service agent thường có địa chỉ dạng **service-PROJECT_NUMBER@gcp-sa-cloudbuild.iam.gserviceaccount.com**. Đây là service agent do Google quản lý, không phải tài khoản để gắn vào các bước build.

Build service account mặc định có thể là legacy Cloud Build service account với địa chỉ **PROJECT_NUMBER@cloudbuild.gserviceaccount.com** hoặc Compute Engine default service account với địa chỉ **PROJECT_NUMBER-compute@developer.gserviceaccount.com**, tùy cấu hình và lịch sử của project. Không nên suy ra danh tính chỉ từ tên dịch vụ hoặc giả định mọi project dùng cùng một tài khoản. Hãy kiểm tra build thực tế trong Cloud Build hoặc cấu hình trigger để xác nhận trường serviceAccount.

Với pipeline cần quyền triển khai, nên dùng user-specified service account có tên thể hiện nhiệm vụ, ví dụ **cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com**. Việc chỉ định rõ danh tính giúp nhóm review policy, audit log và phạm vi quyền của pipeline dễ hơn.

## 2. Tách build service account khỏi runtime service account

Build service account chỉ cần quyền để tạo artifact và triển khai ứng dụng. Runtime service account cần quyền mà ứng dụng sử dụng khi xử lý yêu cầu. Hai danh tính có vòng đời và mức độ tin cậy khác nhau.

Ví dụ với một API đơn hàng:

- **cloud-build-deployer**: build image, đẩy image vào Artifact Registry và triển khai revision Cloud Run.
- **orders-runtime**: được gắn vào Cloud Run service để ứng dụng đọc secret và truy cập dữ liệu đơn hàng.
- **cloudbuild service agent**: thực hiện các hoạt động nền của dịch vụ Cloud Build.

Nếu dùng chung một service account cho build và runtime, pipeline có thể kế thừa quyền đọc dữ liệu sản xuất, còn ứng dụng runtime có thể sở hữu quyền đẩy image hoặc thay đổi dịch vụ. Điều này mở rộng phạm vi ảnh hưởng khi một trong hai môi trường bị xâm phạm.

Không tạo hoặc tải service account key JSON vào repository hay secret của pipeline chỉ để Cloud Build xác thực. Cloud Build có thể sử dụng danh tính gắn trực tiếp với build. Khi cần chạy pipeline từ hệ thống CI bên ngoài, ưu tiên cơ chế liên kết danh tính như Workload Identity Federation thay cho khóa dài hạn.

## 3. Chọn default service account hay user-specified service account

Default service account thuận tiện cho thử nghiệm ban đầu, nhưng quyền thực tế có thể thay đổi theo cấu hình project, chính sách tổ chức và cách tài khoản mặc định được cấp role. Tài khoản mặc định cũng có thể được nhiều build hoặc workload khác sử dụng, khiến việc giới hạn quyền theo từng pipeline khó hơn.

User-specified service account phù hợp khi:

- Build cần quyền triển khai vào production hoặc truy cập tài nguyên nhạy cảm.
- Nhiều repository có mức độ tin cậy khác nhau.
- Cần tách quyền build image, deploy ứng dụng và chạy test.
- Cần audit rõ pipeline nào đã sử dụng principal nào.
- Tổ chức muốn thu hồi quyền của một pipeline mà không ảnh hưởng các build khác.

Khi tạo service account riêng, đặt tên theo ứng dụng, môi trường và nhiệm vụ. Tránh tên chung như **terraform**, **ci** hoặc **build** nếu nhiều pipeline có quyền khác nhau. Tách service account theo ranh giới tin cậy, ví dụ build test từ pull request và build release từ nhánh được bảo vệ.

Trước khi chuyển từ default sang user-specified, hãy liệt kê mọi tài nguyên mà build đang truy cập. Việc đổi danh tính có thể khiến pipeline không còn quyền đọc source, đẩy image, ghi log hoặc triển khai. Cấp role dựa trên các thao tác cần thiết và kiểm tra từng bước trong môi trường thử nghiệm.

## 4. Tạo service account dành riêng cho build

Ví dụ tạo một service account chuyên triển khai ứng dụng trong project:

~~~bash
gcloud iam service-accounts create cloud-build-deployer \
  --project=PROJECT_ID \
  --display-name="Cloud Build deployer"
~~~

Địa chỉ service account sau khi tạo có dạng:

~~~text
cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com
~~~

Người hoặc hệ thống cấu hình build/trigger cần được phép gắn service account này. Quyền quan trọng là **iam.serviceAccounts.actAs**, thường được cấp qua role **roles/iam.serviceAccountUser** trên đúng service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --member="user:release-engineer@example.com" \
  --role="roles/iam.serviceAccountUser"
~~~

Ví dụ dùng một người vận hành làm principal cấu hình pipeline. Trong thực tế, thay principal bằng nhóm hoặc danh tính CI đáng tin cậy. Không cấp **roles/iam.serviceAccountUser** trên toàn project nếu người đó chỉ cần gắn một build service account cụ thể.

Quyền actAs cho phép principal yêu cầu dịch vụ sử dụng service account. Nó không tự cấp các quyền mà build service account có khi thực thi. Hai lớp quyền này phải được review riêng: người khởi chạy được phép chọn danh tính nào, và danh tính được chọn có thể làm gì.

## 5. Cấp quyền theo từng công việc của pipeline

Không có một bộ role duy nhất phù hợp với mọi build. Hãy lập danh sách thao tác thực tế, sau đó cấp role trên tài nguyên nhỏ nhất có thể.

| Công việc | Role có thể dùng | Phạm vi nên cấp |
| --- | --- | --- |
| Đẩy image lên Artifact Registry | **roles/artifactregistry.writer** | Repository chứa image |
| Ghi log vào Cloud Logging | **roles/logging.logWriter** | Project chạy build |
| Triển khai hoặc cập nhật Cloud Run service | **roles/run.developer** | Project hoặc phạm vi dịch vụ phù hợp |
| Gắn runtime service account vào Cloud Run | **roles/iam.serviceAccountUser** | Runtime service account cụ thể |
| Đọc một secret trong build | **roles/secretmanager.secretAccessor** | Secret cụ thể |
| Đọc object từ bucket đầu vào | **roles/storage.objectViewer** | Bucket cần đọc |
| Ghi object vào bucket đầu ra | Role Storage phù hợp với thao tác ghi | Bucket đích |

Các role trong bảng là lựa chọn tham khảo theo chức năng. Nếu pipeline chỉ cần một tập nhỏ quyền, tổ chức có thể xây dựng custom role để giới hạn chính xác permission. Hãy kiểm tra quyền của role tại thời điểm triển khai và thử bằng danh tính thực tế; role có thể chứa thêm quyền phụ trợ ngoài thao tác mà tên gọi gợi ý.

### Ví dụ cấp quyền đẩy image

Nếu repository Artifact Registry tên **app-images** ở region **asia-southeast1**, có thể cấp writer ngay tại repository:

~~~bash
gcloud artifacts repositories add-iam-policy-binding app-images \
  --location=asia-southeast1 \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
~~~

Build service account có thể đẩy image vào repository này. Nó không cần quyền quản trị tất cả repository hoặc xóa repository nếu pipeline chỉ thực hiện push.

### Ví dụ cấp quyền triển khai Cloud Run

Nếu pipeline tạo hoặc cập nhật Cloud Run service trong project, cấp role triển khai phù hợp ở phạm vi project chứa service:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.developer"
~~~

Để Cloud Run chạy ứng dụng bằng runtime service account, build service account còn cần quyền actAs trên runtime service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
~~~

Role Cloud Run Developer và quyền Service Account User có mục đích khác nhau. Role thứ nhất cho phép quản lý dịch vụ trong phạm vi được cấp; role thứ hai cho phép gắn danh tính runtime vào workload. Nếu pipeline chỉ cập nhật một dịch vụ đã tồn tại, hãy xem xét khả năng giới hạn quyền ở cấp dịch vụ hoặc custom role thay vì cấp rộng trên toàn project.

Nếu image nằm trong repository ở project khác, danh tính thực hiện pull image của Cloud Run có thể cần **roles/artifactregistry.reader** trên repository đó. Đây thường là quyền của Cloud Run service agent hoặc principal được dịch vụ chỉ định, không phải lý do để tự động cấp Reader cho build service account.

## 6. Chỉ định service account trong cloudbuild.yaml

Trường serviceAccount trong cấu hình build xác định danh tính mà build sử dụng. Ví dụ sau xây dựng image, đẩy lên Artifact Registry và triển khai lên Cloud Run:

~~~yaml
serviceAccount: projects/PROJECT_ID/serviceAccounts/cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com

steps:
  - id: Build image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA
      - .

  - id: Push image
    name: gcr.io/cloud-builders/docker
    args:
      - push
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA

  - id: Deploy Cloud Run
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - orders-api
      - --image
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA
      - --region
      - asia-southeast1
      - --service-account
      - orders-runtime@$PROJECT_ID.iam.gserviceaccount.com
      - --quiet

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA

options:
  logging: CLOUD_LOGGING_ONLY
~~~

Thay **PROJECT_ID**, repository, region và tên service account bằng giá trị của môi trường thực tế. Trong ví dụ, build service account đẩy image và triển khai; runtime service account được gắn cho ứng dụng Cloud Run. **CLOUD_LOGGING_ONLY** yêu cầu build ghi log vào Cloud Logging, vì vậy build service account cần quyền **roles/logging.logWriter** trên project.

Nếu sử dụng log bucket riêng, hãy cấu hình logsBucket và cấp quyền ghi object phù hợp trên đúng bucket cho build service account. Không cần cấp Storage Admin toàn project chỉ để ghi log. Nếu không chỉ định log destination phù hợp khi dùng user-specified service account, build có thể không khởi chạy hoặc không ghi được log như mong đợi.

Build được gọi từ CLI có thể sử dụng cấu hình này:

~~~bash
gcloud builds submit \
  --project=PROJECT_ID \
  --config=cloudbuild.yaml \
  .
~~~

Khi dùng trigger, cấu hình service account ở trigger hoặc build config theo workflow đang sử dụng. Người tạo hoặc cập nhật trigger phải có quyền **iam.serviceAccounts.actAs** trên service account được chọn. Hãy xác minh build thực tế sử dụng đúng principal sau khi tạo hoặc cập nhật trigger.

## 7. Phân quyền cho từng loại pipeline

Một tổ chức thường có nhiều loại pipeline với mức độ tin cậy khác nhau. Dùng một build service account có quyền production cho mọi nhánh sẽ làm tăng rủi ro từ pull request, dependency và script build.

| Pipeline | Quyền nên có | Quyền nên tránh |
| --- | --- | --- |
| Pull request từ nhánh hoặc fork chưa tin cậy | Chạy test, lint và tạo artifact tạm trong môi trường cô lập | Deploy production, đọc secret production, sửa IAM |
| Build từ nhánh chính đã bảo vệ | Đọc dependency, tạo image và đẩy vào repository staging | Quản trị project hoặc thay đổi policy bảo mật |
| Release production được phê duyệt | Đẩy artifact vào repository release và deploy dịch vụ được chỉ định | Truy cập dữ liệu nghiệp vụ runtime hoặc quản lý toàn bộ project |
| Pipeline quản trị hạ tầng | Quyền Terraform cần thiết trên phạm vi tài nguyên do pipeline quản lý | Dùng chung principal với pipeline build ứng dụng |

Có thể tạo các danh tính riêng như **cloud-build-test**, **cloud-build-staging** và **cloud-build-prod**. Chỉ trigger từ nhánh được bảo vệ hoặc quy trình release đã phê duyệt mới được dùng service account production. Nếu các bước có mức độ tin cậy khác nhau, tách thành các build riêng để mỗi build dùng một danh tính riêng.

Mọi step trong cùng một build thường sử dụng cùng build service account. Việc chia thành nhiều step trong một tệp YAML không tạo ranh giới IAM giữa các step. Nếu một step chạy script từ pull request hoặc dependency không đáng tin cậy, script đó có thể sử dụng quyền của build service account. Không đưa step không tin cậy vào build đang có quyền deploy production hoặc đọc secret nhạy cảm.

## 8. Quyền truy cập Secret Manager và tài nguyên phụ trợ

Chỉ cấp quyền đọc secret cho build khi chính bước build cần secret, ví dụ lấy token từ registry riêng hoặc truy cập hệ thống kiểm thử. Nếu secret chỉ được ứng dụng sử dụng khi chạy, hãy cấp quyền cho runtime service account thay vì build service account.

Ví dụ cấp quyền đọc một secret cụ thể:

~~~bash
gcloud secrets add-iam-policy-binding test-registry-token \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
~~~

Đối với bucket, chỉ cấp quyền object cần thiết. Build đọc artifact đầu vào có thể cần Storage Object Viewer trên bucket đó; build ghi kết quả cần quyền ghi phù hợp trên bucket đầu ra. Không cấp **roles/storage.admin** ở project chỉ vì pipeline cần tải một tệp hoặc ghi log.

Nếu build thực hiện thao tác mã hóa hoặc giải mã trực tiếp bằng Cloud KMS, cấp role sử dụng khóa trên đúng CryptoKey. Nếu dịch vụ đích dùng CMEK và service agent của dịch vụ thực hiện thao tác mật mã, cấp quyền cho service agent theo hướng dẫn của dịch vụ. Không cấp Cloud KMS Admin cho build service account chỉ để push image hoặc deploy ứng dụng.

## 9. Người khởi chạy build và quyền actAs

Quyền của người khởi chạy build khác với quyền của build service account. Người khởi chạy cần quyền tạo build hoặc quản lý trigger theo trách nhiệm của họ. Khi build dùng user-specified service account, người đó còn cần **iam.serviceAccounts.actAs** trên service account được gắn.

Điều này tạo ra một ranh giới quan trọng: người có quyền actAs một service account có thể yêu cầu dịch vụ chạy workload bằng danh tính đó. Vì vậy:

- Chỉ cấp actAs cho nhóm vận hành hoặc hệ thống CI đáng tin cậy.
- Cấp trên từng service account cần dùng, không cấp toàn project nếu không cần.
- Tách service account production khỏi service account test.
- Review quyền tạo và sửa trigger vì trigger có thể chạy tự động theo sự kiện repository.
- Kiểm soát ai có quyền sửa cloudbuild.yaml, builder image, substitutions và nguồn được trigger.

Không nên cho phép mọi contributor tự thay đổi trigger production hoặc chọn tùy ý service account có quyền cao. Quyền sửa cấu hình pipeline có thể tương đương quyền sử dụng danh tính mà pipeline được phép gắn.

## 10. Kiểm tra quyền và điều tra khi build thất bại

Khi build bị từ chối quyền, hãy xác định principal thực tế trong build details trước khi thêm role. Kiểm tra:

1. Build sử dụng default hay user-specified service account.
2. Principal bị từ chối là build service account, Cloud Build service agent, service agent của dịch vụ đích hay người khởi chạy.
3. Permission nào bị thiếu và tài nguyên nào đang được truy cập.
4. Role hiện có được gắn ở project, folder, organization, repository, bucket hay service account.
5. Có điều kiện IAM, organization policy, VPC Service Controls hoặc ràng buộc khác ảnh hưởng không.
6. Build log và Cloud Audit Logs có ghi lại method, principal, resource và lý do từ chối không.

Không giải quyết lỗi bằng cách cấp Owner hoặc Editor ngay lập tức. Tìm permission cụ thể bị thiếu, xác định principal cần permission đó và cấp role hẹp nhất ở phạm vi tài nguyên phù hợp. Sau đó chạy lại pipeline và xác nhận build hoàn thành đúng các thao tác cần thiết.

Nếu build không ghi được log khi dùng user-specified service account, kiểm tra logging option, log bucket và quyền ghi log. Nếu push image thất bại, kiểm tra Artifact Registry repository, location và role Writer. Nếu Cloud Run từ chối deploy, kiểm tra quyền quản lý service và quyền actAs trên runtime service account. Mỗi lỗi thuộc một lớp quyền khác nhau.

## 11. Kiểm soát và rà soát định kỳ

Service account của build là một phần của chuỗi cung ứng phần mềm. Khi quyền của nó bị lạm dụng, kẻ tấn công có thể thay đổi artifact, triển khai mã độc hoặc truy cập tài nguyên trong project. Hãy duy trì các biện pháp sau:

- Dùng service account riêng cho từng pipeline hoặc ranh giới tin cậy.
- Không tạo key dài hạn nếu có thể dùng danh tính gắn với build hoặc Workload Identity Federation.
- Pin builder image và dependency quan trọng theo phiên bản hoặc digest khi phù hợp.
- Bảo vệ nhánh, trigger, cấu hình build và quy trình phê duyệt release.
- Bật và rà soát Cloud Audit Logs cho thay đổi IAM, service account, trigger và tài nguyên triển khai.
- Kiểm tra role binding và quyền actAs định kỳ; thu hồi binding không còn cần thiết.
- Theo dõi ai có thể sửa repository, cấu hình trigger và image builder.
- Giới hạn quyền truy cập build logs vì log có thể vô tình chứa thông tin nhạy cảm.
- Xác minh artifact được tạo từ nguồn và build đáng tin cậy trước khi triển khai production.

Khi cần điều tra, đối chiếu build ID, source revision, trigger, build service account, artifact digest và thời điểm deploy. Những dữ liệu này giúp liên kết thay đổi trong repository với artifact và dịch vụ đang chạy.

## 12. Checklist thiết kế Cloud Build least privilege

Trước khi đưa pipeline vào production, hãy xác nhận:

- Build service account được chỉ định rõ ràng và không dùng chung với runtime service account.
- Đã xác định đúng Cloud Build service agent và không nhầm nó với build execution identity.
- Người khởi chạy hoặc người quản lý trigger chỉ có quyền tạo build và actAs trên service account cần thiết.
- Quyền đẩy image được giới hạn ở Artifact Registry repository đích.
- Quyền deploy được giới hạn theo project hoặc dịch vụ cần quản lý.
- Quyền actAs runtime service account chỉ được cấp trên danh tính runtime cụ thể.
- Secret và bucket chỉ được truy cập khi build thực sự cần.
- Logging option và log destination phù hợp với user-specified service account.
- Pipeline từ pull request không đáng tin cậy không có quyền production.
- Các step có mức độ tin cậy khác nhau được tách build khi cần ranh giới IAM riêng.
- Cloud Audit Logs, build logs và artifact metadata đủ để truy vết hoạt động.
- Quy trình rà soát và thu hồi IAM binding được thực hiện định kỳ.

Quyền tối thiểu cho Cloud Build bắt đầu từ việc chọn đúng danh tính cho từng công việc. Khi người khởi chạy, service agent, build service account và runtime service account được phân biệt rõ, mỗi principal chỉ nhận quyền trên tài nguyên mà nó cần. Pipeline khi đó có thể build và deploy hiệu quả mà giảm đáng kể phạm vi ảnh hưởng nếu một bước thực thi hoặc credential bị xâm phạm.
