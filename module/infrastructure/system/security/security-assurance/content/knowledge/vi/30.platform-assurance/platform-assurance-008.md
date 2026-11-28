# Platform patching: Bảo đảm việc vá lỗi nền tảng có thể kiểm chứng

Trong một hệ thống đang vận hành, bản vá có thể sửa lỗ hổng bảo mật, lỗi ảnh hưởng tính ổn định, điểm yếu trong cơ chế xác thực hoặc hành vi không an toàn của các thành phần hạ tầng. Tuy nhiên, việc nhà cung cấp phát hành bản vá **không đồng nghĩa** hệ thống đã được bảo vệ. Một bản vá có thể chưa được triển khai, triển khai thiếu tài nguyên, chưa được kích hoạt sau khi khởi động lại, gây lỗi tương thích hoặc bị cấu hình cũ làm mất tác dụng.

**Platform patching** là quá trình xác định, đánh giá, lên kế hoạch, áp dụng và xác nhận các bản vá cho những lớp nền tảng vận hành ứng dụng: hệ điều hành máy chủ, hypervisor, firmware, dịch vụ nền tảng, runtime được quản lý, lớp điều phối container và các thành phần hạ tầng liên quan. Phạm vi trách nhiệm thay đổi theo kiến trúc và hợp đồng dịch vụ.

Trong chương **Platform assurance** của module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá **có bằng chứng** rằng biện pháp kiểm soát vá lỗi giúp hệ thống đáp ứng các mục tiêu bảo mật, đồng thời quản lý rủi ro của quá trình thay đổi. Người đánh giá cần nối được chuỗi: **yêu cầu bảo mật → tài sản và thành phần chịu ảnh hưởng → phiên bản/bản vá yêu cầu → triển khai thực tế → kiểm thử hiệu lực → phát hiện và khắc phục**.

Sau bài học, người học có thể xác định phạm vi và trách nhiệm patching; thiết kế quy trình ưu tiên dựa trên rủi ro; tổ chức cập nhật an toàn trên hệ thống đang chạy; xác minh trạng thái vá lỗi bằng chứng cứ kỹ thuật; và vận hành chương trình patch assurance liên tục.

## 1. Platform patching giải quyết vấn đề gì?

Một nền tảng thường bao gồm nhiều lớp phụ thuộc lẫn nhau:

~~~text
Ứng dụng và dữ liệu nghiệp vụ
          │
Runtime / thư viện nền tảng / middleware
          │
Orchestrator / container runtime / dịch vụ quản lý
          │
Hệ điều hành khách, kernel và các gói hệ thống
          │
Hypervisor / host OS / firmware / thiết bị vật lý
          │
Mạng, lưu trữ và các dịch vụ nền tảng khác
~~~

Mỗi lớp có thể phát sinh lỗ hổng hoặc lỗi vận hành. Việc vá một lớp không mặc nhiên vá toàn bộ các lớp khác. Ví dụ: cập nhật image cho workload container không tự cập nhật kernel của node; cập nhật worker node không tự nâng phiên bản ứng dụng chạy bên trong; cập nhật hệ điều hành VM không thay thế việc sửa cấu hình IAM sai.

Cần phân biệt:

| Thuật ngữ | Ý nghĩa | Lưu ý đối với assurance |
|---|---|---|
| **Patch / bản vá** | Thay đổi được phát hành để sửa lỗi, lỗ hổng hoặc hành vi cụ thể. | Phải biết lỗ hổng/phát hiện nào được xử lý và phiên bản khắc phục nào phù hợp. |
| **Update / cập nhật** | Thay đổi phần mềm, có thể bao gồm bản vá, tính năng mới hoặc thay đổi khác. | Không phải mọi update đều là bản vá bảo mật; cần xem release notes và mức độ ảnh hưởng. |
| **Upgrade / nâng cấp** | Chuyển sang phiên bản, nhánh hoặc thế hệ mới. | Có thể cần kiểm thử tương thích, thay đổi API và phương án migration. |
| **Hotfix / bản sửa khẩn** | Sửa một vấn đề cụ thể theo cơ chế phát hành của nhà cung cấp. | Cần kiểm tra điều kiện hỗ trợ, phạm vi sửa và xung đột với bản cập nhật sau. |
| **Mitigation / giảm thiểu** | Giảm khả năng khai thác hoặc tác động trong khi chưa vá hoặc không thể vá. | Không chứng minh lỗ hổng đã được loại bỏ; cần theo dõi rủi ro còn lại và hạn xử lý. |
| **Reboot / restart** | Khởi động lại thành phần để kích hoạt thay đổi nếu cần. | “Đã cài” có thể khác với “mã đã vá đang thực thi”. |
| **Baseline / mức cấu hình chuẩn** | Trạng thái phiên bản và cấu hình được phê duyệt cho nhóm tài sản. | Cần có phiên bản baseline, lý do và thời điểm hiệu lực. |
| **End of life/end of support** | Sản phẩm hoặc nhánh đã hết vòng đời/hỗ trợ theo chính sách nhà cung cấp. | Có thể không còn bản vá mới; phải nâng cấp, thay thế hoặc quản trị ngoại lệ rủi ro. |

**Patch compliance** chỉ phản ánh mức đáp ứng với chính sách cập nhật được xác định. **Security assurance** yêu cầu thêm bằng chứng rằng đúng tài sản đã được đánh giá, bản vá thực sự có hiệu lực, rủi ro được xử lý và các ngoại lệ có chủ sở hữu.

## 2. Ranh giới trách nhiệm theo từng mô hình nền tảng

Không thể gán mọi bản vá cho một nhóm duy nhất. Phải lập ma trận sở hữu từ **thành phần thực tế đang chạy** và mô hình shared responsibility.

| Nền tảng | Ai thường triển khai bản vá? | Khách hàng/tổ chức vẫn phải bảo đảm điều gì? |
|---|---|---|
| Máy chủ vật lý tự vận hành | Nhóm hạ tầng vận hành firmware, OS, hypervisor và dịch vụ thuộc quyền quản lý. | Kiểm kê, phối hợp bảo trì, đánh giá tương thích, cập nhật và thu thập bằng chứng ở các lớp. |
| Máy ảo IaaS | CSP vá hạ tầng vật lý/host thuộc trách nhiệm họ; khách hàng vá guest OS và phần mềm do mình cài. | Chọn image/phiên bản được hỗ trợ, lên lịch patch VM, khởi động lại khi cần và kiểm tra sau vá. |
| Managed Kubernetes | CSP thường vá các phần được quản lý theo đặc tả dịch vụ; khách hàng có thể phải nâng cấp phiên bản cluster, node pool, add-on và workload. | Phân biệt control plane, worker, network plugin, storage plugin, node image và manifest ứng dụng; kiểm tra chính sách hỗ trợ phiên bản. |
| Container platform tự quản | Đội platform quản lý orchestrator, node OS, container runtime và các add-on; đội ứng dụng quản lý image của workload. | Đảm bảo phối hợp giữa host, runtime, image, thư viện và quy trình triển khai. |
| PaaS/managed database | CSP vá hệ điều hành hoặc engine trong phạm vi dịch vụ được quản lý theo cơ chế cung cấp. | Chọn/duy trì engine version, maintenance window, tùy chọn nâng cấp, kiểm thử tương thích và xác minh sau bảo trì khi thuộc quyền khách hàng. |
| SaaS | CSP thường vận hành nền tảng và ứng dụng SaaS theo hợp đồng. | Kiểm tra cam kết/bằng chứng của CSP, cấu hình tenant, tích hợp, agent, connector hoặc tiện ích do khách hàng quản lý. |
| Thiết bị mạng/lưu trữ và phần mềm bảo mật | Bên sở hữu/vận hành thiết bị theo hợp đồng. | Theo dõi firmware, cấu hình, HA/failover, lịch bảo trì, hiệu lực bản vá và khả năng phục hồi. |

Bảng là mô hình **điển hình**, không phải cam kết áp dụng cho mọi sản phẩm. Có dịch vụ managed chỉ tự động cập nhật trong phạm vi nhất định, có dịch vụ yêu cầu khách hàng chọn phiên bản và chấp nhận maintenance window. Phải đối chiếu tài liệu chính thức của dịch vụ, thỏa thuận hỗ trợ và phạm vi shared responsibility.

**Trách nhiệm vận hành khác trách nhiệm giải trình.** Dù CSP hoặc MSP áp dụng bản vá, chủ sở hữu hệ thống của tổ chức vẫn phải đánh giá mức bảo đảm phù hợp với rủi ro, xác minh các nghĩa vụ còn thuộc phía mình và theo dõi những phần chưa có bằng chứng.

### Ma trận phân công đến cấp công việc

Với một cluster Kubernetes managed, cụm từ “CSP phụ trách Kubernetes” là quá chung chung. Có thể tách ra thành:

- **Control plane:** ai quyết định phiên bản mục tiêu, lịch nâng cấp, thời hạn hỗ trợ và xác minh API sau nâng cấp?
- **Worker node:** ai cập nhật node image, kubelet, runtime và thoát tải các pod an toàn?
- **Add-on:** ai cập nhật DNS, ingress controller, CNI, CSI, monitoring agent và admission controller?
- **Workload:** ai xây lại image nền, sửa thư viện, triển khai ứng dụng và kiểm tra regression?
- **Assurance:** ai nhận bằng chứng, đánh giá coverage, phát hiện ngoại lệ và đóng finding?

Mỗi công việc cần owner, tiêu chí hoàn thành và bằng chứng riêng. Một trách nhiệm “shared” không rõ phạm vi thường tạo khoảng trống giữa các nhóm.

## 3. Xây dựng inventory và baseline có thể kiểm tra

### 3.1. Inventory là điều kiện tiên quyết

Không thể xác nhận “đã vá đầy đủ” nếu không biết hệ thống có những gì. Inventory phải bao phủ cả tài sản lâu dài và tài sản tồn tại ngắn, chẳng hạn node auto-scaling hoặc workload chạy bằng image mới tạo.

| Thuộc tính inventory | Vì sao cần |
|---|---|
| Asset ID, tên cụm/tài nguyên, account/project, region, environment | Xác định phạm vi tài sản và tránh bỏ sót. |
| OS, kernel, runtime, firmware, product/engine và phiên bản | Ánh xạ advisory và bản vá phù hợp. |
| Image ID, template, artifact digest, nguồn build | Truy vết phiên bản gốc, nhất là với immutable infrastructure. |
| Chủ sở hữu, nhóm vận hành, mức nhạy cảm dữ liệu, độ quan trọng | Phân công trách nhiệm và ưu tiên dựa trên rủi ro. |
| Vị trí kết nối, mức phơi nhiễm Internet, ranh giới tin cậy | Đánh giá khả năng bị khai thác. |
| Phụ thuộc kỹ thuật, cụm HA, topology và maintenance window | Lập kế hoạch triển khai không gây gián đoạn ngoài mức cho phép. |
| Trạng thái hỗ trợ, thời điểm cập nhật gần nhất, bằng chứng gần nhất | Phát hiện thành phần EOL, bản vá trễ và bằng chứng đã cũ. |
| Patch policy, nhánh phát hành được phê duyệt và ngoại lệ | Xác định mục tiêu đánh giá cho đúng đối tượng. |

Nguồn thu thập có thể gồm cloud API, hệ thống quản lý cấu hình, package manager, image registry, orchestrator, CMDB, inventory agent và dữ liệu của nhà cung cấp. Với container, danh mục **image đang chạy theo digest** thường đáng tin hơn chỉ xem tag, bởi tag có thể trỏ tới image khác ở thời điểm khác. Với serverless và managed service, cần sử dụng các trường phiên bản và khả năng cấu hình mà dịch vụ thực sự công bố.

**Điều cần kiểm chứng:** inventory có bao phủ mọi account, region, site, node pool và môi trường trong phạm vi không? Thiếu quyền đọc hoặc thiếu một region phải ghi thành khoảng trống coverage; không coi tài nguyên chưa quan sát được là đã đạt.

### 3.2. Baseline phiên bản không chỉ là số lớn nhất

Baseline xác định hệ thống cần chạy những bản vá hay nhánh phiên bản nào, kèm thời điểm phải đạt và điều kiện hỗ trợ. Không thể áp dụng quy tắc “phiên bản mới nhất” cho mọi thiết bị: nhánh LTS, backport bảo mật, firmware vendor-customized hoặc image của nhà cung cấp có thể nhận bản vá nhưng giữ nguyên một số trường phiên bản upstream.

Một baseline đủ dùng cần chỉ rõ:

1. **Đối tượng:** loại tài sản, môi trường, service/OS/engine, nhánh phát hành.
2. **Nguồn thẩm quyền:** advisory và thông tin phiên bản được nhà cung cấp công bố cho đúng sản phẩm/nhánh.
3. **Điều kiện đạt:** gói đã được vá, build/revision hợp lệ, lỗ hổng đã khắc phục hoặc có biện pháp thay thế được phê duyệt.
4. **Thời hạn:** mốc phải xử lý theo rủi ro và cam kết nội bộ.
5. **Cơ chế xác minh:** máy nào đo, bằng chứng nào ghi nhận, kết quả nào được xem là đủ.
6. **Ngoại lệ:** ai có thẩm quyền chấp nhận rủi ro và khi nào phải đánh giá lại.

Ví dụ, một bản vá kernel có thể đã được cài vào filesystem nhưng tiến trình vẫn chạy kernel cũ. Baseline cần yêu cầu **đúng trạng thái thực thi sau reboot** nếu nhà cung cấp chỉ định phải khởi động lại.

## 4. Thu nhận thông tin bản vá và ưu tiên theo rủi ro

Thông tin đầu vào gồm advisory của nhà cung cấp, danh sách CVE áp dụng, mức độ nghiêm trọng, thông tin khai thác thực tế, sản phẩm/nhánh bị ảnh hưởng, bản vá khả dụng, hướng dẫn giảm thiểu, tình trạng hỗ trợ và dependency có liên quan.

Có thể sử dụng CVSS như một dữ liệu đánh giá mức độ nghiêm trọng, nhưng **không dùng CVSS làm yếu tố duy nhất** để quyết định thứ tự xử lý. Cần xem xét:

| Yếu tố | Câu hỏi cần trả lời |
|---|---|
| Khả năng bị khai thác | Đã có bằng chứng khai thác ngoài thực tế, exploit đáng tin cậy hoặc thông tin cảnh báo từ nguồn phù hợp chưa? |
| Bề mặt tấn công | Thành phần có Internet-facing không? Có cần xác thực hoặc điều kiện đặc biệt không? |
| Ngữ cảnh tài sản | Ảnh hưởng đến control plane, tài khoản đặc quyền, dữ liệu nhạy cảm hay dịch vụ trọng yếu nào? |
| Phạm vi bị ảnh hưởng | Bao nhiêu asset, region, node pool hoặc image đang chạy bị tác động? |
| Kiểm soát bù trừ | Có segmentation, giới hạn quyền, cấu hình vô hiệu hóa tính năng dễ bị khai thác hay không? Có bằng chứng hiệu lực không? |
| Tác động khi vá | Bản vá có đòi restart, thay API, cập nhật schema hoặc có nguy cơ gây ngừng dịch vụ không? |
| Giới hạn thời gian | Có deadline từ yêu cầu nội bộ, hợp đồng, rủi ro được phê duyệt hoặc chính sách của tổ chức không? |

Một vấn đề có mức CVSS cao nhưng chỉ ảnh hưởng tới tính năng chưa bật có thể được ưu tiên khác so với vấn đề có mức thấp hơn nhưng đang bị khai thác trên tài sản công khai. Kết luận phải được ghi cùng nguồn thông tin, thời điểm đánh giá, người phê duyệt và lý do.

### Phân loại luồng xử lý

- **Khẩn cấp:** dấu hiệu khai thác thực tế, khả năng tác động lớn và đường khai thác đáng tin cậy. Có thể áp dụng mitigation trước, sau đó patch theo cơ chế thay đổi khẩn.
- **Ưu tiên cao:** rủi ro đáng kể, bản vá đã khả dụng nhưng cần kiểm thử hoặc phối hợp lịch triển khai.
- **Thông thường:** cập nhật nằm trong lịch bảo trì và thời hạn được xác định theo chính sách.
- **Chưa thể vá:** thiếu bản vá, không hỗ trợ nhánh hiện hành hoặc xung đột kỹ thuật. Cần remediation thay thế, kế hoạch nâng cấp/thay thế và chấp nhận rủi ro có hạn.

Thời hạn xử lý phải do tổ chức phê duyệt theo mức rủi ro. Chẳng hạn, một đơn vị có thể đặt mục tiêu xử lý khẩn trong vài ngày và xử lý thường kỳ theo chu kỳ bảo trì; các con số này chỉ có ý nghĩa khi nêu rõ phạm vi, điều kiện tính thời gian và cơ chế ngoại lệ. **Không gán một mốc SLA chung như thể đó là yêu cầu bắt buộc của mọi tiêu chuẩn hoặc nhà cung cấp.**

## 5. Quy trình patching an toàn từ phát hiện đến xác nhận

~~~mermaid
flowchart TD
    A["Inventory + baseline + nguồn advisory"] --> B["Ánh xạ thành phần bị ảnh hưởng"]
    B --> C["Đánh giá rủi ro và mức ưu tiên"]
    C --> D{"Có thể vá ngay?"}
    D -->|Có| E["Kiểm thử patch và tác động phụ thuộc"]
    D -->|Chưa| M["Mitigation + owner + ngoại lệ có hạn"]
    M --> N["Theo dõi patch hoặc kế hoạch thay thế"]
    N --> C
    E --> F["Lập lịch, backup và kế hoạch phục hồi"]
    F --> G["Pilot / canary / rolling rollout"]
    G --> H["Kiểm tra phiên bản đang chạy và health"]
    H --> I{"Đạt tiêu chí?"}
    I -->|Không| J["Khoanh vùng lỗi, phục hồi, điều tra"]
    J --> C
    I -->|Có| K["Đối chiếu toàn bộ inventory và log"]
    K --> L["Lưu evidence, đóng finding và giám sát drift"]
    L --> A
~~~

### Bước 1 — Phát hiện và xác định ảnh hưởng

Nhận advisory, xác minh nguồn phát hành và xác định phiên bản bị ảnh hưởng theo đúng nhánh. Truy vấn inventory để tạo danh sách tài sản liên quan. Đánh dấu tài sản không thu thập được phiên bản hoặc không đủ quyền kiểm tra là **cần xác minh**; không suy luận rằng chúng không bị ảnh hưởng.

Cần lưu mã advisory/CVE (nếu có), nguồn tài liệu, thời điểm nhận, mapping sản phẩm–phiên bản, tập asset và kết luận applicability.

### Bước 2 — Phân tích phụ thuộc và tác động

Xem xét những ứng dụng, cluster, storage, network path, monitoring agent và API sẽ bị ảnh hưởng khi thay đổi. Kiểm tra yêu cầu restart, giới hạn tương thích trước/sau nâng cấp, thứ tự cập nhật và tình trạng HA. Một node có thể vá được về mặt kỹ thuật nhưng không thể restart tức thì nếu cluster không đủ bản sao phục vụ.

Lập kế hoạch fallback trước khi triển khai: backup/snapshot khả dụng, điểm khôi phục, phương án chuyển traffic, hạn chế rollback và người quyết định dừng rollout. Không coi snapshot là bằng chứng có thể khôi phục nếu chưa kiểm tra cơ chế restore.

### Bước 3 — Kiểm thử trên môi trường đại diện

Đánh giá thay đổi trong staging hoặc môi trường có workload, cấu hình, topology và tích hợp đủ đại diện. Kiểm tra ít nhất:

- Bản vá có cài đặt/thực thi đúng nhánh hay không, có yêu cầu restart không.
- Dịch vụ khởi động bình thường, health check/readiness đáp ứng yêu cầu.
- Các luồng nghiệp vụ, authentication, TLS, logging, mạng và kết nối dữ liệu không bị ảnh hưởng trái kỳ vọng.
- Migration, schema, plugin, kernel module, driver và agent có tương thích không.
- Mức hiệu năng, tải, độ trễ và lỗi sau thay đổi có còn trong ngưỡng chấp nhận không.

Không phải mọi lỗ hổng đều cần thử khai thác. Có thể xác nhận remediation từ bản vá và thông tin nhà cung cấp, kết hợp kiểm tra trạng thái phiên bản đang hoạt động và kiểm thử kỹ thuật an toàn khi phù hợp. Tuyệt đối không dùng exploit trên production ngoài phạm vi được ủy quyền.

### Bước 4 — Lên lịch và phê duyệt thay đổi

Chọn hình thức triển khai theo mức rủi ro: rolling update, canary, blue/green, thay thế image bất biến hoặc downtime có kế hoạch. Đặt điều kiện dừng rõ ràng (lỗi dịch vụ, latency, mất quorum, error budget hoặc dữ liệu sai lệch), lịch giám sát, đầu mối liên hệ và thời gian kiểm tra sau vá.

Với các hệ thống quan trọng, cần xem xét phụ thuộc giữa nhiều lớp trước khi thao tác. Ví dụ, việc nâng cấp control plane và worker node có thể phải tuân theo ma trận tương thích phiên bản của nhà cung cấp.

### Bước 5 — Triển khai và theo dõi rollout

Thực hiện thay đổi theo kế hoạch được duyệt, ghi ticket/change ID, người/thành phần tự động thực hiện, thời gian, bản trước/sau và kết quả từng batch. Không cập nhật đồng thời tất cả thành viên của cụm HA nếu điều đó làm mất tính sẵn sàng hoặc quorum.

Triển khai tự động không miễn trừ việc theo dõi kết quả. Một pipeline hoàn tất có thể chỉ chứng minh tác vụ chạy xong; cần kiểm tra xem **các tài nguyên đích đã chuyển sang phiên bản/vòng đời mong muốn hay chưa**.

### Bước 6 — Xác minh và đóng vòng kiểm soát

Sau triển khai, thu thập trạng thái đang chạy và kiểm tra tác động:

1. So sánh tập asset được cập nhật với inventory đầu vào, bao gồm node mới do auto-scaling tạo.
2. Xác minh package/build/engine phiên bản đã khắc phục; với kernel, firmware hoặc thành phần cần restart, kiểm tra bản đang hoạt động.
3. Xác minh sức khỏe dịch vụ và kiểm thử nghiệp vụ trọng yếu; kiểm tra log, alert và độ trễ.
4. Xác nhận lỗ hổng/phát hiện liên quan đã được xử lý bằng phương pháp phù hợp, không dựa duy nhất vào lời báo “job succeeded”.
5. Ghi bằng chứng, phát hiện còn mở, ngoại lệ được phê duyệt, owner và thời điểm review tiếp theo.

Khi phát hiện tình trạng sai lệch, tạo finding và retest sau khi sửa. Nếu phải phục hồi, vẫn duy trì nghĩa vụ xử lý lỗ hổng hoặc mitigation tạm thời; rollback không được coi là đóng thành công finding bảo mật.

## 6. Những trường hợp patching nền tảng cần chú ý riêng

### 6.1. Máy ảo và hệ điều hành

Ở IaaS, một tác vụ patch có thể cài gói thành công nhưng chưa kích hoạt vì máy ảo chưa reboot. Review phải so sánh **installed version** với **running version**, kiểm tra trạng thái dịch vụ và thực hiện restart được lên kế hoạch khi cần.

Nếu sử dụng golden image, phải cập nhật image nguồn, kiểm thử, thay instance cũ và kiểm tra không còn VM dùng image lỗi thời. Nếu chỉ sửa vài VM hiện hữu mà template auto-scaling vẫn cũ, tài nguyên mới có thể tái sinh cùng lỗ hổng.

Một số hệ điều hành và sản phẩm dùng backport bảo mật: số phiên bản upstream nhìn thấp không nhất thiết chứng minh thiếu bản vá. Cần dựa trên advisory, package release/build của nhà cung cấp và cơ chế xác minh tương ứng.

### 6.2. Hypervisor, firmware và thiết bị nền tảng

Firmware, BIOS/UEFI, controller và hypervisor có chu kỳ cập nhật riêng. Việc vá có thể yêu cầu reboot host, migration VM hoặc tạm dừng một phần dịch vụ. Kiểm tra phải gắn với hardware model, firmware compatibility và hướng dẫn hỗ trợ của vendor. Trên dịch vụ cloud được quản lý, thường phải dùng báo cáo/điều khoản assurance của CSP cho những lớp khách hàng không có quyền quan sát hoặc cập nhật trực tiếp.

Không tự suy luận rằng patch guest OS đã giải quyết vấn đề thuộc hypervisor, và không yêu cầu khách hàng thao tác lên hạ tầng chỉ CSP mới kiểm soát được.

### 6.3. Kubernetes và cluster orchestration

Cần đánh giá riêng control plane, worker node, container runtime, CNI, CSI, ingress controller, DNS, add-on và image của workload. Đối với managed Kubernetes, ranh giới trách nhiệm có thể khác theo dịch vụ và chế độ node management.

Với node pool tự quản, rolling patch thường cần:

1. Xác minh còn đủ capacity và các bản sao phục vụ khi rời một node.
2. Xem xét PodDisruptionBudget, health/readiness, local state, affinity và workload đặc biệt.
3. Đưa node ra khỏi lập lịch, di chuyển workload theo cơ chế an toàn, vá hoặc thay node.
4. Kiểm tra node trở lại trạng thái sẵn sàng, workload ổn định và dữ liệu không bị ảnh hưởng.
5. Lặp lại từng nhóm nhỏ, kiểm tra version thực tế trên tất cả node và node phát sinh trong quá trình autoscaling.

Nếu một ứng dụng chỉ có một replica hoặc sử dụng dữ liệu cục bộ không được bảo vệ, quy trình drain có thể gây downtime hoặc mất dữ liệu. Phải điều chỉnh kiến trúc/kế hoạch trước khi rollout.

**Không nhầm** patch của worker node với patch của container image. Một image ứng dụng chứa thư viện có lỗ hổng cần được build lại từ base image đã cập nhật, kiểm tra dependency, triển khai digest mới và xác nhận các pod đang chạy đều dùng image đúng.

### 6.4. Managed database và nền tảng PaaS

CSP có thể tự vá hệ điều hành hoặc thành phần nội bộ, nhưng khách hàng vẫn cần xét engine version, extension, maintenance window, cấu hình HA/failover, driver/client compatibility và kết quả sau thay đổi. Một bản nâng cấp major version có thể thay đổi query planner, kiểu dữ liệu, API hoặc hỗ trợ plugin.

Bằng chứng assurance gồm lịch bảo trì, version engine được báo cáo, dấu vết sự kiện nâng cấp, kết quả health, thử nghiệm ứng dụng và backup/restore nếu thuộc yêu cầu. Với lớp vô hình thuộc CSP, bằng chứng phải lấy từ tài liệu dịch vụ, báo cáo assurance và hợp đồng phù hợp.

### 6.5. Container image, pipeline và nguồn cung ứng

Một gói đã sửa trong repository nguồn chưa đồng nghĩa runtime đang an toàn. Chuỗi kiểm chứng cần bao phủ:

~~~text
Advisory / lỗ hổng
   → mã nguồn và dependency được cập nhật
   → build image mới
   → scan / kiểm tra provenance theo chính sách
   → phê duyệt phát hành
   → deploy image digest mới
   → xác minh workload đang chạy phiên bản đã vá
   → loại bỏ workload/image cũ theo chính sách
~~~

Nếu pipeline tái sử dụng cache, dùng tag có thể ghi đè hoặc tự động tạo node từ template cũ, cần bổ sung kiểm tra trên hiện trạng. SBOM hoặc danh sách dependency giúp xác định những thư viện ảnh hưởng nhưng **không tự chứng minh việc triển khai bản sửa lên production**.

### 6.6. Tài sản ngoài vòng hỗ trợ

Một nền tảng EOL có thể không còn nhận được bản vá cho lỗ hổng mới. Đánh dấu “không có patch” không đủ. Cần đưa ra phương án nâng cấp, thay thế, cô lập, giới hạn quyền hoặc chặn chức năng rủi ro trong thời gian chuyển đổi. Việc chấp nhận rủi ro phải có hạn, owner, điều kiện đánh giá lại và kế hoạch kết thúc trạng thái EOL.

## 7. Xử lý khi không thể vá ngay và quản trị ngoại lệ

Các nguyên nhân hoãn vá có thể gồm thiếu bản vá từ vendor, xung đột driver, yêu cầu chứng nhận ứng dụng, rủi ro gián đoạn vượt ngưỡng hoặc phần cứng không còn hỗ trợ. Không được biến “cần bảo trì sau” thành một kết luận PASS.

Các kiểm soát bù trừ có thể là cô lập mạng, loại bỏ public endpoint, giảm đặc quyền, tắt thành phần dễ bị khai thác, hạn chế nguồn truy cập, phát hiện hành vi khả nghi hoặc tăng giám sát. Mức độ hiệu quả phụ thuộc đường tấn công và phải được kiểm tra; WAF hoặc firewall không phải giải pháp thay thế cho mọi loại lỗ hổng.

Một ngoại lệ nên ghi:

| Trường | Nội dung |
|---|---|
| Tài sản và bản vá | Asset ID, service, phiên bản bị ảnh hưởng, advisory/CVE, thông tin patch. |
| Nguyên nhân | Lý do chưa vá, bằng chứng thử nghiệm hoặc giới hạn kỹ thuật. |
| Đánh giá rủi ro | Tác động, khả năng khai thác, exposure, kiểm soát bù trừ và rủi ro còn lại. |
| Người phê duyệt | Chủ sở hữu rủi ro có thẩm quyền; không chỉ người trực tiếp triển khai. |
| Thời gian | Ngày bắt đầu, ngày hết hạn, thời điểm đánh giá lại, deadline kế hoạch sửa. |
| Theo dõi | Ticket, trạng thái mitigation, alert, kết quả xác minh và phương án thay thế. |

Nếu có bản vá khả dụng sau đó hoặc xuất hiện bằng chứng khai thác mới, ngoại lệ phải được đánh giá lại sớm, không chờ đến ngày hết hạn.

## 8. Thiết kế bằng chứng cho chương trình patch assurance

### 8.1. Các lớp bằng chứng

| Lớp bằng chứng | Chứng minh điều gì? | Giới hạn cần lưu ý |
|---|---|---|
| Advisory và quyết định applicability | Thành phần nào có nguy cơ và bản vá nào liên quan. | Thông tin có thể đổi khi vendor cập nhật advisory; cần lưu phiên bản và thời điểm. |
| Inventory có timestamp | Tài sản/phiên bản nằm trong phạm vi đánh giá. | Có thể thiếu account, region, node tạm thời hoặc asset không được agent nhìn thấy. |
| Patch policy/baseline | Tổ chức yêu cầu trạng thái nào và đến khi nào. | Policy không chứng minh bản vá đã được triển khai. |
| Change record, ticket, pipeline log | Ai yêu cầu, ai triển khai, batch nào thành công/thất bại. | “Job succeeded” có thể không đồng nghĩa patch có hiệu lực. |
| Trạng thái từ host/API/runtime | Phiên bản package, kernel, engine, node hoặc image đang hoạt động. | Cần hiểu backport, reboot và giới hạn quan sát của dịch vụ managed. |
| Kết quả kiểm thử và giám sát | Hệ thống còn đáp ứng chức năng, SLO và kiểm soát sau vá. | Health check xanh chưa đủ chứng minh mọi nghiệp vụ và tính năng an toàn. |
| Retest/remediation record | Finding đã được xử lý, có kết quả xác nhận sau thay đổi. | Retest trên phạm vi hẹp có thể bỏ sót tài sản mới hoặc lỗi tái phát. |

### 8.2. Ví dụ control register ở dạng YAML

Đây là **bản ghi minh họa** cho việc lưu bằng chứng, không phải schema mặc định của một CSP hoặc công cụ triển khai:

~~~yaml
control:
  id: PLATFORM-PATCH-01
  name: "Critical platform patch remediation"
  objective: "Giảm rủi ro lỗ hổng nghiêm trọng trên nền tảng sản xuất"
  baseline_version: "2026.11"
  applicability: "Production VM và managed worker node"

assessment:
  id: "PATCH-REV-EXAMPLE-001"
  collected_at_utc: "2026-11-28T04:00:00Z"
  scope:
    environment: production
    asset_group: "payments-worker-pool"
    expected_assets: 12
    observed_assets: 12
  advisory_id: "VENDOR-ADVISORY-EXAMPLE"
  affected_build: "branch-old"
  required_state: "Vendor-fixed build trong nhánh được hỗ trợ"
  source: "Host inventory và cloud control plane"
  evidence:
    - "evidence/patch-review/inventory-export"
    - "evidence/patch-review/running-version-export"
    - "evidence/patch-review/change-ticket"
    - "evidence/patch-review/smoke-test-report"
  evaluation:
    verified_fixed_assets: 10
    pending_reboot_assets: 2
    result: FAIL

remediation:
  owner: "Platform Operations"
  accountable: "Payments Service Owner"
  next_action: "Hoàn tất khởi động lại có kiểm soát và retest"
  risk_exception_id: null
~~~

Các giá trị ngày giờ, build, ID, tên đội và số lượng trong ví dụ chỉ để minh họa. Kết quả là **FAIL** khi 2 asset vẫn chưa chạy bản vá đang có hiệu lực, ngay cả khi báo cáo cài đặt package cho biết tất cả đều thành công. Trạng thái chỉ được đổi sau khi xác minh đúng 12 asset và cập nhật bằng chứng mới.

Mỗi bằng chứng nên có nguồn, asset ID, thời điểm UTC, phương pháp thu thập, phiên bản của rule, phạm vi, owner và đường dẫn lưu có kiểm soát truy cập. Không đưa dữ liệu nhạy cảm, token, mật khẩu hoặc thông tin nhận dạng cá nhân không cần thiết vào bằng chứng. Với báo cáo CSP hoặc MSP, phải tuân theo quyền sử dụng và điều khoản bảo mật tương ứng.

### 8.3. Định nghĩa kết quả đánh giá

| Trạng thái | Khi nào dùng |
|---|---|
| **PASS** | Có bằng chứng đủ mới và đủ phạm vi chứng minh tất cả tiêu chí vá lỗi áp dụng đã được đáp ứng trên tài sản đang hoạt động. |
| **FAIL** | Có bằng chứng xác nhận chưa đạt tiêu chí: còn bản vá thiếu, còn runtime lỗi thời, quá hạn xử lý hoặc thiếu biện pháp theo policy. |
| **INCONCLUSIVE** | Thiếu inventory, API không đủ quyền, trạng thái reboot không rõ hoặc chưa thể xác định applicability. |
| **NOT_APPLICABLE** | Control/advisory thực sự không áp dụng cho thành phần; lưu lý do và căn cứ. |

**Ngoại lệ rủi ro** được ghi tách biệt với trạng thái kỹ thuật. Một tài sản chưa vá nhưng có mitigation được duyệt vẫn cần được theo dõi, không tự chuyển thành PASS chỉ vì rủi ro tạm thời được chấp nhận.

## 9. Kiểm tra trạng thái thực thi: “đã cài” khác “đã có hiệu lực”

Đây là một nguồn sai lệch phổ biến trong patch assurance:

| Quan sát | Có thể kết luận gì? | Cần kiểm tra thêm |
|---|---|---|
| Tác vụ patch trả exit code thành công | Tác vụ hoàn thành theo điều kiện của công cụ. | Phiên bản package, asset thực sự bị tác động, log lỗi từng bước. |
| Package manager ghi phiên bản mới | Bản cập nhật đã cài vào hệ thống file/package database. | Module/kernel/process có đang chạy bản cũ; cần restart hay không. |
| Image registry có image mới | Artifact đã được build hoặc push. | Deployment, node/pod đang chạy có dùng đúng digest không. |
| Managed service báo maintenance complete | Hoạt động bảo trì kết thúc theo cơ chế dịch vụ. | Phiên bản hiệu lực, trạng thái replica, error rate, tương thích nghiệp vụ. |
| Scanner không còn finding | Công cụ không thấy điều kiện trigger trong phạm vi quét. | Inventory, rule version, quyền quét, trường hợp false negative. |
| Service health check đạt | Các endpoint kiểm thử hoạt động. | Nghiệp vụ quan trọng, failover, log, backup và trạng thái bảo mật còn lại. |

Nếu vendor dùng backport, cần kiểm tra package revision và thông báo sửa lỗi của đúng nhánh. Việc so sánh số phiên bản upstream theo thứ tự chữ có thể báo sai: một bản của distro với số upstream thấp vẫn có thể chứa bản sửa được backport, và một build mới hơn về số không bảo đảm đã xử lý đúng CVE trên nhánh sản phẩm khác.

Vì vậy, tiêu chí kiểm tra nên dùng **vendor-fixed build hoặc thông tin sửa lỗi tương ứng** thay vì chỉ áp dụng bất đẳng thức so sánh phiên bản thuần túy. Khi không đủ thông tin kết luận, ghi INCONCLUSIVE và yêu cầu xác nhận từ vendor hoặc nhóm vận hành.

## 10. Đo lường chương trình patching

Các chỉ số hữu ích cần mẫu số rõ ràng và tách biệt các trường hợp chưa biết:

| Chỉ số | Công thức/cách hiểu | Điều cần kiểm soát |
|---|---|---|
| **Inventory coverage** | Số asset được nhận diện / số asset thuộc phạm vi theo nguồn kiểm kê đã đối chiếu. | Thiếu account, asset tạm thời hoặc tài sản không cài agent. |
| **Patch assessment coverage** | Số cặp asset–advisory áp dụng có kết luận đủ bằng chứng / tổng số cặp cần đánh giá. | Đừng coi INCONCLUSIVE là PASS. |
| **Patch compliance rate** | Số asset đạt baseline trong phạm vi / số asset áp dụng đã xác định. | Chốt thời điểm, phiên bản baseline và cách xử lý ngoại lệ rõ ràng. |
| **Time to remediate** | Thời gian từ mốc kích hoạt đo đến lúc đã có bằng chứng remediation. | Nêu rõ mốc bắt đầu: advisory, phát hiện nội bộ hay xác nhận applicability. |
| **Overdue exposure** | Số tài sản/phát hiện quá hạn theo mức độ ưu tiên. | Phân biệt quá hạn với mitigation/exception còn hiệu lực. |
| **Reboot pending** | Số asset đã cài bản vá nhưng chưa kích hoạt thay đổi cần restart. | Tránh tính chúng là hoàn tất. |
| **Patch failure/rollback rate** | Tỷ lệ batch/thay đổi thất bại hoặc phải phục hồi. | Gắn với chất lượng kiểm thử và phương án rollout. |
| **Recurrence rate** | Tỷ lệ lỗ hổng/phiên bản lỗi thời xuất hiện lại sau khi sửa. | Kiểm tra template, image, autoscaling và drift. |

Ví dụ: một nhóm có 80 VM trong phạm vi, trong đó 72 VM có bản kê phiên bản đáng tin cậy; 60 VM đã đạt yêu cầu patch, 8 VM còn thiếu và 4 VM chưa xác minh được điều kiện hiệu lực. Kết luận phải trình bày riêng **coverage = 72/80 = 90%** và **60 VM có bằng chứng đạt**, kèm 8 VM không được quan sát đầy đủ. Không được thông báo “75% hệ thống bảo mật” rồi che đi các giới hạn phạm vi.

Chỉ số tổng hợp không chứng minh tất cả rủi ro đã hết. Một asset có vai trò đặc quyền, Internet-facing và đang bị khai thác có thể quan trọng hơn nhiều asset thử nghiệm chậm một bản vá ít liên quan.

## 11. Những sai lầm thường gặp trong platform patching

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ tính số bản vá đã cài thành công | Không phát hiện patch chưa được kích hoạt, reboot pending hoặc cài sai asset. | Đọc trạng thái runtime và kiểm tra hậu triển khai. |
| Bỏ qua auto-scaling template / golden image | Node mới tái tạo phiên bản chứa lỗ hổng. | Cập nhật nguồn tạo tài nguyên và xác minh node mới. |
| Chỉ dựa vào CVSS | Không phân biệt tài sản phơi nhiễm và rủi ro khai thác thực tế. | Kết hợp exploitability, asset criticality và kiểm soát bù trừ. |
| Nâng cấp đồng thời mọi node | Mất quorum, mất HA hoặc cạn năng lực phục vụ. | Thử nghiệm, canary, rolling update, điều kiện dừng. |
| Coi managed service là đã tự vá mọi lớp | Khách hàng bỏ sót runtime, engine, node pool hoặc add-on cần tự quản. | Đọc ranh giới trách nhiệm theo sản phẩm và bằng chứng CSP. |
| Không phân biệt upstream version và bản vá backport | Phát sinh false positive/negative. | Đối chiếu advisory và build của đúng vendor/nhánh. |
| Có rollback nhưng không thử phục hồi | Không thể khôi phục vì thay đổi schema, firmware hoặc state không tương thích. | Xác định giới hạn rollback và diễn tập các luồng trọng yếu. |
| Chấp nhận hoãn vá không thời hạn | Lỗ hổng tích lũy, không có owner. | Ngoại lệ có thời hạn, mitigation được chứng minh và kế hoạch chấm dứt. |
| Chỉ quét một thời điểm | Không thấy VM mới, drift hoặc patch bị thay thế. | Kết hợp kiểm tra khi thay đổi và giám sát định kỳ theo rủi ro. |
| Không lưu evidence/version baseline | Không thể kiểm tra lại kết luận audit. | Gắn ID, thời điểm, rule version, kết quả và retest vào control register. |

## 12. Tình huống thực hành: vá kernel trên cluster xử lý đơn hàng

Một ứng dụng thương mại điện tử chạy trên cluster gồm **12 worker node** phân bố ở ba vùng sẵn sàng. Hệ thống cần cập nhật kernel để xử lý một advisory bảo mật ảnh hưởng đến image node hiện tại. Hai node mới được auto-scaling tạo gần đây vẫn dùng template cũ. Nhóm vận hành nhận báo cáo patch job thành công trên tất cả 12 node, nhưng dashboard cho thấy có hai node đang chờ reboot. Hệ thống đồng thời có một workload xử lý đơn hàng chỉ chạy một replica.

**Yêu cầu:** Nhóm assurance phải quyết định có thể đánh dấu kiểm soát vá lỗi là PASS chưa, xác định hành động an toàn và thu thập bằng chứng nào.

### Phân tích từng bước

**1. Xác định phạm vi và trách nhiệm.** Đối chiếu 12 node thực tế, image ID, kernel đang chạy, template auto-scaling, trạng thái cluster và ứng dụng quan trọng. Xác minh ai chịu trách nhiệm worker node, ai quyết định thời điểm drain/reboot, ai duyệt rủi ro nghiệp vụ và ai kiểm tra bằng chứng.

**2. Đánh giá tính hiệu lực của bản vá.** Báo cáo patch job thành công cho biết công việc cài đặt đã thực hiện, nhưng **hai node chưa reboot** có thể vẫn chạy kernel cũ. Nếu điều kiện sửa lỗi yêu cầu reboot, không được đánh dấu toàn bộ cluster PASS. Cần đối chiếu phiên bản đang chạy và khuyến cáo vendor; giữ trạng thái FAIL hoặc INCONCLUSIVE theo mức độ dữ liệu hiện có.

**3. Kiểm tra tính sẵn sàng.** Với workload một replica, thao tác drain có thể gián đoạn dịch vụ. Trước khi rollout, cần đánh giá khả năng tăng replica, lưu trạng thái, PodDisruptionBudget, readiness, quota, resource capacity và nhu cầu bảo trì có kế hoạch. Không thực hiện cập nhật đồng loạt.

**4. Rollout có kiểm soát.** Kiểm thử node image mới ở nhóm nhỏ, theo dõi lỗi và hiệu năng. Sau khi điều kiện ổn định đạt, thực hiện rolling node replacement hoặc patch/reboot từng batch thích hợp; dừng khi có lỗi vượt ngưỡng.

**5. Khắc phục nguồn tái phát.** Cập nhật image/template của node pool, xác nhận các node auto-scaling mới không dùng bản lỗi thời. Đây là điều kiện để phòng ngừa lỗi quay lại sau khi phần 12 node hiện tại đã được sửa.

**6. Retest và đóng finding.** Kiểm tra phiên bản kernel đang chạy, node readiness, trạng thái pod, các luồng nghiệp vụ đơn hàng, error rate, log và đầy đủ 12 asset. Ghi change ID, thời điểm, evidence link, kết quả retest và ngoại lệ nếu còn.

### Bảng kiểm bằng chứng cho tình huống

| Câu hỏi assurance | Bằng chứng cần có |
|---|---|
| Có kiểm kê đủ mọi node không? | Snapshot node list, node pool/ASG, region/AZ, mapping asset ID và timestamp. |
| Bản sửa đúng với nhánh đang dùng không? | Advisory vendor, fixed build, baseline đã phê duyệt. |
| Mọi node đã chạy bản sửa chưa? | Kết quả truy vấn kernel/runtime của từng node sau reboot/thay thế. |
| Có gián đoạn hoặc mất năng lực phục vụ không? | Readiness, workload replicas, PDB, health, error rate và biên bản quan sát. |
| Lỗi có quay lại khi scale không? | Image/template ID mới, thử tạo node và xác nhận version. |
| Finding có đủ điều kiện đóng không? | Ticket, owner, thay đổi thực tế, kết quả retest và phê duyệt kết luận. |

**Đáp án trọng tâm:** Không thể kết luận PASS chỉ dựa vào patch job thành công. Cần xác minh hiệu lực trên **tất cả node hiện hành**, đảm bảo khả năng phục vụ khi cập nhật, sửa nguồn image để tránh tái phát và lưu bằng chứng retest.

## 13. Checklist dành cho người làm Platform Assurance

Trước khi phê duyệt kết quả đánh giá patching, tự kiểm tra:

1. **Phạm vi:** Đã bao phủ toàn bộ asset, account, region, node pool, image, managed service và phần của bên thứ ba trong phạm vi chưa?
2. **Trách nhiệm:** Ranh giới CSP–khách hàng–MSP đã được làm rõ theo từng lớp chưa? Có owner và đầu mối accountable không?
3. **Nguồn thông tin:** Advisory đúng sản phẩm/nhánh, build khắc phục, baseline và tình trạng hỗ trợ đã được xác nhận chưa?
4. **Ưu tiên:** Có xét mức độ khai thác, vị trí phơi nhiễm, tác động, kiểm soát bù trừ và hạn xử lý không?
5. **Thay đổi an toàn:** Đã kiểm tra tương thích, backup/restore, quorum/HA, thời điểm bảo trì, điều kiện dừng và khả năng rollback chưa?
6. **Hiệu lực thực tế:** Có bằng chứng phiên bản đang chạy hoặc trạng thái dịch vụ sau update, bao gồm reboot và tài sản mới được tạo không?
7. **Chất lượng bằng chứng:** Có asset ID, thời điểm, nguồn thu thập, phiên bản rule, coverage, kết quả và giới hạn quan sát không?
8. **Khắc phục:** Các trường hợp FAIL/INCONCLUSIVE được gán owner, ticket, thời hạn và retest chưa? Các ngoại lệ có hạn và có người phê duyệt đúng thẩm quyền không?
9. **Vận hành liên tục:** Có cơ chế cảnh báo bản vá mới, rà soát EOL, phát hiện drift, cập nhật image nguồn và kiểm tra định kỳ không?

**Một chương trình platform patching chỉ đạt giá trị assurance khi chứng minh được rằng đúng tài sản đã nhận đúng biện pháp khắc phục, biện pháp đó đang có hiệu lực, dịch vụ vẫn đáp ứng mục tiêu vận hành và mọi rủi ro còn lại đều được nhận diện, phân công và theo dõi.**
