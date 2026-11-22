# Cloud Adoption Framework và quá trình áp dụng Google Cloud

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao áp dụng Google Cloud là một thay đổi về **con người, quy trình, công nghệ và quản trị**, không chỉ là chuyển máy chủ lên đám mây.
2. Sử dụng **Google Cloud Adoption Framework (CAF)** để đánh giá bốn chủ đề **Learn, Lead, Scale, Secure** theo ba mức trưởng thành **Tactical, Strategic, Transformational**.
3. Chuyển kết quả đánh giá thành lộ trình **Assess → Plan → Deploy → Optimize**, có mục tiêu kinh doanh, người chịu trách nhiệm, kiểm soát rủi ro và chỉ số đo lường.
4. Nhận diện các quyết định nền tảng liên quan đến project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, phát hành tự động, quan sát hệ thống và chi phí.
5. Lập kế hoạch áp dụng Google Cloud cho một hệ thống thực tế, từ thử nghiệm nhỏ đến vận hành ổn định.

## 1. Cloud adoption là gì và CAF giải quyết vấn đề nào?

Một doanh nghiệp có thể tạo vài máy ảo trên **Compute Engine** trong một ngày, nhưng vẫn chưa có năng lực vận hành cloud ở cấp tổ chức. Khi thiếu mô hình phân quyền, quy trình thay đổi, cách kiểm soát chi phí hoặc kỹ năng xử lý sự cố, việc mở rộng từ một ứng dụng thử nghiệm sang hàng chục ứng dụng sản xuất sẽ trở nên khó dự đoán.

**Cloud adoption (áp dụng điện toán đám mây)** là quá trình đưa năng lực cloud vào cách tổ chức thiết kế, phát triển, triển khai, bảo vệ, vận hành và cải tiến sản phẩm. Quá trình này có thể bao gồm di chuyển hệ thống sẵn có, hiện đại hóa ứng dụng và xây dựng dịch vụ mới trực tiếp trên cloud.

**Google Cloud Adoption Framework** là khung đánh giá mức độ sẵn sàng và trưởng thành của tổ chức. Khung giúp trả lời ba câu hỏi:

- **Chúng ta đang ở đâu?** Các nhóm đã có kỹ năng, quyền quyết định, nền tảng tự phục vụ và biện pháp bảo vệ đến mức nào?
- **Chúng ta muốn tới đâu?** Năng lực nào thực sự cần để đạt mục tiêu kinh doanh, thay vì chạy theo một mức trưởng thành chung cho mọi hệ thống?
- **Cần thay đổi điều gì?** Chọn các khoảng trống quan trọng, người phụ trách và công việc ưu tiên để tiến bộ có thể kiểm chứng.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tiếp cận Google Cloud từ phân cấp tài nguyên, project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu; đồng thời thực hành lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. CAF là cầu nối giúp biến những kiến thức kỹ thuật đó thành một chương trình áp dụng cloud nhất quán.

### Phân biệt ba khung thường gặp

| Khái niệm | Câu hỏi chính | Đầu ra điển hình |
|---|---|---|
| **Cloud Adoption Framework** | Tổ chức đã sẵn sàng sử dụng cloud hiệu quả chưa? | Đánh giá năng lực, khoảng trống, lộ trình cải tiến |
| **Quy trình migration** | Chuyển một danh mục workload sang môi trường đích thế nào? | Danh mục ứng dụng, phương án di chuyển, từng đợt triển khai, xác nhận sau chuyển đổi |
| **Well-Architected Framework** | Kiến trúc và vận hành của workload có đáp ứng các yêu cầu chất lượng không? | Đánh giá thiết kế, độ tin cậy, bảo mật, chi phí, hiệu năng và vận hành |

Các khung bổ trợ nhau: **CAF định hướng sự thay đổi ở cấp tổ chức**, quy trình migration tổ chức việc chuyển workload và đánh giá kiến trúc giúp cải thiện chất lượng giải pháp cụ thể. Một chương trình áp dụng cloud cũng có thể bắt đầu bằng ứng dụng mới mà không có hoạt động migration.

## 2. Bốn chủ đề của Google Cloud Adoption Framework

CAF chính thức của Google Cloud mô tả bốn chủ đề **Learn, Lead, Scale, Secure**. Đây là những năng lực cần phát triển song song; chỉ đầu tư vào một chủ đề thường tạo ra điểm nghẽn ở chủ đề khác.

| Chủ đề | Trọng tâm | Dấu hiệu tiến bộ có thể quan sát | Câu hỏi cần đặt ra |
|---|---|---|---|
| **Learn — Học hỏi** | Kỹ năng và khả năng chia sẻ kiến thức | Đào tạo theo vai trò, thực hành trên môi trường thử nghiệm, tài liệu và cộng đồng nội bộ | Nhóm có thể tự thiết kế, triển khai, xử lý sự cố hay phụ thuộc hoàn toàn vào chuyên gia ngoài? |
| **Lead — Dẫn dắt** | Cam kết lãnh đạo và phối hợp giữa các nhóm | Nhà tài trợ, chủ sản phẩm, người chịu trách nhiệm nền tảng; mục tiêu chung và cơ chế ra quyết định | Ai quyết định ưu tiên, chấp nhận rủi ro và tháo gỡ các phụ thuộc liên phòng ban? |
| **Scale — Mở rộng** | Dịch vụ cloud phù hợp, tự động hóa và quy trình lặp lại được | Mẫu project, Infrastructure as Code, CI/CD, tiêu chuẩn vận hành, dịch vụ được quản lý | Khi thêm ứng dụng hoặc nhóm mới, có phải dựng lại mọi thứ thủ công? |
| **Secure — Bảo vệ** | Danh tính, tài nguyên, dữ liệu và kiểm soát liên tục | Phân quyền tối thiểu, log/audit, quản lý bí mật, chính sách và theo dõi cấu hình | Ai được phép truy cập dữ liệu nào, bằng cách nào và làm sao phát hiện sai lệch? |

### 2.1. Learn: xây dựng khả năng tự chủ

Học hỏi không chỉ là số chứng chỉ đạt được. Một nhóm phát triển cần biết cách đóng gói và triển khai ứng dụng; nhóm nền tảng phải hiểu IAM, VPC, tài khoản dịch vụ, giới hạn tài nguyên; nhóm vận hành cần biết đọc metric, log, trace và xử lý sự cố.

Ví dụ, trước khi đưa ứng dụng lên **Cloud Run**, nhóm thực hành triển khai ở môi trường thử nghiệm, đọc log, thiết lập cảnh báo, xác định lỗi kết nối **Cloud SQL** và thử quay về phiên bản trước. Bằng chứng trưởng thành là nhóm có **runbook** và tự khôi phục được trong bài diễn tập, thay vì chỉ hoàn thành một khóa học.

### 2.2. Lead: liên kết kỹ thuật với mục tiêu kinh doanh

Sự ủng hộ của lãnh đạo cần thể hiện qua mục tiêu, ngân sách, quyền quyết định và trách nhiệm rõ ràng. Cộng tác từ dưới lên cũng quan trọng: nhóm ứng dụng, bảo mật, dữ liệu, tài chính và vận hành cần cùng tham gia.

Ví dụ, mục tiêu “giảm thời gian phát hành từ mỗi tháng xuống mỗi tuần” dẫn đến quyết định dành ngân sách cho CI/CD, tự động kiểm thử, quản lý môi trường và đào tạo. Nếu chỉ đặt KPI “số lượng VM đã chuyển”, chương trình có thể hoàn thành chỉ tiêu kỹ thuật nhưng không cải thiện tốc độ giao hàng hoặc trải nghiệm khách hàng.

### 2.3. Scale: nhân rộng với quy trình có thể lặp lại

Khả năng mở rộng ở đây bao gồm **mở rộng năng lực tổ chức**, không chỉ tự động tăng số instance. Các quyết định thường gặp:

- Chuẩn hóa cấu trúc **organization → folder → project**, nhãn tài nguyên và cách quản lý billing.
- Tạo nền tảng mạng **VPC/subnet**, kết nối tới hệ thống hiện hữu, DNS và quy tắc tường lửa theo chính sách.
- Dùng **Terraform** hoặc công cụ IaC phù hợp để tái tạo cấu hình; dùng pipeline để kiểm tra và phát hành.
- Chọn **Cloud Run**, **GKE**, **Compute Engine** theo yêu cầu workload và năng lực vận hành; ưu tiên dịch vụ được quản lý khi giải quyết đúng bài toán.
- Duy trì mẫu giám sát, cảnh báo, sao lưu và quy trình xử lý sự cố cho các nhóm ứng dụng.

Ví dụ, khi cần thêm một project cho đội phân tích dữ liệu, quy trình có thể tự cấp project, áp dụng IAM và policy chuẩn, gắn billing, bật logging và đặt ngân sách cảnh báo; mỗi bước đều có kiểm chứng và quyền phê duyệt phù hợp.

### 2.4. Secure: bảo mật được thiết kế từ đầu

Các kiểm soát thực hành gồm phân quyền theo **least privilege**, tách danh tính người dùng và workload, quản lý **service account**, lưu bí mật trong **Secret Manager**, mã hóa và phân loại dữ liệu, giới hạn luồng mạng, audit log và chính sách tổ chức.

Phân biệt **trách nhiệm chung**: Google Cloud bảo vệ các thành phần hạ tầng do nhà cung cấp quản lý theo mô hình dịch vụ; khách hàng vẫn chịu trách nhiệm đối với dữ liệu, danh tính, cấu hình, quyền truy cập, ứng dụng và nhiều hoạt động vận hành thuộc phạm vi mình kiểm soát. Dùng dịch vụ được quản lý có thể giảm công việc duy trì máy chủ, nhưng không tự động giải quyết các sai cấu hình IAM hoặc quyền truy cập dữ liệu.

Ví dụ, với cơ sở dữ liệu khách hàng, chỉ tài khoản dịch vụ của ứng dụng cần quyền truy cập tối thiểu; truy cập quản trị phải có quy trình kiểm soát; bản sao lưu và khả năng khôi phục phải được kiểm tra định kỳ.

## 3. Ba mức trưởng thành: Tactical, Strategic, Transformational

Google Cloud mô tả **Cloud Maturity Scale** với ba mức. Đây là các mức trưởng thành theo **từng chủ đề CAF**; một tổ chức hoàn toàn có thể ở Strategic về bảo mật nhưng vẫn Tactical về đào tạo.

| Chủ đề | **Tactical** — tác nghiệp | **Strategic** — chiến lược | **Transformational** — chuyển đổi |
|---|---|---|---|
| **Learn** | Mỗi cá nhân tự học, phụ thuộc chuyên gia | Có chương trình đào tạo theo vai trò, chia sẻ kiến thức giữa nhóm | Học tập gắn vào công việc, cộng đồng thực hành và cải tiến liên tục |
| **Lead** | Từng nhóm tự thực hiện, mục tiêu rời rạc | Có chủ chương trình cloud, nhóm phối hợp liên chức năng | Cloud là năng lực chung để thúc đẩy sản phẩm và đổi mới kinh doanh |
| **Scale** | Thiết lập thủ công, thay đổi khó và rủi ro | Có mẫu hạ tầng, pipeline, quy trình quản trị và tự động hóa | Nền tảng tự phục vụ có kiểm soát, đo lường và tối ưu liên tục |
| **Secure** | Kiểm soát riêng lẻ, dựa nhiều vào rà soát thủ công | Danh tính, chính sách, log và quy trình bảo mật được chuẩn hóa | Kiểm soát và phát hiện sai lệch được tích hợp, tự động và cải tiến thường xuyên |

*Các biểu hiện trong bảng là ví dụ thực hành để người học tự đánh giá, không phải thang điểm chấm chính thức của Google Cloud.*

Điều quan trọng là **mức đích phụ thuộc vào mục tiêu và rủi ro**. Một nhóm triển khai website nội bộ nhỏ có thể chưa cần nền tảng Kubernetes nhiều cluster. Ngược lại, hệ thống thanh toán hoặc xử lý dữ liệu nhạy cảm cần tiêu chuẩn bảo mật, khôi phục và giám sát nghiêm ngặt ngay từ giai đoạn đầu, dù quy mô chưa lớn.

### Cách tổ chức một buổi đánh giá mức trưởng thành

1. **Xác định phạm vi:** toàn tổ chức, một đơn vị kinh doanh hoặc danh mục workload; ghi rõ phạm vi để tránh đánh giá mơ hồ.
2. **Thu thập bằng chứng:** quy trình phê duyệt, sơ đồ kiến trúc, pipeline, tài liệu IAM, ngân sách, báo cáo sự cố, kết quả diễn tập phục hồi, kế hoạch đào tạo.
3. **Đánh giá từng chủ đề:** gán Tactical, Strategic hoặc Transformational và ghi nguyên nhân; có thể khác nhau giữa các bộ phận.
4. **Xác định khoảng trống:** chẳng hạn ứng dụng đã tự động triển khai nhưng chưa có người sở hữu cảnh báo và sự cố.
5. **Ưu tiên công việc:** dựa trên giá trị kinh doanh, rủi ro, mức phụ thuộc, chi phí và khả năng thực hiện.
6. **Hẹn thời điểm đánh giá lại:** dùng cùng loại bằng chứng để xem năng lực có thay đổi thật hay không.

Ví dụ một phiếu đánh giá **nội bộ minh họa** (không phải định dạng API hay công cụ chính thức của Google):

~~~yaml
assessment:
  scope: "Nhóm vận hành sản phẩm bán hàng"
  business_goal: "Phát hành an toàn hằng tuần"
  themes:
    learn:
      current: tactical
      target: strategic
      evidence: "Chưa có diễn tập xử lý sự cố"
      next_action: "Tổ chức lab Cloud Monitoring và viết runbook"
    lead:
      current: strategic
      target: strategic
      evidence: "Đã có chủ sản phẩm và nhóm cloud chung"
      next_action: "Duy trì họp đánh giá rủi ro và kết quả"
    scale:
      current: tactical
      target: strategic
      evidence: "Tạo project và triển khai bằng thao tác tay"
      next_action: "Chuẩn hóa Terraform và pipeline CI/CD"
    secure:
      current: tactical
      target: strategic
      evidence: "Quyền truy cập chưa được rà soát định kỳ"
      next_action: "Chuẩn hóa nhóm IAM, service account và audit"
~~~

Chỉ dùng đánh giá này để **ra quyết định**. Không lấy trung bình các mức thành một điểm số duy nhất rồi che mất một rủi ro nghiêm trọng về Secure.

## 4. Chuyển kết quả CAF thành hành trình áp dụng Google Cloud

Trong hướng dẫn migration của Google Cloud, quy trình được trình bày thành bốn giai đoạn **Assess → Plan → Deploy → Optimize**. Đây là **các giai đoạn công việc**, khác với ba **mức trưởng thành** Tactical/Strategic/Transformational của CAF.

~~~mermaid
flowchart LR
    A["Assess: hiểu hiện trạng<br/>và khả năng sẵn sàng"] --> B["Plan: thiết kế nền tảng<br/>và các đợt triển khai"]
    B --> C["Deploy: triển khai, kiểm thử<br/>và chuyển đổi"]
    C --> D["Optimize: đo lường, cải tiến<br/>và mở rộng"]
    D --> E["Đánh giá lại Learn / Lead / Scale / Secure"]
    E --> A
~~~

### Giai đoạn 1 — Assess: hiểu hiện trạng và mục tiêu

**Đầu vào:** yêu cầu kinh doanh, hệ thống đang vận hành, giới hạn pháp lý hoặc dữ liệu, đội ngũ và ngân sách hiện có.

Các công việc trọng tâm:

- **Đặt mục tiêu có thể đo:** rút ngắn thời gian phát hành, mở rộng theo nhu cầu, tăng khả năng khôi phục, giảm công sức vận hành hoặc tăng tốc xây dựng sản phẩm.
- **Kiểm kê workload:** chủ ứng dụng, phiên bản hệ điều hành và database, dữ liệu, luồng kết nối, phụ thuộc nội bộ/bên ngoài, yêu cầu độ trễ và thời gian ngừng dịch vụ cho phép.
- **Phân loại dữ liệu và rủi ro:** dữ liệu cá nhân, yêu cầu vị trí lưu trữ, thời gian lưu giữ, quyền truy cập, yêu cầu kiểm toán.
- **Đo hiện trạng:** traffic, CPU/RAM, dung lượng, latency, tỷ lệ lỗi, chi phí tổng thể hiện hành và các mục tiêu khả dụng; xây dựng baseline để so sánh.
- **Đánh giá mức trưởng thành CAF:** xác định liệu con người, lãnh đạo, quy trình mở rộng và bảo mật có sẵn sàng cho workload dự kiến.
- **Thử nghiệm nhỏ nếu cần:** một proof of concept có giả thuyết và tiêu chí thành công rõ ràng.

**Đầu ra:** danh mục workload và phụ thuộc, đánh giá CAF, business case sơ bộ, rủi ro, yêu cầu phi chức năng và danh sách ứng viên cho đợt đầu. **Migration Center** có thể hỗ trợ việc khám phá tài sản và ước tính, nhưng vẫn cần người xác nhận dữ liệu và giả định.

### Giai đoạn 2 — Plan: thiết kế nền tảng và lộ trình

Khi biết nhu cầu, tổ chức thiết kế **landing zone** — tập hợp nền tảng và chính sách dùng chung trước khi cho workload sản xuất hoạt động.

| Thành phần cần quyết định | Ví dụ thiết kế trên Google Cloud | Tiêu chí kiểm tra |
|---|---|---|
| **Phân cấp tài nguyên** | Organization, folder theo đơn vị/môi trường, project theo workload | Rõ chủ sở hữu, phạm vi policy, ranh giới billing |
| **Danh tính và quyền** | Nhóm người dùng, IAM role tối thiểu, service account riêng cho workload | Không cấp vai trò quá rộng; có quy trình cấp/thu hồi quyền |
| **Kết nối mạng** | VPC, subnet theo region, DNS, firewall, Cloud VPN hoặc Interconnect khi cần | Có sơ đồ luồng, giới hạn truy cập, đường đi tới hệ thống phụ thuộc |
| **Bảo vệ dữ liệu** | Secret Manager, mã hóa và quản lý khóa phù hợp, backup, chính sách lưu giữ | Khả năng khôi phục được diễn tập; dữ liệu được phân loại |
| **Triển khai** | Terraform/IaC, kho mã nguồn, CI/CD, quy trình review và rollback | Tái tạo được môi trường, thay đổi được kiểm soát |
| **Quan sát và vận hành** | Cloud Logging, Cloud Monitoring, cảnh báo, dashboard, runbook | Có người trực và cơ chế xử lý sự cố |
| **Tài chính** | Billing account, budget và alerts, nhãn phân bổ chi phí | Theo dõi được chi phí theo nhóm, sản phẩm và môi trường |

Sau đó **phân nhóm workload thành các đợt (waves)** dựa trên độ phụ thuộc và rủi ro. Ứng dụng ít phụ thuộc có thể phù hợp với đợt đầu; các hệ thống chia sẻ dữ liệu và có yêu cầu downtime nghiêm ngặt cần kế hoạch phức tạp hơn.

Với từng workload, cân nhắc các chiến lược:

- **Rehost:** chuyển gần như nguyên trạng, ví dụ máy ảo từ trung tâm dữ liệu lên Compute Engine; triển khai nhanh hơn nhưng có thể giữ nguyên chi phí hoặc gánh nặng vận hành.
- **Replatform:** thay một phần nền tảng, ví dụ chuyển database tương thích sang Cloud SQL hoặc chạy container trên dịch vụ được quản lý.
- **Refactor/re-architect:** sửa kiến trúc để dùng autoscaling, xử lý bất đồng bộ hay dịch vụ serverless; cần thêm thử nghiệm và năng lực phát triển.
- **Replace/repurchase:** thay bằng sản phẩm hoặc dịch vụ khác khi hiệu quả hơn duy trì hệ thống tự xây.
- **Retain/retire:** tạm giữ workload chưa phù hợp để chuyển hoặc loại bỏ hệ thống không còn tạo giá trị.

Không mặc định phải container hóa mọi thứ. Quyết định dựa trên yêu cầu chạy ứng dụng, kỹ năng nhóm, rủi ro, tổng chi phí sở hữu và lợi ích mong đợi.

**Đầu ra:** landing zone đã được kiểm chứng, kiến trúc đích, lựa chọn chiến lược cho mỗi workload, thứ tự các đợt, ước tính chi phí, kế hoạch kiểm thử, rollback, trách nhiệm và mốc phê duyệt.

### Giai đoạn 3 — Deploy: triển khai có kiểm soát

Thực hiện **pilot** cho một workload nhỏ và có giá trị kiểm chứng, sau đó mở rộng theo các đợt. Một vòng triển khai điển hình:

1. Tạo hạ tầng bằng cấu hình đã được kiểm tra; áp dụng IAM, kết nối mạng, lưu bí mật và giám sát theo chuẩn.
2. Triển khai ứng dụng ở môi trường kiểm thử; kiểm thử tính năng, dữ liệu, tải, bảo mật và tích hợp.
3. Đồng bộ hoặc chuyển dữ liệu bằng phương pháp tương thích với hệ thống nguồn/đích; kiểm tra toàn vẹn và thời gian gián đoạn dự kiến.
4. Lập cửa sổ chuyển đổi (**cutover**), phương án rollback và cách liên lạc khi có sự cố.
5. Chuyển traffic theo kế hoạch; theo dõi lỗi, độ trễ, tính đúng dữ liệu và KPI kinh doanh; quyết định tiếp tục hoặc quay lui theo ngưỡng đã thống nhất.
6. Bàn giao cho nhóm vận hành với dashboard, cảnh báo, runbook, quyền truy cập và hồ sơ thay đổi.

**Đầu ra:** workload chạy được trong môi trường đích, bằng chứng kiểm thử, biên bản chuyển đổi, đánh giá sau triển khai và các vấn đề còn tồn đọng được giao người xử lý.

### Giai đoạn 4 — Optimize: tối ưu theo số liệu

Khi workload ổn định, dùng số liệu thực tế để cải thiện:

- **Độ tin cậy:** xác định SLI/SLO phù hợp, điều chỉnh cảnh báo, kiểm tra backup/restore, đánh giá vùng lỗi và thời gian phục hồi.
- **Chi phí:** phát hiện tài nguyên nhàn rỗi, quyền sử dụng hoặc kích thước vượt nhu cầu, theo dõi ngân sách và chi phí theo workload; đối chiếu với giá trị tạo ra.
- **Hiệu năng và mở rộng:** đo latency, throughput và mẫu tải trước khi thay đổi cấu hình autoscaling, bộ nhớ đệm, cơ sở dữ liệu hoặc kiến trúc.
- **An toàn:** rà soát quyền, xoay vòng bí mật khi cần, phát hiện cấu hình sai, cập nhật lỗ hổng và kiểm chứng các chính sách kiểm soát.
- **Năng lực tổ chức:** đưa kinh nghiệm pilot vào template, đào tạo nhóm tiếp theo và cập nhật đánh giá CAF.

**Optimize không kết thúc sau một đợt migration**. Đây là hoạt động liên tục để đưa việc sử dụng cloud từ mức triển khai đơn lẻ thành năng lực đáng tin cậy của tổ chức.

## 5. CAF ảnh hưởng đến lựa chọn dịch vụ như thế nào?

Chọn dịch vụ cần kết hợp nhu cầu kỹ thuật với năng lực **Learn**, điều phối **Lead**, mức chuẩn hóa **Scale** và yêu cầu **Secure**. Bảng sau gợi ý hướng đánh giá, không phải quy tắc chọn mặc định:

| Nhu cầu/workload | Lựa chọn Google Cloud có thể xem xét | Câu hỏi CAF cần trả lời trước |
|---|---|---|
| Ứng dụng phụ thuộc sâu vào máy ảo hoặc phần mềm hệ điều hành | **Compute Engine** | Nhóm có khả năng vá lỗi, sao lưu, giám sát và quản lý vòng đời VM không? |
| API hoặc worker stateless chạy trong container | **Cloud Run** | Ứng dụng đã tách trạng thái và quản lý kết nối, bí mật, autoscaling đúng cách chưa? |
| Nền tảng nhiều dịch vụ cần kiểm soát Kubernetes | **GKE** | Có lý do kỹ thuật rõ ràng và năng lực vận hành cluster, network policy, nâng cấp, giám sát không? |
| Database quan hệ tương thích với dịch vụ quản lý | **Cloud SQL** hoặc **AlloyDB** khi phù hợp | Có đánh giá tương thích phiên bản, hiệu năng, HA, backup, RPO/RTO và phương án migration không? |
| Lưu object như hình ảnh, tài liệu, backup | **Cloud Storage** | Có lớp lưu trữ, thời gian lưu giữ, truy cập và chính sách vòng đời thích hợp không? |
| Phân tích dữ liệu ở quy mô lớn | **BigQuery** | Có quản trị dữ liệu, kiểm soát truy vấn và chi phí, phân quyền tập dữ liệu không? |
| Giao tiếp bất đồng bộ giữa các thành phần | **Pub/Sub** | Nhóm đã xử lý retry, thông điệp lặp, thứ tự (nếu cần) và dead-letter chưa? |

Ví dụ: nếu nhóm nhỏ chỉ cần triển khai API stateless, Cloud Run thường giảm phần vận hành hạ tầng. Nếu ứng dụng cần daemon hệ điều hành đặc thù, Compute Engine có thể phù hợp hơn. Nếu đã có đội platform và nhiều workload đòi hỏi khả năng cấu hình Kubernetes, GKE có thể đáng đầu tư. Các lựa chọn đều cần được kiểm chứng bằng thử nghiệm và yêu cầu thực tế.

## 6. Tình huống xuyên suốt: doanh nghiệp bán lẻ chuyển hệ thống đặt hàng

Giả sử công ty **An Phát** có website đặt hàng chạy trên một số VM tự quản, một cơ sở dữ liệu PostgreSQL và hệ thống lưu ảnh sản phẩm cục bộ. Nhóm phát triển muốn phát hành hằng tuần, nhưng mỗi lần phát hành phải thao tác thủ công; nhóm vận hành lo mất dữ liệu hoặc gián đoạn hệ thống.

### 6.1. Đánh giá hiện trạng theo CAF

| Chủ đề | Quan sát | Mục tiêu ngắn hạn |
|---|---|---|
| Learn | Hai lập trình viên biết container, chưa ai diễn tập khôi phục database | Thực hành Cloud Run, Cloud SQL, Logging; kiểm tra restore |
| Lead | Có tài trợ ngân sách nhưng trách nhiệm vận hành chưa rõ | Chỉ định product owner, platform owner, security owner, người duyệt cutover |
| Scale | VM, cấu hình mạng và phát hành được quản lý thủ công | Tạo cấu hình IaC và pipeline deploy cho môi trường thử nghiệm |
| Secure | Tài khoản dùng chung và bí mật lưu trong tệp cấu hình | Tách IAM/service account, dùng Secret Manager, giới hạn luồng kết nối |

Điểm nghẽn quan trọng không nhất thiết là công suất VM. Ngay cả khi máy mới có thể chạy nhanh hơn, **quy trình phát hành và khôi phục** vẫn khiến mục tiêu kinh doanh khó đạt.

### 6.2. Thiết kế đích có điều kiện

- **Organization/folder/project:** tách project thử nghiệm và production, xác định chủ sở hữu, billing và chính sách truy cập phù hợp.
- **Frontend/API:** đánh giá chuyển sang Cloud Run nếu ứng dụng đóng gói container và không giữ trạng thái cục bộ; cân nhắc Compute Engine nếu yêu cầu hệ điều hành buộc phải giữ VM.
- **PostgreSQL:** kiểm tra phiên bản, extension, workload, tính năng cần dùng và yêu cầu kết nối trước khi chọn Cloud SQL; kế hoạch dữ liệu phải có kiểm tra đồng nhất và rollback.
- **Ảnh sản phẩm:** xem xét Cloud Storage, chuyển dữ liệu, xác định quyền truy cập và cache phù hợp.
- **Mạng/bảo mật:** thiết kế kết nối ứng dụng–database, sử dụng IAM tối thiểu, Secret Manager, kiểm soát egress và audit log theo yêu cầu thực tế.
- **Phát hành/vận hành:** pipeline có thử nghiệm và bước duyệt production, quan sát lỗi/latency, cảnh báo đến người trực, sao lưu và diễn tập phục hồi.

Đây là **phương án giả định để học**, chưa phải kiến trúc có thể đưa vào sản xuất khi chưa đo tải, kiểm tra tính tương thích, bảo mật và yêu cầu tuân thủ.

### 6.3. Tổ chức từng đợt

| Đợt | Việc làm | Điều kiện hoàn thành |
|---|---|---|
| **Pilot** | Dựng project thử nghiệm; triển khai phiên bản mẫu, cấu hình IAM/logging và pipeline | Ứng dụng chạy, log truy vết được, có người chịu trách nhiệm |
| **Dữ liệu và tích hợp** | Kiểm thử kết nối, di chuyển bản sao dữ liệu phù hợp và diễn tập restore | Dữ liệu đúng, backup khôi phục được, biết giới hạn downtime |
| **Production có kiểm soát** | Chuyển traffic theo kế hoạch, giám sát, sẵn sàng rollback | Chỉ số vận hành và nghiệp vụ đạt ngưỡng đã duyệt |
| **Nhân rộng** | Đưa bài học thành template; chuyển workload tiếp theo | Có bằng chứng tái sử dụng, chi phí và rủi ro được theo dõi |

### 6.4. Đo kết quả bằng gì?

Thay vì chỉ báo cáo “đã chuyển 5 VM”, nhóm theo dõi:

| Mục tiêu | Chỉ số | Cách sử dụng |
|---|---|---|
| Phát hành nhanh hơn | Tần suất deploy, lead time từ merge đến production | So sánh trước/sau và kiểm tra chất lượng phát hành |
| Phát hành an toàn | Tỷ lệ triển khai lỗi, thời gian khôi phục sau sự cố | Xác định lỗi quy trình, cải thiện runbook và rollback |
| Tin cậy với người dùng | Tỷ lệ request thành công, latency ở các phân vị, SLO | Điều chỉnh cảnh báo và ưu tiên cải thiện |
| Kiểm soát chi phí | Chi phí theo workload/đơn hàng, ngân sách và biến động sử dụng | Quyết định rightsizing, autoscaling và kế hoạch năng lực |
| Bảo vệ hệ thống | Số quyền truy cập quá rộng được xử lý, tỷ lệ kiểm tra restore đạt | Đo tiến bộ Secure bằng bằng chứng thực tế |

Các giá trị mục tiêu cần do doanh nghiệp tự đặt từ **baseline** và yêu cầu dịch vụ. Không có một con số SLO, ngân sách hoặc lịch chuyển đổi thích hợp cho mọi ứng dụng.

## 7. Mẫu kế hoạch áp dụng trong 90 ngày

Đây là **ví dụ lịch thực thi**, không phải thời hạn chuẩn của Google Cloud. Với hệ thống nhiều phụ thuộc, khâu đánh giá, bảo mật và migration có thể cần lâu hơn đáng kể.

| Khoảng thời gian | Kết quả cần tạo | Trách nhiệm chính |
|---|---|---|
| **Ngày 1–15** | Đề bài kinh doanh, phạm vi, workload inventory, dependency map, đánh giá CAF, baseline và rủi ro | Product owner, kiến trúc sư, vận hành, bảo mật |
| **Ngày 16–35** | Landing zone, IAM/VPC, logging, billing/budget, IaC, chiến lược từng workload, kế hoạch rollback | Platform/cloud team phối hợp security, finance |
| **Ngày 36–60** | Pilot hoàn chỉnh, kiểm thử dữ liệu và khôi phục, dashboard/cảnh báo, runbook, review kết quả | Nhóm ứng dụng và vận hành |
| **Ngày 61–75** | Triển khai production hoặc wave đầu nếu vượt tiêu chí nghiệm thu | Product owner quyết định go/no-go cùng các bên liên quan |
| **Ngày 76–90** | Tối ưu, rà soát chi phí, tổng kết sự cố, cập nhật mẫu chuẩn và đánh giá lại CAF | Platform, SRE/operations, finance, security |

Ở các cột thời gian, hãy gắn **điều kiện chuyển giai đoạn**: đủ bằng chứng về bảo mật và rollback trước production; có số đo thực tế trước tối ưu chi phí hoặc hiệu năng. Quyền quyết định go/no-go phải được xác định trước thời điểm cutover.

## 8. Các sai lầm dễ gặp

**Chỉ đếm số tài nguyên đã chuyển.** Workload chạy trên cloud không chứng minh khả năng vận hành đã trưởng thành. Cần đo trải nghiệm, độ tin cậy, tốc độ giao hàng, rủi ro và chi phí.

**Coi Secure là bước cuối.** Nếu để tài khoản chung, network mở rộng và bí mật trong mã nguồn tồn tại từ pilot, việc sửa khi đã lên production sẽ khó hơn. Thiết kế IAM, nhật ký và phân loại dữ liệu từ đầu.

**Chọn GKE cho mọi ứng dụng.** Kubernetes đem lại khả năng điều phối mạnh nhưng có chi phí học và vận hành. Chọn dịch vụ dựa trên yêu cầu và năng lực, kiểm chứng bằng pilot.

**Bỏ qua phụ thuộc và khả năng quay lui.** Ứng dụng có thể chạy tốt nhưng lỗi kết nối hệ thống thanh toán hoặc mất đồng bộ database khi cutover. Cần mapping phụ thuộc, kế hoạch dữ liệu, kiểm thử phục hồi và tiêu chí go/no-go.

**Tối ưu bằng chi phí hạ tầng đơn lẻ.** Giá VM thấp hơn không bảo đảm tổng chi phí thấp hơn nếu tăng công vận hành, thời gian downtime hoặc rủi ro. So sánh **TCO** và giá trị kinh doanh cùng với chi phí dịch vụ.

**Ép mọi chủ đề CAF lên cùng một mức.** Mục tiêu đào tạo, bảo mật, tự động hóa và lãnh đạo thường khác nhau theo phạm vi. Ưu tiên khoảng trống có ảnh hưởng lớn nhất đến kết quả.

## 9. Bài tập ứng dụng

Một nhóm nội bộ dự định đưa ứng dụng quản lý lịch làm việc lên Google Cloud. Ứng dụng có API Java, PostgreSQL, khoảng vài trăm người dùng, yêu cầu sao lưu hằng ngày, tích hợp với hệ thống xác thực của công ty và chưa có pipeline phát hành.

**Yêu cầu thực hành:**

1. Lập bảng **Learn, Lead, Scale, Secure** với bằng chứng hiện trạng, mức trưởng thành và mục tiêu trong ba tháng.
2. Chọn phương án triển khai bước đầu giữa Compute Engine, Cloud Run hoặc GKE; giải thích lựa chọn theo đặc tính ứng dụng và kỹ năng đội ngũ.
3. Liệt kê tối thiểu năm thành phần landing zone cần có trước khi chạy production.
4. Thiết kế một pilot có tiêu chí thành công, kiểm thử dữ liệu, phương án rollback và người ra quyết định.
5. Đề xuất ba chỉ số để đánh giá việc áp dụng cloud thành công **sau** triển khai.

**Gợi ý tự kiểm tra:** một phương án tốt phải nói rõ *vì sao chọn dịch vụ*, *ai sở hữu rủi ro*, *bằng chứng nào cho phép cutover* và *cách đo cải tiến*. Không có đáp án duy nhất cho dịch vụ triển khai khi thiếu thông tin về tải, yêu cầu nền tảng và giới hạn tổ chức.

## 10. Ghi nhớ và tài liệu tham khảo

- **CAF** trả lời câu hỏi về **mức sẵn sàng của tổ chức**, thông qua bốn chủ đề **Learn, Lead, Scale, Secure** và ba mức trưởng thành **Tactical, Strategic, Transformational**.
- **Assess → Plan → Deploy → Optimize** là quy trình thực thi migration trên Google Cloud, có thể lặp lại theo các đợt; khác với ba mức trưởng thành của CAF.
- Kết quả áp dụng cloud được đo bằng **giá trị kinh doanh, sự an toàn, khả năng vận hành và năng lực cải tiến**, bên cạnh mức độ sử dụng dịch vụ cloud.

Nguồn chính thức để đọc sâu:

1. [Google Cloud Adoption Framework](https://cloud.google.com/adoption-framework) — bốn chủ đề của khung áp dụng cloud.
2. [Migrate to Google Cloud: Get started](https://docs.cloud.google.com/architecture/migration-to-gcp-getting-started) — ba mức trưởng thành và các giai đoạn Assess, Plan, Deploy, Optimize.
3. [Migrate to Google Cloud: Assess and discover your workloads](https://docs.cloud.google.com/architecture/migration-to-gcp-assessing-and-discovering-your-workloads) — kiểm kê, phụ thuộc, TCO và chuẩn bị migration.
4. [Migration Center: About migration planning](https://docs.cloud.google.com/migration-center/docs/migration-planning-overview) — landing zone, phân nhóm workload thành waves và quản lý rủi ro.
