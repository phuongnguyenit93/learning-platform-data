# Phân chia đợt di chuyển theo phụ thuộc và giá trị nghiệp vụ

Di chuyển một hệ thống lên đám mây hiếm khi là thao tác đưa từng máy chủ sang môi trường mới theo một danh sách cố định. Một ứng dụng có thể gọi dịch vụ nhận diện, chia sẻ cơ sở dữ liệu với ứng dụng khác, nhận dữ liệu từ ERP tại trung tâm dữ liệu và phục vụ một quy trình kinh doanh không được phép gián đoạn. Vì vậy, **thứ tự di chuyển phải phản ánh cả quan hệ phụ thuộc kỹ thuật lẫn giá trị và rủi ro nghiệp vụ**.

Bài học này hướng dẫn cách biến danh mục ứng dụng thành các **migration wave** (đợt di chuyển) có phạm vi, điều kiện bắt đầu, kế hoạch chuyển đổi, tiêu chí nghiệm thu và phương án xử lý sự cố rõ ràng. Đây là một bài toán thiết kế kiến trúc đám mây: quyết định không chỉ ứng dụng nào đi trước, mà còn dữ liệu nào phải đi cùng, kết nối lai (hybrid) nào cần duy trì, năng lực hạ tầng nào phải sẵn sàng, và khi nào có thể dừng hệ thống cũ.

## 1. Migration wave là gì và vì sao cần chia đợt?

**Migration wave** là một nhóm workload được tổ chức để chuẩn bị, di chuyển, kiểm thử và ổn định trong một giai đoạn có kế hoạch. Mỗi wave có mục tiêu kinh doanh, danh sách đối tượng, người phụ trách, nguồn lực, cửa sổ chuyển đổi và tiêu chí hoàn tất.

Cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Workload** | Một ứng dụng hoặc năng lực kỹ thuật với tài nguyên, dữ liệu và cách vận hành cụ thể | Dịch vụ xử lý đơn hàng, database đơn hàng |
| **Migration group / cutover unit** | Các thành phần phải được chuyển cùng nhau hoặc theo một giao thức phối hợp chặt chẽ để giữ tính nhất quán | Dịch vụ đơn hàng, schema dữ liệu và tác vụ ghi đơn hàng |
| **Migration wave** | Một đợt quản trị có thể chứa một hoặc nhiều migration group và những lần cutover riêng | Wave 3 gồm hệ thống đơn hàng cùng các tích hợp bắt buộc |

Chia đợt giúp:

- Giới hạn **blast radius**: sự cố trong một đợt không nhất thiết lan tới toàn bộ hệ thống.
- Tạo nhịp học hỏi: pilot trước, chuẩn hóa quy trình rồi tăng quy mô ở các đợt sau.
- Điều phối nguồn lực hữu hạn như kỹ sư dữ liệu, mạng, bảo mật, vận hành và người dùng nghiệm thu.
- Đưa giá trị lên sớm: chọn những workload khả thi đem lại lợi ích rõ ràng mà không cần chờ toàn bộ hệ thống.
- Giữ tính liên tục của nghiệp vụ trong thời gian các thành phần chạy ở hai môi trường.

Không có quy tắc rằng “ứng dụng ít quan trọng luôn đi trước” hoặc “ứng dụng có ROI cao nhất luôn đi trước”. Ứng dụng ít quan trọng nhưng phụ thuộc vào một database chưa thể tách có thể không phù hợp làm pilot. Ứng dụng có giá trị lớn nhưng chưa có kế hoạch khôi phục cũng không đủ điều kiện vào đợt đầu.

## 2. Bắt đầu bằng mục tiêu nghiệp vụ và ranh giới thiết kế

Trước khi xếp lịch, nhóm kiến trúc và chủ sở hữu sản phẩm cần thống nhất **di chuyển để đạt điều gì**. Những mục tiêu thường gặp:

- Giảm rủi ro do trung tâm dữ liệu hoặc thiết bị sắp hết vòng đời.
- Tăng khả năng mở rộng trong mùa cao điểm, giảm thời gian triển khai tính năng.
- Cải thiện độ sẵn sàng, khôi phục sau thảm họa và khả năng quan sát.
- Đáp ứng hạn chót hợp đồng, quy định, yêu cầu lưu trữ dữ liệu hoặc cam kết với khách hàng.
- Giảm tổng chi phí sở hữu (TCO) trong một khung thời gian được xác định.

Mỗi mục tiêu phải đi kèm **chỉ số đo và ràng buộc**. Ví dụ:

| Mục tiêu | Chỉ số có thể đo | Ràng buộc cần đưa vào kế hoạch |
|---|---|---|
| Duy trì bán hàng | Tỷ lệ giao dịch thành công, số đơn thất lạc/trùng, thời gian gián đoạn | Tránh giờ cao điểm và thời gian chốt doanh thu |
| Tăng độ tin cậy | SLO dịch vụ, RTO, RPO, kết quả kiểm thử phục hồi | Có bản sao lưu và diễn tập khôi phục trước cutover |
| Cải thiện hiệu năng | p95/p99 latency, throughput ở tải mục tiêu | Đo cả độ trễ gọi qua ranh giới on-premises/cloud |
| Kiểm soát chi phí | Chi phí chạy song song, mạng liên vùng, bản quyền, vận hành | Có ngân sách cho giai đoạn dual-run và phương án tối ưu |
| Tuân thủ | Vị trí dữ liệu, quyền truy cập, nhật ký kiểm toán | Được phê duyệt các kiểm soát bảo mật trước khi chuyển dữ liệu |

Các chỉ số nêu trên phải lấy **baseline** từ hệ thống hiện tại và ngưỡng mục tiêu từ yêu cầu nghiệp vụ. Không tự xem một ngưỡng mẫu là SLO chung cho mọi dự án.

### 2.1. Quyết định phạm vi di chuyển

Đối với từng workload, xác định chiến lược phù hợp: giữ nguyên tại chỗ (**retain**), loại bỏ (**retire**), thay bằng sản phẩm khác (**repurchase**), chuyển hạ tầng gần như nguyên trạng (**rehost**), điều chỉnh nền tảng (**replatform**) hoặc cải tổ kiến trúc (**refactor/re-architect**). Các tổ chức có thể dùng biến thể phân loại “6R”, “7R”; tên gọi không quan trọng bằng **quyết định cụ thể cho từng hệ thống**.

Nếu một ứng dụng được giữ tại chỗ, nó vẫn có thể là **phụ thuộc đang hoạt động** của workload đã lên đám mây. Do đó, “không di chuyển” không có nghĩa là “không cần thiết kế kết nối, bảo mật, vận hành và kiểm thử”.

## 3. Khám phá và phân loại phụ thuộc

Tập hợp danh mục tài sản là điều kiện cần nhưng chưa đủ. Cần mô hình hóa các quan hệ tạo ra sự cố khi cắt khỏi môi trường cũ.

### 3.1. Những loại phụ thuộc cần ghi nhận

| Loại phụ thuộc | Câu hỏi phát hiện | Ảnh hưởng đến chia wave |
|---|---|---|
| **Gọi đồng bộ** | Dịch vụ A gọi HTTP/gRPC/TCP tới B với độ trễ và timeout bao nhiêu? | Có thể cần di chuyển gần nhau hoặc bảo đảm đường truyền lai đạt SLO |
| **Dữ liệu** | Ai đọc, ai ghi, có dùng chung bảng/schema hoặc giao dịch phân tán? | Có thể buộc ghép thành một cutover unit; dữ liệu thường quyết định ranh giới wave |
| **Sự kiện/batch** | Có queue, CDC, file ETL, lịch chạy và yêu cầu thứ tự sự kiện không? | Cần chuyển producer/consumer theo hợp đồng, chống lặp và xử lý trễ |
| **Định danh và bảo mật** | Ứng dụng dùng SSO, LDAP, khóa mã hóa, chứng thư, secret nào? | Nền tảng nhận diện và quyền truy cập phải sẵn sàng trước |
| **Mạng/DNS** | Dải IP, private endpoint, NAT, firewall, DNS, tải liên vùng ra sao? | Đặt điều kiện hạ tầng và giới hạn những phụ thuộc có thể chạy xuyên môi trường |
| **Vận hành** | Ai trực sự cố, cảnh báo liên thông, triển khai, backup và khôi phục bằng gì? | Đợt di chuyển chưa hoàn tất nếu chưa thể vận hành và phục hồi |
| **Nghiệp vụ/thời gian** | Hệ thống dùng cho chốt sổ, thanh toán, lễ bán hàng hay báo cáo pháp lý? | Giới hạn thời điểm cutover và thứ tự đạt giá trị |
| **Nhà cung cấp/bên ngoài** | Có whitelist IP, license, API đối tác, hợp đồng hoặc chứng nhận cần cập nhật? | Có thể tạo điều kiện chặn ngoài quyền kiểm soát của đội di chuyển |

Nguồn thu thập nên kết hợp **sơ đồ kiến trúc, tracing/APM, flow log, cấu hình ứng dụng, truy vấn database, pipeline dữ liệu, lịch batch, hạ tầng dưới dạng mã, phỏng vấn owner và diễn tập lỗi**. Không nên chỉ dựa vào bản sơ đồ cũ: phụ thuộc ít dùng như báo cáo cuối tháng có thể không xuất hiện trong một tuần quan sát.

Với mỗi quan hệ, ghi tối thiểu: **nguồn → đích; mục đích; giao thức; dữ liệu; tần suất/tải; đồng bộ hay bất đồng bộ; mức độ quan trọng; cách xác minh; người sở hữu**. Đánh dấu phụ thuộc chưa xác minh thay vì ngầm coi là không tồn tại.

### 3.2. Đồ thị phụ thuộc không tự động quyết định thứ tự

Giả sử có quan hệ **A → B**, nghĩa là A cần B để thực hiện một chức năng. Điều này **không bắt buộc** B phải được di chuyển trước A. Có ít nhất ba cách xử lý:

1. **Di chuyển B trước A** nếu B đã sẵn sàng và tương thích ngược khi A còn tại chỗ.
2. **Di chuyển A trước, giữ B tại chỗ** nếu kết nối hybrid, độ trễ, bảo mật và vận hành đáp ứng yêu cầu.
3. **Di chuyển A và B trong cùng cutover unit** nếu ràng buộc dữ liệu hoặc giao dịch khiến trạng thái chạy tách biệt không an toàn.

Muốn chuyển một quan hệ thành quy tắc sắp lịch, phải xác định rõ **điều kiện**: “B đã hoạt động trên cloud”, “B có endpoint hybrid được kiểm thử”, hoặc “A và B cutover đồng thời”. Đừng chuyển mọi mũi tên phụ thuộc thành một thứ tự cứng.

### 3.3. Vòng phụ thuộc và cơ sở dữ liệu dùng chung

Nếu A gọi B, B lại gọi A, việc chia A và B thành hai đợt có thể làm phát sinh vòng gọi xuyên mạng, tăng độ trễ và khó rollback. Tương tự, hai ứng dụng cùng ghi vào các bảng có ràng buộc giao dịch tạo ra một **ranh giới nhất quán dữ liệu**.

Hướng xử lý tùy trường hợp:

- **Ghép vào cùng migration group** khi không thể vận hành an toàn ở trạng thái tách rời.
- **Phá vòng phụ thuộc** bằng API có hợp đồng rõ ràng, event, outbox hoặc thành phần chuyển tiếp; kiểm thử khả năng tương thích trong giai đoạn chuyển tiếp.
- **Tách quyền sở hữu dữ liệu** theo domain và lộ trình schema; dùng CDC cho bên đọc khi phù hợp, tránh cho các hệ thống cùng ghi tùy ý vào hai nguồn.
- **Trì hoãn di chuyển** khi chưa chứng minh được tính nhất quán hoặc phương án khôi phục.

Một đồ thị ứng dụng đẹp nhưng bỏ qua các cạnh “cùng ghi database” có thể dẫn đến kế hoạch wave sai ngay từ đầu.

## 4. Ưu tiên theo giá trị nghiệp vụ và mức độ sẵn sàng

Sau khi biết các ràng buộc phụ thuộc, nhóm mới chọn trong **những phương án khả thi** dựa trên giá trị.

### 4.1. Hồ sơ đánh giá từng workload

Mỗi workload nên có một bản ghi quyết định ngắn:

| Trường | Nội dung cần chốt |
|---|---|
| Business owner và technical owner | Người chấp nhận rủi ro nghiệp vụ; người chịu trách nhiệm hệ thống |
| Giá trị và thời hạn | Lợi ích được kỳ vọng, mức khẩn cấp, quy định/hợp đồng |
| Độ quan trọng | Hậu quả mất dịch vụ, dữ liệu nhạy cảm, mức độ ảnh hưởng khách hàng |
| Phụ thuộc bắt buộc | Hệ thống, dữ liệu, tích hợp và điều kiện tương thích |
| Mức sẵn sàng | Kiểm thử tự động, tài liệu triển khai, quan sát, backup/restore, tài nguyên đích |
| Cách di chuyển | Rehost/replatform/refactor/retain/... và điểm thay đổi thiết kế |
| Rủi ro và biện pháp | Khả năng mất dữ liệu, downtime, chi phí, độ trễ, năng lực nhân sự |
| Tiêu chí chấp nhận | SLO/SLA, kết quả đối soát, UAT và điều kiện vận hành |

### 4.2. Điểm ưu tiên chỉ là công cụ hỗ trợ

Có thể dùng thang 1–5 cho bốn yếu tố:

- **B**: giá trị nghiệp vụ khi chuyển xong; 5 là rất cao.
- **U**: độ khẩn cấp theo hạn chót/cam kết; 5 là rất gấp.
- **S**: mức sẵn sàng kỹ thuật; 5 là đã đủ bằng chứng.
- **R**: rủi ro còn lại; 5 là rủi ro rất cao.

Một công thức minh họa:

\[
P=0.40B+0.25U+0.20S-0.15R
\]

Trọng số phải được chủ sở hữu nghiệp vụ và kiến trúc thống nhất; **P không phải một tiêu chuẩn ngành**. Đặc biệt, điểm cao không vượt qua được các điều kiện chặn như không có khả năng phục hồi dữ liệu, chưa được phê duyệt tuân thủ hay thiếu tích hợp bắt buộc.

Ví dụ đánh giá giả định:

| Workload | B | U | S | R | P | Kết luận hiện tại |
|---|---:|---:|---:|---:|---:|---|
| Đơn hàng | 5 | 5 | 2 | 5 | 2,90 | Chưa đủ điều kiện vì tích hợp và rollback |
| Tồn kho | 4 | 4 | 3 | 3 | 2,75 | Cần hoàn tất cầu nối tới ERP |
| Danh mục sản phẩm | 3 | 2 | 5 | 1 | 2,55 | Có thể làm pilot |

Điểm số đơn hàng cao nhất nhưng danh mục mới là lựa chọn hợp lý cho wave đầu **tại thời điểm đánh giá**. Khi điều kiện thay đổi, phải tính lại và ghi quyết định, không cố giữ thứ tự ban đầu.

### 4.3. Phân biệt “đáng làm sớm” và “có thể làm sớm”

Quyết định thứ tự nên qua hai lớp:

1. **Feasibility gate:** phụ thuộc, an toàn dữ liệu, kết nối, bảo mật, vận hành, kiểm thử, cửa sổ nghiệp vụ và nhân sự đã đáp ứng chưa?
2. **Prioritization:** trong tập các ứng viên đã qua gate, chọn tổ hợp có giá trị tốt nhất, rủi ro chấp nhận được và phù hợp năng lực đội.

Đợt đầu thường ưu tiên workload có tính đại diện, ranh giới rõ, ít tác động khách hàng và đủ công cụ quan sát để học quy trình. Tuy nhiên, nếu deadline pháp lý hoặc rủi ro trung tâm dữ liệu buộc chuyển một hệ thống quan trọng sớm, nên bổ sung nguồn lực và phương án kiểm soát thay vì dựa máy móc vào nguyên tắc “dễ trước”.

## 5. Thiết kế các wave từ đồ thị, giá trị và năng lực triển khai

Quy trình thực hành có thể gồm bảy bước.

### Bước 1: Lập danh mục và xác nhận phụ thuộc

Lập một hàng cho mỗi workload, database, integration hoặc thành phần hạ tầng có trách nhiệm độc lập. Đánh dấu **nguồn dữ liệu chuẩn (system of record)**, chiều đồng bộ và đường xử lý nghiệp vụ quan trọng. Với đường đi tạo doanh thu, lần theo **toàn bộ chuỗi gọi**, không chỉ dịch vụ ở cửa ngõ.

### Bước 2: Xác định nền tảng chung (wave 0)

Trước khi chuyển workload sản xuất, chuẩn bị các năng lực dùng chung cần thiết: phân vùng tài khoản/subscription/project, IAM/SSO, mạng và DNS, khóa/secret, logging, tracing, cảnh báo, IaC, CI/CD, backup, kiểm soát chi phí, vận hành sự cố và kết nối tới hệ thống còn tại chỗ.

**Wave 0 không nhất thiết là di chuyển toàn bộ hệ thống IAM hoặc ERP.** Nó là việc hoàn tất các năng lực và hợp đồng tích hợp cần cho đợt kế tiếp, ví dụ federation với SSO on-premises hoặc kết nối private tới ERP.

### Bước 3: Tìm các nhóm không thể chia nhỏ

Xác định nhóm thành phần có yêu cầu chuyển cùng nhau: dịch vụ và database cùng giao dịch, hệ thống có vòng phụ thuộc chặt, hoặc phiên bản giao thức không tương thích khi chạy lẫn. Với nhóm có thể tách, mô tả cơ chế tách như contract versioning, event bridge và bộ chuyển đổi dữ liệu.

Đừng gom mọi ứng dụng dùng chung một máy chủ thành một nhóm bắt buộc nếu có thể di chuyển độc lập; cũng đừng tách hai ứng dụng chỉ vì chúng nằm ở hai repository khác nhau.

### Bước 4: Tạo các ứng viên wave theo luồng giá trị

Tổ chức theo **năng lực kinh doanh** (ví dụ “tra cứu hàng”, “đặt hàng”, “giao hàng”) và ranh giới dữ liệu. Chọn đợt pilot, đợt có giá trị sớm, đợt chuyển hệ thống lõi và đợt ngừng nền tảng cũ. Kiểm tra những phụ thuộc xuyên môi trường sẽ tồn tại trong từng trạng thái trung gian.

### Bước 5: Kiểm tra năng lực và lịch nghiệp vụ

Một kế hoạch có thể đúng về kiến trúc nhưng không thực hiện được nếu mọi đợt đều cần cùng một DBA, nhóm an ninh mạng hoặc business owner. Với mỗi wave, xác nhận:

- Nhân sự chuẩn bị, người chấp thuận cutover, trực ca và người nghiệm thu;
- Năng lực đường truyền, quota, tài nguyên dự phòng, ngân sách chạy song song;
- Lịch cao điểm, lịch đối soát, đóng sổ, hạn chế thay đổi (change freeze);
- Thời gian diễn tập, thời gian chuyển dữ liệu, thời gian ổn định (hypercare) và thời gian sẵn sàng cho wave tiếp theo.

Các wave có thể chuẩn bị song song, nhưng những cutover dùng chung tài nguyên hoặc có phụ thuộc dữ liệu phải được sắp lịch phù hợp.

### Bước 6: Định nghĩa điều kiện vào và ra của từng wave

Ví dụ một **entry gate** bao gồm: kiến trúc đích được duyệt; phụ thuộc có owner; kết nối mạng, quyền truy cập và mã hóa được thử; dữ liệu có phương án đồng bộ; backup/restore đã diễn tập; test chức năng và tải đạt; runbook cutover/rollback có người phụ trách; nghiệp vụ chấp thuận thời điểm.

**Exit gate** gồm: người dùng truy cập đường mới; giao dịch đúng; đối soát dữ liệu đạt; chỉ số dịch vụ trong ngưỡng đã thỏa thuận; cảnh báo và on-call hoạt động; tài liệu/cấu hình được cập nhật; các tồn đọng có owner và thời hạn. Chỉ khi đã ổn định mới nâng phạm vi hoặc tốc độ của wave sau.

### Bước 7: Ghi quyết định và cập nhật liên tục

Kế hoạch wave là một **living plan**. Mỗi thay đổi phụ thuộc, rủi ro hoặc mức sẵn sàng phải cập nhật đồ thị, thứ tự, ngân sách và lịch. Những lựa chọn quan trọng nên ghi thành ADR (Architecture Decision Record): bối cảnh, lựa chọn, đánh đổi, quyết định, người duyệt và điều kiện xem xét lại.

## 6. Ví dụ xuyên suốt: di chuyển nền tảng bán hàng

Một doanh nghiệp có trang web bán hàng, danh mục sản phẩm, quản lý đơn, tồn kho, báo cáo và tích hợp ERP. Mục tiêu là mở rộng phục vụ mùa cao điểm và giảm phụ thuộc hạ tầng cũ, nhưng **ERP vẫn chạy on-premises** trong giai đoạn đầu. Cổng thanh toán của đối tác vẫn là dịch vụ bên ngoài.

### 6.1. Sơ đồ phụ thuộc minh họa

~~~mermaid
flowchart LR
    U[Khách hàng] --> F[Web bán hàng]
    F --> C[Catalog API]
    F --> O[Order API]
    O --> I[Inventory API]
    O --> P[Cổng thanh toán bên ngoài]
    O --> D[(Order DB)]
    I --> E[ERP on-premises]
    E --> S[Luồng đồng bộ danh mục]
    S --> C
    D --> X[CDC / sự kiện đơn hàng]
    X --> B[BI / báo cáo]
~~~

Mũi tên thể hiện luồng gọi hoặc dữ liệu; sơ đồ **không có nghĩa** tất cả nút đích phải di chuyển trước. Chẳng hạn, Inventory có thể chạy trên cloud và gọi ERP tại chỗ nếu độ trễ, an toàn mạng, khả năng khôi phục và hành vi khi mất kết nối đã được kiểm thử.

Đội triển khai xác định các điều kiện then chốt:

- Đường đồng bộ danh mục từ ERP tới Catalog chạy được qua kết nối đã kiểm thử.
- Inventory có cơ chế timeout, retry có giới hạn và xử lý khi ERP chậm; không giả định mạng hybrid luôn sẵn sàng.
- Order API và phần dữ liệu ghi giao dịch đơn hàng là một **cutover unit** vì tính nhất quán; thiết kế chuyển quyền ghi trước khi đổi luồng khách hàng.
- Tích hợp cổng thanh toán phải chống ghi nhận trùng; sử dụng idempotency key và quy trình đối soát với đối tác.
- BI tiêu thụ CDC/sự kiện, phải chịu được replay và xử lý trùng; không truy vấn trực tiếp vào database đang chuyển đổi để ghi dữ liệu.

### 6.2. Phân chia đợt đề xuất

| Đợt | Phạm vi | Giá trị/ý nghĩa | Điều kiện chính trước khi chuyển |
|---|---|---|---|
| **Wave 0: Foundation** | Landing zone, mạng hybrid, SSO, DNS, logging, secrets, IaC, backup, monitoring, đồng bộ danh mục | Tạo nền tảng vận hành an toàn và khả năng kiểm thử | Kết nối, phân quyền, diễn tập sự cố và kiểm soát chi phí đạt |
| **Wave 1: Pilot** | Catalog API và dữ liệu đọc danh mục | Giá trị sớm, ít giao dịch ghi, xác minh quy trình chuyển đổi | Feed ERP→Catalog ổn định; có đường quay về phiên bản cũ |
| **Wave 2: Integration** | Cầu nối ERP và Inventory API | Giảm phụ thuộc hạ tầng cũ ở lớp ứng dụng, kiểm thử mô hình hybrid | Hợp đồng tích hợp, độ trễ, retry và tình huống mất mạng đạt |
| **Wave 3: Core transactions** | Order API và Order DB trong một cutover unit; cấu hình tích hợp thanh toán | Di chuyển năng lực nghiệp vụ trọng tâm | Inventory sẵn sàng; CDC, đối soát đơn, thử tải và runbook khôi phục đạt |
| **Wave 4: Experience & analytics** | Web bán hàng và BI tiêu thụ sự kiện | Khép luồng khách hàng trên cloud, khai thác dữ liệu mới | Order ổn định; hợp đồng API và dữ liệu báo cáo được đối soát |
| **Wave 5: Decommission** | Gỡ các tài nguyên cũ không còn phục vụ lưu lượng | Giảm chi phí và nợ vận hành | Không còn consumer; đáp ứng lưu giữ dữ liệu, audit và rollback horizon |

Đây là một **phương án**, không phải thứ tự bắt buộc cho mọi hệ thống bán hàng. Nếu Web có thể sử dụng các API hybrid an toàn, có thể đưa Web sang sớm để tạo giá trị. Nếu Inventory và Order chung giao dịch database, phải điều chỉnh ranh giới và ghép cutover hoặc tách dữ liệu trước. Quyết định phụ thuộc bằng chứng khảo sát.

### 6.3. Trạng thái trung gian là một kiến trúc phải được vận hành

Giữa Wave 1 và Wave 3, Catalog đã ở cloud nhưng Order vẫn tại chỗ. Thiết kế cần giải quyết:

- **Đường gọi:** vị trí endpoint, DNS, định tuyến, chứng chỉ, timeout, circuit breaker và đường đi khi mất kết nối.
- **Dữ liệu:** ai là nguồn chuẩn; dữ liệu nào chỉ đọc, dữ liệu nào được ghi; độ trễ đồng bộ cho phép; cách phát hiện bản ghi thiếu/trùng.
- **Bảo mật:** danh tính dịch vụ, mTLS hoặc cơ chế xác thực phù hợp, phân đoạn mạng và nguyên tắc quyền tối thiểu.
- **Quan sát:** trace nối hai môi trường, dashboard cho luồng đặt hàng, log có correlation ID, cảnh báo theo ảnh hưởng nghiệp vụ.
- **Chi phí:** truyền dữ liệu, chạy hệ thống cũ và mới song song, bản sao cơ sở dữ liệu, chi phí vận hành hai mặt bằng.

Nếu độ trễ xuyên môi trường phá vỡ mục tiêu p95 hoặc lỗi mạng gây đơn hàng không thể đối soát, phải đổi thiết kế: đặt các thành phần gần nhau, thay gọi đồng bộ bằng sự kiện khi phù hợp, hoặc ghép wave.

## 7. Phối hợp dữ liệu, cutover và rollback

Dữ liệu thường là yếu tố rủi ro nhất trong một wave. Chuyển compute thành công không đồng nghĩa nghiệp vụ đã chuyển thành công.

### 7.1. Kế hoạch di chuyển dữ liệu

Với hệ thống có giao dịch ghi, cần trả lời:

1. **Nguồn chuẩn nằm ở đâu trước, trong và sau cutover?** Tại một thời điểm, quyền ghi phải rõ ràng.
2. **Chuyển dữ liệu ban đầu thế nào?** Bulk copy, backup/restore, replication hoặc công cụ chuyển đổi schema.
3. **Bắt kịp thay đổi ra sao?** CDC, log shipping hay luồng ứng dụng có thứ tự, kèm watermark và đo replication lag.
4. **Kiểm tra đúng dữ liệu bằng gì?** Số lượng, checksum, khóa ngoại, số dư/giá trị tổng, các bất biến nghiệp vụ (business invariants).
5. **Dữ liệu tạo ra sau cutover được bảo vệ thế nào?** Backup, khôi phục và hướng xử lý nếu quay lại môi trường cũ.

Đối với cơ sở dữ liệu có nhiều bên ghi, tránh thiết kế **dual-write tùy ý**: một giao dịch thành công ở nơi A nhưng thất bại ở nơi B tạo chênh lệch khó sửa. Nếu cần ghi hai phía, phải thiết kế cơ chế đồng bộ, idempotency, phát hiện xung đột và bù trừ rõ ràng; thường nên ưu tiên **một nguồn ghi** trong từng giai đoạn.

### 7.2. Một trình tự cutover điển hình

~~~text
1. Chốt baseline, chủ sở hữu và điều kiện Go/No-Go.
2. Sao lưu hoặc tạo restore point; xác minh thật sự phục hồi được.
3. Đưa dữ liệu đích đến trạng thái gần đồng bộ; kiểm tra watermark/lag.
4. Tạm dừng hoặc kiểm soát các luồng ghi cần thiết; hoàn tất đồng bộ cuối.
5. Chuyển quyền ghi và định tuyến lưu lượng theo runbook.
6. Chạy smoke test, giao dịch thử, đối soát và giám sát SLO.
7. Quyết định giữ đích, khôi phục theo phương án được chứng minh
   hoặc áp dụng sửa lỗi tiến (forward fix) khi không thể quay ngược.
8. Bàn giao trực vận hành và hypercare; chưa vội xóa nguồn cũ.
~~~

Độ dài thời gian read-only, dừng ghi, giảm TTL DNS hoặc chuyển theo tỷ lệ lưu lượng phụ thuộc công nghệ và cam kết của sản phẩm. Chuyển một phần lưu lượng **không an toàn** nếu hai nơi cùng ghi vào dữ liệu không có cơ chế nhất quán.

### 7.3. Rollback là khả năng được kiểm thử, không phải lời hứa

Runbook cần nêu rõ:

- **Điểm quyết định:** trước và sau bước nào còn có thể quay lại?
- **Tín hiệu kích hoạt:** lỗi giao dịch, chênh lệch đối soát, latency, tính toàn vẹn dữ liệu hoặc sự cố bảo mật.
- **Dữ liệu phát sinh:** có thể đồng bộ ngược an toàn, bù trừ nghiệp vụ hay phải xử lý tiến?
- **Người có quyền:** ai đưa ra lệnh Go/No-Go và ai thực thi?
- **Bằng chứng diễn tập:** đã phục hồi từ backup, kiểm thử chuyển tuyến và đối soát chưa?

Ví dụ, một dự án có thể đặt ngưỡng thử nghiệm “tỷ lệ lỗi giao dịch vượt 1% trong 5 phút” hoặc “p95 gấp đôi baseline trong 15 phút”; **đây chỉ là số minh họa**. Ngưỡng thực phải gắn với SLO, mùa vụ và hành vi bình thường. Đặc biệt, một thanh toán đã được đối tác ghi nhận không thể xóa chỉ bằng cách rollback database: cần idempotency, tra soát và quy trình hoàn tiền/bù trừ khi thích hợp.

## 8. Mẫu Wave Plan để đội dự án cùng thực thi

Một bản kế hoạch hữu ích có thể dùng bảng sau và bổ sung liên kết tới thiết kế chi tiết:

| Trường kế hoạch | Nội dung ví dụ |
|---|---|
| Wave ID / tên | W3 – Order core |
| Kết quả nghiệp vụ | Đơn hàng mới được xử lý từ cloud, không mất hoặc nhân đôi đơn |
| Phạm vi | Order API, Order DB, luồng CDC, cấu hình payment integration |
| Ngoài phạm vi | ERP on-premises, cổng thanh toán bên ngoài |
| Dependency gate | Inventory API ổn định; dữ liệu đơn đối soát đạt; PSP xác nhận luồng tích hợp |
| Migration strategy | Replatform ứng dụng; database replicate rồi chuyển quyền ghi |
| Người chịu trách nhiệm | Business owner, tech lead, DBA, SRE, security, người duyệt change |
| Kế hoạch triển khai | Dry run → đóng băng thay đổi → đồng bộ cuối → cutover → nghiệm thu |
| Tiêu chí Go/No-Go | Backup/restore đạt; kiểm thử tải đạt; runbook và nhân sự trực đủ |
| Tiêu chí thành công | Giao dịch, dữ liệu, SLO và nghiệp vụ đạt ngưỡng đã phê duyệt |
| Kế hoạch sự cố | Chuyển tuyến về nguồn chỉ khi an toàn dữ liệu; nếu không, forward fix/compensation |
| Hypercare và kết thúc | Dashboard, trực tăng cường, ký nghiệm thu, đóng tồn đọng trước wave sau |

Nên quản lý **risk register** cho từng wave với xác suất, mức ảnh hưởng, biện pháp giảm thiểu, người sở hữu và tín hiệu kích hoạt. Một rủi ro có điểm cao nhưng chưa có phương án xử lý phải là vấn đề cần quyết định, không được che bởi tiến độ phần trăm.

### 8.1. Bảng điều khiển theo dõi

Không nên chỉ báo “đã chuyển 70% máy chủ”. Các chỉ số hữu ích hơn gồm:

- **Readiness:** số workload đã qua entry gate, phụ thuộc chưa có owner, số lần dry run đạt.
- **Delivery:** migration group đã cutover, số rollback/forward fix, thời gian hoàn tất, tỉ lệ task đúng hạn.
- **Reliability:** availability, p95/p99, error rate, độ trễ sự kiện, kết quả đối soát và SLO burn.
- **Security & operations:** mức tuân thủ cấu hình, cảnh báo có người nhận, backup/restore pass, sự cố sau di chuyển.
- **Business value:** kết quả kinh doanh đo được và mức giảm nợ hạ tầng/chi phí sau khi tắt hệ thống cũ.

Một wave chỉ được ghi “hoàn tất” khi **vận hành được và đạt tiêu chí**, không phải ngay khi máy chủ hoặc container đã chạy trên cloud.

## 9. Đánh đổi kiến trúc theo Well-Architected

Phân chia wave là quyết định tối ưu nhiều mục tiêu, liên quan trực tiếp tới các trụ cột kiến trúc:

| Góc đánh giá | Câu hỏi khi lựa chọn wave | Ví dụ đánh đổi |
|---|---|---|
| **Operational Excellence** | Có runbook, IaC, quan sát, quy trình thay đổi và owner chưa? | Di chuyển ít workload hơn để chuẩn hóa vận hành trước khi tăng tốc |
| **Reliability** | RTO/RPO, khả năng chịu lỗi và xử lý phụ thuộc hybrid có đạt không? | Ghép ứng dụng với dữ liệu để giảm lỗi nhất quán, dù wave lớn hơn |
| **Security** | Quyền tối thiểu, mã hóa, vị trí dữ liệu và audit có kiểm chứng không? | Giữ dữ liệu nhạy cảm tại chỗ cho tới khi kiểm soát đích đạt |
| **Performance Efficiency** | Độ trễ và thông lượng qua mạng có đáp ứng không? | Chuyển các dịch vụ gọi đồng bộ rất nhiều lần sang cùng vùng |
| **Cost Optimization** | Chi phí chạy song song, truyền dữ liệu, license, rollback và vận hành bao nhiêu? | Rút ngắn thời gian dual-run nhưng vẫn đủ cửa sổ kiểm chứng |
| **Sustainability** | Có giảm tài nguyên nhàn rỗi và loại bỏ hạ tầng dư thừa sau ổn định không? | Có kế hoạch decommission có kiểm soát thay vì duy trì hai hệ thống vô hạn |

Một wave nhỏ giảm phạm vi sự cố nhưng có thể kéo dài thời gian vận hành hybrid và tăng chi phí. Một wave lớn giảm giai đoạn chuyển tiếp nhưng phức tạp hơn khi kiểm thử và rollback. Kích thước wave phù hợp phụ thuộc **ranh giới dữ liệu, năng lực đội và mức rủi ro tổ chức chấp nhận**.

## 10. Những cách chia wave dễ thất bại

**Chia theo danh sách máy chủ hoặc phòng ban:** các phụ thuộc thực tế không đi theo ranh giới tổ chức. Cách khắc phục là lập đồ thị theo luồng nghiệp vụ và dữ liệu, sau đó mới xét owner.

**Chỉ dựa vào điểm ROI:** workload có giá trị cao nhưng không vượt qua entry gate bị đưa vào lịch quá sớm. Cần tách feasibility gate khỏi việc xếp hạng ưu tiên.

**Chuyển application trước khi hiểu nguồn ghi dữ liệu:** hai môi trường ghi vào cùng thực thể, gây sai lệch và không thể rollback. Cần thiết kế chuyển quyền ghi và tiêu chí đối soát trước.

**Giữ phụ thuộc hybrid quá lâu mà không đo:** nhiều lượt gọi đồng bộ xuyên môi trường làm tăng latency, egress và điểm lỗi. Cần đo call path thực tế, giới hạn thời gian tồn tại của trạng thái trung gian.

**Xem thành công kỹ thuật là thành công nghiệp vụ:** container khỏe nhưng quy trình hoàn tiền, chốt sổ, batch đêm hoặc báo cáo cuối tháng hỏng. Cần bộ test hành trình nghiệp vụ và bằng chứng UAT theo lịch vận hành.

**Không dành thời gian cho hypercare và decommission:** đội triển khai bước sang wave tiếp khi cảnh báo, dữ liệu và vận hành còn chưa ổn định; hệ thống cũ vẫn phát sinh chi phí. Cần exit gate, thời gian ổn định và đợt gỡ hạ tầng rõ ràng.

## 11. Bài tập thiết kế wave

Một công ty có năm workload: **Identity** (SSO hiện tại có thể federation), **Catalog** (chủ yếu đọc), **Order** (ghi đơn), **Inventory** (gọi ERP tại chỗ) và **BI** (đọc dữ liệu đơn qua CDC). Order phụ thuộc Inventory; Catalog nhận dữ liệu đồng bộ từ ERP; BI cần dữ liệu Order. Đội dự án có một DBA chuyên trách và chỉ đủ năng lực xử lý **một cutover dữ liệu ghi lớn tại một thời điểm**.

Hãy lập ba đến bốn wave sau wave nền tảng, xác định:

1. Thành phần nào cần di chuyển cùng nhau và thành phần nào có thể tạm giữ tại chỗ?
2. Nếu Inventory chưa có cơ chế chịu lỗi mạng hybrid, Order có nên vào wave đầu không?
3. Ba điều kiện Go/No-Go quan trọng nhất cho wave chứa Order là gì?
4. Khi BI chuyển sau Order, làm thế nào chứng minh dữ liệu báo cáo không thiếu hoặc trùng?

**Một đáp án tham khảo:**

| Đợt | Phạm vi | Lý do |
|---|---|---|
| Wave 0 | SSO federation, mạng hybrid, IAM, DNS, logging, backup, CDC nền tảng | Tạo điều kiện để các ứng dụng tương tác an toàn |
| Wave 1 | Catalog | Pilot luồng đọc, xác minh feed ERP và khả năng vận hành |
| Wave 2 | Inventory và cầu nối ERP | Đo độ trễ, kiểm thử timeout và phục hồi khi mất đường truyền |
| Wave 3 | Order cùng database/khối dữ liệu giao dịch | Sau khi tích hợp và kế hoạch chuyển quyền ghi đã được kiểm chứng |
| Wave 4 | BI | Dùng CDC đã ổn định; đối soát số lượng, khóa và bất biến doanh thu |

Với Order, ba nhóm gate tối thiểu là: **(1)** luồng phụ thuộc Inventory/ERP và payment hoạt động trong tải/lỗi dự kiến; **(2)** đồng bộ, chuyển quyền ghi, backup/restore và đối soát dữ liệu đạt; **(3)** kiểm thử hành trình đặt hàng, SLO, on-call và quyết định Go/No-Go được phê duyệt. Với BI, không chỉ so số dòng mà phải xác minh checkpoint/watermark CDC, xử lý sự kiện lặp, tổng đơn và tổng giá trị theo mốc thời gian với hệ thống nguồn.

Nếu khảo sát cho thấy Order và Inventory cùng ghi một database không thể tách, đáp án phải **thay đổi**: gộp vào một cutover unit hoặc thực hiện dự án tách dữ liệu trước. Đây là dấu hiệu của một kế hoạch tốt: thứ tự được sửa theo bằng chứng, thay vì ép hệ thống phù hợp sơ đồ ban đầu.

## 12. Checklist quyết định trước khi chốt lịch

- [ ] Giá trị nghiệp vụ, business owner, thời hạn và chỉ số thành công đã được xác nhận.
- [ ] Đã kiểm chứng luồng gọi, luồng dữ liệu, bên ghi, tác vụ batch và phụ thuộc bên ngoài.
- [ ] Mọi quan hệ xuyên môi trường có thiết kế mạng, bảo mật, latency, timeout và giám sát.
- [ ] Các thành phần cần tính nhất quán được ghép đúng cutover unit hoặc có chiến lược tách được chứng minh.
- [ ] Wave 0 cung cấp năng lực IAM, DNS, triển khai, quan sát, bảo vệ dữ liệu và vận hành tối thiểu.
- [ ] Mỗi wave có entry/exit gate, RTO/RPO, dry run, UAT, người duyệt Go/No-Go và runbook sự cố.
- [ ] Kế hoạch chuyển quyền ghi, CDC, đối soát, rollback/forward fix và dữ liệu phát sinh đã được thử.
- [ ] Năng lực nhóm, change freeze, chi phí dual-run và thời gian hypercare được đưa vào lịch.
- [ ] Hệ thống cũ chỉ được decommission sau khi xác nhận hết consumer và thỏa điều kiện lưu giữ dữ liệu.

**Nguyên tắc cốt lõi:** hãy chọn wave từ những **ranh giới nghiệp vụ và dữ liệu có thể vận hành an toàn trong từng trạng thái trung gian**, sau đó ưu tiên theo giá trị, hạn chót và mức sẵn sàng. Một kế hoạch migration tốt không chỉ cho biết *đi cái gì trước*, mà còn chứng minh được *vì sao thứ tự đó an toàn, có ích và có thể kiểm soát khi sai lệch xảy ra*.
