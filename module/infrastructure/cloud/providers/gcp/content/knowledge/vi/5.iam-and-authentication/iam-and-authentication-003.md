# Quyền hiệu lực và kế thừa IAM policy

Khi một lập trình viên mở Google Cloud Console và thấy mình có quyền xem project nhưng không thể triển khai Cloud Run, câu hỏi thường gặp là: **“Tại sao tôi có role ở Folder mà vẫn bị từ chối?”** Trường hợp ngược lại còn nguy hiểm hơn: nhóm đã gỡ một quyền trong project production, nhưng người dùng vẫn thao tác được vì quyền đó được cấp từ Organization hoặc Folder cha.

Đây là lý do cần hiểu **quyền hiệu lực (effective permissions)** và **kế thừa IAM policy (policy inheritance)**. Trong Google Cloud, IAM không chỉ kiểm tra policy gắn trực tiếp vào tài nguyên đích: hệ thống còn xét các chính sách ở những cấp tổ tiên và các cơ chế giới hạn quyền khác.

Bài này thuộc chương **IAM và xác thực** của học phần **CLOUD_PROVIDERS_GCP**. Cách tính quyền hiệu lực xuất hiện trong mọi công việc của module: phân tách project, dùng VPC, triển khai Compute Engine, GKE, Cloud Run, truy cập Cloud Storage/cơ sở dữ liệu, tự động hóa phát hành và kiểm soát bảo mật, chi phí, độ tin cậy.

Sau bài học, bạn có thể:

- Phân biệt **principal**, **role**, **permission**, **policy** và **binding**.
- Xác định tài nguyên nào thừa hưởng chính sách Allow từ Organization, Folder và Project.
- Giải thích vì sao việc xóa một binding tại project không thu hồi quyền được cấp từ cấp cha.
- Xác định ảnh hưởng của **IAM Deny**, **IAM Conditions** và **Principal Access Boundary**.
- Đánh giá một yêu cầu truy cập cụ thể theo principal, permission, tài nguyên và ngữ cảnh.
- Kiểm chứng quyền bằng Console, `gcloud` và **Policy Troubleshooter**.

## 1. Những khái niệm cần phân biệt

Google Cloud IAM quyết định **ai có thể làm hành động gì trên tài nguyên nào, trong điều kiện nào**.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Principal** | Danh tính được kiểm tra quyền | User, Google Group, service account, workforce/workload identity |
| **Permission** | Một hành động cụ thể mà API yêu cầu | `resourcemanager.projects.get`, `run.services.update` |
| **Role** | Tập hợp các permission được quản lý cùng nhau | `roles/viewer`, `roles/run.admin` |
| **Allow policy** | Chính sách chứa các role binding cấp quyền cho principal | Policy trên project `orders-dev` |
| **Role binding** | Liên kết role với một hoặc nhiều principal, tùy chọn có điều kiện | Nhóm `devs@example.com` nhận `roles/viewer` |
| **IAM Condition** | Biểu thức giới hạn thời điểm/ngữ cảnh binding được áp dụng | Chỉ có hiệu lực đến một thời điểm cụ thể |
| **Deny policy** | Chính sách từ chối permission cho principal nhất định | Không cho nhóm dùng một permission nguy hiểm |
| **Principal Access Boundary (PAB)** | Chính sách giới hạn tập tài nguyên mà một tập principal đủ điều kiện truy cập | Chỉ được truy cập tài nguyên trong phạm vi được xác định |

**Role không tương đương với permission.** Một role gồm nhiều permission; để biết có thể thực hiện một thao tác cụ thể hay không, cần tìm permission mà API thực sự kiểm tra. Tên role gợi ý mục đích sử dụng, nhưng không đủ để kết luận mọi khả năng truy cập.

**Principal không nhất thiết là một người.** Ứng dụng chạy trên Cloud Run, VM hoặc pipeline CI/CD có thể dùng service account; khi đó quyền của danh tính workload khác quyền của lập trình viên triển khai ứng dụng.

**Authentication khác Authorization:** xác thực cho biết danh tính nào đang gửi yêu cầu; IAM authorization quyết định danh tính đó được phép làm gì. Đăng nhập thành công không có nghĩa được tự động cấp quyền trên project.

## 2. Chính sách IAM gắn với cây tài nguyên

Một hệ thống công ty có thể tổ chức như sau:

~~~text
Organization: example.com
├── Folder: engineering
│   ├── Folder: nonproduction
│   │   ├── Project: orders-dev
│   │   └── Project: orders-staging
│   └── Folder: production
│       └── Project: orders-prod
│           ├── Cloud Run service: orders-api
│           └── Cloud Storage bucket: orders-exports
└── Folder: security
    └── Project: security-logs
~~~

Các tài nguyên ở cấp thấp có **chuỗi tổ tiên (ancestry)**:

~~~text
orders-api
→ orders-prod
→ production
→ engineering
→ example.com
~~~

Khi đánh giá quyền trên `orders-api`, IAM xem xét những Allow policy áp dụng trực tiếp tại tài nguyên (nếu dịch vụ hỗ trợ) và tại các cấp tổ tiên. IAM không lấy policy từ `orders-dev` hay `security-logs` vì hai project đó không phải tổ tiên của `orders-api`.

**Điểm then chốt:** đặt binding tại Organization sẽ ảnh hưởng phạm vi rộng; đặt tại Folder sẽ ảnh hưởng tài nguyên bên trong Folder; đặt tại Project chỉ ảnh hưởng project và các tài nguyên thuộc project đó; binding trực tiếp trên tài nguyên dịch vụ (nếu hỗ trợ) thường có phạm vi hẹp hơn.

Không phải dịch vụ nào cũng hỗ trợ gắn IAM policy trực tiếp ở mọi cấp tài nguyên con. Vì vậy, phải kiểm tra tài liệu IAM của Compute Engine, GKE, Cloud Run, Cloud Storage hoặc dịch vụ cụ thể trước khi thiết kế phạm vi binding.

## 3. Kế thừa Allow policy hoạt động ra sao?

**Allow policy có tính kế thừa theo chiều từ trên xuống.** Một binding cấp ở Organization, Folder hoặc Project áp dụng cho tài nguyên đó và các tài nguyên con trong phạm vi hỗ trợ. Các binding được kế thừa và các binding gắn trực tiếp đều được xét khi tính quyền.

Ta có thể hình dung **effective allow policy** của tài nguyên là hợp của:

~~~text
Allow policy trên tài nguyên
+ Allow policy trên project cha
+ Allow policy trên folder cha và những folder tổ tiên
+ Allow policy trên organization
---------------------------------------------------
= Effective allow policy (các binding có thể cấp quyền)
~~~

Đây là **hợp các cơ hội được cấp quyền**, không phải phép giao. Nếu một binding hợp lệ ở cấp cha cấp permission đang xét, một Allow policy hẹp hơn tại project không thể tự “phủ định” binding đó. Mỗi binding được đánh giá độc lập, gồm cả điều kiện gắn trên binding.

### Ví dụ cấp quyền ở ba vị trí

Giả sử hệ thống có các Allow binding sau:

| Cấp | Principal | Role | Ý nghĩa |
|---|---|---|---|
| Organization `example.com` | `group:auditors@example.com` | `roles/viewer` | Nhóm kiểm toán nhận các quyền xem thuộc role trên nhiều project |
| Folder `nonproduction` | `group:developers@example.com` | `roles/editor` | Nhóm phát triển nhận quyền tương đối rộng trong dev/staging |
| Folder `production` | `group:developers@example.com` | `roles/viewer` | Trong production, developer chủ yếu có quyền xem tương ứng role |
| Project `orders-prod` | `serviceAccount:deploy-orders@ci-tools.iam.gserviceaccount.com` | `roles/run.admin` | Danh tính triển khai có quyền quản lý Cloud Run trong phạm vi project |

*Lưu ý:* `roles/editor` là **basic role rộng**, dùng ở đây để minh họa rõ sự khác nhau giữa các cấp; hệ thống thực tế nên ưu tiên predefined role cụ thể với quyền tối thiểu.

Nếu **Lan** thuộc `developers@example.com`, ta có:

| Truy cập | Binding liên quan | Kết luận ở tầng Allow |
|---|---|---|
| Lan thao tác trên `orders-dev` | `roles/editor` kế thừa từ `nonproduction` | Có các permission của Editor được áp dụng cho tài nguyên và request đó |
| Lan thao tác trên `orders-staging` | `roles/editor` kế thừa từ `nonproduction` | Tương tự `orders-dev` |
| Lan xem thông tin `orders-prod` | `roles/viewer` kế thừa từ `production` | Có các quyền xem được role này cấp |
| Lan sửa Cloud Run production | Chỉ có Viewer từ `production` | Viewer không mặc nhiên cấp quyền triển khai; phải xét thêm binding khác nếu có |
| Service account triển khai sửa Cloud Run production | `roles/run.admin` ở project `orders-prod` | Có thể được cấp các permission Cloud Run thuộc role, còn phải thỏa yêu cầu khác của thao tác |

Ví dụ này chỉ cho biết **Allow có thể cấp permission nào**. Kết luận truy cập cuối cùng còn phụ thuộc Deny, PAB, điều kiện và những yêu cầu kỹ thuật khác.

### Một người có nhiều binding được cộng quyền

Nếu Lan đồng thời thuộc `auditors@example.com`, các Allow binding từ hai nhóm đều được xem xét. IAM không chọn “role gần tài nguyên nhất” hay “role có tên nhỏ hơn”; một Allow binding phù hợp và có hiệu lực có thể cấp permission cần thiết.

Membership của Google Group và service account identity có thể khiến quyền khó nhận biết nếu chỉ nhìn một binding đơn lẻ. Khi phân tích quyền của người dùng, cần kiểm tra nhóm mà họ thuộc về, kể cả các quan hệ nhóm lồng nhau được dịch vụ hỗ trợ.

## 4. Vì sao không thể “gỡ quyền ở project” để chặn cấp cha?

Giả sử nhóm `developers@example.com` nhận `roles/editor` tại Folder `engineering`. Người quản trị vào IAM của `orders-prod`, không thấy binding Editor của nhóm tại project rồi quyết định xóa các binding local để hạn chế quyền.

Kết quả: **quyền Editor từ Folder `engineering` vẫn được kế thừa**. Xóa một binding tại project không làm mất binding đã được cấp ở Folder/Organization.

Để xử lý đúng, hãy chọn cách phù hợp với yêu cầu:

1. **Thu hẹp phạm vi Allow:** gỡ role rộng tại Folder `engineering`, sau đó cấp lại tại Folder `nonproduction` hoặc các project thật sự cần. Đây thường là cách đơn giản, dễ kiểm soát.
2. **Dùng role cụ thể hơn:** thay basic role rộng bằng predefined/custom role có các permission cần thiết.
3. **Dùng IAM Deny khi cần ngoại lệ:** nếu một quyền phải bị cấm trong một vùng tài nguyên dù được Allow ở cấp cha, có thể xem xét Deny policy với permission được hỗ trợ.
4. **Dùng PAB khi cần giới hạn phạm vi tài nguyên của principal:** ví dụ hạn chế một nhóm danh tính chỉ đủ điều kiện truy cập các tài nguyên thuộc phạm vi được định nghĩa.

**Sai lầm phổ biến:** cho rằng đặt Viewer tại project production sẽ “ghi đè” Editor kế thừa từ Folder. Trong IAM, các Allow binding không ghi đè nhau theo kiểu cấu hình CSS; chúng được cộng về khả năng cấp quyền.

## 5. Deny policy và cơ chế chặn quyền

**IAM Deny** được tạo và gắn tại Organization, Folder hoặc Project. Nó áp dụng cho tài nguyên nơi được gắn và các tài nguyên bên dưới, tương tự phạm vi kế thừa của Allow policy. Quy tắc Deny có thể định nghĩa principal bị chặn, permission bị chặn, principal ngoại lệ và một số điều kiện được hỗ trợ.

Khi một Deny rule áp dụng và chặn permission đang xét, quyền đó bị từ chối **ngay cả khi** Allow policy ở cùng cấp hoặc cấp khác cho phép.

~~~text
Allow: nhóm được cấp permission P ở Folder engineering
                         │
                         ▼
Project orders-prod: Deny permission P cho nhóm đó
                         │
                         ▼
Yêu cầu dùng P trên tài nguyên orders-prod: BỊ CHẶN
~~~

Ví dụ tình huống: doanh nghiệp có nhóm quản trị chung trên nhiều project, nhưng muốn cấm một số thao tác đặc biệt nguy hiểm tại project production. Có thể nghiên cứu gắn Deny policy ở project production cho các **permission được IAM Deny hỗ trợ**, thay vì áp dụng lệnh cấm cho mọi project.

Những giới hạn cần nhớ:

- **Deny không xóa binding Allow.** Nó chặn quyền khi chính sách có hiệu lực; binding Allow vẫn tồn tại.
- **Không phải permission nào cũng được hỗ trợ trong Deny.** Hãy tra danh sách permission được Deny hỗ trợ trước khi thiết kế.
- **Deny có thể chứa ngoại lệ principal**, nhưng ngoại lệ cần được cấu hình cẩn thận và không tự cấp quyền cho ai.
- **Điều kiện của Deny hạn chế hơn IAM Conditions trong Allow**, chẳng hạn các điều kiện dùng resource tags theo quy định của dịch vụ.
- Một thay đổi Deny tại Organization có thể ảnh hưởng nhiều project; nên đánh giá phạm vi, danh tính máy và khả năng khôi phục trước khi áp dụng.

Không nên chọn Deny làm cách chữa mọi trường hợp cấp quyền rộng. Đầu tiên hãy thu hẹp Allow theo nguyên tắc quyền tối thiểu; Deny phù hợp khi thật sự cần tạo ranh giới cấm rõ ràng hoặc ngoại lệ cho permission được kế thừa.

## 6. Principal Access Boundary (PAB) khác Deny ở đâu?

**Principal Access Boundary** xác định những tài nguyên mà các principal trong một **principal set** đủ điều kiện truy cập. PAB **không cấp quyền**; nó chỉ giới hạn phạm vi truy cập có thể được cấp bởi Allow.

Ví dụ, một tổ chức muốn hạn chế các service account được tạo bởi một nhóm project chỉ đủ điều kiện truy cập tài nguyên trong phạm vi đã xác định. Kể cả khi service account nhận Allow binding ở nơi rộng hơn, PAB có thể chặn quyền nằm ngoài phạm vi cho phép đối với các permission mà cơ chế này áp dụng.

| Yếu tố | Allow | Deny | PAB |
|---|---|---|---|
| Mục đích | Cấp permission | Chặn permission | Giới hạn tài nguyên principal đủ điều kiện truy cập |
| Phạm vi gắn | Resource / cấp cha hỗ trợ IAM | Organization, Folder, Project | Principal set, không gắn vào resource theo kiểu Allow/Deny |
| Có tự cấp quyền? | Có, nếu binding phù hợp | Không | Không |
| Kế thừa qua cây resource? | Có | Có | Không theo cùng cách; phụ thuộc membership của principal set |
| Dùng để giải quyết | Ai được làm gì trên tài nguyên | Quyền nào bị cấm bất kể Allow | Principal có thể tiếp cận vùng tài nguyên nào |

PAB có **phạm vi permission được cơ chế này kiểm soát** và quy tắc đánh giá riêng. Không nên khẳng định rằng một PAB đơn lẻ là “tường lửa tuyệt đối” cho mọi API. Trước khi dùng trong sản xuất, hãy kiểm tra phiên bản hỗ trợ, tập permission áp dụng và cách các PAB liên quan được kết hợp.

**Phân biệt với Organization Policy:** Organization Policy đặt ràng buộc về cách sử dụng dịch vụ, loại tài nguyên, cấu hình hoặc vị trí; nó không phải một Allow binding và không thay thế IAM. Một thao tác được IAM cho phép vẫn có thể bị từ chối vì Organization Policy, VPC Service Controls, điều kiện mạng hoặc logic riêng của dịch vụ.

## 7. IAM Conditions và thời điểm quyền có hiệu lực

Một Allow binding có thể gắn **IAM Condition** để giới hạn quyền theo ngữ cảnh được hỗ trợ: thời điểm yêu cầu, thuộc tính tài nguyên, hoặc resource tags trong những trường hợp phù hợp.

Ví dụ một binding dành cho nhóm hỗ trợ được phép truy cập trong đợt xử lý sự cố đến một thời điểm giới hạn:

~~~json
{
  "role": "roles/viewer",
  "members": [
    "group:support@example.com"
  ],
  "condition": {
    "title": "temporary_support_access",
    "description": "Quyen xem het han sau dot ho tro",
    "expression": "request.time < timestamp('2027-01-01T00:00:00Z')"
  }
}
~~~

Đây chỉ là **một binding minh họa** trong Allow policy, không phải một tệp policy hoàn chỉnh để áp dụng độc lập. Khi request không thỏa điều kiện, binding này không cấp quyền. Nếu cùng principal vẫn có **binding khác** (ở tài nguyên này hoặc cấp cha) cấp permission đó mà không bị giới hạn, quyền vẫn có thể được Allow.

Các lỗi dễ gặp:

- Thêm điều kiện tại project nhưng bỏ sót một binding không điều kiện ở Folder.
- Dùng điều kiện có thuộc tính không hỗ trợ với dịch vụ/tài nguyên định kiểm tra.
- Hiểu sai múi giờ hoặc thời điểm hết hạn của điều kiện.
- Tưởng điều kiện trong Allow sẽ tự chặn mọi quyền từ các role khác.

IAM Conditions cần được thử với từng permission và resource thực tế. Khi điều tra tình huống phụ thuộc thời gian hoặc thuộc tính request, nên cung cấp đủ ngữ cảnh cho Policy Troubleshooter.

## 8. Cách xác định quyền hiệu lực của một yêu cầu

Muốn trả lời chính xác câu hỏi **“Principal A có thể dùng permission P trên resource R không?”**, cần ít nhất bốn đầu vào:

1. **Principal:** email user, service account hoặc định danh workload đang thực sự thực hiện yêu cầu.
2. **Permission:** permission cụ thể API kiểm tra, ví dụ `resourcemanager.projects.get`.
3. **Resource:** tài nguyên đích đầy đủ, ví dụ project, bucket hoặc Cloud Run service.
4. **Request context:** thời điểm, thuộc tính tài nguyên, tags và các điều kiện liên quan.

Quy trình đánh giá ở mức khái niệm:

~~~mermaid
flowchart TD
    A["Principal gửi yêu cầu P trên R"] --> B{"Có Allow binding phù hợp trên R hoặc tổ tiên?"}
    B -- "Không" --> X["IAM không cấp quyền"]
    B -- "Có" --> C{"Điều kiện của ít nhất một Allow binding thỏa?"}
    C -- "Không" --> X
    C -- "Có" --> D{"Deny rule áp dụng và chặn P?"}
    D -- "Có" --> Y["IAM từ chối"]
    D -- "Không" --> E{"PAB liên quan có chặn quyền trên R?"}
    E -- "Có" --> Y
    E -- "Không" --> F["Được IAM cho phép"]
    F --> G["Dịch vụ còn có thể kiểm tra API, mạng, Org Policy và các điều kiện khác"]
~~~

Sơ đồ là **mô hình học tập**, không mô tả toàn bộ thứ tự nội bộ của hệ thống IAM hay mọi policy type mà Google Cloud hỗ trợ. Một số loại tài nguyên có cơ chế riêng hoặc nhiều permission cần kiểm tra đồng thời.

Có thể nhớ bằng biểu thức:

~~~text
IAM cho phép về mặt policy khi:
  tồn tại Allow binding phù hợp (và điều kiện của binding là TRUE)
  AND không có Deny rule đang chặn permission
  AND không bị Principal Access Boundary liên quan chặn
~~~

**Không có Allow** thường dẫn tới không có quyền, kể cả không có Deny. **Có Allow** cũng không đủ nếu Deny hoặc PAB chặn. Khi policy đã cho phép, request thực tế vẫn có thể thất bại vì API chưa bật, quota, cấu hình mạng, thiếu permission khác, Organization Policy hoặc các cơ chế truy cập riêng của dịch vụ.

### Quyền của nhóm, người dùng và service account

Trong một hệ thống CI/CD, user có thể được phép **impersonate** service account, trong khi lệnh gọi API cuối cùng chạy dưới danh tính service account. Phải kiểm tra cả hai lớp:

- User có quyền sử dụng/impersonate service account theo cơ chế phù hợp hay không?
- Service account có permission cần thiết trên resource đích không?

Việc một user có `roles/viewer` trên project không bảo đảm rằng Cloud Run service chạy dưới service account của user đó, và quyền của Cloud Run runtime service account cũng không tự động trở thành quyền của người triển khai.

## 9. Thực hành tính quyền qua ba tình huống

### Tình huống A — Quyền tại Folder lan xuống Project

Folder `nonproduction` chứa `orders-dev` và `orders-staging`. Nhóm developers được cấp một role cho phép đọc metadata của project tại Folder.

**Hỏi:** thành viên nhóm có cần binding tương tự ở cả hai project không?

**Trả lời:** thường không. Binding ở Folder áp dụng cho các project con; nếu permission phù hợp và không bị chặn bởi cơ chế khác, cả hai project đều có quyền được kế thừa. Cấp lặp tại từng project khiến kiểm toán phức tạp hơn.

### Tình huống B — Project không thể phủ định Allow cấp Organization

Organization cấp một role rộng cho nhóm operations. Project `orders-prod` chỉ cấp Viewer cho nhóm đó.

**Hỏi:** role Viewer ở project có giới hạn quyền đến Viewer hay không?

**Trả lời:** không. Allow ở project được cộng với Allow đã kế thừa. Muốn giảm quyền, cần điều chỉnh binding ở nơi cấp rộng hoặc áp cơ chế giới hạn được thiết kế đúng phạm vi.

### Tình huống C — Allow có nhưng bị Deny

Nhóm vận hành nhận Allow ở Folder cho một permission. Tại project production, Deny rule nhắm đúng nhóm và permission đó được cấu hình theo khả năng hỗ trợ của IAM.

**Hỏi:** người dùng có thực hiện được thao tác ở production không?

**Trả lời:** không, nếu Deny thực sự áp dụng và không có ngoại lệ hợp lệ. Tại project dev không thuộc phạm vi Deny, cùng permission có thể vẫn được Allow.

### Tình huống D — Người dùng có nhiều đường cấp quyền

User thuộc cả nhóm `developers` và `security-reviewers`. Binding của `developers` có điều kiện hết hạn, nhưng nhóm `security-reviewers` được cấp permission tương tự không điều kiện.

**Hỏi:** hết hạn binding của developers có làm mất quyền không?

**Trả lời:** chưa chắc. Phải xem mọi Allow binding phù hợp với user, kể cả role có được từ nhóm khác hoặc tổ tiên.

## 10. Kiểm tra policy bằng Console và gcloud

### Xem policy tại từng cấp

Trong Google Cloud Console, mở **IAM & Admin → IAM** tại project. Giao diện có thể cho phép xem các quyền được cấp và nguồn kế thừa. Khi điều tra một principal, hãy ghi nhận project, Folder, Organization và phạm vi của từng role binding.

Với Google Cloud CLI, chạy các lệnh **chỉ đọc**:

~~~bash
# Policy gắn trực tiếp tại project (thay project ID thật).
gcloud projects get-iam-policy orders-prod --format=json

# Policy trực tiếp của folder (thay FOLDER_ID thật).
gcloud resource-manager folders get-iam-policy FOLDER_ID --format=json

# Policy trực tiếp của organization (thay ORG_ID thật).
gcloud organizations get-iam-policy ORG_ID --format=json
~~~

**Quan trọng:** `get-iam-policy` của một project chủ yếu trả về **policy gắn tại project đó**. Nó không phải bản liệt kê tự động của mọi binding từ Folder, Organization và service-level policy. Nếu không thấy role trong đầu ra project, không được kết luận principal không có quyền kế thừa.

Đối với tài nguyên cụ thể, sử dụng lệnh `get-iam-policy` tương ứng nếu dịch vụ hỗ trợ. Ví dụ một Cloud Storage bucket hoặc Cloud Run service có thể có policy riêng; phải xem thêm policy của resource đích khi quyền của tài nguyên đó là trọng tâm.

### Tìm lý do bằng Policy Troubleshooter

**Policy Troubleshooter** nhận ba tham số quan trọng: principal, full resource name và permission. Nó kiểm tra các Allow/Deny policy và, theo mức hỗ trợ, Principal Access Boundary để giải thích tại sao có hoặc không có quyền.

Ví dụ kiểm tra người dùng có permission **xem project** hay không:

~~~bash
gcloud policy-intelligence troubleshoot-policy iam \
  "//cloudresourcemanager.googleapis.com/projects/orders-prod" \
  --principal-email="lan@example.com" \
  --permission="resourcemanager.projects.get"
~~~

Nếu cần phân tích PAB theo khả năng hỗ trợ, tài liệu hiện hành hướng dẫn sử dụng lệnh ở phiên bản **beta**:

~~~bash
gcloud beta policy-intelligence troubleshoot-policy iam \
  "//cloudresourcemanager.googleapis.com/projects/orders-prod" \
  --principal-email="lan@example.com" \
  --permission="resourcemanager.projects.get"
~~~

Cần thay project và email giả định bằng giá trị thật, bật API của Policy Troubleshooter và có quyền xem các chính sách liên quan. Hãy kiểm tra `gcloud policy-intelligence troubleshoot-policy iam --help` vì tùy chọn và trạng thái hỗ trợ có thể thay đổi.

Đọc kết quả theo thứ tự:

1. Principal và resource có đúng với yêu cầu bị lỗi không?
2. Permission có thật sự là permission API cần dùng không?
3. Binding nào từ project/Folders/Organization đã cấp Allow? Condition của binding có thỏa không?
4. Có Deny rule nào áp dụng không? Có principal ngoại lệ không?
5. Có PAB nào đang giới hạn phạm vi không?
6. Có policy mà người chạy công cụ **không đủ quyền xem** không?

**Giới hạn:** Troubleshooter không thay thế hoàn toàn kiểm tra service-specific access control, Cloud Storage ACL hoặc VPC Service Controls. Điều kiện phụ thuộc thời gian/thuộc tính request cần đủ ngữ cảnh; kết quả cũng có thể không đầy đủ nếu người điều tra không có quyền đọc policy hoặc custom role liên quan. Công cụ hỗ trợ phân tích principal cá nhân/danh tính phù hợp; không nên giả định có thể trực tiếp phân tích mọi loại principal set hoặc Google Group như một user.

### Đọc Audit Logs khi lỗi xảy ra

Nếu một lệnh thực tế thất bại với `PERMISSION_DENIED`:

- Xác định **đúng caller** trong Audit Logs hoặc thông báo lỗi; caller có thể là service account khác với tài khoản đang mở Console.
- Tìm permission, API, tài nguyên và thời điểm request. Không đoán chỉ từ tên role.
- Dùng thông tin đó để kiểm tra bằng Troubleshooter; với IAM Conditions, kiểm tra ngữ cảnh thời gian và resource.
- Sau khi sửa IAM, chờ chính sách lan truyền rồi thử lại. Không vội cấp `Owner` chỉ để vượt qua lỗi.

## 11. Thiết kế IAM an toàn cho nhiều môi trường

Ví dụ nhóm phát triển hệ thống đơn hàng có:

~~~text
Folder nonproduction
├── orders-dev
└── orders-staging

Folder production
└── orders-prod
    └── Cloud Run orders-api
~~~

Mô hình đề xuất:

| Nhóm/danh tính | Nơi cấp quyền | Mục đích |
|---|---|---|
| `developers@example.com` | Project dev hoặc Folder nonproduction, role cụ thể | Viết và chạy thử ứng dụng |
| `qa@example.com` | Project staging và tài nguyên kiểm thử liên quan | Chạy kiểm thử, xem kết quả |
| `prod-observers@example.com` | Project production, quyền quan sát phù hợp | Đọc trạng thái, metric/log cần thiết |
| `deploy-orders@ci-tools.iam.gserviceaccount.com` | Project/tài nguyên Cloud Run production và service account được phép sử dụng | CI/CD triển khai theo quy trình được duyệt |
| `platform-admins@example.com` | Các phạm vi hạ tầng cần quản trị | Quản lý mạng, quyền và chính sách có kiểm toán |

Để triển khai Cloud Run thực tế, quyền của danh tính CI/CD phải đủ cho các hành động liên quan đến Cloud Run, image, và khả năng **sử dụng service account chạy ứng dụng**; role Cloud Run duy nhất có thể chưa đáp ứng toàn bộ thao tác. Danh tính chạy ứng dụng chỉ nên có quyền truy cập database/bucket cần thiết khi chạy, độc lập với danh tính deploy.

Các quy tắc thiết kế:

1. **Đặt Allow ở phạm vi nhỏ nhất đáp ứng nhu cầu.** Folder phù hợp khi mọi project bên dưới thật sự cần cùng role; tránh cấp rộng tại Organization vì tiện.
2. **Dùng Google Group cho nhân sự**, service account riêng cho workload và CI/CD. Có quy trình thu hồi thành viên.
3. **Ưu tiên predefined/custom role tối thiểu**, hạn chế sử dụng basic role rộng cho production.
4. **Rà soát quyền kế thừa trước khi cấp mới.** Một role ở Folder có thể đã đủ; cấp trùng ở project tăng gánh nặng kiểm toán.
5. **Đánh giá khi di chuyển project sang Folder khác.** Chuyển tổ tiên có thể thay đổi toàn bộ Allow/Deny và Organization Policy được kế thừa.
6. **Kiểm chứng bằng permission cụ thể**, không chỉ so sánh tên role.
7. **Cần người có quyền kiểm tra và sửa lỗi** nếu Deny/PAB hoặc thay đổi cấp Organization làm nhiều project bị mất quyền vận hành.
8. **Lưu lịch sử thay đổi IAM** bằng quy trình review, Infrastructure as Code khi phù hợp, Audit Logs và kiểm tra định kỳ.

### Vì sao di chuyển project có thể thay đổi quyền?

Giả sử `orders-staging` được chuyển từ Folder `nonproduction` sang `production`. Sau khi di chuyển, project không còn kế thừa các binding chỉ thuộc nhánh cũ; nó nhận các Allow/Deny và chính sách tổ chức phù hợp của nhánh mới. Không cần sửa trực tiếp IAM tại project để xảy ra thay đổi quyền.

Trước khi di chuyển, nên liệt kê các principal phụ thuộc quyền kế thừa, dịch vụ CI/CD, network/shared resources, Organization Policy và người chịu trách nhiệm ứng cứu. Việc di chuyển cần được review như một thay đổi bảo mật.

## 12. Những nhầm lẫn thường gặp

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| “Xóa role ở project sẽ xóa quyền từ Folder.” | **Sai** | Binding ở Folder vẫn được kế thừa |
| “Project gắn Viewer sẽ ghi đè Editor ở Organization.” | **Sai** | Allow binding có thể cộng quyền |
| “Có một Allow binding là chắc chắn API gọi thành công.” | **Sai** | Còn Deny, PAB, conditions, IAM khác và kiểm soát dịch vụ |
| “Deny ở Organization ảnh hưởng project con.” | **Đúng** | Nếu Deny áp dụng cho permission/principal đó |
| “PAB tự cấp quyền truy cập các tài nguyên nằm trong phạm vi.” | **Sai** | PAB chỉ giới hạn eligibility; vẫn cần Allow |
| “Xem `get-iam-policy` của project là thấy mọi quyền hiệu lực.” | **Sai** | Phải xét policy của tổ tiên và tài nguyên dịch vụ |
| “Thành viên của hai nhóm có thể nhận quyền từ cả hai.” | **Đúng** | Các binding phù hợp được xét độc lập |
| “IAM và Organization Policy là cùng một loại chính sách.” | **Sai** | IAM cấp/chặn quyền, Organization Policy đặt ràng buộc cấu hình và sử dụng |
| “Một project chuyển Folder có thể làm thay đổi quyền.” | **Đúng** | Tổ tiên và chính sách kế thừa thay đổi |

## 13. Checklist khi điều tra lỗi và rà soát quyền

- [ ] Đã xác định **principal đang thực hiện request**, tránh nhầm user với service account.
- [ ] Đã xác định đúng **permission** và **full resource name**.
- [ ] Đã xem Allow policy ở resource, project và toàn bộ các cấp tổ tiên liên quan.
- [ ] Đã kiểm tra membership của nhóm và điều kiện của các binding.
- [ ] Đã kiểm tra Deny policy, ngoại lệ và phạm vi permission được hỗ trợ.
- [ ] Đã kiểm tra PAB nếu tổ chức sử dụng và cơ chế đó áp dụng cho permission.
- [ ] Đã phân biệt kết luận **IAM cho phép** với lỗi API, mạng hoặc Organization Policy.
- [ ] Đã thử Policy Troubleshooter với đủ quyền xem và ngữ cảnh.
- [ ] Đã đánh giá tác động tới dev, staging, production trước khi sửa IAM ở cấp cha.
- [ ] Đã lưu và review thay đổi, kiểm chứng sau khi policy lan truyền.

**Bài tập vận dụng:** Organization `example.com` có Folder `engineering` với hai Folder con `nonproduction` và `production`. Nhóm `developers` nhận Viewer tại `engineering` và Editor tại `nonproduction`. Một user thuộc nhóm `developers` được cấp thêm một role Cloud Run tại project `orders-prod`. Hãy trả lời: (1) user có thể xem project staging không, vì sao; (2) user có thể sửa Compute Engine ở production chỉ nhờ Editor tại nonproduction không; (3) gỡ role Cloud Run ở `orders-prod` có khiến user mất mọi quyền trên project đó không; (4) nếu có Deny áp dụng cho một permission Cloud Run tại production, điều gì xảy ra; (5) bạn dùng những lệnh/công cụ nào để kiểm chứng kết luận? Với từng câu, nêu cấp tài nguyên chứa binding và permission cần kiểm tra thay vì chỉ liệt kê tên role.

## Tài liệu tham khảo chính thức

- [IAM overview](https://cloud.google.com/iam/docs/overview) — principal, role, permission và policy.
- [Understanding allow policies](https://cloud.google.com/iam/docs/allow-policies) — kế thừa Allow và effective allow policy.
- [Deny access to resources](https://cloud.google.com/iam/docs/deny-access) — Deny policies, phạm vi và ngoại lệ.
- [Principal Access Boundary policies](https://cloud.google.com/iam/docs/principal-access-boundary-policies) — giới hạn phạm vi tài nguyên của principal.
- [Policy types](https://cloud.google.com/iam/docs/policy-types) — phân biệt Allow, Deny và các loại policy khác.
- [Troubleshoot IAM permissions](https://cloud.google.com/policy-intelligence/docs/troubleshoot-access) — Policy Troubleshooter và giới hạn đánh giá.
- [Google Cloud IAM Conditions](https://cloud.google.com/iam/docs/conditions-overview) — các điều kiện có thể dùng trong binding.
