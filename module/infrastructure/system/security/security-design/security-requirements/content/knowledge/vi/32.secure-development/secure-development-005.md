# Dependency scanning — Đặc tả yêu cầu quét và xử lý rủi ro thành phần

## 1. Dependency scanning là gì?

**Dependency scanning** là quá trình nhận diện các thành phần phần mềm trong một phạm vi đã xác định, đối chiếu chúng với dữ liệu rủi ro phù hợp và tạo kết quả để đánh giá/xử lý. Trong bài này, trọng tâm là quét lỗ hổng đã biết của thư viện, package và các thành phần liên quan tới sản phẩm hoặc quá trình build.

Quá trình thường gồm: xác định đúng thành phần/version, dựng quan hệ dependency, đối chiếu advisory, đánh giá mức độ ảnh hưởng, áp chính sách và theo dõi khắc phục. Một số sản phẩm còn cung cấp dữ liệu license, nguồn gốc hoặc dấu hiệu khác; phải đặc tả riêng khả năng nào thực sự được sử dụng và kiểm chứng.

Trong chương **Secure development**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu là chuyển câu “pipeline phải chạy dependency scanner” thành yêu cầu đo được: quét cái gì, bằng nguồn dữ liệu nào, lúc nào đủ bằng chứng, lỗi nào phải chặn, ai xử lý finding và bằng chứng nào xác nhận đã khắc phục.

Sau bài học, người học cần biết:

- Chọn phạm vi ở source, build, artifact và deployment.
- Phân biệt thành phần hiện diện, advisory khớp và khả năng ảnh hưởng thực tế.
- Đặc tả tính đầy đủ, độ mới, nguồn và ràng buộc của báo cáo.
- Thiết kế gate không nhầm scan lỗi với không tìm thấy finding.
- Quản lý triage, ngoại lệ, nâng cấp, kiểm thử và tái đánh giá bản đang chạy.

Tên package, advisory, version, schema và ngưỡng trong bài là dữ liệu minh họa; chúng không nêu một lỗ hổng thật hay chính sách bắt buộc cho mọi tổ chức.

## 2. Scanner trả lời câu hỏi nào?

| Bằng chứng/hoạt động | Câu hỏi chính | Giới hạn cần giữ rõ |
| --- | --- | --- |
| Manifest và lock/resolution data | Build khai báo hoặc chọn thành phần nào? | Không tự bao phủ mọi file/native/package thực sự được đóng gói |
| SBOM/inventory | Artifact/phạm vi có những thành phần nào? | Không tự chứng minh mọi thành phần đã được nhận diện hoặc không có lỗ hổng |
| Quét dependency | Thành phần nào khớp dữ liệu rủi ro đã dùng? | Không phát hiện mọi lỗ hổng chưa biết hoặc mọi lỗi logic của ứng dụng |
| SAST | Mã được phân tích có pattern/luồng đáng ngờ nào? | Không thay inventory và đối chiếu đầy đủ dependency bên ngoài |
| Kiểm thử động | Trong điều kiện thử, hệ thống có hành vi/rủi ro nào? | Không chứng minh mọi thành phần/version đều không ảnh hưởng trong mọi cấu hình |
| Reachability/assessment | Đường mã/điều kiện liên quan có thể được sử dụng thế nào? | Phân tích thiếu hoặc chưa làm không đồng nghĩa không thể khai thác |
| Gate phát hành | Với bằng chứng hiện có, policy có cho phép release không? | Quyết định cho một artifact/thời điểm không tự áp dụng mãi cho mọi bản triển khai |

Một dependency hiện diện không có nghĩa mọi advisory cùng tên đều áp dụng. Một advisory match cũng chưa luôn chứng minh khai thác được trong ứng dụng. Ngược lại, chưa chứng minh reachability không có nghĩa thành phần chắc chắn không bị ảnh hưởng.

Cần phân biệt ít nhất ba phát biểu:

1. **Không tìm thấy finding trong phạm vi đã quét với dữ liệu này.** Đây là kết quả có điều kiện.
2. **Không đánh giá được hoặc đánh giá chưa đầy đủ.** Đây là thiếu bằng chứng, không phải kết quả sạch.
3. **Có finding nhưng được đánh giá/miễn trừ đúng phạm vi.** Rủi ro và quyết định vẫn phải được giữ lại để truy vết.

## 3. Phạm vi quét và thời điểm kiểm tra

### 3.1. Quét đúng đối tượng

Đối tượng có thể là commit, graph đã resolve, archive ứng dụng, image của một platform, công cụ build hoặc tập artifact triển khai. Với mỗi quyết định, phải nêu đối tượng nào cần được bảo vệ và định danh bất biến nào gắn với báo cáo.

| Phạm vi | Nội dung cần xem xét | Điều dễ bỏ sót |
| --- | --- | --- |
| Source/manifest | Dependency trực tiếp, file vendoring và profile khai báo | Không phản ánh chính xác dependency đã resolve hoặc artifact cuối |
| Build/resolution | Dependency bắc cầu, plugin, generator, toolchain thuộc phạm vi | Chỉ cố định version trực tiếp hoặc bỏ qua mã chạy ở CI |
| Artifact ứng dụng | Thành phần đóng gói, shaded/repackaged code, native library | Thư viện copy thủ công không có trong manifest |
| Container/phân phối | Ứng dụng, runtime và package OS theo từng image/platform | Chỉ quét JAR rồi kết luận toàn container không có finding |
| Runtime/deployment | Artifact đang chạy, plugin hoặc thành phần thêm qua volume/cài động | Source hiện tại đã sửa nhưng môi trường vẫn chạy artifact cũ |

Scope build/test không tự có nghĩa rủi ro thấp: plugin hoặc test dependency có thể thực thi trên worker có quyền đọc source và ảnh hưởng artifact. Có thể áp chính sách khác runtime, nhưng không bỏ chúng chỉ bằng một nhãn scope.

### 3.2. Các điểm kiểm tra trong vòng đời

- Khi thay dependency, manifest, profile, repository hoặc công cụ build: phát hiện sớm thay đổi graph và finding mới.
- Khi tạo artifact cuối: xác nhận inventory và kết quả áp dụng đúng nội dung sẽ phát hành.
- Trước promote/deploy: kiểm tra digest, phạm vi, dữ liệu đánh giá và policy hiện hành.
- Theo lịch hoặc khi có advisory/dữ liệu mới: đánh giá lại artifact đang được hỗ trợ/triển khai.
- Khi rollback/restore hoặc thay runtime/plugin: xác nhận bằng chứng cũ còn áp dụng và quyết định hiện hành có cho phép không.

Không cần cài lại hay build lại một artifact bất biến chỉ để đánh giá advisory mới nếu inventory đủ tin cậy và công cụ hỗ trợ luồng đó. Nhưng nếu phát hiện inventory trước đây thiếu thành phần, phải sửa bằng chứng và xác định các quyết định bị ảnh hưởng.

### 3.3. Định danh artifact và cấu hình quét

Tên file, tag hoặc tên nhánh có thể đổi đích. Báo cáo phục vụ release cần gắn với digest/định danh bất biến của đúng artifact, platform khi có, profile quét, phiên bản engine/ruleset, nguồn dữ liệu và policy revision.

Nếu build dùng profile khác, platform khác hoặc đóng gói thêm thành phần, báo cáo cho cùng Git commit chưa chắc mô tả đúng artifact cuối. Cần kiểm tra mối liên kết giữa source, resolution, artifact và báo cáo thay vì chỉ so tên dự án.

## 4. Mô hình đe dọa và bất biến

### 4.1. Tài sản và giả định

Tài sản gồm tính đúng đắn của quyết định phát hành, dữ liệu/credential của CI, mã và artifact được triển khai, khả năng phản ứng advisory và bằng chứng về rủi ro còn lại.

Giả định tác nhân có thể đưa một dependency rủi ro vào, sửa cấu hình/exclusion quyền thấp, làm output cũ được tái sử dụng hoặc cung cấp báo cáo không đúng đối tượng. Lỗi vận hành, dữ liệu nhận diện chưa đủ và scanner không hỗ trợ một dạng đóng gói cũng có thể gây thiếu bằng chứng mà không có tấn công.

| Risk ID | Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- | --- |
| DSR-01 | Chỉ quét dependency trực tiếp hoặc sai profile | Bỏ sót dependency bắc cầu/được đóng gói | Phạm vi rõ và đối chiếu resolution/artifact |
| DSR-02 | Scanner lỗi/timeout nhưng pipeline đọc danh sách finding rỗng | Fail open khi chưa đánh giá | Trạng thái kỹ thuật riêng và gate không đổi lỗi thành thành công |
| DSR-03 | Báo cáo cũ của artifact A dùng cho artifact B | Quyết định không áp dụng đúng phần mềm | Subject digest, platform và ràng buộc bất biến |
| DSR-04 | Database quá tuổi hoặc đồng bộ thất bại | Bỏ sót thông tin đã có hoặc dùng dữ liệu không đủ điều kiện | Bằng chứng độ mới, nguồn và chính sách khi stale |
| DSR-05 | Match sai tên, ecosystem, version hoặc variant | Báo sai/loại nhầm rủi ro | Định danh chuẩn hóa và triage phần chưa chắc chắn |
| DSR-06 | Suppression toàn cục, ngoại lệ vô hạn hoặc VEX sai phạm vi | Mất finding và bỏ chặn trái phép | Quyết định có chủ sở hữu, phạm vi, căn cứ và expiry/trigger |
| DSR-07 | Nâng version trong source nhưng artifact/deployment chưa đổi | Báo đã sửa khi bản rủi ro còn chạy | Xác minh artifact mới và triển khai thực tế |
| DSR-08 | Chỉ dựa mức severity hoặc reachability chưa đủ | Ưu tiên sai hoặc kết luận không ảnh hưởng thiếu căn cứ | Đánh giá rủi ro, độ chắc chắn và điều kiện áp dụng |
| DSR-09 | Scanner/resolve chạy mã từ project không tin cậy với credential rộng | Chiếm CI hoặc lộ source/token | Môi trường quét ít quyền và kiểm soát thực thi/network |
| DSR-10 | Parser/báo cáo hoặc database đầu vào bị thay | Gate tin bằng chứng giả hoặc quá tải | Xác thực nguồn, schema và giới hạn tài nguyên |
| DSR-11 | Finding bắc cầu bị xóa bằng exclusion nhưng vẫn được đóng gói | Trạng thái “fixed” không khớp inventory | Kiểm tra nội dung và thay đổi graph thực sự |
| DSR-12 | Bản đã quét không được tái đánh giá khi advisory thay đổi | Rủi ro tồn tại lâu trên sản phẩm đang hỗ trợ | Inventory triển khai và luồng đánh giá lại có owner |

### 4.2. Bất biến bảo mật

1. Chỉ dùng bằng chứng đủ điều kiện, đúng subject/phạm vi cho quyết định release tương ứng.
2. Scan lỗi, phạm vi thiếu, định danh chưa rõ và dữ liệu quá tuổi không tự trở thành không có finding.
3. Ngoại lệ/assessment không xóa sự hiện diện của component hoặc lịch sử finding.
4. Khắc phục chỉ được đóng khi có bằng chứng cho nội dung và phạm vi đã cam kết, không chỉ một thay đổi trong manifest.
5. Công cụ quét không được cấp quyền rộng hơn nhu cầu hoặc trở thành đường thực thi mã không tin cậy ngoài kiểm soát.

## 5. Hợp đồng bằng chứng quét

### 5.1. Các trường cần có

| Nhóm | Nội dung cần xác định |
| --- | --- |
| Subject | Loại đối tượng, digest, platform/profile, build/release linkage |
| Inventory | Package/ecosystem/namespace/version, variant khi cần, component reference và nguồn nhận diện |
| Graph/phạm vi | Direct/transitive, runtime/build/test theo hợp đồng, included/excluded và coverage gap |
| Lần chạy | Run ID, engine/version, ruleset, cấu hình có hiệu lực, thời điểm bắt đầu/kết thúc |
| Dữ liệu nguồn | Nguồn được phép, snapshot/version, thời điểm dữ liệu và kết quả đồng bộ/xác minh |
| Trạng thái kỹ thuật | Complete/incomplete/error, phần nào thành công/thất bại và giới hạn công cụ |
| Finding | Advisory/alias, component đúng danh tính, range/match basis, severity/nguồn, độ chắc chắn |
| Assessment | Affected/not affected/unknown theo bằng chứng, điều kiện, người/nguồn có quyền, phạm vi hiệu lực |
| Quyết định | Policy revision, block/allow/exception, reason code, owner và liên kết remediation |

Đây là hợp đồng dữ liệu minh họa, không phải tên field bắt buộc của một định dạng scanner cụ thể. Adapter phải ánh xạ đầy đủ và phát hiện trường quan trọng bị thiếu khi đổi công cụ hoặc phiên bản báo cáo.

### 5.2. Match và chuẩn hóa finding

Tên hiển thị đơn lẻ không đủ để match. Cần đối chiếu ecosystem, namespace, version và dữ liệu nhận diện phù hợp; có trường hợp phải kiểm tra variant, package downstream hoặc thông tin bản vá do nhà phân phối cung cấp.

Không so version bằng chuỗi từ điển một cách tùy tiện, không coi mọi ecosystem đều dùng cùng quy tắc version/range. Không tự thay version chưa biết bằng `0.0.0` hoặc “latest” để tăng tỷ lệ hoàn thành.

Một advisory có thể có nhiều alias. Cần tránh đếm cùng vấn đề thành nhiều finding chỉ vì khác ID, nhưng vẫn giữ alias/nguồn để truy vết. Ngược lại, không gộp hai package hoặc hai điều kiện ảnh hưởng khác nhau chỉ vì cùng một nhãn advisory.

Khóa theo dõi finding nên bao gồm định danh component và advisory đã chuẩn hóa trong phạm vi sản phẩm; liên kết mỗi lần quan sát với artifact/version/deployment tương ứng. Không dùng một ID ngẫu nhiên mới mỗi lần scan để làm mất lịch sử hoặc đặt lại thời hạn xử lý.

### 5.3. Độ mới của dữ liệu

Thời điểm chạy scanner, thời điểm tải database và thời điểm snapshot dữ liệu phản ánh các điều khác nhau. Chạy hôm nay với database cũ một tuần không đáp ứng một policy yêu cầu snapshot không quá 24 giờ.

Phải xác định timestamp nào đo tuổi dữ liệu, nguồn tin cậy của nó, dung sai thời gian và hành vi khi không đủ chứng cứ. Không tin một field do báo cáo chưa xác thực tự khai để chứng minh freshness. Cũng không khẳng định dữ liệu mới nghĩa là mọi lỗ hổng đều đã được biết hoặc được nguồn xử lý ngay.

SBOM/inventory của artifact bất biến có thể vẫn đúng trong khi assessment cần được cập nhật vì advisory/ruleset mới. Đừng tạo timestamp SBOM mới chỉ để che việc dữ liệu rủi ro cũ.

## 6. Yêu cầu kiểm chứng được

Các ngưỡng sau là hợp đồng nghiệm thu minh họa cho nhóm sản phẩm. Chúng cần được owner phê duyệt theo rủi ro và khả năng vận hành, không phải SLA chung cho mọi dependency.

| ID | Yêu cầu | Owner | Bằng chứng đạt |
| --- | --- | --- | --- |
| DSC-01 | Mỗi loại sản phẩm phải có phạm vi scan, inventory nguồn, ecosystem/platform, exclusion và owner được duyệt. | Chủ sản phẩm/bảo mật | Hồ sơ bao phủ thành phần ứng dụng, build/runtime/OS theo phạm vi; phần chưa hỗ trợ được nêu rõ |
| DSC-02 | Inventory phải được đối chiếu với resolution và artifact theo hợp đồng, gồm dependency bắc cầu và phần đóng gói không nằm trong manifest. | Build/nền tảng | Fixture direct/transitive, copy/shade/native hoặc package image làm hiện rõ match/gap, không im lặng bỏ sót |
| DSC-03 | Báo cáo và quyết định phải ràng buộc đúng subject digest, platform và cấu hình quét; không dùng tag/tên file như bằng chứng duy nhất. | Build/release | Thay artifact hoặc platform làm bằng chứng không còn áp dụng; không dùng output cũ cho build mới |
| DSC-04 | Nguồn/engine/report/ruleset phải được kiểm soát và xác minh theo mô hình tin cậy; báo cáo sai schema hoặc nguồn không được phép không được dùng cho gate. | Nền tảng supply chain | Sửa report, đổi nguồn/engine hoặc thiếu trường quan trọng bị phát hiện trước quyết định |
| DSC-05 | Trạng thái complete, incomplete và error phải độc lập với danh sách finding; thiếu output/timeout/coverage gap không trả kết quả sạch. | Nền tảng/QA | Tiêm lỗi từng bước, report rỗng và partial scan; gate phân loại không đánh giá được đúng |
| DSC-06 | Ví dụ dữ liệu advisory tại gate không quá 24 giờ theo snapshot được xác minh; timestamp bất thường hoặc thiếu bằng chứng độ mới không được mặc nhiên chấp nhận. | Quản lý lỗ hổng | Test biên độ mới, snapshot cũ, đồng bộ lỗi và thời gian nguồn không tin cậy |
| DSC-07 | Match phải giữ danh tính ecosystem/namespace/version và căn cứ; unknown/alias/false match phải được phân loại, không tự sửa dữ liệu để qua gate. | Quản lý lỗ hổng | Test cùng tên khác package, version/range khác quy tắc, advisory alias và version chưa biết |
| DSC-08 | Gate phải áp policy có phiên bản cho severity, applicability, độ chắc chắn, phạm vi và ngoại lệ; lỗi kỹ thuật không được bị finding exception che đi. | Release/bảo mật | Test dương tính/âm tính và bảng quyết định; cùng input/policy cho kết quả có thể giải thích |
| DSC-09 | Triage phải phân biệt match sai, affected, not affected có bằng chứng và unknown; không dùng thiếu reachability analysis làm bằng chứng không ảnh hưởng. | Chủ ứng dụng/bảo mật | Fixture reachability chưa đủ giữ trạng thái unknown; not affected có căn cứ/phạm vi/nguồn được kiểm chứng |
| DSC-10 | Ngoại lệ/VEX phải gắn advisory/component, sản phẩm/artifact hoặc phạm vi áp dụng rõ, điều kiện, owner, quyền phê duyệt và expiry/trigger đánh giá lại. | Chủ rủi ro/bảo mật | Ngoại lệ hết hạn, sai digest/cấu hình hoặc suppression quá rộng không tự cho release qua |
| DSC-11 | Remediation phải có owner và deadline theo policy; rescan hoặc đổi ID finding không được đặt lại tuổi rủi ro một cách mù quáng. | Chủ sản phẩm | Theo dõi được first-seen/triage/deadline và chuỗi artifact chứa finding qua nhiều lần scan |
| DSC-12 | Chỉ đóng fixed khi thành phần hoặc điều kiện ảnh hưởng đã thay đúng phạm vi, artifact mới được xác minh và deployment/nhánh hỗ trợ liên quan được xử lý theo cam kết. | Ứng dụng/release | Version khai báo đổi nhưng artifact cũ/deployment cũ còn tồn tại không bị báo đã sửa toàn bộ |
| DSC-13 | Scanner/resolve phải chạy với quyền tối thiểu, giới hạn tài nguyên và mạng; không tùy ý chạy script/plugin từ project không tin cậy với credential phát hành. | CI/nền tảng | Fixture project/parser độc hại không đọc secret, ghi repository/phát hành hoặc tải tài nguyên ngoài phạm vi |
| DSC-14 | Cấu hình exclusion, suppression và gate phải kiểm soát quyền/thay đổi; audit nêu actor, lý do và revision. | Nền tảng/bảo mật | Thay file cấu hình quyền thấp không tự loại finding/scope hoặc tắt điều kiện chặn |
| DSC-15 | Artifact đang hỗ trợ/triển khai phải có inventory và quy trình đánh giá lại; ví dụ tạo danh sách candidate ban đầu trong 4 giờ sau tiếp nhận advisory cần xử lý. | Ứng phó/vận hành | Diễn tập tìm đúng release/platform/deployment cùng candidate/unknown và owner |
| DSC-16 | Promote/rollback/restore phải kiểm tra policy/assessment hiện hành và giữ liên kết bằng chứng; quyết định cũ không tự có hiệu lực mãi. | Release/vận hành | Restore đúng artifact nhưng assessment quá tuổi hoặc ngoại lệ hết hiệu lực bị xử lý theo policy mới |
| DSC-17 | Log/report/metric phải đủ truy vết subject, run, nguồn, policy và quyết định, không chứa secret/source dư thừa hoặc gộp error thành clean. | Vận hành/bảo mật | Kiểm tra audit các trạng thái, kênh upload/debug và phạm vi truy cập dữ liệu |
| DSC-18 | Thay engine, schema, ruleset, nguồn database hoặc cách đóng gói phải có regression trên fixture đã biết và kiểm tra cấu hình có hiệu lực. | Nền tảng/QA | Test phát hiện thay đổi match, coverage, alias, exit/result semantics trước áp dụng rộng |

## 7. Thiết kế pipeline và hành vi khi lỗi

### 7.1. Luồng từ inventory tới quyết định

```text
Source + resolution/profile + artifact cuối theo từng platform
                         |
                         v
Tạo/đối chiếu inventory theo phạm vi đã duyệt
                         |
                         v
Scanner trong worker có giới hạn, nguồn dữ liệu được kiểm soát
                         |
                         v
Chuẩn hóa report: kỹ thuật + coverage + finding + dữ liệu nguồn
                         |
                         v
Xác minh nguồn/subject/schema/freshness
                         |
                         v
Triage và assessment/ngoại lệ đúng phạm vi
                         |
                         v
Policy gate có phiên bản → allow / block / approved exception
                         |
                         v
Remediation + kiểm chứng artifact/deployment + đánh giá lại
```

Không đặt hành vi “nếu file report không có thì dùng file scan trước” trong luồng bình thường. Workspace/cache có thể chứa output thuộc commit hoặc artifact khác. Tạo run context rõ và kiểm tra subject của output thực nhận.

### 7.2. Adapter không được chỉ nhìn exit code

Công cụ có thể phân biệt finding và lỗi thực thi theo exit code/schema khác nhau. Adapter phải được đặc tả và kiểm thử theo hợp đồng của công cụ đang dùng: không mặc định mọi nonzero đều là cùng một loại lỗi, và không mặc định zero nghĩa là không có finding hoặc coverage đầy đủ.

```text
evaluate_release(subject, scan_profile, policy):
    inventory = collect_and_reconcile_inventory(subject, scan_profile)
    require_inventory_scope_and_identifiers_sufficient(inventory)

    execution = run_scanner_in_bounded_worker(subject, inventory)
    report = normalize_using_supported_engine_contract(execution)
    require_report_present_and_schema_valid(report)
    verify_report_origin_and_approved_engine_configuration(report)
    require_subject_digest_platform_and_run_binding(report, subject)
    require_technical_status_complete_and_coverage_sufficient(report)
    require_approved_dataset_snapshot_and_time_evidence(report, policy)

    candidates = normalize_component_advisory_identity_and_aliases(report)
    findings = attach_current_verified_assessments_and_exceptions(
        candidates, subject, policy
    )
    decision = evaluate_all_findings_and_global_gate_conditions(findings, policy)
    persist_report_decision_owner_and_remediation_links()
    return decision
```

Tính đầy đủ của report do công cụ tự khai chưa đủ nếu inventory đầu vào đã thiếu. Cần đối chiếu phạm vi ở bước trước và giữ giới hạn nhận diện của cả inventory lẫn scanner.

### 7.3. Quét trong môi trường ít quyền

Scanner và parser xử lý dữ liệu chưa được tin cậy. Nếu một bước cần resolve dependency bằng công cụ build, phải xem xét khả năng project chạy script, plugin hoặc code generator. Không chạy mã tùy ý từ một nhánh không tin cậy với token ký/phát hành hoặc quyền ghi repository rộng.

Worker cần giới hạn thời gian, tài nguyên, file được đọc/ghi và mạng theo nhu cầu. Credential đọc artifact/advisory, nếu cần, phải có phạm vi phù hợp và không được dump vào report/debug. Có thể dùng dữ liệu đã đồng bộ được kiểm chứng trong môi trường quét ít quyền thay vì cấp mọi quyền tải/thực thi cho scanner.

Không tự resolve external reference, tải URL hoặc giải nén nội dung vô hạn từ report/SBOM chưa tin cậy. Khi job quá giới hạn, trả trạng thái kỹ thuật không đầy đủ/lỗi theo hợp đồng; không chuyển nó thành finding rỗng để kịp release.

## 8. Chính sách gate minh họa

YAML sau là **schema chính sách minh họa do hệ thống sở hữu**, không phải flag hay file cấu hình có thể đưa trực tiếp cho một scanner cụ thể.

```yaml
policyRevision: dependency-gate-demo-r3
subject:
  requireImmutableDigest: true
  requirePlatformBindingWhenApplicable: true
coverage:
  requireCompleteDeclaredScope: true
  requireTransitiveDependencies: true
  requireArtifactReconciliation: true
execution:
  maxWallTimeSeconds: 600
  maxReportBytes: 20971520
  maxConcurrentScansPerWorker: 2
  externalReferenceResolution: disabled
advisoryData:
  maxSnapshotAgeHours: 24
  maxFutureSkewSeconds: 300
  requireApprovedSource: true
technicalFailure:
  decision: block
  findingExceptionCannotOverride: true
findingPolicy:
  highOrCriticalAffectedOrUnknown: block
  unknownSeverityWithoutVerifiedDisposition: review-required
  mediumOrLowAffectedOrUnknown: allow-with-remediation-tracking
  verifiedNotAffectedInCurrentScope: allow-with-evidence
  verifiedCurrentFindingException: allow-by-exception
```

Số lượng worker là một yếu tố của giới hạn tổng; `maxConcurrentScansPerWorker: 2` không tự thành giới hạn toàn dịch vụ là 2. Quy tắc queue, ưu tiên và ngân sách tổng cần được đặc tả khi nhiều dự án cùng scan.

### 8.1. Thứ tự áp dụng policy

1. Kiểm tra điều kiện toàn cục: nguồn/report đúng, subject đúng, phạm vi đủ, scan complete và dữ liệu đủ mới.
2. Xác minh assessment/ngoại lệ còn áp dụng cho đúng finding và đối tượng.
3. Áp bảng quyết định của từng finding và tổng hợp kết quả release.
4. Lưu riêng finding được cho qua, lý do, owner và thời hạn; không xóa chúng khỏi report.

Finding exception không được che lỗi report, subject mismatch hay partial scan. Nếu tổ chức có một quy trình phát hành khẩn cấp chấp nhận thiếu bằng chứng kỹ thuật, đó phải là quyết định rủi ro riêng với quyền/phạm vi/bằng chứng tương ứng, không phải tác dụng phụ của một suppression cho advisory.

Trong policy ví dụ, finding High/Critical còn affected hoặc unknown bị chặn. Medium/Low được cho qua với theo dõi không có nghĩa đã chứng minh không ảnh hưởng; owner và thời hạn xử lý vẫn bắt buộc. Severity chưa biết cần review, không tự đổi thành Low.

Assessment not affected chỉ được dùng khi có nguồn/căn cứ/phạm vi đã xác minh. Match sai danh tính package cần được sửa/phân loại bằng bằng chứng; không dùng blanket suppression cho mọi package có tên gần giống.

### 8.2. Độ mới và kiểm thử biên

Giả sử gate dùng thời điểm đáng tin `T` và snapshot advisory đã xác minh là `S`. Chính sách ví dụ chấp nhận tuổi dữ liệu tối đa 24 giờ, bao gồm biên; timestamp tương lai vượt 300 giây không đủ điều kiện:

```text
age = T - S

-300 giây <= age <= 24 giờ
```

Snapshot đúng 24 giờ đạt điều kiện tuổi; 24 giờ cộng 1 đơn vị độ phân giải kiểm thử thì không đạt. Timestamp tương lai trong dung sai chỉ là chấp nhận sai lệch theo policy, không chứng minh dữ liệu thật đã được công bố từ tương lai. Thiếu nguồn thời gian hoặc bằng chứng snapshot vẫn không đạt, dù phép trừ cho một giá trị có vẻ gần.

Độ mới của dữ liệu và tuổi finding có mục đích khác nhau. Đồng bộ database mới không đặt lại deadline remediation của finding đã biết.

### 8.3. Ví dụ Java phân loại finding đã được đánh giá

Đoạn mã JDK 17 chỉ minh họa bảng quyết định từng finding. Assessment và boolean ngoại lệ phải do hệ thống triage kiểm chứng cho đúng subject/policy/thời điểm gate, không lấy trực tiếp từ JSON do người yêu cầu release tự gửi.

```java
import java.util.Objects;

public final class DependencyFindingPolicy {
    public enum Severity { CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN }
    public enum Applicability { AFFECTED, NOT_AFFECTED, UNKNOWN }
    public enum Decision {
        BLOCK,
        REVIEW_REQUIRED,
        ALLOW_WITH_REMEDIATION_TRACKING,
        ALLOW_WITH_NOT_AFFECTED_EVIDENCE,
        ALLOW_BY_VERIFIED_EXCEPTION
    }

    public record AssessedFinding(
            Severity severity,
            Applicability applicability,
            boolean currentScopedExceptionVerified) {
        public AssessedFinding {
            Objects.requireNonNull(severity);
            Objects.requireNonNull(applicability);
        }
    }

    public static Decision classify(AssessedFinding finding) {
        Objects.requireNonNull(finding);
        if (finding.applicability() == Applicability.NOT_AFFECTED) {
            return Decision.ALLOW_WITH_NOT_AFFECTED_EVIDENCE;
        }
        if (finding.currentScopedExceptionVerified()) {
            return Decision.ALLOW_BY_VERIFIED_EXCEPTION;
        }
        return switch (finding.severity()) {
            case CRITICAL, HIGH -> Decision.BLOCK;
            case UNKNOWN -> Decision.REVIEW_REQUIRED;
            case MEDIUM, LOW -> Decision.ALLOW_WITH_REMEDIATION_TRACKING;
        };
    }
}
```

Tên record hoặc field không tạo gốc tin cậy. Trước khi gọi hàm, phải kiểm tra source, quyền phê duyệt, căn cứ, phạm vi và hiệu lực của assessment/ngoại lệ. Một trạng thái NOT_AFFECTED chưa được xác minh không được đưa vào record như thể đã có bằng chứng.

Hàm chưa kiểm tra nguồn báo cáo, completeness, coverage, subject digest, tuổi database hoặc expiry của ngoại lệ. Các bước đó nằm ở gate toàn cục và dịch vụ đánh giá trước đó. Kết quả cho phép của một finding không được dùng để bỏ điều kiện toàn cục hoặc các finding đang bị chặn khác.

Không trả một boolean chung `secure=true` cho mọi quyết định allow. Cho qua nhờ ngoại lệ, nhờ bằng chứng không ảnh hưởng và cho qua có nhiệm vụ remediation là những quyết định có ý nghĩa và nghĩa vụ khác nhau.

## 9. Ví dụ xuyên suốt: dependency bắc cầu và xác minh khắc phục

Giả sử ứng dụng `demo-orders` dùng `demo-client@1.5.0`, thư viện này kéo theo `example.demo/demo-parser@2.3.0`. Graph được resolve và nội dung artifact A đều xác nhận parser có mặt.

Advisory tổng hợp `ADVISORY-DEMO-002` xác định phạm vi ảnh hưởng của package thử là từ 2.0.0 tới trước 2.4.0 và gán severity High trong fixture. Đây không phải advisory thật. Chưa có bằng chứng not affected hoặc ngoại lệ hợp lệ cho ứng dụng.

```text
artifact A
  └─ demo-orders
       └─ demo-client@1.5.0
            └─ demo-parser@2.3.0
                 └─ ADVISORY-DEMO-002: candidate/affected theo fixture
```

Với policy ví dụ, gate chặn vì finding High còn affected/unknown. Report phải giữ đường dependency để owner hiểu parser đến từ đâu; không chỉ yêu cầu đội ứng dụng “xóa parser khỏi danh sách”.

| Thay đổi/lần đánh giá | Kết quả cần thấy |
| --- | --- |
| Chỉ quét dependency trực tiếp | Coverage không đáp ứng phạm vi; không dùng danh sách thiếu parser để kết luận sạch |
| Thêm exclusion trong scanner nhưng artifact A vẫn chứa parser | Không được coi là fixed; thay exclusion phải qua kiểm soát policy và giữ bằng chứng |
| Đổi khai báo parser nhưng lock/resolution vẫn chọn 2.3.0 | Artifact thực vẫn cần bị đánh giá theo thành phần có mặt; diff manifest chưa đủ |
| Build artifact B chứa parser 2.4.1 theo đúng fixture range | Tạo/ràng buộc report đúng B và scan lại; advisory thử này không còn áp theo range nhưng vẫn kiểm tra finding khác |
| Báo cáo cho B được dùng khi deploy A | Subject mismatch; không cho qua nhờ kết quả của B |
| B đã qua gate nhưng production vẫn chạy A | Remediation triển khai chưa hoàn tất trong phạm vi cam kết |
| Database có advisory mới sau khi B được triển khai | Đánh giá lại inventory B; kết quả trước đây không là chứng nhận an toàn vĩnh viễn |

Nâng dependency bắc cầu có thể cần thay dependency cha, constraint/resolution hoặc cách đóng gói. Lựa chọn phải được kiểm tra tương thích và hành vi ứng dụng; không mặc định một override version là luôn an toàn hoặc đủ.

Trạng thái fixed của issue cần gắn với các nhánh/release/deployment đã cam kết. Nếu còn A trong một môi trường được hỗ trợ, ghi rõ phần tồn tại và quyết định xử lý; không đóng toàn bộ issue chỉ vì nhánh chính đã dùng B.

## 10. Triage, ưu tiên và quản lý ngoại lệ

### 10.1. Tách các loại kết luận

| Kết luận | Ý nghĩa | Bằng chứng cần có |
| --- | --- | --- |
| Match sai | Component/advisory được liên kết sai danh tính hoặc điều kiện version | Dữ liệu nhận diện, nguồn range, cách đóng gói và lý do sửa match |
| Affected | Có căn cứ advisory áp dụng trong phạm vi đánh giá | Subject/component, điều kiện và dữ liệu advisory/assessment |
| Not affected | Có căn cứ không ảnh hưởng trong đúng phạm vi/điều kiện đã xét | Lý do kỹ thuật, nguồn có quyền, cấu hình/đường mã liên quan và trigger xem lại |
| Unknown/under investigation | Chưa đủ căn cứ kết luận | Phần thiếu bằng chứng, owner và thời hạn điều tra |
| Accepted risk | Người có thẩm quyền chấp nhận rủi ro có điều kiện | Phạm vi, hậu quả còn lại, biện pháp bù, expiry và quyết định phê duyệt |
| Fixed/mitigated | Thành phần/điều kiện đã thay với bằng chứng đúng phạm vi | Artifact, kiểm thử, deployment hoặc điều kiện giảm thiểu đã xác minh |

Accepted risk không biến finding thành false positive. Không có đường gọi được phát hiện bởi một công cụ reachability chưa đủ chứng minh không thể đạt tới trong runtime; cần xét reflection, nạp động, cấu hình hoặc giới hạn phân tích liên quan khi chúng có trong thiết kế.

Nếu rủi ro được giảm bằng tắt tính năng hoặc giới hạn exposure, component có thể vẫn hiện diện. Inventory phải giữ đúng sự thật đó; assessment và mitigation mô tả vì sao policy cho phép vận hành trong điều kiện hiện tại.

### 10.2. Owner, thời hạn và tuổi rủi ro

Mỗi finding cần owner sản phẩm/component, liên kết artifact/release, first-seen, lần quan sát gần nhất, trạng thái triage, deadline và tác vụ khắc phục. Tách thời gian phát hiện, thời gian xác nhận và thời gian triển khai để không che khoảng chờ giữa các bước.

Ví dụ một policy nội bộ có thể đặt:

| Mức trong phạm vi policy | Triage tối đa | Khắc phục hoặc giảm thiểu được phê duyệt |
| --- | --- | --- |
| Critical | 24 giờ | 72 giờ |
| High | 2 ngày | 14 ngày |
| Medium | 5 ngày | 30 ngày |
| Low | Theo lịch được duyệt, không quá 30 ngày | 90 ngày |

Đây là ngưỡng minh họa, tính theo thời gian lịch từ mốc first-seen đủ điều kiện do policy xác định và lưu lại. Không phải khuyến nghị phổ quát về mức rủi ro chấp nhận được. Rủi ro phơi lộ, thông tin khai thác có căn cứ hoặc tác dụng nghiệp vụ có thể yêu cầu ưu tiên nhanh hơn.

Nếu chưa có bản vá, owner vẫn phải xem xét giảm thiểu, thay thành phần hoặc xin chấp nhận rủi ro theo quyền; không tự dừng đồng hồ xử lý. Khi mức độ, điều kiện hoặc phạm vi thay đổi, policy phải nêu cách tính lại deadline và giữ lịch sử. Rescan, đổi alias hoặc tái tạo ticket không được tự đặt first-seen về hôm nay.

### 10.3. Ngoại lệ và suppression

Một hồ sơ ngoại lệ nên gồm:

- Finding/advisory/alias và định danh component cụ thể.
- Sản phẩm, artifact/release hoặc tập đối tượng được mô tả rõ; môi trường/cấu hình áp dụng khi có.
- Lý do, căn cứ kỹ thuật, hậu quả còn lại và biện pháp bù có kiểm chứng.
- Owner, người có quyền phê duyệt, ngày hết hạn và trigger đánh giá lại.
- Liên kết remediation và điều kiện phải chặn lại.

Một suppression trong file scanner chỉ là cơ chế triển khai quyết định, không tự tạo thẩm quyền phê duyệt. Phải kiểm soát ai được đổi file đó và cách nó được đối chiếu với registry quyết định hiện hành. Không dùng pattern quá rộng để che mọi finding của cả ecosystem hoặc toàn bộ dependency bắc cầu.

Ngoại lệ hết hạn phải bị đánh giá lại. Nếu điều kiện giảm thiểu không còn đúng hoặc artifact/phạm vi thay đổi, không tự kế thừa approval. Báo cáo và dashboard vẫn cần hiện finding được miễn trừ cùng lý do; không xóa nó để làm tỷ lệ finding thấp đi.

## 11. Khắc phục và xác nhận đã sửa

### 11.1. Luồng khắc phục có bằng chứng

```text
Finding và owner đã được xác định
  → chọn nâng cấp/thay thế/giảm thiểu phù hợp
  → cập nhật dependency cha, constraint/resolution hoặc đóng gói
  → build artifact mới và đối chiếu inventory thực tế
  → quét đúng artifact bằng dữ liệu đủ điều kiện
  → kiểm thử tương thích và luồng bảo mật/nghiệp vụ bị ảnh hưởng
  → deploy theo quy trình, xác minh digest/runtime inventory
  → đóng phần phạm vi đã xử lý, theo dõi phần còn lại
```

Xóa dependency khỏi manifest không đủ nếu nó vẫn được dependency khác kéo vào hoặc còn trong archive/image. Tương tự, scanner không còn báo một advisory có thể do suppression, lỗi match hoặc dữ liệu nguồn thay đổi; cần hiểu nguyên nhân trước khi kết luận fixed.

Bằng chứng closure cần phù hợp cách sửa. Với nâng version, kiểm tra version/variant thực tế và advisory range. Với thay thư viện, kiểm tra thành phần cũ không còn trong phạm vi. Với mitigation, kiểm chứng điều kiện kiểm soát và trigger đánh giá lại, giữ trạng thái phù hợp thay vì giả định component đã biến mất.

### 11.2. Tương thích và rollback

Nâng dependency có thể thay API, định dạng dữ liệu, mặc định cấu hình hoặc hành vi bảo mật. Kiểm thử cần tập trung vào phần sử dụng và bất biến liên quan, không chỉ ứng dụng khởi động thành công.

Nếu B đã khắc phục nhưng rollback về A, rủi ro của A quay lại phạm vi triển khai. Gate/qui trình rollback cần đánh giá policy hiện hành và quyết định rủi ro cho A; không mặc định release cũ luôn là phương án được phép.

Khi có nhiều nhánh hỗ trợ hoặc nhiều môi trường, phải ghi rõ chúng được xử lý ra sao. Có thể có bản đã fixed ở artifact nhưng chưa deployed, hoặc một phạm vi còn vận hành theo ngoại lệ. Không gộp các trạng thái đó thành “đã sửa toàn hệ thống”.

### 11.3. Thay công cụ và dữ liệu nguồn

Giữ bộ fixture đã biết để kiểm tra engine/ruleset/schema mới: dependency trực tiếp/bắc cầu, version unknown, package cùng tên khác ecosystem, advisory alias, scope bị loại, report partial và finding có assessment.

So sánh thay đổi match/coverage/decision, không chỉ số lượng finding. Ít finding hơn sau nâng scanner có thể là giảm false positive hoặc mất coverage; cần bằng chứng để phân biệt. Nhiều finding hơn có thể do dữ liệu mới, thay range hoặc nhận diện tốt hơn, không tự là lỗi công cụ.

## 12. Logging, metric và đánh giá lại sản phẩm đang chạy

Audit nên liên kết subject digest, platform, run ID, engine/config/ruleset, dataset snapshot, policy revision, trạng thái kỹ thuật, coverage, finding/assessment và quyết định. Đủ thông tin để hiểu vì sao một artifact được cho qua tại thời điểm đó, kể cả khi dữ liệu về sau thay đổi.

Không upload source, token repository, URL có credential hoặc toàn bộ môi trường tiến trình chỉ để thuận tiện quét. Nếu dùng dịch vụ quét bên ngoài, cần xác định dữ liệu nào được gửi, danh tính/quyền truy cập và chính sách bảo vệ tương ứng. Báo cáo inventory/lỗ hổng cũng cần phân loại và phân quyền vì có thể mô tả chi tiết sản phẩm.

Metric hữu ích gồm scan complete/incomplete/error, coverage gap, dữ liệu quá tuổi, thời gian triage/remediation, finding theo trạng thái và ngoại lệ sắp hết hạn. Không chỉ báo “số finding mới” vì lỗi quét có thể làm số đó bằng không. Tránh nhãn token, URL đầy đủ hoặc ID có cardinality không giới hạn trên metric tổng hợp.

Khi advisory mới cần xử lý, truy vấn component/alias tới artifact/release/platform và deployment đang dùng. Giữ cả candidate và unknown cần điều tra. Mục tiêu danh sách ban đầu trong 4 giờ của ví dụ là mục tiêu truy vết, không cam kết đã khắc phục mọi rủi ro trong 4 giờ.

Dữ liệu advisory và trạng thái triển khai thay đổi độc lập. Phải biết artifact nào còn chạy dù nhánh source đã sửa, artifact nào đã hết hỗ trợ nhưng còn tồn tại và ai chịu trách nhiệm xử lý. Restore chỉ mục phải khôi phục được các liên kết này, không chỉ file report.

## 13. Ma trận kiểm thử nghiệm thu

Dùng package/advisory giả định, artifact tổng hợp và dữ liệu thời gian kiểm soát. Không phụ thuộc số lượng finding hiện tại của một dự án thật để làm oracle cho logic gate, vì dữ liệu advisory có thể đổi.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-DSC-01 | Một artifact có dependency trực tiếp, bắc cầu, package đóng gói thủ công và scope build/runtime khác nhau | Nhận diện/ghi gap đúng phạm vi; không bỏ transitive hoặc mã chạy CI chỉ vì không ship | DSC-01, 02 |
| T-DSC-02 | Báo cáo đúng cho A; đổi một byte/platform/profile để tạo B hoặc dùng output cũ trong workspace | Subject/phạm vi không khớp bị chặn; không suy từ tên file/tag hoặc commit giống nhau | DSC-03 |
| T-DSC-03 | Report bị sửa, nguồn/engine không được phép, schema thiếu field hoặc phiên bản không hỗ trợ | Không dùng báo cáo đó cho quyết định; lỗi được phân loại và audit | DSC-04, 18 |
| T-DSC-04 | Scanner timeout/crash, không có output, partial scan hoặc danh sách finding rỗng kèm trạng thái error | Không trả clean/PASS; phân biệt lỗi kỹ thuật với finding và không lấy report trước thay thế | DSC-05, 08 |
| T-DSC-05 | Snapshot đúng 24 giờ, quá 24 giờ một đơn vị thử; tương lai đúng/vượt 300 giây; timestamp thiếu nguồn tin cậy | Áp đúng biên tuổi/dung sai của policy; không nhận dữ liệu chưa có bằng chứng dù phép tính tuổi có vẻ đạt | DSC-06 |
| T-DSC-06 | Package cùng tên khác ecosystem/namespace, version/range có quy tắc khác, version chưa biết | Match/unknown đúng bằng chứng; không đoán version hoặc so chuỗi tùy tiện để giảm finding | DSC-07 |
| T-DSC-07 | Một advisory có nhiều alias; rescan cùng vấn đề với ID output mới | Không đếm/đóng mở ticket mù quáng; giữ lịch sử, first-seen và liên kết quan sát | DSC-07, 11 |
| T-DSC-08 | High/Critical affected hoặc unknown, severity unknown và Medium/Low theo policy ví dụ | Quyết định đúng bảng: block/review/tracking; không tự hạ unknown thành Low | DSC-08, 09 |
| T-DSC-09 | Reachability analysis không hoàn tất; lượt khác có bằng chứng not affected đúng phạm vi | Phần chưa rõ vẫn unknown; chỉ bằng chứng đã được kiểm chứng mới áp dụng not affected | DSC-09 |
| T-DSC-10 | Exception/VEX hết hạn, sai subject/cấu hình hoặc được dùng để che scan lỗi | Không miễn trừ sai phạm vi; finding exception không vượt điều kiện kỹ thuật toàn cục | DSC-08, 10 |
| T-DSC-11 | Đổi manifest nhưng lock/artifact vẫn có version bị ảnh hưởng; exclusion làm report không thấy finding | Không đóng fixed chỉ vì diff manifest hoặc finding biến mất do suppression | DSC-02, 12, 14 |
| T-DSC-12 | Artifact B được xác minh đã sửa nhưng production/nhánh hỗ trợ vẫn dùng A | Ghi phần closure đúng phạm vi; phần A còn tồn tại có owner/quyết định, không báo sửa toàn bộ | DSC-11, 12, 15 |
| T-DSC-13 | Project thử chạy script/plugin; input report quá lớn hoặc external reference yêu cầu tải URL | Worker không lộ credential/phát hành trái quyền; giới hạn và chính sách mạng/parse có hiệu lực | DSC-13 |
| T-DSC-14 | Người không có quyền sửa exclusion/gate; suppression wildcard toàn bộ nhóm component | Thay đổi không tự được áp; audit chỉ rõ nguồn/actor/revision và phạm vi cần phê duyệt | DSC-10, 14 |
| T-DSC-15 | Advisory mới khớp nhiều release/platform/deployment, một số version unknown; sau đó restore inventory | Tìm danh sách ban đầu trong 4 giờ theo hợp đồng, gồm khoảng trống và owner; phục hồi liên kết đúng | DSC-15, 16 |
| T-DSC-16 | Promote/rollback artifact từng được cho qua nhưng database cũ, assessment/exception không còn hiệu lực | Quyết định theo policy/assessment hiện hành; kết quả trước không tự là giấy phép vĩnh viễn | DSC-06, 10, 16 |
| T-DSC-17 | Bật debug/upload và tạo scan lỗi, coverage gap, exception approved | Không lộ source/secret dư thừa; dashboard/audit không gộp các trạng thái thành clean | DSC-17 |
| T-DSC-18 | Artifact đúng subject, scope đủ, scan complete, dữ liệu đủ mới và không có điều kiện chặn; lặp trên engine/adapter mới | Test dương tính được qua, quyết định có bằng chứng; regression phát hiện khác biệt engine/config/result semantics | DSC-04, 08, 18 |

### 13.1. Acceptance criteria theo Given–When–Then

**AC-01 — Quét hợp lệ và đúng artifact.** Given artifact A bất biến, inventory đủ phạm vi, report từ nguồn/engine được phép và dữ liệu đủ điều kiện. When đánh giá theo policy mà không có finding thuộc điều kiện chặn. Then A được cho qua với audit đúng run/subject/policy. When thay A bằng B khác bytes hoặc platform không được report bao phủ. Then quyết định của A không được tái dùng cho B.

**AC-02 — Không có output không có nghĩa không có finding.** Given scanner lỗi/timeout hoặc report có technical status incomplete/error. When pipeline tổng hợp. Then trạng thái phản ánh chưa đánh giá đầy đủ và gate chặn theo policy; không dùng finding list rỗng hoặc report cũ để báo clean. Ngoại lệ của một advisory không thay đổi kết quả kỹ thuật này.

**AC-03 — Finding bắc cầu và phần chưa rõ.** Given graph `demo-orders → demo-client → demo-parser@2.3.0` cùng advisory tổng hợp High. When scanner/adapter tạo candidate và chưa có assessment not affected/ngoại lệ hợp lệ. Then finding vẫn chặn theo policy dù dependency không được khai báo trực tiếp; thiếu reachability analysis không làm nó biến mất.

**AC-04 — Ngoại lệ có phạm vi và còn hiệu lực.** Given finding được chủ rủi ro cho phép trong một phạm vi có thời hạn. When gate kiểm chứng đúng đối tượng/điều kiện và tất cả điều kiện kỹ thuật đạt. Then kết quả được ghi allow-by-exception, vẫn giữ finding/owner/deadline. When ngoại lệ hết hạn, subject/điều kiện không khớp hoặc report lỗi. Then không tự áp approval cũ.

**AC-05 — Khắc phục được kiểm chứng đến deployment.** Given source đã đổi dependency và build tạo B. When resolution/artifact/rescan xác nhận bản sửa trong phạm vi cùng kiểm thử tương thích đạt. Then ghi B đã được xác minh. Chỉ khi các deployment/nhánh hỗ trợ trong cam kết đã xử lý hoặc có quyết định riêng mới đóng phần phạm vi tương ứng; A còn chạy không bị che bởi kết quả của B.

**AC-06 — Tuổi rủi ro và tái đánh giá.** Given một finding đã có first-seen/deadline và các release đang hỗ trợ được liên kết inventory. When rescan, đổi alias, đổi scanner hoặc có advisory mới. Then giữ lịch sử và tính lại trạng thái theo policy rõ ràng, không tự đặt tuổi finding về không; truy vấn được các bản triển khai liên quan và cả phần chưa chắc chắn.

### 13.2. Bằng chứng kiểm thử

Lưu fixture inventory/artifact, digest đo thực tế, cấu hình/profile quét, engine/ruleset, dataset snapshot có nguồn, report thô và normalized, assessment/ngoại lệ thử, policy revision, trạng thái mong đợi/thực tế và tác dụng ở gate/deployment.

Với false match hoặc alias, giữ căn cứ nhận diện để giải thích vì sao issue được gộp/sửa. Với remediation, giữ graph và nội dung artifact/deployment thay vì chỉ ảnh màn hình scanner. Với lỗi CI, kiểm tra cả output thiếu, cache cũ và các kênh log/upload.

Các test của logic policy không thay kiểm thử tích hợp adapter/engine. Report hợp lệ về JSON chưa chứng minh match đúng; scan thành công của source chưa chứng minh artifact được deploy đã được quét đúng phạm vi.

## 14. Truy vết qua vòng đời phát triển

```text
Mục tiêu kiểm soát rủi ro dependency bằng bằng chứng đủ điều kiện
  → DSR-xx: bỏ sót, sai match/subject, stale data, lỗi thành clean, exception sai
  → DSC-xx: phạm vi + điều kiện đạt + owner + hành vi khi không đạt
  → Inventory/resolution/artifact + worker scan + adapter + policy/triage registry
  → T-DSC-xx và AC-xx
  → Remediation, deployment inventory, advisory response và phục hồi
```

| Mục tiêu | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Đủ phạm vi và đúng artifact | DSC-01, 02, 03 | T-DSC-01, 02, 11; AC-01, 03 |
| Bằng chứng nguồn và trạng thái kỹ thuật đúng | DSC-04, 05, 06 | T-DSC-03, 04, 05; AC-02 |
| Match/assessment/exception có căn cứ | DSC-07, 08, 09, 10 | T-DSC-06, 07, 08, 09, 10; AC-03, 04 |
| Theo dõi và sửa đúng phạm vi | DSC-11, 12 | T-DSC-07, 11, 12; AC-05, 06 |
| Công cụ/cấu hình không mở đường tấn công | DSC-13, 14, 18 | T-DSC-13, 14, 18 |
| Quan sát và đánh giá lại sản phẩm đang chạy | DSC-15, 16, 17 | T-DSC-15, 16, 17; AC-06 |

Một thay đổi nguồn advisory, matcher, schema báo cáo, rule severity, scope/exclusion, cách đóng gói hoặc registry ngoại lệ đều có thể thay quyết định. Cần owner và regression tương ứng, không chỉ một dấu tick “scanner đã chạy”.

## 15. Lỗi thường gặp và bài tập áp dụng

| Cách làm | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Pipeline có scanner là đáp ứng yêu cầu.” | Chưa biết scope, subject, dữ liệu và semantics lỗi | Hợp đồng bằng chứng, gate và test có thể kiểm chứng |
| “Exit zero hoặc report rỗng là sạch.” | Có thể thiếu scope, stale data hoặc adapter sai | Kiểm tra kỹ thuật, coverage và nguồn dữ liệu độc lập finding list |
| “Không khai báo trực tiếp nên không liên quan.” | Thành phần có thể được kéo bắc cầu hoặc đóng gói thủ công | Dựng graph và đối chiếu artifact |
| “Cùng tên thư viện thì advisory áp dụng.” | Có thể khác ecosystem/namespace/variant | Match theo định danh và căn cứ version đúng |
| “Reachability chưa phát hiện nghĩa là không ảnh hưởng.” | Phân tích có giới hạn, có thể chưa đủ dữ liệu | Giữ unknown, bổ sung assessment có phạm vi |
| “Suppression là đã chấp nhận rủi ro.” | File cấu hình không tự có thẩm quyền phê duyệt | Registry quyết định, owner, expiry và audit thay đổi |
| “Đổi version trong source là fixed.” | Lock/artifact/deployment có thể chưa đổi | Xác minh resolution, nội dung và phạm vi triển khai |
| “Database vừa tải về nên dữ liệu mới.” | Gói tải có thể chứa snapshot cũ hoặc nguồn chưa xác minh | Theo dõi nguồn/snapshot và kiểm tra độ mới theo hợp đồng |
| “Quét lại thì deadline bắt đầu lại.” | Che tuổi rủi ro đã tồn tại | Khóa theo dõi ổn định, first-seen và lịch sử quan sát |
| “Bản rollback từng qua gate nên luôn được phép.” | Advisory, policy và ngoại lệ có thể đã đổi | Kiểm tra lại quyết định theo trạng thái hiện hành |

Một nhóm chỉ quét manifest trực tiếp. Khi scanner timeout, shell vẫn tiếp tục deploy vì report được tạo rỗng. Một suppression wildcard do developer thêm làm dashboard về không finding. Nhánh chính đã nâng dependency nhưng production vẫn chạy image cũ. Database advisory được copy từ cache mà pipeline chỉ ghi thời điểm tải file hôm nay.

Hãy thực hiện:

1. Nêu ít nhất sáu rủi ro và bất biến bị vi phạm.
2. Định nghĩa scope, subject, platform và nguồn inventory/report cho dự án.
3. Viết sáu yêu cầu có ID, owner, điều kiện đạt, hành vi lỗi và bằng chứng.
4. Thiết kế bảng quyết định phân biệt scan lỗi, coverage gap, High unknown, not affected và exception hợp lệ.
5. Nêu test để phát hiện transitive dependency, report cũ, snapshot cũ và suppression sai phạm vi.
6. Thiết kế cách theo dõi tuổi finding và xác minh fixed tới các bản triển khai đã cam kết.
7. Nêu quy trình đánh giá lại khi có advisory mới hoặc khi đổi scanner/ruleset.

Trước khi chấp nhận đặc tả, kiểm tra:

- Đối tượng và scope quét có rõ, bao phủ transitive/build/runtime/OS theo trách nhiệm không?
- Report có đúng artifact/platform/profile và nguồn/engine được phép không?
- Technical status, coverage và finding list có được tách rõ không?
- Timestamp/snapshot/ruleset đủ điều kiện và có căn cứ tin cậy không?
- Match, alias, version unknown và reachability chưa đủ có được xử lý đúng không?
- Gate có policy version và test dương tính/âm tính không?
- Exception/suppression có quyền, phạm vi, thời hạn và trigger đánh giá lại không?
- Remediation có owner, deadline, lịch sử và bằng chứng artifact/deployment không?
- Worker quét, log/upload và config có được bảo vệ khỏi đầu vào/quyền không phù hợp không?
- Advisory mới, rollback và restore có giữ đúng liên kết và trách nhiệm xử lý không?

Dependency scanning hỗ trợ phát triển an toàn khi kết quả của nó đủ điều kiện cho một quyết định cụ thể và được nối tới hành động khắc phục, thay vì chỉ tồn tại như một bước chạy trong pipeline.
