# Đặt cổng kiểm soát trước tác động lên môi trường dùng chung

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao cần đặt cổng kiểm soát trước khi một thay đổi tác động đến môi trường dùng chung.
- Phân biệt kiểm tra trên mã nguồn, môi trường tạm thời, môi trường tích hợp dùng chung, staging và production.
- Thiết kế điều kiện vào, điều kiện ra và bằng chứng cần có cho mỗi cổng.
- Kiểm soát xung đột triển khai, trạng thái môi trường, dữ liệu kiểm thử, quyền truy cập và thay đổi cơ sở dữ liệu.
- Chọn mức kiểm soát theo rủi ro, tự động hóa quyết định có thể tự động hóa và xác định trường hợp cần phê duyệt.
- Xây dựng luồng promote artifact có truy vết, dừng an toàn và phục hồi khi xác minh không đạt.

## 1. Vì sao cần cổng kiểm soát trước môi trường dùng chung?

Trong CI/CD, không phải mọi bước kiểm tra đều có thể thực hiện trên máy của lập trình viên hoặc trong một môi trường cô lập. Có những kiểm thử cần nhiều dịch vụ cùng hoạt động, cần một cơ sở dữ liệu tích hợp, cần cấu hình gần production hoặc cần xác minh hành vi của hệ thống khi nhiều thành phần tương tác. Những bước này thường phải dùng đến môi trường chung của đội ngũ.

Môi trường dùng chung có giá trị vì phản ánh tương tác thật giữa các thành phần. Tuy nhiên, nó cũng là tài nguyên có giới hạn và có nhiều người cùng sử dụng. Một bản triển khai lỗi có thể làm hỏng kiểm thử của nhóm khác. Một migration chưa tương thích có thể khiến các phiên bản ứng dụng đang chạy đồng thời không truy cập được dữ liệu. Một bộ test xóa dữ liệu dùng chung có thể làm mất trạng thái của một quy trình kiểm thử khác. Một job chạy quá lâu có thể giữ môi trường ở trạng thái không xác định.

Vì vậy, cần đặt một **cổng kiểm soát trước khi thay đổi đi vào môi trường dùng chung**. Cổng này xác định liệu thay đổi đã có đủ bằng chứng, có tương thích với trạng thái hiện tại và có thể được triển khai mà không tạo ra rủi ro không chấp nhận được hay chưa.

Cổng kiểm soát không chỉ là nút bấm “Approve”. Nó là tập hợp điều kiện có thể kiểm chứng, quyết định cho phép hoặc từ chối chuyển bước, cùng với bằng chứng và trách nhiệm xử lý khi không đạt.

Một nguyên tắc quan trọng là:

> Mức độ kiểm soát phải tăng theo phạm vi tác động của môi trường. Thay đổi càng khó cô lập, càng nhiều người phụ thuộc và càng khó phục hồi thì cổng trước khi triển khai càng cần chặt chẽ.

## 2. Hiểu các loại môi trường và phạm vi tác động

Không phải mọi môi trường đều có cùng mức độ chia sẻ hoặc rủi ro. Cần phân loại chúng trước khi thiết kế gate.

| Loại môi trường | Đặc điểm | Rủi ro chính | Kiểm soát phù hợp |
|---|---|---|---|
| Local | Máy của lập trình viên | Khác biệt cấu hình, thiếu phụ thuộc | Hướng dẫn chạy chuẩn, container hoặc dev environment |
| CI runner | Môi trường thực thi theo job | Job không tái lập, rò rỉ dữ liệu giữa job | Runner sạch, quyền tối thiểu, workspace riêng |
| Ephemeral / preview | Tạo riêng cho nhánh hoặc pull request, có vòng đời ngắn | Tốn tài nguyên, dữ liệu không được cô lập | Tự động tạo/hủy, dữ liệu giả lập hoặc riêng biệt |
| Integration dùng chung | Nhiều nhóm hoặc dịch vụ cùng kiểm thử | Xung đột triển khai, dữ liệu và cấu hình | Gate đầu vào, lịch hoặc khóa triển khai, quản lý phiên bản |
| Staging | Môi trường xác minh gần production | Khác biệt cấu hình, test phá trạng thái | Gate chất lượng, kiểm soát quyền, xác minh sau deploy |
| Production | Phục vụ người dùng thật | Gián đoạn dịch vụ, mất dữ liệu, tác động nghiệp vụ | Chính sách phát hành, rollout, quan sát và khôi phục |

Một môi trường được gọi là staging không tự động có nghĩa là nó an toàn. Nếu staging dùng chung cơ sở dữ liệu, message broker hoặc tài khoản với nhóm khác, nó vẫn có các rủi ro của môi trường dùng chung. Ngược lại, một môi trường preview được tạo riêng cho mỗi pull request có thể có mức cô lập tốt hơn một staging dùng chung.

Khi thiết kế gate, hãy xem xét cả những tài nguyên mà ứng dụng phụ thuộc vào, không chỉ máy chủ hoặc cluster nơi ứng dụng được triển khai. Cơ sở dữ liệu, bucket lưu trữ, queue, cache, tài khoản thử nghiệm, DNS và dịch vụ bên ngoài đều có thể là tài nguyên dùng chung.

## 3. Gate là hợp đồng giữa hai giai đoạn

Mỗi cổng nên được định nghĩa như một hợp đồng có đầu vào, điều kiện quyết định, đầu ra và cách xử lý thất bại.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Đầu vào | Đối tượng nào đang được xét? | Commit, artifact digest, manifest triển khai |
| Bằng chứng | Cần biết điều gì trước khi chuyển bước? | Unit test, scan, SBOM, kết quả integration test |
| Điều kiện | Tiêu chí nào cho phép đi tiếp? | Tất cả required checks đạt, artifact đúng nguồn |
| Quyết định | Ai hoặc thành phần nào đưa ra quyết định? | Policy engine, pipeline, người phê duyệt |
| Đầu ra | Hệ thống ghi nhận điều gì? | Gate pass/fail, danh tính người duyệt, timestamp |
| Thất bại | Khi không đạt thì chuyện gì xảy ra? | Chặn deploy, báo chủ sở hữu, giữ nguyên môi trường |

Gate cần kiểm tra đúng đối tượng sẽ được đưa vào môi trường. Nếu test được chạy trên commit A nhưng pipeline lại triển khai artifact được build từ commit B, bằng chứng đó không đủ để cho phép phát hành B. Tương tự, một báo cáo scan của artifact cũ không chứng minh artifact mới an toàn.

Vì vậy, bằng chứng nên được gắn với các định danh cụ thể như commit SHA, artifact digest, phiên bản cấu hình và lần chạy pipeline. Với môi trường có thay đổi trạng thái thường xuyên, gate cũng cần xác nhận dữ liệu môi trường vẫn còn mới tại thời điểm triển khai.

Có thể phân biệt ba kiểu gate:

- **Quality gate:** xác nhận chất lượng kỹ thuật, ví dụ test, phân tích tĩnh, coverage hoặc kiểm tra dependency.
- **Environment gate:** xác nhận môi trường đích đủ điều kiện nhận thay đổi, ví dụ môi trường khỏe mạnh, không có deployment đang chạy, dữ liệu kiểm thử sẵn sàng.
- **Release gate:** xác nhận thay đổi được phép phát hành theo chính sách, ví dụ phê duyệt, cửa sổ triển khai hoặc yêu cầu tuân thủ.

Một luồng có thể kết hợp cả ba kiểu gate. Không nên gộp tất cả thành một trạng thái “green” mà không biết điều kiện nào đã được kiểm tra.

## 4. Đặt kiểm tra ở nơi ít tốn kém nhất trước

Lỗi nên được phát hiện càng sớm càng tốt, tại nơi có chi phí và phạm vi tác động thấp nhất. Một kiến trúc hợp lý thường xếp kiểm tra theo tầng:

1. **Trước khi merge:** lint, unit test, phân tích tĩnh, kiểm tra bí mật và dependency.
2. **Sau khi tạo artifact:** xác minh metadata, digest, chữ ký hoặc provenance nếu yêu cầu.
3. **Trong môi trường cô lập:** integration test, contract test và kiểm thử theo nhánh.
4. **Trước môi trường dùng chung:** kiểm tra tương thích, trạng thái môi trường, quyền, lịch triển khai và bằng chứng test.
5. **Sau khi triển khai vào môi trường dùng chung:** smoke test, kiểm tra phiên bản, health và tín hiệu vận hành.
6. **Trước production:** policy phát hành, phê duyệt theo rủi ro và xác nhận khả năng phục hồi.
7. **Sau production rollout:** theo dõi chỉ số và quyết định tiếp tục, dừng hoặc rollback.

~~~mermaid
flowchart TD
    A["Pull request / commit"] --> B["Source checks"]
    B --> C{"Source gate"}
    C -- "Fail" --> X["Sửa thay đổi"]
    X --> A
    C -- "Pass" --> D["Build artifact bất biến"]
    D --> E["Artifact checks: digest, provenance, scan"]
    E --> F{"Artifact gate"}
    F -- "Fail" --> Y["Chặn phát hành"]
    F -- "Pass" --> G["Preview / ephemeral environment"]
    G --> H["Integration và contract tests"]
    H --> I{"Shared environment gate"}
    I -- "Fail" --> J["Giữ nguyên môi trường chung"]
    I -- "Pass" --> K["Deploy có khóa / điều phối"]
    K --> L["Smoke test và health verification"]
    L --> M{"Environment verification"}
    M -- "Fail" --> N["Dừng rollout / khôi phục"]
    M -- "Pass" --> O["Release policy gate"]
    O --> P["Production rollout"]
    P --> Q["Post-deploy monitoring"]
~~~

Không phải dự án nào cũng cần đủ các tầng thành những job riêng. Với hệ thống nhỏ, một số kiểm tra có thể chạy trong cùng workflow. Điều quan trọng là không đưa một thay đổi chưa được kiểm tra đến nơi có phạm vi tác động lớn hơn mức cần thiết.

## 5. Cổng trước môi trường dùng chung cần xác minh điều gì?

Trước khi triển khai vào integration hoặc staging dùng chung, có thể tổ chức gate theo các nhóm điều kiện sau.

### 5.1. Chất lượng của thay đổi

- Các required checks trên đúng commit đã đạt.
- Kiểm thử đơn vị và các kiểm thử nhanh liên quan không thất bại.
- Không có phát hiện bảo mật mức chặn theo chính sách.
- Contract hoặc schema mà dịch vụ phụ thuộc vẫn tương thích.
- Các ngoại lệ đã được ghi nhận, có người chịu trách nhiệm và thời hạn.

Không nên chỉ kiểm tra trạng thái cuối cùng của workflow. Gate cần xác định rõ những job nào là bắt buộc. Một workflow xanh vì job bảo mật bị bỏ qua hoặc job kiểm thử bị đánh dấu optional không đủ để chứng minh chất lượng.

### 5.2. Danh tính và tính toàn vẹn của artifact

- Artifact được tạo từ commit dự kiến.
- Digest hoặc mã định danh khớp với artifact đã được kiểm thử.
- Artifact được lấy từ kho được tin cậy.
- Metadata và bằng chứng build được lưu.
- Không có bước build lại âm thầm sau khi gate đã đạt.

Nếu hệ thống yêu cầu mức bảo đảm cao hơn, có thể kiểm tra chữ ký, provenance hoặc SBOM. Những kiểm tra này nên được đưa vào theo yêu cầu chuỗi cung ứng phần mềm và mức rủi ro của sản phẩm.

### 5.3. Khả năng sẵn sàng của môi trường

- Môi trường đang ở trạng thái khỏe mạnh.
- Không có deployment hoặc migration xung đột đang chạy.
- Phiên bản dịch vụ phụ thuộc nằm trong phạm vi tương thích.
- Tài nguyên cần thiết còn đủ, ví dụ quota, kết nối, storage hoặc worker.
- Cấu hình môi trường đã được kiểm tra và không chứa giá trị thiếu.
- Có thể xác định phiên bản hiện tại để đối chiếu hoặc phục hồi.

Một gate có thể hỏi hệ thống điều phối xem có rollout đang hoạt động hay không, hoặc yêu cầu lấy deployment lock trước khi tiếp tục. Nếu môi trường không khỏe mạnh từ trước, cần xác định liệu triển khai mới có làm khó việc điều tra hơn hay không.

### 5.4. Dữ liệu và trạng thái kiểm thử

- Bộ dữ liệu kiểm thử đã được chuẩn bị và có thể tái tạo.
- Test không ghi đè dữ liệu của nhóm hoặc job khác.
- Dữ liệu nhạy cảm được giả lập hoặc ẩn danh theo chính sách.
- Các migration cần thiết tương thích với phiên bản đang chạy.
- Có cách dọn dẹp dữ liệu hoặc tài nguyên do lần kiểm thử tạo ra.

Dữ liệu thường là nguồn gây xung đột bị bỏ sót. Hai job cùng chạy test trên một tài khoản, một đơn hàng hoặc một bảng dữ liệu có thể làm kết quả không ổn định dù code không thay đổi. Hãy cấp namespace, tenant, schema hoặc dữ liệu riêng theo job nếu kiến trúc cho phép.

### 5.5. Quyền và trách nhiệm

- Job chỉ có quyền cần thiết cho hành động sắp thực hiện.
- Secret được cấp từ nguồn quản lý phù hợp và chỉ trong thời gian cần thiết.
- Người hoặc nhóm chịu trách nhiệm cho môi trường đã được xác định.
- Có kênh nhận thông báo khi gate thất bại.
- Nếu cần phê duyệt, người duyệt có đủ ngữ cảnh và quyền hạn.

Cổng kiểm soát cần ngăn việc một pull request không tin cậy nhận được credential có thể thay đổi môi trường dùng chung hoặc production.

## 6. Kiểm soát đồng thời và xung đột triển khai

Môi trường dùng chung thường không thể nhận nhiều thay đổi không tương thích cùng lúc. Nếu hai pipeline cùng triển khai một dịch vụ, pipeline chạy sau có thể ghi đè phiên bản của pipeline trước. Nếu một pipeline đang chạy integration test trong khi pipeline khác thay đổi schema, kết quả test có thể không còn đáng tin.

Có một số cơ chế thường dùng:

**Deployment lock hoặc concurrency group:** chỉ cho phép một hoạt động thay đổi môi trường hoặc một tài nguyên cụ thể tại một thời điểm. Khóa nên có thời hạn, có cơ chế giải phóng khi job kết thúc và tránh bị giữ mãi khi runner gặp sự cố.

**Queue:** xếp các yêu cầu triển khai theo thứ tự. Cần quyết định có hủy phiên bản cũ khi phiên bản mới hơn đã sẵn sàng hay phải xử lý tuần tự, tùy loại kiểm thử và mục đích của môi trường.

**Environment lease:** cấp quyền sử dụng môi trường trong một khoảng thời gian cho một pipeline hoặc nhóm. Hết thời hạn phải giải phóng hoặc gia hạn có kiểm soát.

**Namespace hoặc môi trường tạm thời:** mỗi nhánh hoặc job có vùng tài nguyên riêng, giảm nhu cầu tranh chấp. Cách này phù hợp khi nền tảng có thể tạo tài nguyên độc lập với chi phí chấp nhận được.

**Optimistic concurrency:** trước khi deploy, xác nhận trạng thái môi trường vẫn giống trạng thái mà gate đã đánh giá. Nếu môi trường đã thay đổi sau khi gate pass, pipeline phải đánh giá lại thay vì triển khai dựa trên bằng chứng cũ.

Không nên dùng một khóa toàn cục cho mọi thao tác nếu các dịch vụ hoàn toàn độc lập. Hãy khóa theo phạm vi tài nguyên thực sự xung đột, chẳng hạn một namespace, một database schema hoặc một dịch vụ. Khóa quá rộng làm giảm khả năng song song; khóa quá hẹp không ngăn được xung đột.

## 7. Môi trường tạm thời giúp giảm tải cho môi trường chung

Nếu mọi pull request đều phải triển khai lên một staging duy nhất, staging nhanh chóng trở thành nút thắt. Một hướng giải quyết là tạo preview environment hoặc ephemeral environment cho mỗi nhánh.

Một môi trường tạm thời thường có vòng đời:

1. Tạo khi pull request cần kiểm thử tích hợp.
2. Cấp cấu hình và dữ liệu riêng.
3. Triển khai artifact của pull request.
4. Chạy integration, contract hoặc acceptance test.
5. Thu thập log và kết quả.
6. Hủy môi trường khi pull request đóng hoặc hết thời hạn.

Cách này giúp nhiều thay đổi được kiểm tra song song mà không ghi đè lẫn nhau. Tuy nhiên, môi trường tạm thời cũng cần quota, chính sách dọn dẹp, quản lý secret và kiểm soát chi phí. Nếu mỗi preview tạo một database hoặc cluster đầy đủ, chi phí có thể tăng nhanh.

Không phải dependency nào cũng dễ cô lập. Một hệ thống có thể dùng database dùng chung nhưng cấp schema riêng cho mỗi preview; hoặc dùng service virtualization cho các dịch vụ bên ngoài. Cần xác định ranh giới cô lập phù hợp với kiến trúc, thay vì giả định rằng một namespace Kubernetes tự động cô lập mọi dữ liệu và tài nguyên.

Môi trường tạm thời cũng không thay thế hoàn toàn staging. Một số kiểm tra cần cấu hình, dữ liệu, tích hợp hoặc năng lực gần production. Staging vẫn cần thiết để xác minh toàn bộ hệ thống trong một trạng thái được quản lý.

## 8. Cổng kiểm soát cho thay đổi database và hợp đồng dịch vụ

Thay đổi database thường có phạm vi tác động rộng vì nhiều phiên bản ứng dụng có thể cùng truy cập một schema. Một migration phá vỡ tương thích có thể làm các instance cũ lỗi ngay khi migration được chạy.

Với môi trường dùng chung, gate nên xác minh:

- Migration đã được kiểm tra trên phiên bản schema gần với môi trường đích.
- Migration có thể chạy lặp lại an toàn hoặc có cách phát hiện đã hoàn tất.
- Thay đổi hỗ trợ phiên bản ứng dụng hiện tại và phiên bản sắp triển khai.
- Thời gian khóa hoặc ảnh hưởng hiệu năng đã được đánh giá.
- Có backup hoặc phương án phục hồi phù hợp với mức rủi ro.
- Các thay đổi phá hủy dữ liệu được tách riêng và có phê duyệt tương ứng.

Một mẫu thường dùng là expand-and-contract:

1. **Expand:** thêm cột, bảng hoặc cấu trúc mới theo cách vẫn tương thích với ứng dụng cũ.
2. **Migrate:** chuyển dữ liệu hoặc ghi song song theo kế hoạch có kiểm soát.
3. **Switch:** triển khai ứng dụng mới và chuyển dần việc đọc/ghi.
4. **Contract:** chỉ xóa cấu trúc cũ khi không còn phiên bản nào phụ thuộc và đã qua gate riêng.

Tương tự, thay đổi API hoặc message schema cần contract test để xác minh bên cung cấp và bên tiêu thụ vẫn tương thích. Gate không chỉ hỏi “service mới có chạy không?” mà cần hỏi “service mới có thể cùng tồn tại với các phiên bản phụ thuộc đang chạy trong môi trường chung không?”.

## 9. Thiết kế quyết định gate theo rủi ro

Không phải thay đổi nào cũng cần phê duyệt thủ công. Một thay đổi chỉ sửa tài liệu có thể cần ít kiểm tra hơn một thay đổi authentication, schema hoặc cấu hình mạng. Mục tiêu là chọn kiểm soát phù hợp với xác suất và mức độ ảnh hưởng của lỗi.

Có thể phân nhóm thay đổi:

| Mức rủi ro | Ví dụ | Kiểm soát gợi ý |
|---|---|---|
| Thấp | Tài liệu, thay đổi không ảnh hưởng runtime | CI cơ bản, không cần deployment gate đặc biệt |
| Trung bình | Logic ứng dụng, API tương thích | Required tests, artifact checks, environment readiness |
| Cao | Schema, authentication, quyền, cấu hình mạng | Contract/migration tests, security gate, phê duyệt có ngữ cảnh, rollout kiểm soát |
| Rất cao | Thay đổi dữ liệu lớn, hạ tầng trọng yếu, tác động rộng | Đánh giá chuyên môn, kế hoạch phục hồi, cửa sổ triển khai và giám sát tăng cường |

Phân loại rủi ro nên dựa trên đặc tính thay đổi và tác động, không chỉ dựa vào nhãn do người tạo pull request tự chọn. Có thể dùng đường dẫn file, loại artifact, thành phần sở hữu, nhãn được reviewer xác nhận hoặc policy engine để bổ sung tín hiệu.

Với các kiểm tra bảo mật và tính toàn vẹn bắt buộc, cần định nghĩa rõ điều kiện fail-closed: nếu không thể xác minh bằng chứng cần thiết thì không được chuyển sang môi trường nhạy cảm. Với một số kiểm tra tư vấn hoặc hệ thống phụ trợ có thể chấp nhận fail-open có giới hạn, nhưng ngoại lệ phải được ghi nhận và có thời hạn.

## 10. Phê duyệt thủ công cần có ngữ cảnh và dấu vết

Phê duyệt có thể cần thiết trước staging, production hoặc một thao tác có tác động lớn. Tuy nhiên, nút “Approve” không nên chỉ hiển thị tên phiên bản. Người duyệt cần thấy tối thiểu:

- Commit và artifact digest.
- Những kiểm tra đã chạy và kết quả.
- Những gate nào đã đạt hoặc được miễn trừ.
- Môi trường và phạm vi tài nguyên bị ảnh hưởng.
- Kế hoạch triển khai và thời gian dự kiến.
- Tác động có thể xảy ra, migration liên quan và phương án khôi phục.
- Người chịu trách nhiệm theo dõi sau triển khai.

Phê duyệt cần gắn với đúng artifact và môi trường. Nếu artifact thay đổi sau khi phê duyệt, quyết định cũ không còn áp dụng. Nếu trạng thái môi trường thay đổi đáng kể trong lúc chờ, gate cần đánh giá lại các điều kiện phụ thuộc vào trạng thái đó.

Cũng cần tránh phê duyệt theo kiểu “một người bấm cho mọi thay đổi”. Người duyệt cần có trách nhiệm phù hợp, tránh tự phê duyệt thay đổi của chính mình khi chính sách yêu cầu phân tách nhiệm vụ, và có thể từ chối với lý do rõ ràng.

## 11. Ví dụ mô hình gate trước môi trường dùng chung

Ví dụ YAML dưới đây mô tả logic tổng quát, không phải cú pháp chạy trực tiếp trên một nền tảng CI/CD cụ thể:

~~~yaml
pipeline:
  source:
    trigger: pull_request
    checks:
      - lint
      - unit_tests
      - secret_scan
      - dependency_policy
    gate: source_checks_passed

  artifact:
    requires: source_checks_passed
    steps:
      - build_once
      - publish_immutable_artifact
      - attach_commit_digest_and_provenance
    gate: artifact_verified

  isolated_validation:
    requires: artifact_verified
    steps:
      - create_ephemeral_environment
      - deploy_artifact_by_digest
      - run_integration_and_contract_tests
      - collect_evidence
      - destroy_ephemeral_environment
    gate: isolated_tests_passed

  shared_environment:
    requires:
      - isolated_tests_passed
      - artifact_verified
    preconditions:
      - environment_healthy
      - no_conflicting_deployment
      - compatible_schema_and_dependencies
      - test_data_ready
      - deployment_identity_authorized
    concurrency:
      resource: integration_environment
      mode: exclusive
    steps:
      - deploy_same_artifact
      - verify_running_digest
      - run_smoke_tests
      - record_environment_state
    gate: shared_environment_verified

  production:
    requires: shared_environment_verified
    preconditions:
      - release_policy_passed
      - approval_if_required
      - rollback_or_recovery_plan_ready
    steps:
      - rollout
      - monitor_health_and_error_rate
      - stop_or_recover_if_thresholds_fail
      - record_release_evidence
~~~

Điểm quan trọng trong ví dụ là cổng trước môi trường dùng chung có cả bằng chứng từ artifact và kiểm thử cô lập, cùng với các điều kiện của môi trường tại thời điểm triển khai. Việc gate đã pass trước đó không có nghĩa là môi trường vẫn sẵn sàng nếu một pipeline khác vừa thay đổi nó.

Trong triển khai thực tế, các preconditions nên được kiểm tra càng gần thời điểm deploy càng tốt. Các điều kiện liên quan đến trạng thái thay đổi nhanh như deployment lock, health hoặc phiên bản schema cần được xác minh lại ngay trước khi thực hiện thao tác có tác động.

## 12. Xử lý khi gate không đạt

Một gate hữu ích phải trả về lý do có thể hành động. Trạng thái thất bại nên phân biệt được:

- **Rejected:** bằng chứng cho thấy thay đổi không đáp ứng chính sách.
- **Blocked:** chưa thể đánh giá vì thiếu tài nguyên, lock hoặc điều kiện phụ thuộc.
- **Stale:** bằng chứng đã cũ hoặc môi trường thay đổi sau khi kiểm tra.
- **Error:** chính gate hoặc dịch vụ kiểm tra gặp lỗi kỹ thuật.
- **Waived:** ngoại lệ được phê duyệt theo quy trình, có lý do và thời hạn.

Không nên biến tất cả các trạng thái này thành một lỗi chung “pipeline failed”. Người vận hành cần biết nên sửa code, chờ môi trường, chạy lại kiểm tra hay liên hệ chủ sở hữu.

| Nguyên nhân | Hành động phù hợp |
|---|---|
| Required test thất bại | Chặn chuyển bước, đính kèm log và báo người tạo thay đổi |
| Artifact digest không khớp | Chặn deploy, điều tra nguồn gốc artifact |
| Môi trường đang có rollout khác | Đưa vào queue hoặc chờ lock |
| Môi trường unhealthy | Giữ nguyên trạng thái, báo owner và điều tra trước |
| Schema không tương thích | Chặn migration/deploy, yêu cầu kế hoạch tương thích |
| Test data bị chiếm dụng | Cấp dữ liệu/namespace riêng hoặc chờ lease |
| Gate service tạm thời lỗi | Retry có giới hạn; không bỏ qua gate quan trọng |
| Phê duyệt bị từ chối | Ghi lý do, trả về bước cần chỉnh sửa |
| Post-deploy verification thất bại | Dừng rollout, đánh giá rollback hoặc khắc phục |

Retry chỉ phù hợp với lỗi tạm thời có thể phục hồi. Không nên retry liên tục một kiểm tra cho kết quả xác định là sai, hoặc bỏ qua gate vì dịch vụ policy đang không truy cập được khi chính sách yêu cầu fail-closed.

## 13. Xác minh sau triển khai và khả năng phục hồi

Sau khi gate cho phép triển khai vào môi trường chung, pipeline vẫn cần xác minh rằng môi trường đạt trạng thái mong đợi.

Bằng chứng tối thiểu có thể gồm:

- Phiên bản hoặc digest thực tế đang chạy.
- Health và readiness của dịch vụ.
- Smoke test của luồng quan trọng.
- Kết quả contract hoặc integration test cần chạy sau triển khai.
- Tín hiệu lỗi, độ trễ hoặc queue backlog trong khoảng theo dõi.
- Trạng thái migration và dependency.

Nếu kiểm tra thất bại, hành động tiếp theo phụ thuộc vào loại thay đổi. Với một dịch vụ stateless, rollback về artifact trước có thể đơn giản. Với migration dữ liệu, rollback mã nguồn có thể không an toàn. Với thay đổi cấu hình hoặc hạ tầng, cần khôi phục trạng thái trước hoặc triển khai bản sửa tương thích.

Cần lưu lại trạng thái trước và sau deploy, bao gồm artifact, cấu hình, phiên bản dependency và kết quả gate. Điều này giúp điều tra sự cố và biết chính xác môi trường đã thay đổi như thế nào.

## 14. Những anti-pattern thường gặp

| Anti-pattern | Vấn đề tạo ra | Cách cải thiện |
|---|---|---|
| Chỉ có một staging cho tất cả pull request | Các nhóm ghi đè và làm hỏng test của nhau | Dùng preview environment hoặc điều phối queue |
| Gate chỉ là một nút approve | Người duyệt thiếu bằng chứng và tiêu chí | Định nghĩa điều kiện, artifact và phạm vi ảnh hưởng |
| Test chạy trước nhưng deploy artifact khác | Bằng chứng không còn gắn với đối tượng phát hành | Gắn commit/digest xuyên suốt |
| Gate pass quá lâu trước khi deploy | Trạng thái môi trường có thể đã thay đổi | Revalidate preconditions gần thời điểm deploy |
| Mọi thay đổi dùng cùng một mức gate | Quá chậm với thay đổi nhỏ hoặc thiếu kiểm soát với thay đổi lớn | Phân loại rủi ro và policy |
| Dùng chung dữ liệu kiểm thử | Test không ổn định, ghi đè trạng thái | Namespace, tenant hoặc dataset riêng |
| Khóa toàn bộ hệ thống | Giảm throughput dù tài nguyên không xung đột | Khóa theo tài nguyên cụ thể |
| Gate service lỗi thì tự động bỏ qua | Mất kiểm soát đúng lúc cần kiểm soát | Quy định fail-closed hoặc ngoại lệ có kiểm soát |
| Không có owner môi trường | Sự cố bị chuyển vòng quanh, không ai xử lý | Chỉ định owner và quy trình escalation |
| Rollback chỉ được ghi trong tài liệu | Không biết có thực hiện được trong thực tế không | Diễn tập phục hồi và lưu bằng chứng |

## 15. Checklist thiết kế gate trước môi trường dùng chung

Trước khi bật tự động triển khai vào một môi trường nhiều người hoặc nhiều dịch vụ cùng phụ thuộc, hãy xác nhận:

- [ ] Phạm vi chia sẻ của môi trường và các dependency đã được lập danh sách.
- [ ] Gate xác định đúng commit, artifact digest và cấu hình sẽ triển khai.
- [ ] Required checks và điều kiện miễn trừ có chính sách rõ.
- [ ] Có bằng chứng kiểm thử cô lập trước khi vào môi trường chung khi phù hợp.
- [ ] Health, schema, dependency và tài nguyên của môi trường được kiểm tra.
- [ ] Có cơ chế lock, queue hoặc namespace để tránh xung đột.
- [ ] Dữ liệu kiểm thử được cô lập, tái tạo và dọn dẹp.
- [ ] Secret và quyền triển khai được giới hạn theo job/môi trường.
- [ ] Thay đổi schema và contract được kiểm tra tương thích.
- [ ] Gate có trạng thái pass, fail, blocked, stale và error rõ ràng.
- [ ] Phê duyệt gắn với artifact và môi trường cụ thể nếu được yêu cầu.
- [ ] Có post-deploy verification và ghi nhận phiên bản thực tế.
- [ ] Có owner, kênh thông báo và quy trình xử lý khi gate thất bại.
- [ ] Phương án rollback hoặc recovery đã được kiểm chứng ở mức phù hợp.

## 16. Bài tập tự đánh giá

Một nhóm có ba dịch vụ cùng dùng một integration environment và một database schema. Mỗi pull request sau khi merge đều tự động triển khai lên môi trường này. Gần đây, test thường thất bại không ổn định: đôi khi một pipeline đang chạy test thì pipeline khác deploy phiên bản mới; một số test còn ghi đè dữ liệu của nhau. Nhóm muốn tăng số lần triển khai mỗi ngày nhưng không muốn tạo thêm một staging cluster lớn.

Hãy phân tích:

1. Những tài nguyên nào thực sự đang được chia sẻ và có thể xung đột?
2. Những kiểm tra nào có thể chuyển sang môi trường ephemeral hoặc namespace riêng?
3. Gate nào cần chạy trước khi deploy vào integration environment?
4. Nên dùng deployment lock, queue, lease hay kết hợp các cơ chế nào? Phạm vi khóa nên là gì?
5. Làm thế nào để xác minh artifact đã test chính là artifact sẽ được triển khai?
6. Dữ liệu test cần được cấp và dọn dẹp như thế nào?
7. Những thay đổi schema hoặc contract nào cần gate riêng?
8. Nếu môi trường thay đổi sau khi gate pass, pipeline phải làm gì?
9. Đo những chỉ số nào để biết gate giảm xung đột mà không tạo ra hàng chờ quá dài?

Một thiết kế tốt sẽ xác định rõ ranh giới cô lập, điều kiện trước khi vào môi trường chung, cơ chế điều phối và bằng chứng sau triển khai. Không nhất thiết phải tạo thêm một cluster lớn nếu có thể cô lập ở cấp namespace, schema, tenant hoặc service virtualization.

## Kết luận

Cổng kiểm soát trước môi trường dùng chung bảo vệ độ tin cậy của kiểm thử và giảm nguy cơ một thay đổi làm ảnh hưởng đến nhóm hoặc dịch vụ khác. Gate cần gắn với đúng commit và artifact, kiểm tra chất lượng thay đổi, xác nhận môi trường sẵn sàng, kiểm soát dữ liệu và quyền truy cập, đồng thời điều phối các thao tác có khả năng xung đột.

Một kiến trúc tốt đặt kiểm tra ở tầng ít tốn kém nhất, dùng môi trường tạm thời khi có thể, đánh giá lại điều kiện ngay trước triển khai và xác minh trạng thái sau triển khai. Khi gate không đạt, hệ thống phải giải thích lý do và đưa ra hành động tiếp theo. Nhờ đó, đội ngũ có thể tăng tốc độ giao phần mềm mà vẫn giữ được môi trường chung ổn định, có thể truy vết và phục hồi.

