# Triển khai IaC qua pipeline và kiểm duyệt change set

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vì sao hạ tầng cần được quản lý như mã nguồn và triển khai qua CI/CD có kiểm soát.
- Thiết kế pipeline IaC gồm source, validate/lint, security checks, package, preview, approval, execute và post-deployment verification.
- Phân biệt CloudFormation template, stack, change set, stack policy, drift detection và rollback.
- Tạo CloudFormation change set để xem trước resource additions, modifications, removals và replacements trước khi thay đổi môi trường.
- Đọc change set ở cấp resource/property, đánh giá rủi ro dữ liệu và xác định khi nào cần từ chối hoặc yêu cầu chỉnh sửa.
- Cấu hình CodePipeline CloudFormation actions theo hai mode CHANGE_SET_REPLACE và CHANGE_SET_EXECUTE, đặt manual approval giữa hai bước.
- Phân biệt pipeline service role, deployment/action role và CloudFormation execution role; áp dụng least privilege và iam:PassRole.
- Kiểm tra template bằng cfn-lint, CloudFormation Validate, CloudFormation Guard và các kiểm tra policy/security khác.
- Giữ nguyên artifact đã được kiểm duyệt từ build tới deploy, ràng buộc approval với đúng commit và change set.
- Triển khai nhiều môi trường/tài khoản/Region với cross-account roles, StackSets hoặc AWS CDK Pipelines.
- So sánh CloudFormation change set với CDK diff và Terraform saved plan.
- Bảo vệ stateful resources, xử lý rollback, drift, secrets, IAM changes, nested stacks và deployment failures.

**Bối cảnh module:** Bài thuộc chương **CI/CD trên AWS** trong CLOUD_PROVIDERS_AWS. Module giúp người học chọn dịch vụ và thiết kế hệ thống AWS an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. IaC pipeline là cầu nối giữa thay đổi trong Git và hạ tầng thực tế trong AWS account/Region.

> **Phạm vi:** Ví dụ chính sử dụng AWS CloudFormation và AWS CodePipeline/CodeBuild. CDK và Terraform được trình bày để so sánh. Các tên stack, role, bucket, account, Region và commit trong ví dụ chỉ mang tính minh họa; hãy pin tool versions và kiểm tra reference docs của phiên bản đang dùng.

## 1. Bài toán: một thay đổi template có thể thay đổi cả production

Một nhóm muốn đổi instance type của dịch vụ, mở thêm subnet hoặc cập nhật policy của S3 bucket. Developer sửa template, pipeline deploy thẳng vào production. Nếu một property khiến CloudFormation thay resource cũ bằng resource mới, hệ thống có thể gián đoạn hoặc mất dữ liệu.

Với IaC, Git commit là đề xuất thay đổi trạng thái hạ tầng. Trước khi apply, team cần biết:

- Resource nào sẽ được tạo, cập nhật, xóa hoặc thay thế?
- Property nào thay đổi và replacement có ảnh hưởng dữ liệu không?
- Có thêm IAM permissions, public access hoặc network exposure không?
- Parameters, secrets, quotas, dependencies và stack policies có phù hợp?
- Ai đã review và ai có quyền cho phép thay đổi production?
- Pipeline có deploy đúng artifact đã được review không?

~~~mermaid
flowchart LR
    Dev[Developer / Pull request] --> Git[Source repository]
    Git --> CI[Validate / Lint / Security]
    CI --> Package[Immutable IaC artifact]
    Package --> Plan[Create change set]
    Plan --> Review[Review resource diff]
    Review --> Gate[Approval]
    Gate --> Deploy[Execute change set]
    Deploy --> Verify[Verify / Monitor / Drift]
~~~

Pipeline tốt tạo ra bằng chứng rõ ràng: commit nào tạo artifact nào, artifact đó đề xuất thay đổi gì, ai phê duyệt, change set nào đã được thực thi và kết quả ra sao.

## 2. IaC deployment khác application deployment ở điểm nào?

Application deployment thường thay binary/container image và điều chỉnh traffic. IaC deployment thay đổi tài nguyên nền tảng: VPC, subnet, route, security group, IAM role, S3 bucket, database, queue, load balancer hoặc service configuration.

| Khía cạnh | Application delivery | IaC delivery |
| --- | --- | --- |
| Artifact | JAR, container image, static bundle | Template, synthesized template, module/configuration, variables |
| Preview | Test, package, deployment plan | CloudFormation change set, CDK diff, Terraform plan |
| Rủi ro | Runtime error, regression, downtime | Resource replacement/deletion, data loss, privilege/network changes |
| Rollback | Deploy version trước hoặc shift traffic | Stack rollback/redeploy config cũ; có thể không khôi phục dữ liệu đã mất |
| Approval | Release/quality gate | Hạ tầng, security, data owner và change-management review |
| Audit | Build/release history | Commit, artifact digest, change set, CloudTrail, stack events |

Một template hợp lệ về cú pháp chưa chắc deploy được. Một change set được tạo thành công cũng chưa bảo đảm mọi resource operation sẽ thành công khi execute. Vì vậy pipeline phải có nhiều lớp kiểm tra.

## 3. Kiến trúc pipeline IaC tham khảo

Với CloudFormation, một pipeline phổ biến dùng CodePipeline điều phối và CodeBuild chạy validation/package scripts.

~~~mermaid
flowchart TD
    Source[Git source / PR merge] --> Validate[Template validation]
    Validate --> Policy[Policy as code / Security scan]
    Policy --> Test[Unit / Integration / Contract tests]
    Test --> Package[Package templates and assets]
    Package --> Dev[Deploy dev change set]
    Dev --> Smoke[Smoke tests / drift check]
    Smoke --> Stage[Stage change set]
    Stage --> Review[Change set review]
    Review --> Approve[Manual approval]
    Approve --> Prod[Execute production change set]
    Prod --> Verify[Stack events / alarms / outputs]
    Verify --> Audit[Record evidence / notify]
~~~

Các stage nên có trách nhiệm riêng:

1. **Source:** lấy đúng revision từ repository.
2. **Validate:** parse, lint và kiểm tra CloudFormation resource schemas.
3. **Policy/Security:** đánh giá encryption, public exposure, IAM privilege, tags và organizational policies.
4. **Test:** kiểm tra module, nested templates, helper scripts và integration behavior.
5. **Package:** upload templates/assets, tạo manifest có commit SHA và checksum.
6. **Deploy non-production:** tạo change set, review/deploy theo policy rồi smoke test.
7. **Production preview:** tạo change set trên account/Region đích.
8. **Approval:** người có thẩm quyền xem diff và rủi ro.
9. **Execute:** thực thi đúng change set đã được duyệt.
10. **Verify/Audit:** theo dõi stack events, alarms, outputs, CloudTrail và drift.

Không phải mọi thay đổi đều cần cùng một approval path. Thay đổi tag có thể dùng gate nhẹ hơn; thay đổi IAM, network perimeter, KMS, database hoặc production data cần reviewer chuyên trách.

## 4. CloudFormation template, stack và change set

**Template** là mô tả declarative của resources và cấu hình mong muốn. **Stack** là một instance được CloudFormation quản lý từ template và parameters. **Change set** là bản preview những thay đổi CloudFormation dự kiến thực hiện khi cập nhật hoặc tạo stack.

~~~mermaid
flowchart TD
    Template[CloudFormation template] --> Stack[Stack: orders-prod]
    Parameters[Parameters / mappings] --> Stack
    Current[Current stack state] --> Diff[CloudFormation comparison]
    NewTemplate[Proposed template + parameters] --> Diff
    Diff --> CS[Change set]
    CS -->|Review only| Reviewer[Reviewer]
    Reviewer -->|Approve| Execute[Execute change set]
    Execute --> Updated[Updated stack]
~~~

Khi tạo change set, CloudFormation so sánh template/parameters mới với stack và mô tả resource changes. Hạ tầng chưa được cập nhật chỉ vì change set đã được tạo. Thay đổi bắt đầu khi change set được execute.

Với stack mới, change set có thể tạo stack ở trạng thái REVIEW_IN_PROGRESS; resources chỉ được tạo sau khi execute.

Tài liệu: [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html).

## 5. Chọn cách tổ chức IaC trong repository

Một repository có thể chứa nhiều stacks và modules. Hãy làm rõ ownership và deployment boundary để một pipeline không vô tình thay đổi môi trường ngoài phạm vi.

Ví dụ:

~~~text
infrastructure/
  network/
    template.yaml
    parameters/
      dev.json
      prod.json
  application/
    template.yaml
    nested/
      database.yaml
      service.yaml
  security/
    iam-roles.yaml
  policies/
    guard/
      s3-encryption.guard
      iam-boundary.guard
  tests/
    fixtures/
  scripts/
    validate.ps1
    package.sh
  pipeline/
    buildspec.yml
~~~

Quy tắc tổ chức hữu ích:

- Mỗi stack có owner, purpose, environment và deployment account rõ ràng.
- Tách shared foundations (network/security/logging) khỏi application stacks khi lifecycle khác nhau.
- Dùng nested stacks hoặc modules có version khi thực sự cần reuse.
- Không copy/paste cùng resource definition sang nhiều account nếu có thể parameterize hoặc dùng StackSets.
- Template, policy rules, parameters và scripts phải được version control.
- Không đưa secret values, state files hoặc credentials vào repository.
- Tên stack ổn định, dễ truy vết và không chứa dữ liệu nhạy cảm.

## 6. Xác định deployment contract trước khi tạo pipeline

Mỗi stack nên có deployment contract, tức là tập đầu vào và ràng buộc mà pipeline phải kiểm tra.

| Thành phần | Ví dụ |
| --- | --- |
| Stack name | orders-network-prod |
| Target account | AWS account production đã được chỉ định |
| Region | ap-southeast-1 |
| Template artifact | network/packaged.yaml |
| Parameter set | parameters/prod.json |
| CloudFormation execution role | CfnOrdersDeployRole |
| Capabilities | CAPABILITY_NAMED_IAM nếu template tạo named IAM resources |
| Change set name | orders-prod-a1b2c3d |
| Approval group | Platform + Security + Service owner |
| Verification | Stack status, outputs, alarms, smoke tests |

Pipeline nên fail sớm nếu account ID, Region, stack name, template digest hoặc environment mapping không khớp deployment contract.

Dùng AWS::AccountId, AWS::Region, AWS::Partition và parameters có constraints để template portable hơn. Không hardcode account/Region vào ARN nếu có thể tạo ARN bằng pseudo parameters và Fn::Sub.

## 7. Validate template trước khi truy cập AWS

Validation nên chạy ở pull request và chạy lại trong pipeline trước khi package/deploy.

| Lớp | Công cụ/kiểm tra | Phát hiện |
| --- | --- | --- |
| YAML/JSON parse | YAML/JSON parser | Cú pháp sai |
| CloudFormation schema | cfn-lint, cfn-validate | Property sai, required fields thiếu, type mismatch |
| Template checks | CloudFormation Validate | Intrinsic references, resource schema và best-practice findings theo tool |
| Policy as code | CloudFormation Guard | Vi phạm quy tắc tổ chức |
| Security scan | IAM Access Analyzer, scanners phù hợp | Quyền quá rộng, secret/public exposure |
| AWS pre-deployment validation | Change set creation validation | Một số lỗi phụ thuộc account/Region/quota/resource state |

Ví dụ chạy validation trong CodeBuild:

~~~bash
set -euo pipefail

cfn-lint infrastructure/**/*.yaml
cfn-validate infrastructure/ --strict

cfn-guard validate \
  --rules infrastructure/policies/guard/ \
  --data infrastructure/network/template.yaml
~~~

Pin version của cfn-lint, cfn-validate và Guard trong build image/tool installer. Với nhiều templates, chạy validation trên tất cả templates, bao gồm nested templates và templates được sinh từ CDK/SAM.

Lưu ý: cfn-guard đánh giá policy trên dữ liệu YAML/JSON; nó không thay thế template syntax/schema validation. cfn-validate có thể kiểm tra template cục bộ nhưng không chứng minh deployment sẽ thành công trong account/Region hiện tại.

Tài liệu: [CloudFormation Validate](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html), [CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html).

## 8. Policy as code: đưa guardrails vào pipeline

Policy as code biến quy định bảo mật thành rules có thể chạy tự động. Ví dụ:

- S3 buckets phải bật encryption và block public access.
- EBS/RDS storage phải được mã hóa.
- Security groups không mở SSH/RDP cho toàn Internet trừ ngoại lệ được duyệt.
- IAM policies không dùng wildcard actions/resources ngoài allowlist.
- Resources bắt buộc có tags Environment, Owner, CostCenter.
- Database production phải bật backup/retention phù hợp.
- CloudTrail/logging/network controls không được tắt trong stack nền tảng.

Một rule minh họa của Guard:

~~~guard
let s3_buckets = Resources.*[ Type == "AWS::S3::Bucket" ]

rule s3_buckets_require_encryption when %s3_buckets !empty {
    %s3_buckets.Properties.BucketEncryption exists
}

rule s3_buckets_block_public_access when %s3_buckets !empty {
    %s3_buckets.Properties.PublicAccessBlockConfiguration exists
}
~~~

Đây là policy mẫu đơn giản; production rules cần xét inherited settings, exceptions, nested templates và các resource types liên quan.

**Guard CLI là kiểm tra trong pipeline.** Nếu cần enforce ở phía CloudFormation khi stack operation diễn ra, xem xét CloudFormation Hooks/Guard Hooks. Không giả định một bước scan trong CI có thể ngăn mọi thay đổi ngoài pipeline.

## 9. Package template và giữ artifact bất biến

Một pipeline phải triển khai đúng template đã được validate/review. Nếu template được package lại sau approval, nội dung có thể khác với thứ reviewer đã xem.

Quy trình:

1. Checkout commit cụ thể.
2. Validate và test template.
3. Upload nested templates, Lambda code hoặc assets lên artifact bucket.
4. Sinh packaged template và manifest.
5. Tính checksum/digest.
6. Gắn commit SHA, build ID, target environment và tool versions vào metadata.
7. Chuyển cùng artifact đó qua các stages.

Ví dụ manifest:

~~~json
{
  "repository": "platform-infrastructure",
  "commit": "a1b2c3d4e5f6",
  "buildId": "build-2026-11-20-001",
  "template": "network/packaged.yaml",
  "sha256": "REPLACE_WITH_REAL_SHA256",
  "target": {
    "environment": "prod",
    "region": "ap-southeast-1"
  }
}
~~~

Không dùng giá trị checksum giả như ví dụ trong manifest thật; pipeline phải tính checksum từ artifact bytes. Bật encryption và versioning cho artifact bucket, giới hạn quyền đọc/ghi và dùng KMS key policy phù hợp. Không cho một stage tùy ý ghi đè artifact đã được review.

## 10. Parameters, secrets và environment configuration

Parameters nên tách biệt khỏi template khi khác nhau theo environment, nhưng vẫn phải có kiểm soát.

- Dùng parameter files được version control cho non-secret settings.
- Dùng CloudFormation parameter types cho AWS resources khi phù hợp.
- Dùng dynamic references tới Secrets Manager/Parameter Store thay vì embed secret.
- Dùng NoEcho để hạn chế hiển thị parameter nhạy cảm, nhưng đừng xem NoEcho là secret storage.
- Không ghi secret values vào build logs, CodePipeline action configuration hoặc artifact.
- Không đưa secret vào change set description/approval comments.
- Kiểm tra UsePreviousValue và parameter overrides để tránh vô tình giữ giá trị cũ không mong muốn.

Ví dụ parameter file không chứa secret:

~~~json
[
  {
    "ParameterKey": "Environment",
    "ParameterValue": "prod"
  },
  {
    "ParameterKey": "InstanceType",
    "ParameterValue": "t3.small"
  }
]
~~~

Nếu cần database password, hãy dùng Secrets Manager dynamic reference hoặc một secret lifecycle phù hợp; IAM role của CloudFormation/resource runtime phải có quyền cần thiết ở đúng thời điểm resolve.

## 11. IAM identity của pipeline và nguyên tắc least privilege

Pipeline thường cần nhiều loại quyền. Không nên gom tất cả vào một role với AdministratorAccess.

| Identity | Vai trò |
| --- | --- |
| CodePipeline service role | Cho phép CodePipeline gọi source/build/deploy/approval actions và đọc/ghi artifacts |
| CodeBuild service role | Chạy build/test, đọc source/artifacts và ghi reports |
| Cross-account deployment role | Cho pipeline ở tooling account truy cập quyền deploy trong target account |
| CloudFormation execution/service role | CloudFormation assume để tạo/cập nhật resource |
| Runtime role | Workload sau khi triển khai dùng để truy cập AWS services |

Cấp quyền theo stack/resource scope, actions cần thiết và target account. Tách quyền tạo change set khỏi quyền phê duyệt khi cần separation of duties.

Không để CodeBuild chạy script từ pull request không tin cậy với role production. Với PR từ fork hoặc contributor không có quyền deploy, chỉ cấp quyền validation không có AWS write access.

## 12. Phân biệt CodePipeline role, cross-account action role và CloudFormation execution role

Đây là phần dễ nhầm khi cấu hình CodePipeline CloudFormation action.

**CodePipeline service role** cho phép pipeline điều phối stages/actions và chuyển artifacts. Khi action chạy ở account khác, **ActionDeclaration.RoleArn** có thể chỉ định cross-account action role mà CodePipeline assume để chạy action trong target account. Trong CloudFormation action configuration, **Configuration.RoleArn** là CloudFormation service role mà CloudFormation assume để thực hiện resource operations. Đây là hai RoleArn ở hai lớp cấu hình khác nhau. Runtime workload sau deploy có role riêng.

~~~mermaid
flowchart TD
    Pipeline[CodePipeline service role] --> Action[CloudFormation deploy action]
    Action -->|Create change set / pass role| CFN[CloudFormation]
    CFN -->|Assume service role| Exec[CloudFormation execution role]
    Exec --> Resources[AWS resources]
    Reviewer[Approval identity] --> Gate[Manual approval]
    Gate --> Execute[Execute approved change set]
~~~

Nếu không dùng cross-account action role, CodePipeline service role cần quyền gọi CloudFormation actions trực tiếp. Nếu dùng ActionDeclaration.RoleArn, pipeline service role cần quyền assume đúng action role; action role cần quyền CloudFormation cần thiết và quyền iam:PassRole cho CloudFormation service role. CloudFormation execution role mới mang permissions tạo/cập nhật resource.

Giới hạn iam:PassRole vào ARN role cụ thể và condition iam:PassedToService khi phù hợp. Trust policy của execution role phải cho phép cloudformation.amazonaws.com assume role. Với cross-account, cần thêm trust relationship và role assumption ở target account.

Với cross-account CloudFormation action, ActionDeclaration.RoleArn là role CodePipeline assume để chạy action trong target account. Configuration.RoleArn là CloudFormation service role và phải nằm cùng account với action role. Action role cần đọc artifact bucket để tạo S3-signed URL cho template; CloudFormation service role không cần quyền đọc artifact bucket vì CloudFormation nhận signed URL.

Theo CloudFormation action reference, Configuration.RoleArn gắn với service role mà CloudFormation sử dụng khi thao tác resources. Trường này được yêu cầu ở CHANGE_SET_REPLACE; nó không được áp dụng lại ở CHANGE_SET_EXECUTE. Change set/stack cần có service role được gắn từ bước tạo change set. ActionDeclaration.RoleArn, nếu dùng, là role CodePipeline assume để chạy action và có semantics khác. Đọc kỹ action mode và account/role context của pipeline đang dùng.

## 13. Change set hoạt động như thế nào?

Quy trình cơ bản:

1. Pipeline cung cấp template mới, parameters và stack options.
2. CloudFormation so sánh đề xuất với stack hiện tại.
3. CloudFormation tạo change set.
4. Reviewer xem resource changes và property-level details.
5. Nếu cần, team tạo change set khác hoặc hủy change set hiện tại.
6. Sau approval, pipeline execute change set.
7. CloudFormation cập nhật stack và phát stack events.

Change set không sửa resources khi mới tạo. Có thể tạo nhiều change sets để so sánh các phương án. Khi execute một change set, các change sets khác của stack trở nên không còn áp dụng và bị xóa.

**Giới hạn quan trọng:** change set không bảo đảm execute sẽ thành công. Runtime conditions, service limits, custom resources, permissions, dependency timing hoặc service-specific constraints vẫn có thể khiến deployment thất bại.

## 14. Các loại change set và trạng thái cần hiểu

| Trường hợp | ChangeSetType | Ý nghĩa |
| --- | --- | --- |
| Tạo stack mới | CREATE | Preview resources sẽ được tạo |
| Cập nhật stack hiện có | UPDATE | Preview changes so với stack |
| Import resources vào stack | IMPORT | Preview resource import operation |

CloudFormation trả hai trường trạng thái riêng:

| Trường | Giá trị | Ý nghĩa |
| --- | --- | --- |
| ChangeSetStatus | CREATE_PENDING | Đang tạo change set |
| ChangeSetStatus | CREATE_IN_PROGRESS | CloudFormation đang xử lý việc tạo |
| ChangeSetStatus | CREATE_COMPLETE | Change set đã sẵn sàng review |
| ChangeSetStatus | FAILED | Không tạo được change set hoặc không có thay đổi áp dụng |
| ExecutionStatus | AVAILABLE | Change set có thể được execute |
| ExecutionStatus | EXECUTE_IN_PROGRESS | Đang execute |
| ExecutionStatus | EXECUTE_COMPLETE | Change set execution hoàn tất |
| ExecutionStatus | OBSOLETE | Change set không còn áp dụng với stack hiện tại |
| ExecutionStatus | UNAVAILABLE | Change set không thể được execute |

Một change set có thể ở FAILED với reason “The submitted information didn't contain changes” khi template/parameters không tạo ra khác biệt. Pipeline nên phân loại no-op thành kết quả không cần deploy sau khi xác minh status reason; không coi mọi FAILED là no-op.

## 15. Đọc resource changes: Add, Modify, Remove và Replacement

Change set cho biết các resource sẽ thay đổi:

| Action | Ý nghĩa | Câu hỏi review |
| --- | --- | --- |
| Add | Tạo resource mới | Có public exposure, quota, cost hoặc IAM impact không? |
| Modify | Cập nhật resource | Property nào đổi? Có downtime hoặc service disruption không? |
| Remove | Xóa resource khỏi stack | Resource có chứa dữ liệu hoặc đang được workload sử dụng không? |
| Import | Import resource có sẵn | Resource identity và drift đã được xác minh chưa? |
| Replacement | Thay resource hiện tại bằng resource mới | Resource cũ có bị xóa? Data migration/backup đã sẵn sàng chưa? |

Replacement thường được thể hiện qua Replacement với các giá trị True, False hoặc Conditional.

- True: CloudFormation dự kiến thay resource.
- False: resource được cập nhật tại chỗ hoặc không cần thay thế.
- Conditional: việc thay thế phụ thuộc giá trị/property/runtime behavior.

Không chỉ nhìn số lượng Add/Modify/Remove. Một Modify trên IAM policy hoặc security group có thể rủi ro hơn nhiều resource mới. Một replacement của RDS, EFS, KMS key hoặc S3 bucket cần đánh giá data retention và migration.

## 16. Change set không phải kế hoạch downtime/data migration

CloudFormation change set preview resource-level changes; nó không mô phỏng đầy đủ mọi tác động ở tầng ứng dụng.

Ví dụ:
- Thay DB instance identifier có thể tạo database mới và loại bỏ database cũ theo update behavior.
- Thay subnet/route/security group có thể cắt kết nối đang chạy.
- Thay KMS key có thể khiến workload không đọc được ciphertext cũ nếu key lifecycle sai.
- Thay S3 bucket name thường không phải update tại chỗ.
- Thay IAM policy có thể làm deployment hoặc runtime bị AccessDenied.
- Custom resource có thể chạy code với side effects mà change set không mô tả đầy đủ.

Với stateful resources, review phải kết hợp change set, resource update behavior trong CloudFormation reference, backup/restore plan, data migration và runbook rollback.

Dùng DeletionPolicy và UpdateReplacePolicy phù hợp để bảo vệ resources cần giữ dữ liệu. Những policies này không thay thế backup/restore test và không bảo đảm ứng dụng không downtime.

## 17. Tạo change set bằng AWS CLI

Ví dụ cập nhật stack orders-network-prod. Pipeline đã package template và có parameter file:

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d \
  --change-set-type UPDATE \
  --template-body file://packaged.yaml \
  --parameters file://parameters-prod.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --role-arn arn:aws:iam::111122223333:role/CfnOrdersDeployRole \
  --description "commit=a1b2c3d environment=prod"
~~~

Change set name phải unique trong phạm vi stack, bắt đầu bằng chữ cái và chỉ dùng chữ/số/dấu gạch nối; nên gắn short commit SHA hoặc pipeline execution ID để các lần chạy song song không ghi đè tên nhau. Giới hạn tên là 128 ký tự.

Trong API CloudFormation, TemplateBody có giới hạn 51.200 bytes; với template lớn hơn, upload template lên S3 và dùng TemplateURL/CLI option template-url. TemplateURL của CloudFormation hỗ trợ template tối đa 1 MB. Với nested templates hoặc assets, package step nên upload các file lên artifact bucket và tạo URL tham chiếu ổn định.

Chờ change set và đọc metadata:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d
~~~

Đọc chi tiết resource changes:

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d \
  --query "Changes[].ResourceChange"
~~~

Chỉ sau khi reviewer chấp thuận mới thực thi:

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-network-prod \
  --change-set-name orders-prod-a1b2c3d

aws cloudformation wait stack-update-complete \
  --stack-name orders-network-prod
~~~

Trong automation, xử lý riêng CREATE và UPDATE, stack chưa tồn tại, no-op change set và failure reason. Lệnh wait cho change set không thay thế việc kiểm tra status reason khi create-change-set thất bại. Đừng tự động execute chỉ vì describe-change-set trả kết quả.

## 18. Checklist review change set

Reviewer nên đọc change set cùng template/commit/manifest, không chỉ nhìn thông báo deployment ready.

| Nhóm review | Câu hỏi |
| --- | --- |
| Identity/scope | Đúng account, Region, stack, environment và owner chưa? |
| Artifact | Template digest có trùng artifact được pipeline build không? |
| Resource actions | Add/Modify/Remove/Import có hợp lý không? |
| Replacement | Resource nào replacement True hoặc Conditional? |
| Data | Có RDS/S3/EFS/KMS/data-bearing resources không? Backup/restore test ở đâu? |
| IAM | Có thêm actions/resources, trust principals hoặc permissions boundary changes không? |
| Network | Có mở public ingress, route, endpoint hoặc egress mới không? |
| Encryption | KMS key, bucket/database encryption có thay đổi không? |
| Availability | Có replacement, restart, rolling update, quota hoặc downtime risk không? |
| Cost | Có instance/throughput/storage/retention tăng không? |
| Nested stacks | Change set của nested stacks có được bật và review không? |
| Drift | Stack hiện tại có drift chưa được reconcile không? |
| Rollback | Stack policy, deletion policy, rollback alarms và recovery plan có phù hợp không? |
| Evidence | Có approval comment, ticket/change ID và approver identity không? |

### Ví dụ phân loại rủi ro

| Thay đổi | Rủi ro mặc định | Hành động review |
| --- | --- | --- |
| Thêm tag CostCenter | Thấp | Xác minh tag policy |
| Tăng ECS desired count | Trung bình | Kiểm tra capacity/cost/alarms |
| Mở ingress 0.0.0.0/0 | Cao | Security review, justification và thời hạn |
| Thay IAM trust policy | Cao | Xác minh principal/assume path |
| Replace RDS instance | Rất cao | Backup, migration, maintenance window, owner approval |
| Xóa KMS key/resource | Rất cao | Kiểm tra dependency, retention và recoverability |

Không có risk score chung thay cho review theo resource type và business context.

## 19. CodePipeline: tạo change set trước approval

CloudFormation deploy action có thể tạo hoặc thay thế change set. Action mode tương ứng là CHANGE_SET_REPLACE. Pipeline dừng ở manual approval để reviewer xem change set. Nếu được duyệt, action tiếp theo dùng CHANGE_SET_EXECUTE.

~~~mermaid
flowchart TD
    Build[Build artifact] --> Create[CloudFormation CHANGE_SET_REPLACE]
    Create --> Review[Reviewer opens change set]
    Review --> Decision{Approve?}
    Decision -->|Reject / timeout| Stop[Pipeline fails / stop]
    Decision -->|Approve| Execute[CloudFormation CHANGE_SET_EXECUTE]
    Execute --> Verify[Verify stack]
~~~

AWS CodePipeline manual approval action làm pipeline tạm dừng cho tới khi một identity có quyền approve/reject phản hồi. Nếu bị reject hoặc không phản hồi trong bảy ngày, action thất bại và pipeline không tiếp tục.

Tài liệu: [CodePipeline CloudFormation action](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CloudFormation.html), [Manual approval actions](https://docs.aws.amazon.com/codepipeline/latest/userguide/approvals.html).

## 20. Ví dụ cấu hình CloudFormation action trong CodePipeline

Đoạn dưới minh họa cấu hình action trong một stage. BuildArtifact chứa template đã package và parameter/config artifact:

~~~yaml
- Name: CreateChangeSet
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: "1"
  RunOrder: 1
  InputArtifacts:
    - Name: BuildArtifact
  Configuration:
    ActionMode: CHANGE_SET_REPLACE
    StackName: orders-network-prod
    ChangeSetName: orders-prod-a1b2c3d
    TemplatePath: BuildArtifact::packaged.yaml
    TemplateConfiguration: BuildArtifact::prod-config.json
    Capabilities: CAPABILITY_NAMED_IAM
    RoleArn: arn:aws:iam::111122223333:role/CfnOrdersDeployRole

- Name: ApproveInfrastructureChange
  ActionTypeId:
    Category: Approval
    Owner: AWS
    Provider: Manual
    Version: "1"
  RunOrder: 2
  Configuration:
    CustomData: "Review the exact CloudFormation change set for orders-network-prod."
    ExternalEntityLink: "https://console.aws.amazon.com/cloudformation/home"

- Name: ExecuteChangeSet
  ActionTypeId:
    Category: Deploy
    Owner: AWS
    Provider: CloudFormation
    Version: "1"
  RunOrder: 3
  InputArtifacts:
    - Name: BuildArtifact
  Configuration:
    ActionMode: CHANGE_SET_EXECUTE
    StackName: orders-network-prod
    ChangeSetName: orders-prod-a1b2c3d
    Capabilities: CAPABILITY_NAMED_IAM
~~~

Đây là fragment minh họa, không phải toàn bộ CodePipeline definition. Pipeline cần source/build stages, artifact store, service role, target account/Region configuration và notification/approval permissions. TemplatePath phải trỏ đúng file trong artifact; TemplateConfiguration là optional.

Nếu dùng nested stacks, cấu hình change set creation để bao gồm nested stack changes khi cần review toàn bộ hierarchy. Với template có IAM resources, cung cấp capability phù hợp và review quyền IAM mới trước khi execute.

### Capabilities cần phân biệt

- CAPABILITY_IAM: acknowledge template có IAM resources không dùng custom names.
- CAPABILITY_NAMED_IAM: acknowledge template có IAM resources được đặt custom names; đây cũng là lựa chọn cần dùng khi resource IAM có tên tùy chỉnh.
- CAPABILITY_AUTO_EXPAND: acknowledge macro transforms khi tạo stack trực tiếp mà không review change set. Khi dùng change set để review macro-expanded result, capability này không có tác dụng ở bước tạo change set; hãy review resources sau transform.

## 21. Manual approval phải phê duyệt đúng revision và change set

Một approval action đơn giản có thể dừng pipeline, nhưng chất lượng review phụ thuộc thông tin reviewer nhận được.

Approval context nên có:

- Repository và commit SHA;
- Build ID và artifact checksum;
- Stack name, account ID và Region;
- Change set name/ARN và creation time;
- Summary resource actions và replacement;
- Link tới CloudFormation change set;
- Link tới pull request, ticket và test results;
- Reviewer group và thời hạn approval;
- Risk summary và rollback plan.

**Không rebuild hoặc tạo change set mới sau approval rồi execute artifact mới.** Nếu template/parameters/stack state thay đổi, tạo change set mới và yêu cầu review lại. Approval gắn với đúng proposed change, không phải chỉ với tên pipeline.

Separation of duties có thể yêu cầu người tạo change không phải người approve production. Chỉ cấp codepipeline:PutApprovalResult cho nhóm được phép phê duyệt.

## 22. Execute, monitor và xác minh sau deploy

Sau approval, pipeline execute đúng change set. CloudFormation bắt đầu stack operation và phát stack events.

Kiểm tra:

1. Action CHANGE_SET_EXECUTE hoàn tất;
2. Stack status về UPDATE_COMPLETE hoặc trạng thái thành công tương ứng;
3. Không còn resources ở trạng thái UPDATE_FAILED, DELETE_FAILED hoặc rollback;
4. Outputs đúng với expected values;
5. Application smoke tests pass;
6. CloudWatch alarms không chuyển ALARM;
7. Health checks, connectivity, IAM access và service metrics bình thường;
8. CloudTrail/CodePipeline history lưu đủ evidence.

Ví dụ CLI:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-network-prod \
  --query "Stacks[0].[StackStatus,Outputs]"

aws cloudformation describe-stack-events \
  --stack-name orders-network-prod \
  --max-items 30
~~~

Không xem action status started là deploy thành công. Theo dõi đến terminal stack status và xác minh behavior của workload.

## 23. Rollback và bảo vệ resource quan trọng

CloudFormation có thể rollback stack operation khi resource update thất bại, nhưng rollback không phải backup/restore. Những side effects ngoài CloudFormation hoặc data đã bị xóa có thể không được khôi phục.

| Cơ chế | Mục đích |
| --- | --- |
| DeletionPolicy | Quy định hành vi khi resource bị remove khỏi stack hoặc stack bị xóa |
| UpdateReplacePolicy | Quy định xử lý physical resource cũ khi replacement |
| Stack policy | Ngăn update các resources được bảo vệ |
| Termination protection | Chặn xóa stack ngoài ý muốn |
| Rollback triggers | Theo dõi CloudWatch alarms trong stack operation và rollback khi alarm kích hoạt |
| Backup/restore | Khôi phục dữ liệu theo RPO/RTO |
| Change approval | Chặn thay đổi rủi ro trước khi execute |

Ví dụ bảo vệ database:

~~~yaml
Resources:
  OrdersDatabase:
    Type: AWS::RDS::DBInstance
    DeletionPolicy: Snapshot
    UpdateReplacePolicy: Snapshot
    Properties:
      DBInstanceClass: db.t4g.small
      Engine: postgres
      AllocatedStorage: 50
      StorageEncrypted: true
~~~

Ví dụ là fragment; production template phải khai báo engine/version/credentials/network/backup options phù hợp. Snapshot policy không thay thế backup retention, restore drills hoặc database migration strategy.

## 24. Stack policy và termination protection

Stack policy là JSON document quy định CloudFormation được phép update resource nào trong stack. Có thể deny updates tới RDS, KMS key hoặc resource quan trọng trừ khi có quy trình break-glass được duyệt.

Termination protection ngăn stack bị delete; nó không ngăn mọi resource update. Stack policy không phải IAM policy: IAM kiểm soát ai gọi CloudFormation APIs, còn stack policy kiểm soát những resource update mà CloudFormation được phép thực hiện.

Khi change set được execute, CloudFormation áp dụng stack policy hiện có. Nếu change set cần update resource bị bảo vệ, phải xử lý stack policy theo quy trình có kiểm soát trước khi execute. Không vô hiệu hóa policy chỉ để pipeline xanh.

## 25. Drift detection: phát hiện thay đổi ngoài IaC pipeline

**Drift** xảy ra khi cấu hình resource thực tế khác cấu hình được CloudFormation quản lý. Ví dụ một người thay security group rule trực tiếp trong console, nhưng template không được cập nhật.

CloudFormation drift detection so sánh actual resource properties với expected properties từ template/parameters cho những resource types hỗ trợ drift detection.

~~~mermaid
flowchart LR
    Template[Template state] --> Expected[Expected properties]
    Console[Manual console change] --> Actual[Actual resource state]
    Expected --> Compare[Drift detection]
    Actual --> Compare
    Compare --> Result{Drift?}
    Result -->|No| Clean[IN_SYNC]
    Result -->|Yes| Drift[MODIFIED / DELETED]
    Drift --> Reconcile[Reconcile template or resource]
~~~

Quy trình xử lý:

1. Detect drift định kỳ và trước change lớn;
2. Xác định người/automation tạo thay đổi qua CloudTrail;
3. Đánh giá thay đổi có hợp lệ không;
4. Nếu hợp lệ, cập nhật template/parameters để IaC phản ánh desired state;
5. Nếu không hợp lệ, tạo change set đưa resource về trạng thái mong muốn;
6. Re-run drift detection và ghi nhận kết quả.

Không phải mọi resource property đều được drift detection hỗ trợ; kết quả cũng cần được diễn giải theo giới hạn resource provider. Drift-aware change sets có thể giúp xem xét/reconcile một số drifted resources, nhưng vẫn phải review kỹ.

Tài liệu: [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html).

## 26. Triển khai cross-account và multi-Region

Mô hình thường gặp là tooling account chứa repository/artifact/pipeline, còn dev/stage/prod nằm ở các workload accounts.

~~~mermaid
flowchart TD
    Tooling[Tooling account: CodePipeline] --> DevRole[Assume DevDeploymentRole]
    Tooling --> StageRole[Assume StageDeploymentRole]
    Tooling --> ProdRole[Assume ProdDeploymentRole]
    DevRole --> Dev[Dev account / Region]
    StageRole --> Stage[Stage account / Region]
    ProdRole --> Prod[Prod account / Region]
~~~

Nguyên tắc:

- Pipeline identity chỉ được assume target roles đã allowlist.
- Trust policy target role chỉ tin đúng tooling account/role và conditions cần thiết.
- Target role chỉ được phép deploy stacks/resources trong phạm vi.
- CloudFormation execution role tách riêng và giới hạn permissions.
- Artifact bucket/KMS key policy cho phép target actions đọc artifact cần thiết.
- Approval cho production nằm trước execute action.
- Mỗi environment có parameters/stack names/Region rõ ràng.
- Dùng STS short-term credentials, không lưu access keys lâu dài.

Cross-account deployment trong CodePipeline cần cấu hình artifact store encryption/key policies và action role phù hợp. Không chỉ thêm RoleArn rồi giả định trust, iam:PassRole, artifact access và KMS access tự động hoạt động.

## 27. StackSets cho hạ tầng dùng chung trên nhiều accounts

CloudFormation StackSets cho phép triển khai một template tới nhiều AWS accounts và Regions trong một operation.

Phù hợp cho baseline IAM roles, CloudTrail/Config/security controls, VPC endpoints/shared networking, logging/monitoring agents và organization-wide guardrails.

StackSets hỗ trợ self-managed permissions và service-managed permissions qua AWS Organizations. Service-managed model có thể target organization hoặc OUs; delegated administrator có thể quản lý StackSets nếu đã bật trusted access.

Đặt concurrency và failure tolerance cẩn thận. Với hạ tầng nền tảng, triển khai tuần tự hoặc canary accounts trước rồi mới mở rộng. Không đặt concurrency quá cao khi thay đổi có thể ảnh hưởng nhiều workload accounts.

Tài liệu: [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html).

## 28. AWS CDK: synth và diff trước khi deploy

AWS CDK cho phép định nghĩa hạ tầng bằng ngôn ngữ lập trình. Pipeline chạy cdk synth để tạo CloudFormation templates; cdk diff so sánh proposed template với deployed stack; deployment cuối cùng vẫn sử dụng CloudFormation.

~~~bash
npm ci
npm test
npx cdk synth --all
npx cdk diff OrdersNetworkProd
~~~

Một số lưu ý:

- Review synthesized templates, không chỉ review TypeScript/Python code.
- Kiểm tra asset manifests, Docker/Lambda assets và bootstrap bucket references.
- CDK diff có thể báo changes nhưng không thay CloudFormation change set trong mọi workflow.
- CDK Pipelines có thể tự động synth/deploy stages và hỗ trợ manual approval steps.
- CDK bootstrap roles/buckets cần trust policy và permissions phù hợp, đặc biệt cross-account.
- Pin CDK CLI/library versions để synth output ổn định.

Với production, có thể kết hợp CDK synth → artifact → CloudFormation change set → approval → execute, tùy pipeline design.

## 29. Terraform: plan/apply là preview tương ứng

Nếu IaC dùng Terraform, workflow tương tự nhưng preview artifact là saved plan, không phải CloudFormation change set.

~~~bash
terraform init -input=false
terraform fmt -check -recursive
terraform validate

terraform plan \
  -input=false \
  -out=tfplan

terraform show -no-color tfplan
~~~

Sau approval, apply chính saved plan:

~~~bash
terraform apply -input=false tfplan
~~~

Điểm quan trọng:

- terraform plan không thay đổi infrastructure.
- terraform plan -out=tfplan lưu execution plan cụ thể để automation apply sau review.
- terraform apply tfplan thực thi plan đã lưu mà không tạo prompt approval mới.
- Plan file có thể chứa sensitive values ở dạng cleartext dù terminal output đã mask; bảo vệ như secret artifact.
- Plan có thể không còn phù hợp nếu state/remote infrastructure thay đổi; tạo plan mới và review lại khi có thay đổi.
- Remote backend, state locking, workspace/environment mapping và provider/module versions phải được kiểm soát.

Không dùng một approval cũ để apply plan mới. Review plan artifact, commit SHA, state context và target workspace/account/Region cùng nhau.

Tài liệu: [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply).

## 30. Security controls cho IaC pipeline

IaC pipeline có quyền tạo IAM, network và data resources nên cần kiểm soát cả source, build, artifact và deployment identity.

| Control | Thực hành |
| --- | --- |
| Source protection | Branch protection, signed commits/tags khi phù hợp, CODEOWNERS |
| Pull request | Required reviews, status checks, no direct production push |
| Build isolation | Ephemeral workers, restricted network, pinned toolchain |
| Dependencies | Pin modules/providers/actions/images; scan supply chain |
| Secrets | Secrets Manager/SSM, OIDC federation, không log credentials |
| Artifact | Encryption, versioning, checksum, restricted access |
| IAM | Least privilege, short-term credentials, iam:PassRole allowlist |
| Approval | Separation of duties, reviewer group, immutable change reference |
| Policy | Guard/CloudFormation Hooks, security scanning, organizational controls |
| Audit | CloudTrail, CodePipeline history, stack events, approval comments |

Đặc biệt cẩn thận với pull requests không tin cậy: không chạy untrusted build scripts bằng production role hoặc cho phép script tự assume deploy role.

## 31. Test IaC: unit, integration và deployment verification

Một pipeline chỉ chạy lint rồi deploy chưa đủ. Test theo các lớp:

- **Unit tests:** kiểm tra construct/function sinh ra resource properties mong đợi.
- **Template tests:** schema, references, policy rules, naming, tags, encryption.
- **Diff review:** resource actions và replacements.
- **Integration tests:** deploy vào ephemeral/test account hoặc sandbox stack.
- **Smoke tests:** xác minh endpoint, connectivity, permissions, alarms và outputs.
- **Drift checks:** so sánh actual state với template sau deploy hoặc theo lịch.
- **Recovery tests:** thử rollback, restore snapshot, recreate resources trong non-production.

Với CDK, dùng assertions/template tests để kiểm tra synthesized CloudFormation. Với Terraform, dùng module tests/plan assertions và test trong sandbox. Với CloudFormation, dùng cfn-lint, cfn-validate, Guard và test stack.

Không coi local template validation là thay thế integration test trên AWS. Một số lỗi chỉ xuất hiện khi CloudFormation gọi service provider trong account/Region thật.

## 32. Observability và audit cho deployment

Mỗi deployment nên có đủ evidence để trả lời: ai deploy, deploy cái gì, ở đâu, dựa trên revision nào, đã được ai duyệt và kết quả thế nào.

Thu thập:

- CodePipeline execution ID và stage/action results;
- CodeBuild build ID, logs và reports;
- Git commit SHA, PR link và artifact digest;
- CloudFormation stack ID, change set ARN/name, status reason;
- CloudFormation stack events;
- CloudTrail events cho API calls và role assumptions;
- Approval identity/comment/time;
- CloudWatch alarms và post-deploy smoke test results.

Có thể gửi SNS/EventBridge notifications khi pipeline fail, stack rollback hoặc drift được phát hiện. Không đưa template secrets hoặc sensitive parameter values vào notification payload.

## 33. Anti-patterns thường gây sự cố

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Deploy trực tiếp từ branch mutable | Không biết chính xác code/template nào đã deploy | Pin commit SHA và immutable artifact |
| Bỏ qua change set | Không nhìn thấy resource replacement/deletion trước deploy | Tạo change set và review |
| Approve rồi rebuild artifact | Nội dung execute khác nội dung đã review | Promote cùng artifact/digest |
| Một role admin cho pipeline | Blast radius lớn, khó audit | Tách pipeline/execution/target roles |
| Lưu secrets trong parameters/artifacts | Lộ secrets qua logs/artifacts | Dynamic references/secret stores |
| Coi change set là bảo đảm deploy thành công | Runtime update vẫn có thể fail | Test, alarms, monitoring, rollback plan |
| Không đọc Replacement | Có thể thay database hoặc resource stateful | Review property-level changes và update behavior |
| Bỏ qua drift | Change set dựa trên giả định sai về current state | Detect/reconcile drift |
| Dùng CAPABILITY_NAMED_IAM mà không review IAM | Có thể cấp quyền ngoài dự kiến | Review policy/trust changes |
| Chạy PR script bằng prod credentials | Supply-chain/privilege escalation | Isolate untrusted PR builds |
| Apply Terraform plan khác plan đã duyệt | Thay đổi không được review | Apply exact saved plan artifact |
| Mở rộng concurrency quá nhanh | Sự cố lan ra nhiều accounts/Regions | Canary, failure tolerance và staged rollout |

## 34. Troubleshooting: pipeline hoặc CloudFormation deployment thất bại

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Template validation failed | YAML/schema/property sai | Chạy cfn-lint, cfn-validate, xem line/column |
| Guard rule failed | Template vi phạm security/compliance policy | Sửa template hoặc dùng exception có owner/expiry |
| InsufficientCapabilitiesException | Thiếu IAM capability acknowledgment | Review IAM resources rồi khai báo capability phù hợp |
| AccessDenied khi tạo change set | Pipeline role thiếu CloudFormation permission | Kiểm tra service role và action permissions |
| iam:PassRole denied | Pipeline không được pass CloudFormation execution role | Scope PassRole vào đúng role và service |
| Change set FAILED | Template invalid, role/quota/resource issue hoặc no changes | Đọc StatusReason, phân loại no-op và lỗi thật |
| Change set tạo được nhưng execute fail | Runtime condition, custom resource, permission hoặc quota | Đọc stack events và CloudTrail; tạo change set mới sau khi sửa |
| Artifact/template không tìm thấy | Sai artifact name/path hoặc S3 access | Kiểm tra TemplatePath, artifact store và KMS |
| Nested stack update fail | Child template/role/parameter mismatch | Xem nested stack events và change sets |
| Replacement bất ngờ | Property update yêu cầu replacement | Kiểm tra resource update behavior, backup và migration |
| Stack rollback | Resource operation hoặc alarm fail | Xem first failure trong stack events và rollback trigger |
| Stack policy blocks update | Resource đang được bảo vệ | Review thay đổi policy theo quy trình |
| Drift detected | Có thay đổi ngoài CloudFormation | Xác định nguồn và reconcile template |
| Manual approval timeout | Không có approver phản hồi trong 7 ngày | Kiểm tra notifications/permissions và chạy pipeline mới sau khi review |
| Cross-account AccessDenied | Trust policy, target role, KMS/artifact policy sai | Kiểm tra STS assume, PassRole và resource policies |
| Pipeline chạy sai Region/account | Environment mapping/variables sai | Assert caller identity, account ID, Region trước deploy |

### Quy trình điều tra theo thứ tự

~~~text
1. Xác nhận source commit, artifact digest, account, Region và stack name.
2. Xem CodePipeline action lỗi và CodeBuild logs.
3. Kiểm tra template validation, policy reports và package paths.
4. Nếu change set fail, đọc DescribeChangeSet.StatusReason.
5. Nếu execute fail, tìm stack event đầu tiên có status *_FAILED.
6. Kiểm tra CloudTrail để xác định principal/API bị deny.
7. Xác minh CloudFormation execution role, trust và iam:PassRole.
8. Kiểm tra resource quota, service-specific constraints và dependencies.
9. Kiểm tra stack policy, deletion/update replacement policies và rollback alarms.
10. Sửa source, tạo artifact/change set mới và review lại trước execute.
~~~

Không sửa trực tiếp resource trong console để làm pipeline pass mà không ghi nhận thay đổi vào IaC; nếu có emergency change, phải reconcile drift sau incident.

## 35. Lab: xây pipeline CloudFormation có approval gate

### Kịch bản

Bạn có template tạo một S3 bucket cho ứng dụng. Pipeline triển khai vào dev tự động; production phải tạo change set, dừng chờ review rồi execute.

### Bước 1 — Tạo template

~~~yaml
AWSTemplateFormatVersion: "2010-09-09"
Description: Orders artifact bucket

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - prod

Resources:
  OrdersArtifactBucket:
    Type: AWS::S3::Bucket
    DeletionPolicy: Retain
    UpdateReplacePolicy: Retain
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      VersioningConfiguration:
        Status: Enabled
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: Application
          Value: orders

Outputs:
  BucketName:
    Value: !Ref OrdersArtifactBucket
~~~

Tên bucket thực tế cần globally unique; có thể thêm suffix/account/Region bằng parameter phù hợp. DeletionPolicy Retain giúp giữ bucket khi stack xóa resource, nhưng không tự bảo vệ object khỏi lifecycle/user deletion.

### Bước 2 — Validate và package

~~~bash
cfn-lint template.yaml
cfn-validate template.yaml --strict

aws cloudformation package \
  --template-file template.yaml \
  --s3-bucket platform-cfn-artifacts \
  --output-template-file packaged.yaml
~~~

Nếu template không có local assets, package step có thể không cần upload resources nhưng pipeline vẫn nên giữ packaged template như artifact đã kiểm tra.

### Bước 3 — Tạo change set production

~~~bash
aws cloudformation create-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d \
  --change-set-type CREATE \
  --template-body file://packaged.yaml \
  --parameters ParameterKey=Environment,ParameterValue=prod \
  --description "commit=a1b2c3d environment=prod"
~~~

Nếu stack đã tồn tại, dùng UPDATE. Pipeline phải kiểm tra stack existence hoặc xử lý CREATE/UPDATE rõ ràng.

### Bước 4 — Review

~~~bash
aws cloudformation describe-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d
~~~

Xác minh đúng account/Region/stack, bucket encryption, public access block, versioning, retention, tags và IAM capabilities nếu có. Reviewer ghi nhận commit/change set đã kiểm tra.

### Bước 5 — Execute sau approval

~~~bash
aws cloudformation execute-change-set \
  --stack-name orders-artifacts-prod \
  --change-set-name orders-artifacts-prod-a1b2c3d

aws cloudformation wait stack-create-complete \
  --stack-name orders-artifacts-prod
~~~

### Bước 6 — Verify

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-artifacts-prod

aws cloudformation detect-stack-drift \
  --stack-name orders-artifacts-prod
~~~

Kiểm tra stack status, output bucket name, encryption/versioning/public access block và drift status. Thực hành thêm một thay đổi ngoài console trong sandbox rồi chạy drift detection để thấy sai khác.

## 36. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Replacement database

Một change set hiển thị Modify cho RDS với Replacement True.

**Yêu cầu:** Giải thích ý nghĩa, xác định data-loss/downtime risks, backup/restore plan, maintenance window và approval owners.

### Bài tập 2 — CodePipeline actions

Một pipeline có CloudFormation action CHANGE_SET_REPLACE, manual approval và CHANGE_SET_EXECUTE.

**Yêu cầu:** Mô tả thứ tự action, quyền cần thiết của pipeline role, CloudFormation execution role và reviewer; giải thích vì sao không rebuild artifact sau approval.

### Bài tập 3 — IAM capability

Template thêm IAM role và policy. Change set creation thất bại do thiếu capabilities.

**Yêu cầu:** Phân biệt CAPABILITY_IAM, CAPABILITY_NAMED_IAM và CAPABILITY_AUTO_EXPAND; review trust policy và permission policy trước khi acknowledge.

### Bài tập 4 — Cross-account deployment

Tooling account triển khai network stack vào production account nhưng nhận iam:PassRole AccessDenied.

**Yêu cầu:** Vẽ trust chain, phân biệt CodePipeline role, target deployment role và CloudFormation execution role; scope iam:PassRole và trust conditions.

### Bài tập 5 — Drift

Một engineer chỉnh security group rule trực tiếp trong console. Change set tiếp theo không phản ánh điều họ mong đợi.

**Yêu cầu:** Chạy drift detection, xác định actual/expected state, tìm CloudTrail actor và reconcile template trước khi deploy.

### Bài tập 6 — Terraform pipeline

Team dùng Terraform và muốn approval gate tương đương CloudFormation change set.

**Yêu cầu:** Tạo saved plan terraform plan -out=tfplan, review terraform show, lưu plan như sensitive artifact và apply đúng file đã được approve.

### Bài tập 7 — Policy as code

Security yêu cầu mọi S3 buckets bật encryption, block public access và có Environment tag.

**Yêu cầu:** Viết Guard rules, chạy trong CodeBuild và giải thích khác biệt giữa Guard CLI và Guard Hooks.

### Bài tập 8 — Multi-account baseline

Tổ chức có 30 AWS accounts và cần triển khai CloudTrail/Config baseline.

**Yêu cầu:** So sánh pipeline assume role từng account với CloudFormation StackSets service-managed permissions; chọn rollout concurrency/failure tolerance và delegated administrator model.

### Câu hỏi ngắn

1. **Template là gì?** Mô tả declarative resources và cấu hình mong muốn.
2. **Stack là gì?** Instance CloudFormation quản lý từ template/parameters.
3. **Change set làm thay đổi resource ngay khi tạo không?** Không; execute mới bắt đầu stack update/create.
4. **Change set có bảo đảm deploy thành công không?** Không; runtime/service-specific failures vẫn có thể xảy ra.
5. **CHANGE_SET_REPLACE làm gì?** Tạo hoặc thay thế change set.
6. **CHANGE_SET_EXECUTE làm gì?** Thực thi change set đã tạo.
7. **Replacement True có nghĩa gì?** Resource dự kiến được thay bằng resource mới.
8. **No changes có luôn là deployment failure không?** Không; có thể là no-op cần được pipeline phân loại rõ.
9. **CodePipeline manual approval timeout sau bao lâu?** Bảy ngày.
10. **CAPABILITY_NAMED_IAM dùng khi nào?** Template tạo IAM resources có custom names.
11. **iam:PassRole cho phép gì?** Cho service được chỉ định sử dụng IAM role; cần scope chặt.
12. **CloudFormation execution role làm gì?** Cấp permissions cho CloudFormation tạo/cập nhật resources.
13. **Stack policy là IAM policy không?** Không; nó bảo vệ resource updates trong stack.
14. **Termination protection ngăn điều gì?** Ngăn xóa stack.
15. **DeletionPolicy thay backup không?** Không.
16. **Drift là gì?** Actual resource properties khác expected template state.
17. **Guard CLI có thay syntax validation không?** Không; dùng cfn-lint/cfn-validate cùng Guard.
18. **Terraform saved plan có thể chứa secrets không?** Có; phải bảo vệ như sensitive artifact.
19. **Có nên rebuild sau approval?** Không; phải execute đúng artifact/change set đã review.
20. **StackSets dùng cho gì?** Triển khai và quản lý stacks trên nhiều accounts/Regions.

## 37. Checklist trước production

- [ ] Source revision/commit SHA được pin và có pull request review.
- [ ] Template, nested templates, scripts và policy rules nằm trong version control.
- [ ] cfn-lint/cfn-validate và Guard/security checks pass.
- [ ] Tool versions, providers/modules và build images được pin.
- [ ] Artifact đã package, checksum và immutable qua các stages.
- [ ] Parameters/environment mapping đúng account, Region và stack.
- [ ] Secrets không xuất hiện trong source, logs, parameters files hoặc artifacts.
- [ ] Pipeline role, target role và CloudFormation execution role được tách và least privilege.
- [ ] iam:PassRole giới hạn vào đúng CloudFormation service role.
- [ ] Cross-account trust, artifact bucket và KMS key policies được xác minh.
- [ ] Change set đã được tạo trên đúng stack/account/Region.
- [ ] Resource actions và property-level changes đã được review.
- [ ] Replacement True/Conditional, deletes và IAM/network/KMS changes có owner approval.
- [ ] Stateful resources có backup/restore và migration plan.
- [ ] Nested stack changes được bao gồm và review khi cần.
- [ ] Stack policies, termination protection, DeletionPolicy và UpdateReplacePolicy phù hợp.
- [ ] Approval gắn với commit, artifact digest và change set cụ thể.
- [ ] Người approve có quyền riêng; separation of duties đáp ứng policy.
- [ ] Execute action dùng đúng change set đã được approve.
- [ ] Stack events, CloudTrail, alarms, outputs và smoke tests được kiểm tra.
- [ ] Drift detection chạy theo lịch và sau emergency changes.
- [ ] Có rollback, break-glass và incident runbook.
- [ ] Multi-account/Region rollout có canary, concurrency và failure tolerance.
- [ ] Terraform plan/CDK synth artifacts được xử lý theo semantics riêng của tool.

## 38. Tổng kết

Triển khai IaC qua pipeline biến thay đổi hạ tầng thành quy trình có thể lặp lại, review và audit. Pipeline cần validate template, kiểm tra policy/security, package artifact bất biến, tạo preview, xin approval, execute và xác minh stack sau deploy.

Với CloudFormation, **change set là điểm kiểm soát quan trọng trước khi thay đổi production**. Reviewer cần hiểu resource actions, property-level changes, replacement behavior, IAM/network impact, data retention và rollback. Change set chỉ là preview; deployment vẫn có thể thất bại do runtime conditions, permissions, quotas hoặc custom resources.

CodePipeline có thể tạo change set bằng CHANGE_SET_REPLACE, dừng ở manual approval và thực thi bằng CHANGE_SET_EXECUTE. Hãy tách CodePipeline service role, cross-account deployment role và CloudFormation execution role; giới hạn iam:PassRole; giữ nguyên artifact đã được duyệt. Với nhiều accounts/Regions, xem xét cross-account roles hoặc StackSets. Với CDK/Terraform, review synthesized templates/diffs hoặc saved plans và deploy đúng artifact đã được phê duyệt.

Những điểm cần nhớ:

1. IaC thay đổi resource thật; review phải tập trung vào replacement, deletion, data và permissions.
2. Change set không sửa stack cho tới khi execute và không bảo đảm runtime deployment sẽ thành công.
3. CHANGE_SET_REPLACE tạo preview; approval gate; CHANGE_SET_EXECUTE thực thi đúng preview đó.
4. Pipeline role và CloudFormation execution role có trách nhiệm khác nhau; iam:PassRole phải được scope chặt.
5. Artifact/plan phải immutable và approval phải gắn với đúng commit/digest/change set.
6. Policy as code, drift detection, stack policies, backups và rollback alarms là các lớp guardrail bổ sung.
7. Terraform saved plan và CDK synth/diff có semantics riêng; không coi chúng là cùng một artifact type với CloudFormation change set.

### Tài liệu chính thức

- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- [Update CloudFormation stacks using change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [Create a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-create.html)
- [Execute a change set](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets-execute.html)
- [CloudFormation change set resource reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-cloudformation-changeset.html)
- [CodePipeline CloudFormation action reference](https://docs.aws.amazon.com/codepipeline/latest/userguide/action-reference-CloudFormation.html)
- [CodePipeline manual approvals](https://docs.aws.amazon.com/codepipeline/latest/userguide/approvals.html)
- [CodePipeline CloudFormation pipeline walkthrough](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/continuous-delivery-codepipeline-basic-walkthrough.html)
- [CloudFormation Validate](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-validate.html)
- [CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html)
- [CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-drift.html)
- [CloudFormation rollback triggers](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-rollback-triggers.html)
- [CloudFormation StackSets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/what-is-cfnstacksets.html)
- [AWS CDK Pipelines](https://docs.aws.amazon.com/cdk/v2/guide/cdk-pipeline.html)
- [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan)
- [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply)

**Lưu ý vận hành:** Change set format, validation tools, CodePipeline action properties và resource update behavior có thể thay đổi. Trước production, đối chiếu docs của service/resource types đang dùng, test trên sandbox account và giữ evidence của change set/approval/stack events trong deployment record.
