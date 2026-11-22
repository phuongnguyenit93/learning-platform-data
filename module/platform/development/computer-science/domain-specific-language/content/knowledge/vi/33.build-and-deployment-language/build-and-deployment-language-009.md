# Kiểm soát quyền thực thi

## Kiểm soát quyền thực thi trong DSL xây dựng và triển khai là gì?

Một DSL dùng để xây dựng và triển khai có thể mô tả các bước biên dịch, chạy kiểm thử, đóng gói artifact, gọi công cụ, truy cập file, tải dependency, đẩy image, tạo hạ tầng hoặc phát hành ứng dụng. Khi engine thực thi một workflow như vậy, nó có thể tác động đến mã nguồn, máy build, registry, tài khoản cloud và môi trường production. Vì thế, việc xác định ai được phép yêu cầu một hành động và hành động nào được phép chạy là một phần cốt lõi của thiết kế ngôn ngữ và runtime.

**Kiểm soát quyền thực thi (execution permission control)** là tập hợp cơ chế xác định principal nào được phép thực hiện action nào trên resource nào, trong context nào và theo điều kiện nào. Cơ chế này có thể được thể hiện trong DSL, được kiểm tra khi compile hoặc plan, rồi được enforcement tại runtime trước khi hành động có tác động được thực hiện.

Ví dụ, một pipeline có thể cho phép mọi developer chạy compile và unit test, nhưng chỉ release operator mới được publish artifact hoặc deploy production:

~~~text
PIPELINE checkout {
  TASK compile {
    RUN build.compile
  }

  TASK test {
    RUN test.unit
  }

  TASK publish {
    RUN artifact.publish
    REQUIRES ROLE "release-operator"
  }

  TASK deployProduction {
    RUN deploy.apply
    TARGET production
    REQUIRES ROLE "production-deployer"
    REQUIRES APPROVAL "release-approval"
  }
}
~~~

Đây là cú pháp minh họa. Mỗi DSL cần định nghĩa rõ cách khai báo principal, role, resource, permission, policy và approval. Ý nghĩa quan trọng là quyền được kiểm tra theo action cụ thể, thay vì chỉ tin rằng người dùng có quyền chạy toàn bộ pipeline vì họ có thể khởi động một job.

Kiểm soát quyền thực thi giúp:

- Ngăn workflow thực hiện hành động vượt quyền của người khởi chạy.
- Giới hạn công cụ, filesystem, network, secret và môi trường mà task được truy cập.
- Phân biệt quyền build, test, publish và deploy.
- Yêu cầu phê duyệt cho hành động có rủi ro cao.
- Cô lập các project, tenant và môi trường.
- Ghi nhận ai đã yêu cầu, phê duyệt và thực hiện hành động.
- Thu hồi quyền hoặc dừng execution khi policy thay đổi.
- Tạo quy trình triển khai có thể kiểm tra và tái lập.

Một thiết kế an toàn cần phối hợp authorization, sandbox, identity, secret management, approval, audit và runtime enforcement. Chỉ kiểm tra quyền trong giao diện hoặc trong file DSL là chưa đủ; executor phải tự xác minh quyền ngay trước khi thực hiện hành động được bảo vệ.

## Phân biệt authentication, authorization và execution policy

Các thuật ngữ bảo mật thường xuất hiện cùng nhau nhưng có trách nhiệm khác nhau.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang yêu cầu? | Người dùng đăng nhập bằng tài khoản công ty |
| Authorization | Người đó được phép làm gì? | Có quyền deploy service checkout |
| Execution policy | Hành động được chạy trong điều kiện nào? | Chỉ deploy từ branch đã bảo vệ |
| Capability | Tiến trình đang giữ quyền cụ thể nào? | Token chỉ cho phép đọc artifact A |
| Approval | Ai phải xác nhận trước khi tiếp tục? | Release manager duyệt production |
| Sandbox | Hành động bị giới hạn trong môi trường nào? | Task chỉ ghi vào thư mục workspace |
| Audit | Ai đã làm gì và quyết định dựa trên policy nào? | Ghi lại deploy request và decision |

Authentication tạo ra identity đáng tin cậy. Authorization dùng identity và context để quyết định quyền. Execution policy có thể thêm điều kiện như branch, artifact provenance, thời gian, môi trường hoặc trạng thái kiểm thử.

Sandbox giới hạn những gì process có thể làm kể cả khi code bên trong có lỗi hoặc bị khai thác. Approval là một bước kiểm soát bổ sung cho hành động quan trọng. Audit cung cấp bằng chứng về quyết định và kết quả.

Các lớp này không thay thế nhau. Người dùng đã xác thực vẫn có thể không được phép deploy. Một task có quyền gọi tool vẫn cần sandbox giới hạn filesystem và network. Một deployment đã được phê duyệt vẫn phải kiểm tra artifact và target đúng với nội dung được duyệt.

## Mô hình authorization: principal, action, resource và context

Một quyết định quyền thường được biểu diễn bằng bốn thành phần chính:

~~~text
AuthorizationRequest
  principal
  action
  resource
  context
~~~

### Principal

Principal là thực thể đang yêu cầu hoặc thực hiện hành động. Có thể là:

- User: developer, operator hoặc administrator.
- Service account: identity của CI runner hoặc deployment controller.
- Workload identity: identity gắn với một job hoặc task.
- Group: nhóm người dùng được quản trị tập trung.
- Role: tập quyền được gán cho principal.
- Delegated identity: identity thực hiện thay mặt một người hoặc hệ thống khác.

Không nên lấy principal từ một chuỗi do pipeline author tự khai báo. Runtime cần lấy identity từ phiên đăng nhập, token đã xác minh hoặc workload identity provider đáng tin cậy.

### Action

Action là thao tác được yêu cầu. DSL nên dùng tên action có ý nghĩa và tập giá trị được kiểm soát, ví dụ:

- build.compile.
- test.execute.
- artifact.read.
- artifact.publish.
- registry.push.
- filesystem.read.
- filesystem.write.
- network.connect.
- secret.read.
- deploy.plan.
- deploy.apply.
- infrastructure.destroy.

Action càng cụ thể thì policy càng dễ giới hạn. Một permission quá rộng như execute-any-command rất khó kiểm soát vì nó có thể bao gồm nhiều hành vi khác nhau.

### Resource

Resource là đối tượng bị tác động. Ví dụ:

- Repository hoặc branch.
- Workspace hoặc file path.
- Build artifact.
- Container image.
- Package registry.
- Cloud project hoặc account.
- Deployment environment.
- Service hoặc cluster.
- Secret hoặc secret namespace.
- Infrastructure stack.

Resource nên có identity ổn định và được resolve theo namespace đáng tin cậy. Một tên resource do người dùng nhập cần được kiểm tra để tránh truy cập sang project hoặc tenant khác.

### Context

Context chứa điều kiện tại thời điểm quyết định:

- Environment đang chạy.
- Branch hoặc commit.
- Pull request status.
- Kết quả test và scan.
- Artifact digest và provenance.
- Thời gian hoặc cửa sổ triển khai.
- Network zone hoặc runner class.
- Tenant và project ownership.
- Approval state.
- Mức độ rủi ro của action.

Context phải đến từ nguồn đáng tin cậy. Nếu client có thể tự gửi branchProtected=true hoặc testsPassed=true mà server không xác minh, policy có thể bị vượt qua.

## Các mô hình phân quyền phổ biến

### Role-Based Access Control (RBAC)

RBAC gán permission cho role, rồi gán role cho user hoặc service identity.

Ví dụ:

~~~text
ROLE developer {
  ALLOW build.compile
  ALLOW test.execute
  ALLOW artifact.read
}

ROLE release-operator {
  ALLOW artifact.publish
  ALLOW deploy.plan
}

ROLE production-deployer {
  ALLOW deploy.apply ON environment.production
}
~~~

Ưu điểm của RBAC là dễ quản trị khi tổ chức có nhóm công việc ổn định. Thay đổi quyền của role có thể áp dụng cho nhiều người cùng lúc.

Hạn chế là role có thể phình to hoặc tạo quá nhiều role khi cần biểu diễn điều kiện chi tiết. RBAC đơn thuần cũng khó diễn tả quyền phụ thuộc branch, thời gian, artifact hoặc trạng thái approval.

### Attribute-Based Access Control (ABAC)

ABAC quyết định dựa trên thuộc tính của principal, action, resource và context.

Ví dụ:

~~~text
POLICY productionDeploy {
  ALLOW deploy.apply
  WHEN principal.department == "platform"
   AND resource.environment == "production"
   AND context.branch == "main"
   AND context.testsPassed == true
}
~~~

ABAC linh hoạt hơn khi quyền phụ thuộc nhiều điều kiện. Tuy nhiên, policy có thể khó đọc và khó kiểm thử nếu thuộc tính không được chuẩn hóa hoặc nguồn dữ liệu không đáng tin.

### Capability-Based Access Control

Capability là quyền cụ thể được trao cho một process hoặc task. Thay vì cho task một identity có quyền rộng, runtime cấp một capability giới hạn theo action, resource và thời hạn.

Ví dụ, task có thể nhận token chỉ đọc một artifact cụ thể và ghi một thư mục output. Token không cho phép truy cập các artifact khác hoặc deploy.

Capability hữu ích cho task chạy trong sandbox và workload identity ngắn hạn. Cần bảo vệ token khỏi bị sao chép, giới hạn lifetime và hỗ trợ thu hồi.

### Ownership-based access

Một số hệ thống cho phép chủ sở hữu resource quản lý quyền. Ví dụ repository owner có thể cấp quyền đọc hoặc ghi cho nhóm. Tuy nhiên, ownership không nên tự động cho phép mọi hành động triển khai production; policy cấp tổ chức vẫn có thể áp dụng.

### Kết hợp các mô hình

Một hệ thống thường dùng RBAC cho quyền nền, ABAC cho điều kiện context và capability để giới hạn quyền của từng execution. Policy engine có thể kết hợp các quyết định theo một thuật toán rõ ràng.

## Quy tắc ALLOW, DENY và xử lý xung đột

Policy cần xác định hành vi khi có nhiều rule cùng áp dụng.

Ví dụ:

~~~text
POLICY buildAccess {
  ALLOW build.compile
  ALLOW test.execute
  DENY deploy.apply
}
~~~

Các thuật toán phổ biến:

- **Default deny:** nếu không có rule ALLOW phù hợp thì từ chối.
- **Deny overrides:** một rule DENY phù hợp thắng mọi rule ALLOW.
- **Permit overrides:** một rule ALLOW phù hợp có thể thắng DENY, chỉ nên dùng khi policy được thiết kế rõ.
- **First applicable:** áp dụng rule đầu tiên theo thứ tự được công bố.
- **Priority-based:** rule có priority cao hơn quyết định.

Với quyền thực thi build và deploy, default deny và deny-overrides thường dễ kiểm soát hơn. Nếu một rule cấm production deploy, một rule ALLOW chung không nên vô tình vượt qua lệnh cấm đó.

Policy engine cần phân biệt:
- Permit: có đủ quyền.
- Deny: bị policy từ chối.
- NotApplicable: không có rule nào áp dụng.
- Indeterminate: không thể đưa ra quyết định vì thiếu dữ liệu hoặc lỗi policy evaluation.

Indeterminate không nên được coi là permit. Với hành động có tác động, hệ thống nên fail closed và yêu cầu đánh giá lại sau khi dependency phục hồi.

### Quyền kế thừa

Role hoặc policy có thể kế thừa từ role khác. Cần xác định:
- Kế thừa permission trực tiếp hay cả policy condition.
- Deny có được kế thừa không.
- Có cho phép chu trình role inheritance không.
- Cách xử lý xung đột giữa parent và child.
- Có quyền override policy tổ chức hay không.

Nên phát hiện inheritance cycle khi validate policy thay vì để runtime đệ quy vô hạn.

## Khai báo permission trong DSL

DSL có thể hỗ trợ khai báo quyền theo resource và action:

~~~text
PERMISSIONS {
  ROLE developer {
    ALLOW build.compile ON project.current
    ALLOW test.execute ON project.current
    ALLOW filesystem.read ON workspace.source
    ALLOW filesystem.write ON workspace.output
  }

  ROLE publisher {
    ALLOW artifact.publish ON registry.internal
  }

  ROLE deployer {
    ALLOW deploy.plan ON environment.staging
    ALLOW deploy.apply ON environment.staging
  }
}
~~~

Cú pháp trên chỉ minh họa mô hình. Ngôn ngữ cần quy định cách resolve role, resource, action và scope.

### Permission theo phạm vi

Permission có thể áp dụng ở cấp:
- Organization.
- Project.
- Repository.
- Branch.
- Pipeline.
- Task.
- Artifact.
- Environment.
- Service hoặc infrastructure stack.

Quyền ở scope cha có thể được kế thừa xuống scope con nếu policy cho phép. Không nên giả định mọi quyền organization đều tự động cấp quyền trên mọi resource nhạy cảm.

### Permission theo task

Một pipeline có thể khai báo quyền tối thiểu cho từng task:

~~~text
TASK compile {
  REQUIRES build.compile
  REQUIRES filesystem.read ON workspace.source
  REQUIRES filesystem.write ON workspace.output
}

TASK publish {
  REQUIRES artifact.publish ON registry.internal
}
~~~

Task compile không cần quyền publish. Nếu tất cả task dùng chung một service account có quyền rộng, lỗi hoặc script độc hại trong task compile có thể sử dụng quyền publish ngoài ý định.

### Permission theo điều kiện

Một policy có thể yêu cầu nhiều điều kiện:

~~~text
ALLOW deploy.apply ON environment.production
WHEN principal.hasRole("production-deployer")
 AND context.branch == "main"
 AND context.releaseApproved
 AND context.securityScanPassed
~~~

Mỗi thuộc tính phải có nguồn xác minh. releaseApproved cần đến từ approval service hoặc record đã ký; không nên chỉ là biến pipeline do author tùy ý đặt.

## Kiểm tra quyền ở thời điểm nào?

Authorization có thể được kiểm tra ở nhiều giai đoạn. Một lần kiểm tra duy nhất ở đầu pipeline thường không đủ.

### Parse và static validation

Ở giai đoạn này, compiler có thể phát hiện:
- Action không tồn tại.
- Role hoặc permission reference không hợp lệ.
- Resource path không resolve được.
- Task khai báo capability không tương thích.
- Policy có rule không thể áp dụng.
- Một bước yêu cầu quyền vượt policy của project.

Static validation giúp phát hiện lỗi trước khi chạy, nhưng không thay thế runtime authorization vì identity và context thực tế có thể thay đổi.

### Planning

Khi tạo execution plan, engine có thể xác định toàn bộ action và permission cần thiết. Nó có thể từ chối plan nếu một task yêu cầu capability không được policy cho phép.

Plan authorization cũng giúp tạo một bản preview: task nào cần quyền gì, resource nào bị tác động và approval nào còn thiếu.

### Runtime trước từng action

Ngay trước khi thực hiện action được bảo vệ, executor cần kiểm tra:
- Principal hiện tại.
- Action cụ thể.
- Resource đã resolve.
- Context và trạng thái approval.
- Capability còn hiệu lực.
- Policy version hiện hành.

Việc kiểm tra sát thời điểm sử dụng giảm rủi ro quyền đã bị thu hồi hoặc context đã thay đổi sau khi plan được tạo.

### Kiểm tra lại trước commit

Một số hành động có nhiều bước prepare và commit. Ví dụ deploy có thể tạo resource trước rồi mới chuyển traffic. Nếu policy hoặc approval thay đổi giữa hai bước, engine có thể cần kiểm tra lại trước commit hoặc trước bước có tác động không thể đảo ngược.

### Không chỉ dựa vào UI

Ẩn nút Deploy trong IDE chỉ cải thiện trải nghiệm. API, CLI, worker và executor đều phải thực hiện authorization độc lập. Người dùng có thể gọi endpoint trực tiếp hoặc sửa file DSL; server-side enforcement mới là ranh giới tin cậy.

## Quy trình thực thi có kiểm soát

Một execution engine có thể dùng pipeline:

~~~text
Receive execution request
          |
          v
Authenticate principal
          |
          v
Resolve project and resources
          |
          v
Parse and validate DSL
          |
          v
Build execution plan
          |
          v
Evaluate policy for required actions
          |
          v
Collect approvals and capabilities
          |
          v
Create isolated execution context
          |
          v
Re-check authorization at runtime
          |
          v
Execute action
          |
          v
Record audit and result
~~~

### Plan trước, execute sau

Engine nên tạo plan có danh sách action, resource và permission trước khi chạy. Điều này giúp người vận hành xem trước tác động và phát hiện task yêu cầu quyền không phù hợp.

Tuy nhiên, plan không phải bằng chứng quyền sẽ còn hợp lệ mãi. Runtime vẫn cần kiểm tra lại khi action được gọi.

### Authorization decision record

Một decision record có thể gồm:

~~~text
AuthorizationDecision
  decisionId
  principalId
  action
  resourceId
  outcome
  policyVersion
  reasonCode
  evaluatedAt
  expiresAt
  contextReference
~~~

Record nên có đủ thông tin để audit mà không lưu secret hoặc payload nhạy cảm. Nếu cần tái dựng context, có thể tham chiếu một snapshot được bảo vệ.

### Transaction boundary

Một action có thể gồm nhiều thao tác. Engine cần xác định thao tác nào nằm trong transaction, thao tác nào có compensation và điểm nào được xem là commit. Authorization phải được kiểm tra trước các bước có tác động và có thể cần kiểm tra lại trước commit.

## Least privilege và capability theo từng task

Nguyên tắc least privilege yêu cầu mỗi principal hoặc task chỉ có những quyền cần thiết để hoàn thành công việc của mình.

Ví dụ, pipeline có các task:

| Task | Quyền cần thiết |
|---|---|
| Compile | Đọc source, ghi build output |
| Unit test | Đọc artifact build, ghi test report |
| Package | Đọc build output, ghi package artifact |
| Publish | Đọc package, ghi registry |
| Deploy staging | Đọc artifact, cập nhật staging |
| Deploy production | Đọc artifact đã ký, cập nhật production |

Không nên cấp quyền deploy production cho toàn bộ pipeline chỉ vì một task cuối cần quyền đó.

### Capability ngắn hạn

Runtime có thể cấp capability cho task khi bắt đầu:

~~~text
CAPABILITY compileAccess {
  ALLOW filesystem.read ON workspace.source
  ALLOW filesystem.write ON workspace.output
  EXPIRES AFTER 10 MINUTES
}
~~~

Capability nên:
- Gắn với task hoặc workload identity.
- Giới hạn action và resource.
- Có thời hạn ngắn.
- Có thể thu hồi.
- Không thể tự nâng quyền.
- Không được truyền sang task khác nếu không có delegation rõ ràng.

### Capability attenuation

Một task cha có thể cấp capability hẹp hơn cho task con. Task con không được nhận quyền rộng hơn task cha.

Ví dụ, task package chỉ cần đọc build output và ghi package output. Nó không cần quyền đọc secret hoặc truy cập network. Việc thu hẹp capability giúp giảm tác động nếu task con bị xâm nhập.

### Delegation

Nếu một service thực hiện thay mặt user, delegation cần ghi rõ:
- Người ủy quyền.
- Service được ủy quyền.
- Action được phép.
- Resource scope.
- Thời hạn.
- Có được ủy quyền tiếp hay không.

Không nên chuyển nguyên access token của người dùng vào mọi task. Hãy cấp token riêng có audience và scope phù hợp.

## Kiểm soát quyền đối với command và plugin

Build DSL thường cho phép gọi command, script, plugin hoặc tool bên ngoài. Đây là bề mặt rủi ro lớn vì một command có thể thực hiện nhiều hành động khác nhau.

### Command allowlist

Thay vì cho phép chạy bất kỳ shell command nào, policy có thể cho phép một tập executable và argument pattern đã kiểm soát.

Ví dụ:

~~~text
EXECUTION_POLICY {
  ALLOW COMMAND "compiler" WITH_ARGS ["--release", "17"]
  ALLOW COMMAND "test-runner" WITH_ARGS ["--suite", "unit"]
  DENY COMMAND "powershell"
  DENY COMMAND "curl"
}
~~~

Allowlist cần kiểm tra executable thực tế sau khi resolve path, không chỉ kiểm tra tên chuỗi do người dùng gửi. Cần tránh executable shadowing qua PATH hoặc file giả mạo trong workspace.

### Argument validation

Một command được phép vẫn có thể bị lạm dụng qua argument. Cần:
- Tách executable và argument thành cấu trúc riêng.
- Tránh shell string interpolation.
- Kiểm tra argument theo schema.
- Giới hạn path và URL.
- Chặn option nguy hiểm nếu policy yêu cầu.
- Không ghép dữ liệu không tin cậy vào shell command.

### Plugin permission manifest

Plugin có thể khai báo quyền cần thiết:

~~~text
PLUGIN deploy-tool {
  REQUIRES deploy.plan
  REQUIRES deploy.apply ON environment.staging
  REQUIRES network.connect TO "deployment-api"
}
~~~

Engine kiểm tra manifest và cấp capability tương ứng. Plugin không nên được cấp quyền ngầm chỉ vì đã được cài đặt.

### Plugin trust và version

Plugin cần có nguồn phát hành, version, signature hoặc checksum và policy cập nhật. Quyền của plugin nên được xem xét lại khi version hoặc publisher thay đổi. Một plugin mới không nên tự động kế thừa mọi quyền chỉ vì tên package giống phiên bản cũ.

### Command output

Command output có thể chứa secret, token hoặc dữ liệu nội bộ. Logging cần masking và giới hạn kích thước. Không nên tự động đưa toàn bộ stdout/stderr vào audit record.

## Sandbox và cô lập execution

Authorization quyết định action nào được phép. Sandbox giới hạn môi trường mà code thực thi có thể truy cập. Hai cơ chế bổ sung cho nhau.

### Filesystem sandbox

Một task có thể được giới hạn:
- Read-only source directory.
- Writable output directory.
- Temporary directory riêng.
- Không truy cập home directory.
- Không truy cập credential file.
- Không ghi ra ngoài workspace hoặc vùng được cấp.

Path cần được canonicalize trước khi kiểm tra. Chỉ so sánh chuỗi prefix có thể bị vượt qua bằng path traversal, symbolic link hoặc junction. Runtime cần kiểm tra resolved path và xử lý symlink theo policy.

### Network sandbox

Task có thể không cần network hoặc chỉ cần truy cập một số host/service. Policy có thể giới hạn:
- Egress destination.
- Port và protocol.
- DNS resolution.
- Metadata service.
- Localhost và private network.
- Proxy configuration.

Chặn network ở tầng DSL nhưng để process có quyền network tự do sẽ không hiệu quả. Enforcement nên được thực hiện ở container, namespace, firewall hoặc network proxy.

### Process isolation

Mỗi task có thể chạy trong process hoặc container riêng với:
- User ID không đặc quyền.
- Read-only root filesystem.
- Giới hạn CPU và memory.
- Giới hạn process count.
- Không chia sẻ host credential.
- Không mount Docker socket hoặc host control socket nếu không cần.
- Timeout và cancellation.

Container không tự động là sandbox hoàn chỉnh. Cần cấu hình capability của OS, mount, namespace và runtime theo threat model.

### Resource limits

Một build script có thể tiêu thụ CPU, memory, disk hoặc tạo quá nhiều process. Có thể đặt:
- CPU quota.
- Memory limit.
- Disk quota.
- Maximum execution time.
- Maximum process/thread count.
- Maximum output size.
- Maximum artifact size.

Khi vượt giới hạn, engine cần dừng task và ghi reason code. Không nên để một task làm cạn tài nguyên của toàn runner.

### Không tin code trong workspace

Build script, plugin và dependency hook có thể chứa code tùy ý. Repository được clone từ bên ngoài cần được coi là input không tin cậy cho đến khi trust policy xác nhận. Việc user có quyền đọc repository không đồng nghĩa họ có quyền chạy script với credential production.

## Kiểm soát filesystem và artifact

DSL xây dựng thường đọc source, ghi intermediate file và tạo artifact. Mỗi loại resource cần permission riêng.

### Source read

Task compile thường cần đọc source và dependency manifest. Nó không cần quyền sửa source hoặc đọc file credential của user.

### Output write

Output directory nên được cấp riêng cho từng task hoặc job. Task không nên ghi đè artifact của job khác hoặc thư mục cache dùng chung nếu không có policy.

### Artifact read và publish

Đọc artifact và publish artifact là hai permission khác nhau. Một task test có thể đọc binary nhưng không cần ghi registry. Publish chỉ nên nhận artifact đã được xác minh về nguồn gốc và nội dung.

### Artifact provenance

Artifact có thể gắn:
- Source commit.
- Build definition version.
- Dependency lockfile digest.
- Builder identity.
- Build run ID.
- Test và scan result.
- Artifact digest.
- Signature.

Deployment policy có thể yêu cầu artifact được tạo bởi builder tin cậy và có provenance hợp lệ. Không nên chỉ dựa vào tên file hoặc tag có thể bị thay đổi.

### Immutable artifact

Sau khi publish, artifact nên được tham chiếu bằng digest hoặc immutable version. Nếu cùng tag trỏ sang nội dung khác, approval trước đó có thể không còn áp dụng cho artifact mới.

## Kiểm soát quyền truy cập secret và credential

Build và deployment thường cần token registry, cloud credential, signing key hoặc database password. Secret là resource có mức nhạy cảm cao.

### Secret permission riêng

Quyền đọc secret nên tách khỏi quyền chạy command:

~~~text
ALLOW secret.read ON secret.registry.publish
WHEN principal.hasRole("publisher")
 AND context.pipelineStage == "publish"
~~~

Một task compile không nên nhận secret registry nếu nó không cần. Càng ít task có secret, rủi ro rò rỉ càng thấp.

### Secret injection

Secret manager có thể cấp secret ngắn hạn vào environment hoặc file được mount riêng cho task. Cần:
- Chỉ inject vào task được phép.
- Giới hạn thời gian tồn tại.
- Không ghi secret vào command line nếu process list có thể lộ.
- Mask trong logs.
- Xóa hoặc unmount sau task.
- Không đưa secret vào artifact hoặc cache.

### Credential theo workload identity

Thay vì lưu credential dài hạn trong DSL, workload identity có thể cấp token tạm thời theo task và target. Token cần giới hạn audience, scope, expiration và có thể thu hồi.

### Secret trong expression

Không nên cho phép DSL nội suy secret vào chuỗi command tùy ý. Secret nên được truyền qua secure input channel hoặc handle không thể serialize tùy tiện. Nếu secret xuất hiện trong error message hoặc diagnostic, cần redact.

## Kiểm soát quyền triển khai theo môi trường

Staging, test và production thường có mức rủi ro khác nhau. DSL nên thể hiện target environment và policy tương ứng.

Ví dụ:

~~~text
DEPLOY checkout {
  TARGET staging
  REQUIRES deploy.apply ON environment.staging
}

DEPLOY checkout {
  TARGET production
  REQUIRES deploy.apply ON environment.production
  REQUIRES APPROVAL "production-release"
  REQUIRES artifact.signed
  REQUIRES security.scan.passed
}
~~~

### Environment isolation

Mỗi environment nên có:
- Resource namespace riêng.
- Credential riêng.
- Network boundary riêng.
- Permission set riêng.
- Audit stream riêng.
- Quota và policy riêng.

Quyền staging không nên tự động bao gồm production. Một service account có quyền trên mọi cluster làm giảm hiệu quả của separation of environments.

### Deployment gates

Trước production deployment, policy có thể yêu cầu:
- Branch được bảo vệ.
- Pull request đã merge.
- Build thành công.
- Test đạt.
- Security scan đạt.
- Artifact signature hợp lệ.
- Change window đang mở.
- Approval từ đúng nhóm.
- Người deploy không phải người phê duyệt nếu yêu cầu separation of duties.

Các điều kiện cần được xác minh từ nguồn authoritative. Một pipeline variable do chính job đặt không phải bằng chứng độc lập rằng test đã thành công.

### Plan và apply

Infrastructure deployment thường có hai bước:
- Plan: tính toán thay đổi dự kiến.
- Apply: thực hiện thay đổi.

Quyền plan có thể rộng hơn quyền apply. Approval nên gắn với plan digest hoặc exact change set. Nếu plan thay đổi sau khi được duyệt, approval cần được xem xét lại.

### Destructive action

Xóa database, destroy infrastructure, revoke key hoặc thay đổi network policy có thể gây tác động lớn. Các action này nên có permission riêng, explicit confirmation hoặc approval, giới hạn scope và audit chi tiết.

## Approval và separation of duties

Approval là cơ chế yêu cầu một người hoặc nhóm khác xác nhận trước khi thực hiện hành động.

### Approval policy

Một policy có thể quy định:

~~~text
APPROVAL_POLICY productionRelease {
  REQUIRED_ROLE "release-manager"
  MIN_APPROVERS 1
  SEPARATION_OF_DUTIES true
  EXPIRES AFTER 4 HOURS
}
~~~

Approval record cần gắn với:
- Execution hoặc release ID.
- Artifact digest.
- Deployment target.
- Plan/change set digest.
- Policy version.
- Approver identity.
- Thời điểm và expiration.

Nếu artifact hoặc plan thay đổi, approval cũ có thể không còn hợp lệ.

### Separation of duties

Với thao tác nhạy cảm, người tạo thay đổi không nên tự phê duyệt chính thay đổi đó. Có thể yêu cầu:
- Author khác approver.
- Approver thuộc nhóm được chỉ định.
- Hai người phê duyệt cho action có rủi ro cao.
- Security approval độc lập với release approval.

### Approval không phải permission thường trực

Một người có quyền approve không đồng nghĩa họ có quyền thực thi deploy. Approval là một điều kiện trong policy; executor vẫn cần permission deploy riêng.

### Approval timeout và revoke

Approval có thể hết hạn hoặc bị thu hồi. Runtime cần xác minh trạng thái tại thời điểm apply. Không nên dùng một boolean đã cache từ lúc tạo plan nếu deployment xảy ra nhiều giờ sau.

## Kiểm soát quyền trong CI/CD và build agent

CI runner thường xử lý nhiều repository và pipeline. Nếu các job dùng chung filesystem hoặc credential, một job có thể tác động đến job khác.

### Runner identity

Mỗi runner hoặc job nên có identity riêng. Quyền nên gắn với workload và repository context thay vì một credential dùng chung cho mọi pipeline.

### Ephemeral runner

Runner tạm thời giúp giảm rủi ro dữ liệu còn sót lại giữa job. Sau khi job kết thúc, workspace, secret mount và temporary credential cần được xóa hoặc hủy.

### Untrusted pull request

Pipeline cho pull request từ fork hoặc contributor không tin cậy không nên nhận secret production hoặc quyền publish. Có thể chạy compile và test trong sandbox không credential, rồi chạy publish ở một workflow riêng sau khi merge và xác minh trust.

### Shared cache

Build cache có thể chứa artifact hoặc intermediate data nhạy cảm. Cache cần được phân vùng theo trust boundary, repository hoặc tenant. Không cho pipeline không tin cậy ghi cache được pipeline production tin cậy sử dụng mà không kiểm tra provenance.

### Worker-to-worker isolation

Một job không nên đọc process memory, environment hoặc file của job khác. Isolation cần được enforce bởi OS/container và quyền storage, không chỉ bởi quy ước đặt thư mục.

## Quyền trong môi trường đa tenant và nhiều project

Một platform có thể chạy DSL cho nhiều tổ chức hoặc project. Authorization cần ngăn truy cập chéo tenant.

### Tenant context

Tenant identity phải được xác định từ authentication/session hoặc workload identity. Không tin tenant ID tùy ý trong file DSL hoặc request body.

### Resource namespace

Resource ID nên có tenant scope. Một đường dẫn hoặc tên ngắn như production cần được resolve trong namespace của tenant đã xác thực.

### Policy inheritance

Organization có thể đặt policy nền; project có thể bổ sung hạn chế. Project không nên tự nới lỏng một deny của organization nếu policy hierarchy không cho phép.

### Cache và capability isolation

Policy decision cache, credential cache và artifact cache cần phân vùng theo tenant/security context. Capability cấp cho tenant A không được dùng để truy cập resource của tenant B.

### Quota và concurrency

Permission không đồng nghĩa với quota. Một principal có quyền chạy build vẫn có thể bị giới hạn số job đồng thời, CPU hoặc chi phí cloud. Quota nên được kiểm tra riêng nhưng tích hợp vào execution policy.

## Thu hồi quyền và thay đổi policy trong lúc chạy

Quyền có thể bị thu hồi sau khi job được tạo hoặc trong khi deployment đang chạy.

### Revocation

Khi user rời nhóm hoặc token bị thu hồi, các request mới cần bị từ chối. Với execution đang chạy, policy cần xác định:
- Dừng ngay.
- Chỉ chặn action tiếp theo.
- Cho phép hoàn tất bước hiện tại nhưng không commit.
- Chuyển sang trạng thái cần can thiệp.
- Hủy capability và credential đang dùng.

Hành vi phụ thuộc loại action. Dừng giữa một thao tác cập nhật hạ tầng có thể để lại trạng thái không nhất quán; cần compensation hoặc recovery policy.

### Short-lived credential

Credential ngắn hạn giảm thời gian tồn tại của quyền bị lộ. Token có expiration và scope hẹp giúp giới hạn tác động. Runtime có thể refresh token khi policy vẫn cho phép.

### Policy version

Mỗi decision nên ghi policy version. Khi policy thay đổi, hệ thống có thể invalidation decision cache và yêu cầu re-evaluate các action chưa bắt đầu.

### Time-of-check to time-of-use

TOCTOU xảy ra khi quyền được kiểm tra tại thời điểm T1 nhưng resource hoặc policy thay đổi trước khi action chạy ở T2.

Giảm rủi ro bằng cách:
- Kiểm tra gần thời điểm sử dụng.
- Dùng immutable resource identity hoặc digest.
- Khóa hoặc compare-and-swap khi cần.
- Gắn decision với resource version.
- Kiểm tra lại approval và policy trước commit.
- Giới hạn thời gian hiệu lực của decision.

## Policy failure và fail-safe behavior

Authorization có thể thất bại vì policy service không khả dụng, identity provider lỗi, context thiếu hoặc resource không resolve được.

### Fail closed

Với action có tác động, nếu không thể xác định quyền thì nên từ chối hoặc tạm hoãn. Không nên cho phép deploy chỉ vì policy service timeout.

### Phân biệt deny và unavailable

Người dùng cần biết:
- DENIED: policy đã đánh giá và từ chối.
- INDETERMINATE: không thể đánh giá do lỗi hoặc thiếu dữ liệu.
- EXPIRED: capability hoặc approval hết hạn.
- REVOKED: quyền đã bị thu hồi.
- RESOURCE_MISMATCH: resource thực tế khác resource được cấp quyền.

Các reason code rõ giúp xử lý sự cố mà không tiết lộ policy nội bộ quá mức.

### Retry policy

Có thể retry khi dependency tạm thời không khả dụng, nhưng retry không được biến lỗi authorization thành permit. Sau retry limit, execution nên dừng ở trạng thái an toàn.

### Partial execution

Nếu pipeline đã chạy compile và test nhưng publish bị deny, engine có thể giữ artifact để debug hoặc xóa theo retention policy. Không nên tiếp tục các bước có tác động vượt quyền chỉ vì các bước trước đã thành công.

## Audit và observability cho execution permission

Audit record cần cho phép trả lời ai đã yêu cầu action, policy nào được áp dụng và điều gì đã xảy ra.

Một record có thể gồm:

~~~text
ExecutionAudit
  timestamp
  principal
  workloadIdentity
  pipelineId
  taskId
  action
  resource
  decision
  reasonCode
  policyVersion
  approvalReference
  capabilityReference
  executionId
  result
~~~

### Decision audit và action audit

Decision audit ghi kết quả authorization kể cả khi action bị từ chối. Action audit ghi hành động thực tế đã bắt đầu, hoàn tất, thất bại hoặc bị hủy.

Hai loại record cần được liên kết bằng execution ID hoặc correlation ID.

### Audit integrity

Audit log nên được bảo vệ khỏi sửa hoặc xóa bởi principal đang được audit. Có thể dùng append-only storage, access control riêng, signed record hoặc chuyển log đến hệ thống quản trị độc lập.

### Không ghi secret

Audit cần ghi secret reference hoặc resource ID đã che, không ghi secret value. Command argument và environment có thể chứa token; cần redaction trước khi lưu.

### Metrics

Metrics hữu ích gồm:
- Authorization request count.
- Permit/deny/indeterminate count.
- Decision latency.
- Policy evaluation error.
- Capability issuance/revocation.
- Approval wait time.
- Expired approval count.
- Sandbox violation.
- Resource limit exceeded.
- Deployment action by environment.

Không đưa user ID, raw path hoặc secret name tùy ý vào metric labels nếu điều đó làm tăng cardinality hoặc tiết lộ thông tin.

## Tích hợp với IDE và Language Server

Language server có thể giúp tác giả DSL hiểu permission trước khi chạy.

Các tính năng hữu ích:
- Completion cho action, resource, role và policy name.
- Hover giải thích permission cần thiết.
- Diagnostics khi task yêu cầu quyền không tồn tại.
- Cảnh báo capability quá rộng.
- Cảnh báo task có quyền cao hơn nhu cầu được khai báo.
- Kiểm tra resource reference sai scope.
- Preview authorization requirements của execution plan.
- Hiển thị approval gate còn thiếu.
- Go to definition cho role và policy.
- Find references cho permission.
- Explain policy decision với thông tin đã được phép hiển thị.

### Static permission analysis

Compiler có thể xác định tập action mà pipeline có thể gọi và so sánh với permission manifest. Nó có thể cảnh báo task không dùng đến một capability đã khai báo.

Tuy nhiên, static analysis không thể luôn biết action được gọi động từ plugin hoặc script. Runtime enforcement vẫn bắt buộc.

### Không biến diagnostics thành cơ chế bảo mật

Một cảnh báo trong editor không ngăn người dùng gọi API hoặc chạy file bằng CLI khác. IDE chỉ hỗ trợ phát hiện sớm và cải thiện trải nghiệm. Quyết định cuối cùng thuộc policy engine và executor.

## Kiểm thử hệ thống kiểm soát quyền

Policy và enforcement cần được kiểm thử độc lập và tích hợp.

### Unit test cho policy

Kiểm tra:
- Role được phép đúng action.
- Principal không có role bị deny.
- Resource scope khớp và không khớp.
- Context condition true/false.
- Deny-overrides.
- Default deny.
- Indeterminate không thành permit.
- Role inheritance và cycle.
- Policy version và expiration.

### Test capability

Kiểm tra capability:
- Chỉ chứa action được cấp.
- Không truy cập resource ngoài scope.
- Hết hạn đúng thời điểm.
- Bị thu hồi có hiệu lực.
- Không thể tự nâng quyền.
- Không thể dùng chéo task hoặc tenant.
- Token không xuất hiện trong logs.

### Integration test với executor

Chạy pipeline trong môi trường test và xác nhận:
- Task compile chạy được với quyền đọc source/ghi output.
- Task compile không publish artifact.
- Task publish bị từ chối khi thiếu role.
- Production deploy bị chặn khi thiếu approval.
- Sandbox chặn path traversal và network egress không được phép.
- Secret chỉ xuất hiện trong task được cấp.
- Policy thay đổi trước action được áp dụng.
- Action audit được ghi cả khi success và deny.

### Negative testing

Các trường hợp bị tấn công cần có test:
- Giả mạo principal hoặc tenant.
- Sửa DSL để thêm role tự khai báo.
- Thay executable qua PATH.
- Dùng symbolic link để thoát filesystem sandbox.
- Truyền shell metacharacter trong argument.
- Đọc credential từ home directory.
- Dùng capability hết hạn.
- Reuse approval cho artifact digest khác.
- Replay request deploy.
- Gọi API trực tiếp bỏ qua IDE.

### Concurrency và revocation test

Giả lập:
- Thu hồi role khi job đang chờ.
- Thu hồi token giữa prepare và commit.
- Hai deploy cùng target.
- Approval hết hạn trong lúc rollout.
- Policy service mất kết nối.
- Runner bị terminate giữa một action.

Kiểm tra execution dừng ở trạng thái xác định, không tạo side effect vượt quyền và có audit record đầy đủ.

### Policy regression test

Mỗi thay đổi policy nên chạy bộ test cho các action quan trọng. Có thể lưu policy fixture và authorization decision mong đợi. Thay đổi làm mở rộng quyền cần được review rõ ràng.

## Quy trình thiết kế kiểm soát quyền thực thi cho DSL

Một quy trình triển khai có thể đi theo các bước:

1. **Xác định threat model:** bảo vệ repository, artifact, credential, runner, registry, cloud account và production environment.
2. **Định nghĩa principal:** user, group, service account và workload identity.
3. **Chuẩn hóa action và resource:** dùng tên ổn định, scope rõ và tránh quyền quá rộng.
4. **Chọn authorization model:** RBAC, ABAC, capability hoặc kết hợp.
5. **Đặc tả policy semantics:** ALLOW, DENY, default deny, precedence và indeterminate.
6. **Khai báo permission trong DSL:** gắn quyền với task, plugin, resource và deployment target.
7. **Xây static validation:** resolve policy reference, kiểm tra permission và phát hiện capability thừa.
8. **Xây runtime enforcement:** kiểm tra trước action và trước commit ở server/executor.
9. **Cấp capability tối thiểu:** scope theo task, resource và thời hạn.
10. **Cô lập execution:** filesystem, network, process, CPU, memory và temporary storage.
11. **Bảo vệ secret:** workload identity, short-lived token, injection riêng và redaction.
12. **Thiết kế approval gate:** gắn approval với artifact/plan digest và separation of duties.
13. **Quản lý lifecycle:** expiration, revocation, policy version và TOCTOU.
14. **Ghi audit:** decision, action, approval, identity và outcome.
15. **Kiểm thử:** positive, negative, sandbox escape, concurrency, revocation và policy regression.
16. **Vận hành:** dashboard, alert, review quyền định kỳ và quy trình xử lý sự cố.

Mỗi task nên có một permission manifest dễ xem: action cần dùng, resource được truy cập, capability được cấp, secret reference, network destination và resource limit. Manifest giúp reviewer hiểu tác động trước khi workflow chạy.

## Kết luận

Kiểm soát quyền thực thi trong DSL xây dựng và triển khai xác định principal nào được phép thực hiện action nào trên resource nào và trong context nào. Cơ chế này cần kết hợp authentication, authorization policy, capability, sandbox, approval và audit. RBAC phù hợp với quyền theo vai trò; ABAC biểu diễn điều kiện theo context; capability giới hạn quyền cụ thể của từng task.

Một execution engine an toàn cần kiểm tra quyền khi lập plan và ngay trước action, áp dụng default deny, xử lý policy error theo hướng fail closed, giới hạn quyền của command/plugin, cô lập filesystem và network, bảo vệ secret và gắn approval với đúng artifact hoặc change set. Quyền cần có expiration, revocation và policy version để xử lý thay đổi trong lúc job đang chạy.

IDE và static analysis giúp tác giả phát hiện permission thiếu hoặc quá rộng, nhưng enforcement phải nằm ở runtime và các ranh giới tin cậy của hệ thống. Audit, observability, kiểm thử negative path và kiểm tra concurrency giúp chứng minh rằng một pipeline chỉ thực hiện những hành động đã được cấp phép. Khi permission được mô hình hóa rõ trong DSL và được thực thi nhất quán, build và deployment workflow trở nên dễ kiểm soát, giải thích và vận hành an toàn hơn.
