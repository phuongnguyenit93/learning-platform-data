# Nâng cấp trực tiếp hoặc qua các mốc trung gian: tiêu chí lựa chọn

Khi lập lộ trình cho một đợt Java migration, nhóm cần quyết định nên chuyển từ phiên bản hiện tại lên phiên bản mục tiêu trong một bước lớn hay chia thành nhiều mốc trung gian. Quyết định này ảnh hưởng đến phạm vi thay đổi, thời gian thực hiện, khả năng tìm nguyên nhân lỗi, chi phí kiểm thử, kế hoạch triển khai và mức độ an toàn khi rollback.

Trong chủ đề **Java Advance Compatibility Migration**, thuộc nhóm **Phiên bản và lộ trình**, không có một quy tắc cố định rằng nâng cấp trực tiếp luôn nhanh hơn hoặc nâng cấp tuần tự luôn an toàn hơn. Cách phù hợp phụ thuộc vào khoảng cách giữa hai phiên bản, các ràng buộc của JDK và framework, mức độ tương thích của dependency, cấu trúc hệ thống, dữ liệu, khả năng kiểm thử và thời gian mà tổ chức có thể dành cho migration.

Điều quan trọng là phải chọn lộ trình dựa trên bằng chứng. Một bước nhảy phiên bản lớn có thể hợp lý nếu đường nâng cấp được hỗ trợ và hệ thống có đủ kiểm thử. Ngược lại, một mốc trung gian có thể là điều kiện bắt buộc nếu framework, công cụ build, dữ liệu hoặc nhà cung cấp yêu cầu chuyển đổi theo thứ tự cụ thể.

## 1. Hai cách tổ chức lộ trình

### 1.1. Nâng cấp trực tiếp

Nâng cấp trực tiếp (direct upgrade) là chuyển hệ thống từ baseline hiện tại sang phiên bản mục tiêu trong một đợt migration chính.

Ví dụ:

~~~text
Trạng thái hiện tại
    Java A
    Framework X
    Dependency set P
        |
        | Một đợt migration
        v
Trạng thái mục tiêu
    Java C
    Framework Z
    Dependency set R
~~~

Nhóm phân tích các thay đổi từ A đến C, điều chỉnh mã nguồn và cấu hình, cập nhật framework/dependency, sau đó kiểm chứng toàn bộ trên trạng thái mục tiêu.

“Nâng cấp trực tiếp” không có nghĩa là bỏ qua việc đọc release notes của các phiên bản nằm giữa A và C. Một nhóm vẫn phải khảo sát các thay đổi, API bị deprecated hoặc removed, yêu cầu toolchain và hướng dẫn migration xuất hiện ở từng phiên bản liên quan. Nó chỉ có nghĩa là không nhất thiết phải cài đặt, phát hành hoặc vận hành hệ thống ở từng phiên bản trung gian.

Cách này thường phù hợp khi:

- Đường nâng cấp trực tiếp được nhà cung cấp hỗ trợ.
- Các thành phần chính có thể chạy trên phiên bản mục tiêu.
- Không có yêu cầu bắt buộc phải đi qua một phiên bản cầu nối.
- Mã nguồn và dependency có thể được điều chỉnh trong cùng một phạm vi kiểm soát.
- Hệ thống có đủ test và môi trường để kiểm tra toàn bộ thay đổi.
- Consumer cần hỗ trợ có thể được cập nhật hoặc vẫn tương thích với API mới.
- Có thể triển khai và rollback trong một kế hoạch được kiểm chứng.

### 1.2. Nâng cấp qua các mốc trung gian

Nâng cấp qua các mốc trung gian (intermediate-step upgrade) chia đường đi từ phiên bản hiện tại đến phiên bản mục tiêu thành nhiều trạng thái có thể kiểm tra riêng.

Ví dụ:

~~~text
Java A
   |
   | Mốc 1: xử lý thay đổi nền tảng
   v
Java B
   |
   | Mốc 2: nâng framework và dependency
   v
Java C
   |
   | Mốc 3: hoàn tất cấu hình và tối ưu runtime
   v
Trạng thái mục tiêu
~~~

Mỗi mốc có thể bao gồm một phiên bản JDK, framework, build tool hoặc một tập hợp thay đổi được lựa chọn. Nhóm kiểm tra build, test và các hợp đồng tương thích ở từng trạng thái trước khi chuyển sang mốc tiếp theo.

Không phải mọi mốc đều cần trở thành một lần triển khai production. Một mốc có thể chỉ là checkpoint trong branch migration hoặc một môi trường kiểm thử. Nếu phiên bản trung gian không được hỗ trợ để vận hành lâu dài, không nên mặc định rằng phải phát hành nó ra production.

Cách này thường phù hợp khi:

- Nhà cung cấp yêu cầu nâng cấp qua một phiên bản framework hoặc công cụ cụ thể.
- Một bước nhảy lớn chứa nhiều thay đổi phá vỡ khó xử lý cùng lúc.
- Hệ thống có nhiều module, plugin hoặc consumer độc lập.
- Cần giữ hoạt động liên tục trong khi các nhóm cập nhật theo lịch khác nhau.
- Thay đổi dữ liệu hoặc giao thức cần giai đoạn tương thích chuyển tiếp.
- Nhóm cần cô lập nguyên nhân lỗi theo từng nhóm thay đổi.
- Có thể kiểm thử và quản lý các trạng thái trung gian một cách đáng tin cậy.

### 1.3. Phân biệt mốc kỹ thuật và mốc triển khai

Một lộ trình có thể có nhiều mốc kỹ thuật nhưng chỉ một lần triển khai production. Ngược lại, một thay đổi kỹ thuật nhỏ có thể cần nhiều đợt rollout do hệ thống phân tán hoặc consumer không thể cập nhật đồng thời.

Cần tách ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Phiên bản kỹ thuật | Phiên bản JDK, framework, build tool hoặc dependency | JDK 17, Spring Boot 3.x |
| Mốc kiểm chứng | Trạng thái code/config được build và test để xác nhận một phần migration | Hoàn tất compile trên JDK mới, hoàn tất chuyển namespace |
| Mốc triển khai | Lần phát hành hoặc rollout tới môi trường chạy thực tế | Canary, staging, production rollout |

Đừng thêm một lần triển khai production chỉ vì muốn có thêm một checkpoint kỹ thuật. Hãy chọn hình thức mốc dựa trên khả năng kiểm chứng, khả năng rollback và yêu cầu vận hành.

## 2. Những yếu tố quyết định lộ trình

Trước khi chọn cách nâng cấp, hãy đánh giá các nhóm yếu tố sau. Mỗi nhóm có thể là một điều kiện bắt buộc hoặc một yếu tố ảnh hưởng đến chi phí và rủi ro.

### 2.1. Đường nâng cấp được nhà cung cấp hỗ trợ

Đây là điều kiện cần kiểm tra đầu tiên.

Một số JDK, framework, application server, plugin hoặc công cụ có thể hỗ trợ nâng cấp trực tiếp từ phiên bản cũ lên phiên bản mới. Một số khác yêu cầu phiên bản cầu nối, quy trình chuyển đổi hoặc thứ tự nâng cấp cụ thể.

Cần xác minh:

- Ma trận tương thích chính thức của JDK, framework và application server.
- Phiên bản tối thiểu của build tool và plugin để build hoặc chạy với JDK mục tiêu.
- Các phiên bản dependency được framework hỗ trợ.
- Hướng dẫn nâng cấp giữa các major release.
- Những thay đổi phải thực hiện trước khi nâng cấp.
- Các phiên bản trung gian còn được hỗ trợ hay đã hết vòng đời.
- Có yêu cầu nâng cấp theo thứ tự đối với metadata, schema, cấu hình hoặc artifact hay không.

Nếu tài liệu chính thức quy định một đường nâng cấp bắt buộc, đó là ràng buộc của lộ trình. Không nên bỏ qua chỉ vì một thử nghiệm nhỏ trên máy phát triển có vẻ chạy được.

Cũng cần phân biệt “được hỗ trợ” với “có thể chạy”. Một tổ hợp phiên bản có thể khởi động được nhưng nằm ngoài ma trận hỗ trợ của nhà cung cấp. Khi xảy ra lỗi, nhóm có thể không nhận được bản vá hoặc hỗ trợ cần thiết.

### 2.2. Khoảng cách giữa phiên bản hiện tại và mục tiêu

Khoảng cách phiên bản càng lớn thì càng có nhiều release notes, deprecation, API removal và thay đổi mặc định cần khảo sát.

Tuy nhiên, số phiên bản bị bỏ qua không tự nó quyết định số mốc cần cài đặt. Một dự án có thể đi trực tiếp qua nhiều major version nếu nhà cung cấp hỗ trợ và các thay đổi có thể được xử lý trong một đợt. Một dự án khác chỉ nâng một major version nhưng vẫn cần nhiều checkpoint vì có thay đổi lớn về kiến trúc hoặc dữ liệu.

Hãy lập danh sách các thay đổi từ baseline đến target:

- API JDK bị deprecated hoặc removed.
- Thay đổi module, package hoặc quyền truy cập.
- Thay đổi bytecode target và runtime requirement.
- Thay đổi cấu hình mặc định.
- Thay đổi framework extension point.
- Thay đổi dependency và plugin.
- Thay đổi serialization, schema hoặc giao thức.
- Thay đổi hành vi của garbage collector, concurrency, TLS hoặc networking nếu có liên quan.

Nếu nhiều thay đổi độc lập cùng xuất hiện, hãy cân nhắc tách checkpoint để xác định nguyên nhân khi kiểm thử thất bại.

### 2.3. Mức độ thay đổi trong mã nguồn và API

Đánh giá số lượng và mức độ phức tạp của các thay đổi cần thực hiện:

- Mã nguồn chỉ cần sửa cảnh báo hoặc API deprecated?
- Có API đã bị xóa khiến phải thay thế cách triển khai?
- Có chuyển đổi namespace hoặc package diện rộng?
- Có thay đổi interface, abstract class hoặc public API?
- Có module sử dụng reflection hoặc truy cập nội bộ JDK?
- Có code generation hoặc annotation processor phụ thuộc phiên bản cũ?
- Có nhiều module cần thay đổi cùng lúc vì phụ thuộc vòng hoặc hợp đồng dùng chung?

Một thay đổi tập trung trong một module có thể được thực hiện trực tiếp. Nhiều thay đổi xuyên suốt các module, framework và consumer độc lập thường cần checkpoint rõ ràng hơn.

### 2.4. Tương thích của dependency và build tool

Một hệ thống Java không chỉ phụ thuộc vào JDK. Nó còn phụ thuộc vào framework, thư viện, plugin build và công cụ hỗ trợ.

Cần kiểm tra:

- Dependency trực tiếp và transitive.
- BOM, dependency constraints và version catalog.
- Gradle wrapper hoặc Maven version.
- Plugin build, test, packaging, code coverage và static analysis.
- Annotation processor, compiler plugin và code generator.
- Test framework, mocking framework và integration-test tooling.
- Agent, instrumentation, bytecode enhancer và native library.
- Dependency chỉ có ở runtime nhưng không xuất hiện trong compile classpath.

Nếu build tool hiện tại không chạy được trên JDK mục tiêu, có thể cần một bước nâng build tool trước khi thay đổi source. Nếu framework mới yêu cầu dependency major version mới, cần đánh giá liệu các thư viện tích hợp còn tương thích hay không.

Không nên nâng tất cả dependency lên phiên bản mới nhất chỉ vì đã nâng JDK. Hãy chọn phiên bản nằm trong ma trận hỗ trợ và có lý do cụ thể.

### 2.5. Khả năng tương thích nhị phân của consumer

Đây là yếu tố đặc biệt quan trọng với thư viện dùng chung, SDK, plugin hoặc module được phát hành độc lập.

Hãy xác định:

- Consumer nào sẽ được build lại?
- Consumer nào giữ nguyên bytecode cũ?
- Consumer nào không thể cập nhật cùng lúc?
- Có API công khai nào bị thay đổi descriptor hoặc quyền truy cập?
- Có lớp cũ triển khai interface mới?
- Có consumer dùng reflection, ServiceLoader hoặc tên class trong cấu hình?
- Có hằng số compile-time được nhúng vào bytecode không?

Nếu yêu cầu là các consumer cũ tiếp tục chạy mà không biên dịch lại, cần chạy chính artifact đã biên dịch từ baseline với dependency mới. Build lại toàn bộ consumer chỉ kiểm tra source compatibility, không thay thế được kiểm thử binary compatibility.

### 2.6. Dữ liệu và giao tiếp giữa các phiên bản

Các hệ thống phân tán thường không thể cập nhật tất cả producer và consumer trong cùng một thời điểm.

Cần đánh giá:

- Database schema có thay đổi không?
- JSON/XML hoặc message schema có thay đổi không?
- Producer cũ và consumer mới có hiểu nhau không?
- Producer mới và consumer cũ có hiểu nhau không?
- Dữ liệu ghi bởi phiên bản mới có thể đọc bởi phiên bản cũ không?
- Có cache, session hoặc serialized object được chia sẻ giữa các phiên bản không?
- Có migration dữ liệu không thể đảo ngược không?

Nếu các phiên bản cũ và mới phải cùng hoạt động trong một khoảng thời gian, các mốc trung gian có thể giúp duy trì khả năng tương thích hai chiều. Trong trường hợp đó, cần thiết kế schema theo chiến lược expand-and-contract hoặc một cơ chế versioning phù hợp.

### 2.7. Quy mô hệ thống và khả năng phối hợp

Một ứng dụng đơn giản do một nhóm sở hữu có thể nâng cấp trực tiếp dễ dàng hơn một hệ thống gồm nhiều service, plugin và consumer do nhiều nhóm quản lý.

Đánh giá:

- Số module và service chịu ảnh hưởng.
- Số nhóm sở hữu các consumer.
- Khả năng triển khai đồng thời.
- Tần suất phát hành của từng thành phần.
- Thời gian cần để kiểm thử regression.
- Khả năng tạo môi trường staging hoặc test độc lập.
- Khả năng quan sát và truy vết lỗi.
- Mức độ sẵn sàng của người phụ trách vận hành.

Nếu một consumer chỉ chạy theo lịch hàng tuần, một đợt rollout ngắn chưa chắc đã kiểm chứng được nó. Lộ trình phải tính đến chu kỳ thực tế của consumer.

## 3. So sánh ưu điểm và chi phí của hai cách

| Tiêu chí | Nâng cấp trực tiếp | Qua các mốc trung gian |
|---|---|---|
| Số đợt thay đổi | Ít đợt hơn | Nhiều đợt hơn |
| Thời gian quản lý tổng thể | Có thể ngắn hơn khi phạm vi đơn giản | Có thể dài hơn do cần kiểm chứng từng mốc |
| Phạm vi thay đổi mỗi đợt | Lớn | Nhỏ hơn nếu chia hợp lý |
| Tìm nguyên nhân regression | Khó hơn nếu nhiều thay đổi cùng lúc | Dễ khoanh vùng hơn theo từng mốc |
| Kiểm thử | Cần bộ test toàn diện ở trạng thái mục tiêu | Cần test tại từng mốc và test tích hợp cuối |
| Quản lý dependency | Có thể cập nhật tập trung | Có thể điều chỉnh từng nhóm |
| Yêu cầu tương thích tạm thời | Có thể ít trạng thái trung gian hơn | Có thể cần hỗ trợ nhiều tổ hợp phiên bản |
| Rollback | Có thể đơn giản nếu chưa thay đổi dữ liệu không đảo ngược | Phải quản lý trạng thái rollback ở từng mốc |
| Phối hợp nhiều nhóm | Có thể cần đồng bộ lớn | Có thể chia công việc, nhưng phải quản lý giao diện giữa các mốc |
| Rủi ro tích lũy | Nhiều thay đổi có thể che khuất nguyên nhân | Có thể phát hiện sớm, nhưng thêm điểm chuyển tiếp |
| Phiên bản trung gian | Không cần vận hành nếu đường nâng cấp trực tiếp hợp lệ | Cần chọn mốc có mục đích và hỗ trợ phù hợp |

Không nên kết luận rằng nhiều mốc luôn giảm rủi ro. Mỗi mốc bổ sung thêm một trạng thái cần build, test, cấu hình, lưu artifact và có thể phải duy trì tương thích. Nếu mốc trung gian không đem lại thông tin hoặc khả năng kiểm soát mới, nó chỉ làm tăng chi phí.

Ngược lại, không nên chọn nâng cấp trực tiếp chỉ vì muốn giảm số lần phát hành. Nếu một bước nhảy gom nhiều thay đổi không thể cô lập, nhóm có thể mất nhiều thời gian hơn để tìm lỗi và khôi phục.

## 4. Các tiêu chí bắt buộc và tiêu chí tối ưu

Để tránh quyết định theo cảm tính, hãy tách điều kiện bắt buộc khỏi yếu tố tối ưu.

### 4.1. Điều kiện bắt buộc (hard constraints)

Nếu một điều kiện sau không đạt, lộ trình tương ứng không được chọn cho đến khi có phương án giải quyết:

- Nhà cung cấp không hỗ trợ đường nâng cấp trực tiếp và yêu cầu đi qua một phiên bản cầu nối.
- Build tool hoặc framework hiện tại không thể chạy hoặc chuyển đổi trực tiếp theo tài liệu hỗ trợ.
- Có migration schema bắt buộc theo thứ tự.
- Có artifact trung gian phải được tạo để chuyển đổi định dạng hoặc metadata.
- Một API hoặc giao thức không hỗ trợ trạng thái cũ và mới chạy đồng thời, trong khi rollout bắt buộc phải rolling.
- Không thể kiểm thử trạng thái mục tiêu một cách đáng tin cậy nếu chưa giải quyết dependency hoặc toolchain ở mốc trước.
- Chính sách vận hành hoặc vendor support yêu cầu một trạng thái trung gian cụ thể.

Khi gặp hard constraint, hãy ghi nguồn xác nhận, phiên bản áp dụng và hậu quả nếu bỏ qua.

### 4.2. Tiêu chí tối ưu (trade-off criteria)

Nếu không có hard constraint, có thể so sánh các phương án theo:

- Tổng thời gian và công sức thực hiện.
- Độ lớn của thay đổi trong mỗi mốc.
- Khả năng xác định nguyên nhân regression.
- Khả năng giữ consumer cũ hoạt động.
- Chi phí tạo và duy trì môi trường.
- Số lần build, kiểm thử và phát hành.
- Khả năng rollback.
- Mức độ sẵn sàng của nhóm.
- Thời gian còn lại của phiên bản hiện tại trước khi hết hỗ trợ.
- Chi phí vận hành nếu phải duy trì phiên bản trung gian.

Một quyết định tốt phải nêu rõ tiêu chí nào quan trọng nhất với hệ thống, thay vì cộng điểm cơ học mà không hiểu mức độ nghiêm trọng.

## 5. Khung ra quyết định

Có thể dùng quy trình sau để chọn direct upgrade hoặc intermediate-step upgrade.

### Bước 1: Chốt baseline và target

Ghi lại:

- JDK hiện tại và JDK mục tiêu.
- Framework/application server hiện tại và mục tiêu.
- Build tool và plugin hiện tại/mục tiêu.
- Dependency quan trọng và phiên bản được hỗ trợ.
- Artifact và consumer cần tiếp tục hoạt động.
- Mục tiêu về source, binary, behavioral và data compatibility.
- Hạn hỗ trợ hoặc thời điểm phải hoàn thành.

Không chọn target chỉ vì đó là phiên bản mới nhất. Cần xét vòng đời hỗ trợ, khả năng tương thích của framework, môi trường triển khai và kế hoạch bảo trì.

### Bước 2: Thu thập các đường nâng cấp chính thức

Đọc tài liệu migration và release notes của các phiên bản nằm giữa baseline và target.

Lập bảng:

| Thành phần | Baseline | Target | Thay đổi quan trọng | Yêu cầu thứ tự |
|---|---|---|---|---|
| JDK | Phiên bản hiện tại | Phiên bản mục tiêu | API, bytecode, runtime, module | Theo tài liệu JDK |
| Framework | Phiên bản hiện tại | Phiên bản mục tiêu | API, cấu hình, extension point | Theo guide của framework |
| Build tool | Phiên bản hiện tại | Phiên bản mục tiêu | Wrapper, plugin, compiler | Theo ma trận tương thích |
| Dependency | Bộ phiên bản hiện tại | Bộ phiên bản mục tiêu | API và transitive graph | Theo BOM/vendor |
| Data/schema | Schema hiện tại | Schema mục tiêu | Đọc/ghi, migration, rollback | Theo kế hoạch dữ liệu |

Ghi rõ đường đi được hỗ trợ và các điều kiện trước khi nâng cấp. Nếu tài liệu chỉ mô tả từng bước liền kề, không được tự suy luận rằng có thể bỏ qua các bước đó.

### Bước 3: Liệt kê thay đổi và phân loại mức độ

Với từng thay đổi, đánh giá:

- Phạm vi file/module bị ảnh hưởng.
- Có breaking change không?
- Có thể xử lý độc lập không?
- Có consumer cũ chịu ảnh hưởng không?
- Có thể viết test tái hiện không?
- Có phụ thuộc vào thay đổi khác không?
- Có cần thay đổi dữ liệu hoặc cấu hình không?

Phân loại gợi ý:

| Nhóm | Mô tả | Ví dụ |
|---|---|---|
| Nhỏ | Thay đổi cục bộ, có thể xác minh nhanh | Cập nhật warning hoặc cấu hình không còn dùng |
| Vừa | Ảnh hưởng một số module hoặc API | Thay API deprecated, nâng plugin build |
| Lớn | Ảnh hưởng nhiều module hoặc contract | Thay framework major, chuyển namespace |
| Rất lớn | Ảnh hưởng kiến trúc, dữ liệu hoặc nhiều consumer độc lập | Thay đổi schema không tương thích, thay runtime/container model |

Mức phân loại phải dựa trên dependency graph và consumer inventory, không chỉ số lượng dòng code thay đổi.

### Bước 4: Xác định các hard constraint

Nếu có điều kiện bắt buộc phải qua phiên bản hoặc trạng thái trung gian, đưa nó vào lộ trình trước. Đừng cố tối ưu số mốc bằng cách bỏ qua một yêu cầu hỗ trợ chính thức.

Nếu không có hard constraint, tiếp tục so sánh chi phí và rủi ro của hai phương án.

### Bước 5: Làm thử nghiệm kỹ thuật nhỏ (spike)

Trước khi quyết định cho toàn bộ hệ thống, chọn một module đại diện có dependency và cách chạy gần với hệ thống thực tế.

Thử nghiệm nên kiểm tra:

- Build bằng JDK và build tool mục tiêu.
- Compile source với dependency mục tiêu.
- Chạy test hiện có và một số luồng nghiệp vụ trọng yếu.
- Nạp plugin hoặc extension nếu hệ thống có.
- Chạy consumer đã biên dịch với phiên bản thư viện cũ nếu binary compatibility là yêu cầu.
- Kiểm tra cấu hình, serialization và dữ liệu đại diện.
- Thu thập lỗi, số lượng thay đổi và thời gian xử lý.

Spike không cần thay thế toàn bộ migration. Mục tiêu là giảm bất định trước khi chọn lộ trình. Chọn module đại diện có rủi ro thực tế; một module quá đơn giản có thể tạo cảm giác an toàn giả.

### Bước 6: So sánh phương án và ghi quyết định

Lập ít nhất hai phương án:

- Phương án A: nâng cấp trực tiếp từ baseline lên target.
- Phương án B: đi qua các mốc trung gian cần thiết.

Với từng phương án, ghi:

- Điều kiện hỗ trợ.
- Các thay đổi cần thực hiện.
- Rủi ro chính và biện pháp kiểm soát.
- Môi trường và test cần có.
- Số lần phát hành hoặc checkpoint.
- Thời gian ước tính và giả định.
- Khả năng rollback.
- Consumer nào cần cập nhật và thời điểm.

Sau đó ghi lại lý do chọn phương án. Nếu dữ liệu chưa đủ, quyết định có thể là “chưa chọn” kèm theo spike hoặc khảo sát cần hoàn thành.

## 6. Ma trận lựa chọn tham khảo

Bảng sau giúp nhận diện dấu hiệu nghiêng về từng phương án. Đây là hướng dẫn định tính; hard constraint và bằng chứng thực tế vẫn quyết định cuối cùng.

| Tiêu chí quan sát | Nghiêng về nâng cấp trực tiếp | Nghiêng về mốc trung gian |
|---|---|---|
| Đường nâng cấp chính thức | Có hỗ trợ trực tiếp | Bắt buộc qua phiên bản cầu nối |
| Framework | Tương thích target, migration guide rõ | Major release yêu cầu chuyển đổi tuần tự |
| Build tool | Có thể nâng wrapper/plugin cùng đợt | Tool cũ không thể thực hiện bước chuyển tiếp |
| API | Ít breaking change, phạm vi nhỏ | Nhiều API removal hoặc extension point thay đổi |
| Consumer cũ | Có thể cập nhật hoặc test binary đầy đủ | Consumer độc lập, không thể cập nhật đồng thời |
| Dữ liệu | Schema và protocol giữ tương thích | Cần expand/contract hoặc nhiều giai đoạn |
| Phạm vi code | Tập trung, phụ thuộc rõ | Nhiều module và dependency chéo |
| Kiểm thử | Có test mục tiêu toàn diện | Cần checkpoint để cô lập thay đổi |
| Rollback | Artifact/config trước đó có thể khôi phục an toàn | Cần trạng thái tương thích chuyển tiếp |
| Nguồn lực | Nhóm đủ khả năng xử lý nhiều thay đổi cùng lúc | Cần chia công việc theo nhóm và thời gian |
| Thời hạn hỗ trợ | Có thể hoàn tất trong một đợt | Cần giảm rủi ro do nhiều nhóm phát hành khác lịch |

Một số tín hiệu cần được ưu tiên cao:

- Một yêu cầu bắt buộc từ vendor có trọng lượng cao hơn điểm số tổng hợp.
- Một consumer quan trọng không thể cập nhật có thể buộc nhóm giữ API hoặc tạo adapter.
- Một migration dữ liệu không thể đảo ngược có thể quyết định thứ tự triển khai.
- Một hệ thống không có test đáng tin cậy cần giảm bất định trước khi thực hiện thay đổi lớn.

## 7. Mô hình chấm điểm để so sánh hai phương án

Nếu cả hai phương án đều khả thi, nhóm có thể dùng thang điểm để làm rõ trade-off. Điểm không thay thế quyết định kỹ thuật; nó giúp các bên nhìn thấy giả định và lý do.

### 7.1. Chọn tiêu chí và trọng số

Ví dụ thang trọng số:

| Tiêu chí | Trọng số ví dụ | Cách hiểu |
|---|---:|---|
| Độ an toàn tương thích | 30% | Khả năng giữ API, binary, behavior và data contract |
| Khả năng kiểm chứng | 20% | Có thể phát hiện và khoanh vùng lỗi bằng test/bằng chứng |
| Khả năng rollback | 15% | Có thể quay về trạng thái hoạt động trước đó |
| Tổng công sức | 15% | Công sức code, test, phối hợp và vận hành |
| Thời gian hoàn thành | 10% | Khả năng đáp ứng deadline và support window |
| Độ phức tạp vận hành | 10% | Số trạng thái phải duy trì và giám sát |

Tổng trọng số bằng 100%. Dự án có thể thay đổi trọng số nhưng phải thống nhất trước khi chấm.

### 7.2. Chấm điểm từng phương án

Dùng thang 1–5, trong đó 5 là thuận lợi nhất. Với tiêu chí “tổng công sức”, điểm cao nghĩa là ít công sức hơn; với “độ phức tạp vận hành”, điểm cao nghĩa là dễ vận hành hơn.

Công thức:

~~~text
Weighted Score = Sum(criterion_score x criterion_weight)
~~~

Ví dụ minh họa:

| Tiêu chí | Trọng số | Direct | Qua mốc trung gian |
|---|---:|---:|---:|
| Độ an toàn tương thích | 30% | 3 | 4 |
| Khả năng kiểm chứng | 20% | 3 | 5 |
| Khả năng rollback | 15% | 4 | 4 |
| Tổng công sức | 15% | 5 | 3 |
| Thời gian hoàn thành | 10% | 5 | 3 |
| Độ phức tạp vận hành | 10% | 4 | 3 |
| **Điểm có trọng số** | **100%** | **3.70/5** | **3.90/5** |

Trong ví dụ này, phương án trung gian có điểm cao hơn do khả năng kiểm chứng. Tuy nhiên, nếu một hard constraint cấm nâng trực tiếp, không cần chấm điểm để chọn phương án trung gian. Ngược lại, nếu đường trực tiếp được hỗ trợ, có test đầy đủ và các mốc thêm vào không giảm rủi ro, direct upgrade có thể là lựa chọn tốt hơn.

Không nên dùng điểm số để che giấu một rủi ro nghiêm trọng. Ví dụ, rủi ro mất dữ liệu không được bù bằng điểm tiết kiệm thời gian cao.

## 8. Ví dụ lựa chọn lộ trình trong các tình huống Java

Các ví dụ dưới đây minh họa cách suy luận. Phiên bản và ma trận hỗ trợ thực tế phải được xác nhận theo tài liệu của từng framework, vendor và dependency.

### 8.1. Thư viện nội bộ nhỏ, consumer được quản lý tập trung

Giả sử thư viện có ít public API, chỉ một số service trong cùng tổ chức sử dụng và tất cả consumer đều có thể build lại.

Đặc điểm:

- Dependency graph nhỏ và đã biết.
- Không có plugin bên ngoài.
- Không có schema hoặc protocol cần chuyển đổi.
- Test unit/integration đủ bao phủ.
- Framework và build tool hỗ trợ trực tiếp target.

Lộ trình có thể là direct upgrade:

1. Chốt artifact baseline.
2. Nâng JDK/build tool/dependency đến target.
3. Sửa source và cấu hình.
4. Build toàn bộ consumer.
5. Chạy regression và integration test.
6. Kiểm tra runtime và rollout.
7. Lưu bằng chứng và quyết định phát hành.

Không cần tạo một bản phát hành production cho từng JDK trung gian nếu không có yêu cầu hỗ trợ hoặc kiểm soát nào đòi hỏi điều đó. Dù vậy, vẫn phải đọc release notes của các phiên bản bị bỏ qua.

### 8.2. Ứng dụng phụ thuộc nhiều major release của framework

Giả sử ứng dụng dùng một framework lớn, có thay đổi cấu hình và extension point qua nhiều major release. Một số thư viện tích hợp chỉ hỗ trợ framework mới sau khi đã nâng lên phiên bản cầu nối.

Lộ trình trung gian có thể phù hợp:

~~~text
Framework cũ
    |
    v
Mốc A: xử lý API/configuration deprecated
    |
    v
Mốc B: nâng lên phiên bản cầu nối được hỗ trợ
    |
    v
Mốc C: cập nhật extension và dependency
    |
    v
Framework mục tiêu
~~~

Tại mỗi mốc:

- Kiểm tra ma trận hỗ trợ.
- Build và test module liên quan.
- Ghi lại cấu hình đã thay đổi.
- Kiểm tra các integration adapter.
- Xác nhận consumer và plugin.
- Chỉ đi tiếp khi gate của mốc đạt.

Không nhất thiết phải triển khai từng mốc lên production. Nếu có thể giữ các mốc trong branch và môi trường kiểm thử, nhóm vẫn có thể cô lập lỗi mà không tạo thêm trạng thái vận hành lâu dài.

### 8.3. Chuyển đổi namespace hoặc API diện rộng

Một số migration framework lớn có thể thay đổi package, API hoặc cách framework phát hiện component. Ví dụ, một đợt chuyển từ hệ sinh thái Java EE cũ sang Jakarta EE có thể ảnh hưởng đến import, annotation, servlet API, validation, persistence, dependency và cấu hình.

Trong trường hợp này, cần khảo sát:

- Toàn bộ namespace đang dùng.
- Các thư viện tích hợp đã hỗ trợ namespace mục tiêu chưa.
- Plugin và code generation có tạo source cũ không.
- Có artifact nào cần được nâng trước để hỗ trợ namespace mới không.
- Có thể tách cập nhật dependency khỏi chuyển đổi source không.
- Có consumer cần tiếp tục chạy trên namespace cũ không.

Nếu dependency hoặc framework có bước cầu nối chính thức, hãy sử dụng mốc đó. Nếu có thể cập nhật toàn bộ trong một branch và test được đầy đủ, một đợt migration trực tiếp vẫn có thể khả thi. Quyết định phải dựa trên dependency inventory và spike thực tế.

### 8.4. Thư viện công khai có plugin được biên dịch độc lập

Giả sử một SDK được dùng bởi nhiều tổ chức. Một số plugin có thể không được biên dịch lại trong nhiều tháng.

Trong tình huống này, tiêu chí binary compatibility có thể quan trọng hơn việc giảm số mốc. Lộ trình cần:

1. Chụp API binary baseline.
2. Kiểm kê các extension point và implementation cũ.
3. Giữ bridge method hoặc adapter khi có thể.
4. Thử chạy plugin artifact cũ với thư viện mục tiêu.
5. Phát hành bản tương thích chuyển tiếp nếu cần.
6. Thông báo deprecation và thời điểm loại bỏ API.
7. Chỉ chuyển sang phiên bản breaking khi đã có chính sách và xác nhận consumer.

Một phiên bản trung gian có thể đóng vai trò phiên bản tương thích chuyển tiếp, nhưng chỉ khi nó có mục đích rõ ràng và được hỗ trợ đủ lâu. Không nên tạo một phiên bản tạm thời chỉ để tăng số bước.

### 8.5. Hệ thống có database migration và rolling deployment

Nếu ứng dụng mới thay đổi schema, nhưng các instance cũ vẫn chạy trong lúc rollout, cần thiết kế lộ trình sao cho hai phiên bản có thể cùng tồn tại trong thời gian chuyển tiếp.

Ví dụ:

~~~text
Schema v1 + Application v1
          |
          v
Mở rộng schema: v1 + cột mới
          |
          v
Application v2 đọc/ghi tương thích
          |
          v
Di chuyển dữ liệu và consumer
          |
          v
Xác nhận không còn sử dụng cấu trúc cũ
          |
          v
Thu hẹp schema: loại bỏ cấu trúc cũ
~~~

Đây là một chuỗi mốc dữ liệu và triển khai. Nó có thể cần thiết ngay cả khi JDK và framework được nâng trực tiếp. Lộ trình Java version và lộ trình schema nên được quản lý riêng nhưng phải phối hợp với nhau.

## 9. Những sai lầm thường gặp khi chọn lộ trình

### 9.1. Bỏ qua release notes của các phiên bản trung gian

Chọn direct upgrade không có nghĩa là bỏ qua các phiên bản ở giữa. Một API có thể bị deprecated ở phiên bản trước và bị xóa ở phiên bản mục tiêu. Nếu chỉ đọc hướng dẫn của target, nhóm có thể bỏ lỡ điều kiện chuyển đổi hoặc thay đổi mặc định đã xuất hiện trước đó.

Cách xử lý: lập danh sách release notes và migration guide từ baseline đến target; đánh dấu các thay đổi có ảnh hưởng đến hệ thống.

### 9.2. Nâng cấp mọi thứ cùng lúc mà không có baseline

Nâng JDK, framework, build tool và tất cả dependency trong cùng một commit có thể khiến lỗi khó truy nguyên. Khi test thất bại, nhóm không biết lỗi do bytecode, API, cấu hình, plugin hay dependency.

Cách xử lý: ghi baseline và chia nhóm thay đổi có quan hệ rõ ràng. Ngay cả khi chọn direct upgrade, vẫn có thể tách commit hoặc checkpoint kiểm thử theo nhóm.

### 9.3. Tạo quá nhiều mốc không cần thiết

Mỗi mốc có thể tạo thêm build, test, artifact, cấu hình và chi phí phối hợp. Nếu mốc không có yêu cầu hỗ trợ, không giảm bất định và không tạo bằng chứng mới, nó không có giá trị đủ lớn.

Cách xử lý: mỗi mốc phải nêu rõ mục đích, điều kiện đầu vào, tiêu chí đầu ra và quyết định được phép đưa ra sau khi đạt mốc.

### 9.4. Triển khai phiên bản trung gian đã hết hỗ trợ

Một phiên bản trung gian có thể hữu ích để chuyển đổi kỹ thuật nhưng không phù hợp để vận hành production. Nếu phải triển khai nó, cần xác nhận vòng đời hỗ trợ và thời gian tồn tại của trạng thái đó.

Cách xử lý: phân biệt checkpoint kiểm thử với production milestone. Chỉ triển khai phiên bản trung gian khi có lý do vận hành và thời hạn rõ ràng.

### 9.5. Chỉ kiểm tra source compatibility

Build thành công sau khi biên dịch lại tất cả module không chứng minh plugin hoặc consumer cũ còn hoạt động.

Cách xử lý: lưu artifact baseline và chạy bytecode cũ với thư viện mới. Kiểm thử các implementation cũ của interface, plugin và service provider.

### 9.6. Không tính thời gian của consumer chạy theo lịch

Một batch chạy hàng tuần có thể không được thực thi trong khoảng rollout. Hệ thống có vẻ ổn nhưng lỗi chỉ xuất hiện ở lần chạy tiếp theo.

Cách xử lý: đưa chu kỳ batch vào acceptance criteria và thời gian quan sát. Có thể kích hoạt test chủ động bằng artifact và dữ liệu đại diện.

### 9.7. Xem rollback code là rollback toàn hệ thống

Nếu phiên bản mới đã thay đổi schema, ghi dữ liệu mới hoặc phát event mà phiên bản cũ không hiểu, rollback binary có thể không khôi phục được trạng thái hoạt động.

Cách xử lý: đánh giá rollback cho code, cấu hình, database, message và external side effects như các phần riêng; diễn tập trước khi triển khai.

### 9.8. Chọn phiên bản mục tiêu chỉ vì mới nhất

Phiên bản mới nhất có thể chưa được framework, application server, plugin hoặc nền tảng triển khai hỗ trợ đầy đủ.

Cách xử lý: chọn target theo support window, tương thích hệ sinh thái, khả năng bảo trì và yêu cầu vận hành. Ghi rõ lý do chọn target.

## 10. Thiết kế checkpoint và tiêu chí đi qua từng mốc

Nếu chọn lộ trình trung gian, mỗi mốc cần có một hợp đồng kiểm chứng. Không nên đặt tên mốc chỉ bằng phiên bản mà không nêu trạng thái cần đạt.

Mẫu định nghĩa một mốc:

| Trường | Nội dung cần ghi |
|---|---|
| Milestone ID | Mã duy nhất, ví dụ M1 |
| Baseline | Phiên bản và artifact đầu vào |
| Target state | JDK/framework/build/dependency sau mốc |
| Scope | Module, consumer và môi trường liên quan |
| Changes | Các thay đổi source, config, dependency hoặc data |
| Preconditions | Điều kiện cần trước khi bắt đầu |
| Acceptance criteria | Các điều kiện Pass có thể kiểm tra |
| Evidence | Build ID, test report, artifact checksum, log |
| Rollback | Cách quay lại trạng thái trước mốc |
| Owner | Người chịu trách nhiệm |
| Decision | Go / No-Go / Pending |

Ví dụ:

| Mốc | Mục tiêu | Điều kiện đi qua |
|---|---|---|
| M0 — Baseline | Chốt trạng thái hiện tại | Artifact, dependency graph, test baseline và consumer inventory đã lưu |
| M1 — Toolchain | Build được với toolchain mục tiêu | Wrapper/plugin hỗ trợ, compile và test cơ bản đạt |
| M2 — API/framework | Hoàn tất thay đổi API và framework | Không còn lỗi compile; binary/API check đạt |
| M3 — Runtime/data | Xác nhận runtime và dữ liệu | Integration, serialization, schema và health check đạt |
| M4 — Release candidate | Xác nhận trạng thái cuối | Regression, performance, rollback và approval đạt |

Đây chỉ là ví dụ cấu trúc. Nếu hệ thống không có thay đổi dữ liệu hoặc framework, không cần tạo mốc tương ứng chỉ để lấp đầy bảng.

### 10.1. Quy tắc Go / No-Go

Một mốc có thể được đánh giá bằng ba trạng thái:

- **Go:** mọi tiêu chí bắt buộc đã Pass và bằng chứng được lưu.
- **No-Go:** có tiêu chí Fail hoặc rủi ro chưa được xử lý vượt ngưỡng.
- **Pending:** chưa có đủ dữ liệu hoặc chưa chạy kiểm tra. Pending không được xem là Go.

Quyết định ngoại lệ phải có risk ID, phạm vi ảnh hưởng, biện pháp bù, thời hạn và người có thẩm quyền chấp nhận.

### 10.2. Không đánh đồng checkpoint với một lần release

Có thể tạo checkpoint bằng:

- Commit hoặc tag trong branch migration.
- Artifact build riêng trong CI.
- Môi trường integration test.
- Báo cáo tương thích API.
- Bộ test với consumer cũ.
- Bản snapshot cấu hình và dependency graph.

Chỉ tạo release hoặc rollout production nếu cần kiểm tra các điều kiện mà môi trường trước đó không thể đại diện.

## 11. Lập kế hoạch kiểm thử theo lộ trình

Dù chọn cách nào, kế hoạch test phải bao phủ trạng thái mục tiêu. Lộ trình trung gian bổ sung kiểm thử tại các checkpoint; nó không thay thế kiểm thử cuối.

### 11.1. Với direct upgrade

Một kế hoạch kiểm thử có thể gồm:

1. Build baseline để bảo đảm điểm xuất phát có thể tái hiện.
2. Chốt artifact và dependency graph.
3. Thực hiện thay đổi lên target.
4. Chạy compile, unit test và static analysis.
5. Chạy source compatibility test cho consumer cần build lại.
6. Chạy binary compatibility test với consumer cũ.
7. Chạy integration, contract và regression test.
8. Kiểm tra data migration, runtime, performance và security.
9. Thử rollout và rollback trên môi trường tương đương.
10. Đối chiếu acceptance criteria trước khi phát hành.

### 11.2. Với intermediate-step upgrade

Ngoài các kiểm tra cuối, mỗi mốc cần:

1. Xác nhận baseline của mốc trước.
2. Chỉ áp dụng nhóm thay đổi thuộc mốc hiện tại.
3. Build và test theo acceptance criteria của mốc.
4. Lưu artifact, cấu hình và báo cáo.
5. Đánh giá lỗi và cập nhật risk register.
6. Quyết định Go/No-Go.
7. Chỉ chuyển sang mốc tiếp theo khi điều kiện đầu vào được đáp ứng.

Khi đã đến target, chạy lại bộ test tích hợp cuối. Các mốc riêng lẻ đạt không đảm bảo rằng toàn bộ tổ hợp cuối cùng sẽ hoạt động đúng.

### 11.3. Chọn consumer đại diện

Nếu có nhiều consumer, hãy phân nhóm theo cách sử dụng API:

- Consumer chỉ gọi public API thông thường.
- Consumer triển khai interface hoặc kế thừa abstract class.
- Consumer dùng reflection hoặc annotation.
- Plugin được nạp động.
- Consumer dùng serialization hoặc chia sẻ schema.
- Consumer chạy trên JDK hoặc môi trường khác.
- Consumer chạy theo lịch hoặc có tải đặc thù.

Chọn ít nhất một đại diện cho từng nhóm có rủi ro khác nhau. Nếu một nhóm consumer quan trọng không thể lấy artifact thật, ghi rõ giới hạn và mức rủi ro còn lại.

## 12. Quản lý dependency và thứ tự nâng cấp

Thứ tự nâng cấp nên theo dependency graph và ma trận hỗ trợ.

Một trình tự tham khảo:

~~~text
1. Baseline và inventory
          |
          v
2. Kiểm tra JDK/build tool/plugin
          |
          v
3. Nâng toolchain đủ điều kiện build target
          |
          v
4. Nâng framework và dependency theo ma trận hỗ trợ
          |
          v
5. Sửa source, cấu hình và extension point
          |
          v
6. Kiểm tra consumer, dữ liệu và runtime
          |
          v
7. Release candidate, rollout và quan sát
~~~

Thứ tự thực tế có thể khác. Ví dụ, một build plugin yêu cầu JDK mới để chạy nhưng compiler target vẫn có thể tạo bytecode cho phiên bản cũ. Hoặc framework yêu cầu nâng dependency trước khi thay JDK. Hãy dựa vào tài liệu chính thức và thử nghiệm, không áp dụng sơ đồ như một quy tắc cứng.

Cần theo dõi riêng:

- JDK dùng để chạy Gradle/Maven.
- JDK compiler/toolchain dùng để biên dịch source.
- Tùy chọn **--release**, source compatibility và target bytecode.
- JDK runtime của ứng dụng.
- JDK trong container, CI và production.
- Phiên bản framework và dependency được resolve thực tế.

Một build thành công trên JDK mới nhưng tạo bytecode target không phù hợp với runtime triển khai vẫn có thể thất bại khi chạy. Ngược lại, bytecode target cũ không bảo đảm ứng dụng chạy được nếu source hoặc dependency sử dụng API chỉ có ở JDK mới.

## 13. Quản lý nhánh, artifact và khả năng rollback

Khi thực hiện migration kéo dài, việc quản lý trạng thái có ý nghĩa ngang với thứ tự nâng cấp.

### 13.1. Lưu baseline có thể tái tạo

Lưu:

- Commit nguồn.
- Artifact đã phát hành.
- Checksum.
- Dependency graph hoặc lockfile.
- JDK và build tool.
- Cấu hình runtime.
- Kết quả test baseline.
- Schema và snapshot dữ liệu nếu chính sách cho phép.

Không dựa vào một thư mục build cũ không rõ nguồn gốc. Artifact cần xác định được commit và quy trình tạo.

### 13.2. Quản lý nhánh migration

Có thể sử dụng một branch migration riêng khi thay đổi lớn, nhưng phải quy định:

- Nhánh nào là source of truth.
- Cách đồng bộ bug fix từ nhánh chính.
- Điều kiện merge.
- Cách tạo release candidate.
- Cách xử lý khi một mốc bị hủy.
- Cách tránh nhiều nhánh giữ các phiên bản dependency khác nhau quá lâu.

Nếu chia nhiều checkpoint, có thể dùng tag hoặc commit để lưu trạng thái đã đạt. Không cần tạo một nhánh dài hạn cho mọi mốc.

### 13.3. Rollback theo từng lớp

Rollback phải xét:

| Lớp | Câu hỏi |
|---|---|
| Application artifact | Có thể khôi phục JAR/image cũ không? |
| Runtime/JDK | Hạ runtime có còn được nền tảng hỗ trợ không? |
| Configuration | Có thể khôi phục config và feature flag không? |
| Dependency | Artifact cũ có resolve đúng dependency cũ không? |
| Database | Schema và dữ liệu mới có tương thích với code cũ không? |
| Messaging | Event/message mới có được consumer cũ hiểu không? |
| External side effects | Có tác vụ không thể đảo ngược đã xảy ra không? |

Nếu rollback không an toàn sau một bước dữ liệu, cần xác định checkpoint sau bước đó là một điểm không thể quay lại đơn giản. Khi đó phải có recovery hoặc forward-fix plan.

## 14. Ghi lại quyết định lựa chọn lộ trình

Một quyết định migration nên đủ rõ để người khác hiểu tại sao nhóm chọn direct upgrade hoặc intermediate-step upgrade.

Mẫu decision record:

~~~text
Decision ID:
Ngày:
Người quyết định:
Hệ thống / module:
Baseline:
Target:
Mục tiêu tương thích:

Phương án A - Direct upgrade:
- Đường nâng cấp được hỗ trợ:
- Các thay đổi chính:
- Consumer bị ảnh hưởng:
- Test và bằng chứng:
- Rủi ro:
- Thời gian/công sức:
- Rollback:

Phương án B - Intermediate steps:
- Các mốc:
- Lý do cần từng mốc:
- Đường hỗ trợ:
- Consumer ở từng mốc:
- Test và bằng chứng:
- Rủi ro:
- Thời gian/công sức:
- Rollback:

Hard constraints:
Trade-offs:
Spike đã thực hiện:
Kết quả spike:
Phương án được chọn:
Lý do:
Rủi ro còn lại:
Điều kiện xem xét lại:
Người phê duyệt:
Evidence location:
~~~

Nếu chọn intermediate steps, mỗi mốc phải có mục đích rõ ràng. Nếu chọn direct upgrade, quyết định phải ghi nhận vì sao không cần một trạng thái trung gian và bằng chứng nào chứng minh đường trực tiếp có thể kiểm soát.

## 15. Checklist trước khi chốt lộ trình

### Phạm vi và mục tiêu

- [ ] Đã chốt baseline và target cho JDK, framework, build tool và dependency.
- [ ] Đã xác định consumer cần hỗ trợ và yêu cầu source/binary/behavior/data compatibility.
- [ ] Đã lưu artifact, checksum và dependency graph nền.
- [ ] Đã xác định thời hạn hỗ trợ và mục tiêu vận hành.

### Đường nâng cấp

- [ ] Đã đọc migration guide và release notes từ baseline đến target.
- [ ] Đã kiểm tra ma trận tương thích chính thức.
- [ ] Đã xác định yêu cầu phiên bản cầu nối hoặc thứ tự bắt buộc.
- [ ] Đã phân loại thay đổi theo phạm vi và mức độ ảnh hưởng.
- [ ] Đã kiểm tra các thay đổi API, cấu hình, module, bytecode và runtime.

### So sánh phương án

- [ ] Đã mô tả direct upgrade và intermediate-step upgrade.
- [ ] Đã tách hard constraint khỏi trade-off.
- [ ] Mỗi mốc trung gian có mục tiêu, đầu vào, đầu ra và tiêu chí Go/No-Go.
- [ ] Không tạo mốc hoặc release chỉ để tăng số bước.
- [ ] Đã làm spike trên module đại diện khi còn bất định lớn.
- [ ] Đã ghi lý do lựa chọn và giả định.

### Kiểm thử và vận hành

- [ ] Có source compatibility test cho consumer cần build lại.
- [ ] Có binary compatibility test cho consumer cũ cần tiếp tục chạy.
- [ ] Có contract, regression, data và integration test phù hợp.
- [ ] Đã xác nhận JDK build, compiler target và JDK runtime.
- [ ] Đã xác định kế hoạch rollout, quan sát và rollback.
- [ ] Có owner và bằng chứng cho từng gate.
- [ ] Rủi ro còn lại được ghi nhận và có quyết định chấp nhận.

Một lộ trình tốt là lộ trình đáp ứng đường nâng cấp được hỗ trợ, giảm bất định ở những điểm có rủi ro thật và tạo đủ bằng chứng trước khi chuyển trạng thái. Nâng cấp trực tiếp phù hợp khi đường đi rõ, phạm vi kiểm soát được và test mục tiêu đủ mạnh. Các mốc trung gian phù hợp khi chúng giải quyết yêu cầu thứ tự, tách biệt thay đổi lớn hoặc tạo checkpoint cần thiết cho consumer, dữ liệu và vận hành. Quyết định nên được ghi lại cùng giả định và điều kiện xem xét lại để nhóm có thể điều chỉnh khi khảo sát phát hiện thông tin mới.
