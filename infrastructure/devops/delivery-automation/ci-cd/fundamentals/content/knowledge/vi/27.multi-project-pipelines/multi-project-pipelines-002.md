# Nhận diện ảnh hưởng của mã và thư viện dùng chung

Trong một hệ thống nhiều dự án, một thay đổi nhỏ ở thư viện dùng chung có thể làm nhiều dịch vụ phải biên dịch, kiểm thử hoặc phát hành lại. Nếu pipeline chỉ chạy kiểm thử của thư viện vừa sửa, lỗi tương thích có thể lọt sang dự án sử dụng thư viện đó. Ngược lại, nếu mọi thay đổi đều kích hoạt toàn bộ hệ thống, thời gian phản hồi sẽ tăng và nhóm phát triển khó nhận ra phạm vi thực sự của một thay đổi.

Phân tích ảnh hưởng giúp pipeline trả lời ba câu hỏi trước khi chọn công việc cần chạy:

- Những dự án nào trực tiếp chứa mã hoặc cấu hình vừa thay đổi?
- Những dự án nào phụ thuộc trực tiếp hoặc gián tiếp vào chúng?
- Mỗi dự án bị ảnh hưởng cần mức xác minh nào trước khi được phép tạo artifact hoặc phát hành?

Mục tiêu là xác định phạm vi kiểm thử có căn cứ từ quan hệ phụ thuộc, giữ được phản hồi nhanh và vẫn bảo vệ các hợp đồng giữa những dự án.

## 1. Vì sao mã dùng chung làm thay đổi phạm vi CI/CD?

Một dự án thường chứa nhiều loại thành phần: ứng dụng có thể triển khai độc lập, thư viện nội bộ, mô hình dữ liệu, schema API, plugin build, cấu hình kiểm thử và các quy ước pipeline. Một thành phần dùng chung có thể được nhiều dự án sử dụng.

Ví dụ, thư viện mô hình đơn hàng được dùng bởi API nhận đơn và worker lập hóa đơn. Khi thư viện đổi tên trường, cả hai ứng dụng có thể không biên dịch được. Khi thư viện vẫn biên dịch nhưng thay đổi cách diễn giải trạng thái đơn hàng, lỗi có thể chỉ xuất hiện trong kiểm thử tích hợp hoặc khi chạy nghiệp vụ. Vì vậy, việc thư viện tự vượt qua unit test chưa chứng minh các dự án tiêu thụ nó vẫn hoạt động đúng.

Phạm vi ảnh hưởng không chỉ nằm ở thư mục chứa file đã sửa. Nó được quyết định bởi quan hệ giữa thành phần thay đổi và các thành phần sử dụng nó.

## 2. Mô hình hóa quan hệ phụ thuộc

### 2.1. Phân biệt dự án, thành phần và artifact

Trong phân tích CI/CD, cần xác định ranh giới mà pipeline có thể xây dựng và xác minh:

- **Dự án (project):** đơn vị có thể được chọn để build, test, đóng gói hoặc triển khai, chẳng hạn một ứng dụng Gradle hoặc một service.
- **Thành phần dùng chung (shared component):** thư viện, schema, plugin, cấu hình hoặc bộ kiểm thử được nhiều dự án sử dụng.
- **Artifact:** đầu ra có thể định danh và phân phối, chẳng hạn JAR, image container hoặc package thư viện.

Một thư viện có thể là một project trong monorepo và tạo ra một JAR. Một ứng dụng có thể phụ thuộc vào project thư viện khi build, sau đó đóng gói JAR đó vào artifact ứng dụng. Khi phân tích ảnh hưởng, phải giữ được mối liên hệ từ source code đến project tiêu thụ và artifact cuối cùng.

### 2.2. Đọc đúng chiều của cạnh phụ thuộc

Có hai cách biểu diễn đồ thị phổ biến:

- Cạnh từ dự án sử dụng đến dự án được sử dụng: ứng dụng → thư viện.
- Cạnh từ thư viện đến dự án sử dụng nó: thư viện → ứng dụng.

Cả hai đều hợp lệ, nhưng pipeline phải thống nhất một quy ước. Trong bài này, sơ đồ dùng chiều thứ hai để luồng ảnh hưởng đi theo chiều mũi tên: khi thư viện thay đổi, ta đi theo các cạnh đi ra để tìm những dự án tiêu thụ.

Ví dụ:

~~~mermaid
flowchart TD
    contracts["Thư viện hợp đồng đơn hàng"]
    auth["SDK xác thực"]
    logging["Thư viện ghi log"]
    orders["Order API"]
    invoices["Invoice Worker"]

    contracts --> orders
    contracts --> invoices
    auth --> orders
    logging --> auth
    logging --> invoices
~~~

Mũi tên biểu thị “được sử dụng bởi”. Order API phụ thuộc trực tiếp vào hợp đồng đơn hàng và SDK xác thực. SDK xác thực lại sử dụng thư viện ghi log. Vì vậy, khi thư viện ghi log thay đổi, Order API vẫn có thể bị ảnh hưởng dù nó không khai báo phụ thuộc trực tiếp vào thư viện đó.

### 2.3. Nhận diện phụ thuộc trực tiếp và gián tiếp

- **Phụ thuộc trực tiếp:** dự án khai báo sử dụng một thư viện hoặc project khác.
- **Phụ thuộc gián tiếp:** dự án sử dụng một thành phần vốn phụ thuộc vào thành phần vừa thay đổi.
- **Phụ thuộc theo build:** cần thiết để biên dịch, đóng gói hoặc sinh mã.
- **Phụ thuộc lúc chạy:** cần thiết khi ứng dụng hoạt động, kể cả khi không xuất hiện trong compile classpath.
- **Phụ thuộc kiểm thử:** test fixture, bộ dữ liệu, mock server hoặc thư viện kiểm thử dùng chung.
- **Phụ thuộc phát hành:** image nền, manifest, chart triển khai, pipeline template hoặc cấu hình môi trường ảnh hưởng đến artifact hay cách triển khai.

Đồ thị do build tool cung cấp thường mô tả tốt quan hệ build, nhưng có thể thiếu quan hệ lúc chạy. Ví dụ, ứng dụng tìm implementation qua reflection, service discovery, tên class trong cấu hình hoặc plugin được nạp động. Những quan hệ này cần được khai báo bổ sung hoặc được bảo vệ bằng kiểm thử tích hợp.

Không nên coi mọi file nằm trong cùng một thư mục là có cùng phạm vi ảnh hưởng. Ranh giới project và dependency metadata mới là cơ sở để chọn công việc CI.

## 3. Từ file thay đổi đến project bị ảnh hưởng

Pipeline thường bắt đầu bằng danh sách file khác biệt giữa commit hiện tại và commit gốc của nhánh đích. Từ danh sách này, nó xác định project sở hữu file, sau đó mở rộng phạm vi theo đồ thị phụ thuộc.

### 3.1. Chọn đúng khoảng so sánh

Với pull request hoặc merge request, cần so sánh commit đang kiểm tra với merge base hoặc commit đích phù hợp. So sánh nhầm với một commit cũ có thể đưa vào danh sách những file không thuộc thay đổi hiện tại hoặc bỏ sót file đã thay đổi.

Phân tích cũng phải xử lý được file mới, file bị xóa và file được đổi tên. Nếu chỉ lấy danh sách file còn tồn tại ở commit mới, một project hoặc cấu hình bị xóa có thể biến mất khỏi kết quả phân tích.

### 3.2. Ánh xạ file vào project

Mỗi đường dẫn cần được gán cho project hoặc nhóm cấu hình sở hữu nó. Có thể dùng cấu trúc thư mục, khai báo trong build tool hoặc một tệp metadata do nhóm duy trì.

Ví dụ:

| Đường dẫn thay đổi | Project hoặc phạm vi sở hữu |
|---|---|
| **services/order-api/src/** | Order API |
| **services/invoice-worker/src/** | Invoice Worker |
| **libraries/order-contract/src/** | Thư viện hợp đồng đơn hàng |
| **build-logic/** | Các project áp dụng build logic |
| **gradle/libs.versions.toml** | Các project dùng alias hoặc version bị thay đổi |
| **.ci/templates/java.yml** | Các pipeline sử dụng template Java |

Bảng ánh xạ cần phản ánh cấu trúc thực tế của repository. Không nên suy ra mọi thay đổi trong thư mục gốc đều ảnh hưởng tất cả project nếu cấu hình có phạm vi hẹp; cũng không được bỏ qua một file gốc thực sự được mọi project sử dụng.

### 3.3. Mở rộng qua các project tiêu thụ

Giả sử tập project chứa thay đổi là **C**. Với quy ước cạnh từ dependency đến consumer, tập project cần xem xét là:

~~~text
Affected(C) = C ∪ tất cả consumer có thể đi tới từ C
~~~

Với một project thư viện, việc mở rộng phải đi qua cả consumer trực tiếp và consumer gián tiếp. Nếu thư viện A được B sử dụng, còn B được ứng dụng C sử dụng, thay đổi ở A có thể tác động đến cả B và C.

Kết quả phân tích nên lưu lý do một project được chọn, ví dụ “được Order API sử dụng trực tiếp” hoặc “phụ thuộc gián tiếp qua SDK xác thực”. Lý do này giúp người review hiểu vì sao pipeline chạy một nhóm kiểm thử và giúp điều tra khi kết quả phân tích sai.

## 4. Phân loại thay đổi để chọn mức xác minh

Đồ thị cho biết những project có khả năng bị ảnh hưởng. Loại thay đổi và mức độ rủi ro quyết định cần xác minh sâu đến đâu.

| Loại thay đổi | Phạm vi cần xem xét | Xác minh phù hợp |
|---|---|---|
| Sửa logic nội bộ của ứng dụng | Ứng dụng thay đổi và các luồng tích hợp liên quan | Unit test, kiểm thử tích hợp theo luồng |
| Sửa logic thư viện dùng chung | Thư viện và các consumer trực tiếp, gián tiếp | Test của thư viện, compile và test consumer |
| Đổi API công khai, kiểu dữ liệu hoặc schema | Tất cả consumer của hợp đồng | Kiểm tra tương thích, contract test và integration test |
| Đổi dependency hoặc version catalog | Các project có resolved dependency thay đổi | Build, test và quét bảo mật dependency |
| Đổi plugin, convention hoặc build logic chung | Các project áp dụng logic đó | Build và test các project thuộc phạm vi áp dụng |
| Đổi test fixture hoặc test utility dùng chung | Các project sử dụng fixture hoặc utility | Chạy test của các consumer liên quan |
| Đổi image nền hoặc cấu hình triển khai chung | Các image hoặc dịch vụ kế thừa cấu hình | Build image, kiểm tra cấu hình và smoke test phù hợp |

Một thay đổi được gọi là “nội bộ” chỉ khi có căn cứ rằng nó không làm đổi hành vi quan sát được của consumer. Thay đổi thuật toán bên trong vẫn có thể làm thay đổi kết quả, thời gian xử lý, thứ tự sự kiện hoặc cách xử lý lỗi. Vì vậy, khi chưa có hợp đồng và kiểm thử đủ mạnh để loại trừ ảnh hưởng, nên giữ consumer trong phạm vi xác minh.

Có thể tổ chức kiểm thử theo nhiều tầng:

1. **Build và unit test:** xác nhận project thay đổi vẫn biên dịch và kiểm thử logic riêng.
2. **Kiểm tra tương thích:** xác nhận consumer có thể biên dịch hoặc trao đổi dữ liệu với phiên bản hợp đồng mới.
3. **Contract và integration test:** xác nhận hai phía thống nhất về request, response, schema, sự kiện và hành vi.
4. **End-to-end hoặc smoke test:** xác nhận luồng nghiệp vụ quan trọng vẫn hoạt động khi các thành phần được ghép lại.

Không phải thay đổi nào cũng cần chạy toàn bộ tầng kiểm thử. Tuy nhiên, việc bỏ một tầng cần dựa trên phân loại thay đổi, dependency graph và bằng chứng kiểm thử hiện có.

## 5. Ví dụ với monorepo Java và Gradle

Giả sử repository có các project sau:

~~~text
root
├── applications
│   ├── order-api
│   └── invoice-worker
└── libraries
    ├── order-contract
    ├── auth-sdk
    └── common-logging
~~~

Order API và Invoice Worker cùng sử dụng thư viện hợp đồng đơn hàng. Order API sử dụng thêm SDK xác thực. SDK xác thực và Invoice Worker cùng sử dụng thư viện ghi log.

Trong build script của Order API, quan hệ project có thể được khai báo như sau:

~~~kotlin
dependencies {
    implementation(project(":libraries:order-contract"))
    implementation(project(":libraries:auth-sdk"))
}
~~~

Trong build script của Invoice Worker:

~~~kotlin
dependencies {
    implementation(project(":libraries:order-contract"))
    implementation(project(":libraries:common-logging"))
}
~~~

SDK xác thực khai báo phụ thuộc vào thư viện ghi log:

~~~kotlin
dependencies {
    implementation(project(":libraries:common-logging"))
}
~~~

### 5.1. Khi thư viện hợp đồng thay đổi

Nếu thay đổi nằm trong **libraries/order-contract**, các project cần xem xét gồm:

- **libraries:order-contract:** project chứa thay đổi.
- **applications:order-api:** consumer trực tiếp.
- **applications:invoice-worker:** consumer trực tiếp.

Pipeline cần build và test thư viện, sau đó xác minh cả hai ứng dụng. Nếu thay đổi schema hoặc hành vi của hợp đồng, contract test và integration test của hai consumer có giá trị cao hơn việc chỉ kiểm tra biên dịch.

### 5.2. Khi thư viện ghi log thay đổi

Nếu thay đổi nằm trong **libraries/common-logging**, phạm vi mở rộng gồm:

- **libraries/common-logging:** project chứa thay đổi.
- **libraries:auth-sdk:** consumer trực tiếp.
- **applications:invoice-worker:** consumer trực tiếp.
- **applications:order-api:** consumer gián tiếp qua SDK xác thực.

Ví dụ lệnh Gradle minh họa cho việc chạy test trong phạm vi này:

~~~bash
./gradlew \
  :libraries:common-logging:test \
  :libraries:auth-sdk:test \
  :applications:invoice-worker:test \
  :applications:order-api:test
~~~

Tên project và task phải khớp với cấu hình thực tế của repository. Gradle có thể tự xây dựng các project dependency cần thiết để chạy task của consumer, nhưng việc đó không đồng nghĩa task test của mọi thư viện phụ thuộc đều tự được gọi. Nếu cần xác nhận unit test của thư viện, hãy đưa task test của thư viện vào danh sách rõ ràng.

Khi cần một lần xác minh toàn repository, có thể dùng task tổng hợp phù hợp với build. Tuy nhiên, pipeline theo thay đổi nên tạo danh sách task từ dependency graph để tránh bỏ sót consumer và tránh chạy những project không liên quan.

## 6. Khi thư viện được chia sẻ qua nhiều repository

Trong mô hình nhiều repository, source của thư viện và source của ứng dụng nằm ở các nơi khác nhau. Thay đổi trong repository thư viện chưa chắc lập tức làm thay đổi ứng dụng, vì ứng dụng có thể đang khóa ở một phiên bản artifact đã phát hành.

Ví dụ:

1. Shared SDK phát hành artifact phiên bản **2.4.0**.
2. Order API khai báo sử dụng **2.4.0**.
3. Shared SDK được sửa và phát hành **2.5.0**.
4. Order API chỉ chịu tác động từ phiên bản mới sau khi cập nhật dependency lên **2.5.0** và chạy pipeline của chính Order API.

Pipeline của thư viện cần xác minh thư viện, kiểm tra tương thích và tạo artifact có version rõ ràng. Pipeline của consumer cần xác minh thay đổi dependency, chạy test với artifact mới và lưu lại version đã được kiểm tra.

Với thay đổi phá vỡ tương thích, cần có chiến lược versioning và nâng cấp consumer có kiểm soát. Không nên dùng version trôi nổi như **latest** để pipeline có thể vô tình lấy một artifact khác nhau giữa hai lần chạy. Artifact bất biến và version được khóa giúp tái hiện kết quả build.

Trong hệ thống nhiều repository, có thể duy trì dependency catalog hoặc manifest thể hiện consumer nào đang sử dụng artifact nào. Catalog phải được cập nhật cùng quy trình nâng version; nếu không, phân tích ảnh hưởng liên repository sẽ thiếu dữ liệu.

## 7. Tổ chức bước phân tích ảnh hưởng trong pipeline

Một luồng CI có thể tách riêng bước phân tích để tạo danh sách project cần xác minh. Các bước sau dùng kết quả đó để tạo ma trận build/test hoặc chọn job tương ứng.

~~~mermaid
flowchart TD
    A["Commit hoặc pull request"] --> B["Tìm base commit và danh sách file thay đổi"]
    B --> C["Ánh xạ file vào project và cấu hình"]
    C --> D["Phân loại thay đổi"]
    D --> E["Mở rộng theo dependency graph"]
    E --> F{"Đồ thị và ánh xạ đầy đủ?"}
    F -->|Có| G["Tạo danh sách project bị ảnh hưởng"]
    F -->|Không| H["Chọn phạm vi an toàn: toàn bộ project liên quan"]
    G --> I["Sinh ma trận build và test"]
    H --> I
    I --> J["Kiểm tra chất lượng"]
    J --> K["Đủ điều kiện tạo artifact hoặc phát hành"]
~~~

Logic khái quát có thể biểu diễn như sau:

~~~text
base_commit = find_merge_base(target_branch, current_commit)
changed_files = diff(base_commit, current_commit)

changed_projects = map_files_to_projects(changed_files)
changed_scopes = classify_shared_configuration(changed_files)

if dependency_map_is_incomplete(changed_projects, changed_scopes):
    affected_projects = all_projects_in_safe_scope
else:
    affected_projects = changed_projects
    affected_projects += transitive_consumers(changed_projects)
    affected_projects += projects_using(changed_scopes)

validation_plan = select_tests(affected_projects, change_types)
run(validation_plan)
~~~

Bước phân tích nên xuất kết quả có cấu trúc để các job sau sử dụng. Ví dụ:

~~~json
{
  "changedProjects": [
    "libraries:order-contract"
  ],
  "affectedProjects": [
    "libraries:order-contract",
    "applications:order-api",
    "applications:invoice-worker"
  ],
  "reasons": {
    "applications:order-api": [
      "direct consumer of libraries:order-contract"
    ],
    "applications:invoice-worker": [
      "direct consumer of libraries:order-contract"
    ]
  }
}
~~~

Đầu ra cần ổn định và có thể lưu cùng log của pipeline. Khi một job bị bỏ qua, người review vẫn có thể xem project nào đã được chọn, project nào không được chọn và lý do. Nếu dùng ma trận job, mỗi phần tử nên nhận project và tập task đã được phân tích thay vì tự suy luận lại từ một bộ path filter khác.

## 8. Những thay đổi có phạm vi rộng cần xử lý riêng

Không phải mọi ảnh hưởng đều bắt đầu từ file source trong một project. Một số thay đổi ở cấp repository có thể làm thay đổi cách nhiều project được build hoặc triển khai.

- **Build logic chung:** thay đổi convention plugin, script dùng chung hoặc cấu hình compiler có thể ảnh hưởng mọi project áp dụng chúng.
- **Dependency catalog và lockfile:** version được cập nhật có thể làm thay đổi classpath, runtime behavior hoặc mức độ rủi ro bảo mật của nhiều consumer.
- **Schema và mã sinh tự động:** thay đổi schema có thể cần chạy generator trước khi biên dịch consumer. Cần xác định cả project tạo mã và project sử dụng mã.
- **Dockerfile nền hoặc image nền:** thay đổi image có thể ảnh hưởng nhiều ứng dụng dù source không đổi.
- **Pipeline template và action dùng chung:** thay đổi có thể tác động đến mọi pipeline đang gọi template hoặc action đó.
- **Cấu hình triển khai:** thay đổi chart, manifest hoặc biến cấu hình chung có thể ảnh hưởng nhiều môi trường hoặc dịch vụ.

Đối với các phạm vi này, cần có ánh xạ từ cấu hình dùng chung đến những project hoặc pipeline sử dụng nó. Nếu không thể xác định chính xác, hãy mở rộng đến toàn bộ phạm vi có khả năng bị ảnh hưởng. Một lần chạy dư kiểm thử thường dễ xử lý hơn việc bỏ sót một consumer quan trọng.

## 9. Những lỗi thường gặp khi chọn phạm vi pipeline

| Cách làm sai | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ chạy test của thư viện vừa sửa | Lỗi tương thích ở ứng dụng tiêu thụ bị bỏ sót | Mở rộng đến consumer trực tiếp và gián tiếp |
| Chỉ dùng path filter | Không thấy quan hệ phụ thuộc xuyên project | Kết hợp ánh xạ file với dependency graph |
| Chỉ xét phụ thuộc trực tiếp | Consumer ở nhiều tầng bị bỏ qua | Duyệt toàn bộ consumer có thể tiếp cận |
| Coi build thành công là đủ | Hành vi sai có thể chỉ xuất hiện lúc chạy | Chạy contract, integration hoặc smoke test theo rủi ro |
| Bỏ qua build logic và cấu hình gốc | Nhiều project có thể dùng cấu hình mới mà không được kiểm tra | Theo dõi phạm vi áp dụng của cấu hình chung |
| Đánh dấu project không bị ảnh hưởng khi thiếu metadata | Pipeline có thể bỏ qua công việc cần thiết | Dùng phạm vi dự phòng an toàn và bổ sung metadata |
| Tạo lại artifact ở từng môi trường | Các môi trường có thể chạy nội dung khác nhau | Gắn version hoặc digest và promote cùng artifact đã kiểm tra |

Một hệ thống chọn phạm vi tốt cần cân bằng độ chính xác và độ an toàn. Chọn quá rộng làm CI chậm và tốn tài nguyên; chọn quá hẹp làm mất niềm tin vào kết quả kiểm thử. Có thể tối ưu dần sau khi dependency graph, hợp đồng và kiểm thử đã đủ tin cậy.

## 10. Kiểm tra kết quả phân tích trước khi cho phép phát hành

Trước khi pipeline sử dụng kết quả impact analysis làm cổng chất lượng, hãy xác nhận:

- Mỗi file thay đổi được gán vào đúng project hoặc phạm vi cấu hình.
- Dependency graph bao gồm quan hệ trực tiếp, gián tiếp và các phụ thuộc quan trọng lúc chạy.
- Thay đổi ở thư viện chung đã mở rộng đến consumer ở mọi tầng.
- Thay đổi API, schema, dependency, build logic và cấu hình phát hành được phân loại đúng.
- Danh sách task bao gồm test của project cần xác minh, không chỉ các task biên dịch phụ thuộc.
- Khi thiếu dữ liệu, pipeline mở rộng phạm vi theo chính sách dự phòng đã định.
- Log pipeline lưu base commit, file thay đổi, dependency graph hoặc phiên bản metadata, danh sách project và lý do lựa chọn.
- Artifact chỉ được tạo hoặc phát hành sau khi các cổng chất lượng áp dụng cho toàn bộ phạm vi bị ảnh hưởng đã đạt.

Khi review một thay đổi trong repository nhiều dự án, hãy lần theo đường đi từ file thay đổi đến project sở hữu, từ project đó đến các consumer, rồi đến artifact và luồng kiểm thử cần thiết. Nếu mỗi bước đều có dữ liệu và lý do rõ ràng, pipeline có thể chọn đúng phạm vi xác minh và cung cấp bằng chứng đủ để quyết định tiếp tục phát hành.
