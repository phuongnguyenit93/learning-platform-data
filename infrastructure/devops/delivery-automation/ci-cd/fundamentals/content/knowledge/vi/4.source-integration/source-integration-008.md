# Tách chiến lược nhánh chi tiết khỏi nguyên lý CI/CD

## 1. Vì sao cần tách hai chủ đề?

Khi thiết kế quy trình tích hợp mã nguồn, nhóm thường phải trả lời hai nhóm câu hỏi có liên quan nhưng thuộc hai cấp độ khác nhau.

Nhóm câu hỏi thứ nhất nói về **nguyên lý CI/CD**: thay đổi cần được tích hợp thường xuyên đến mức nào, kiểm tra tự động ra sao, artifact được tạo và lưu thế nào, điều kiện nào cho phép phát hành, làm sao truy vết và khôi phục khi có lỗi.

Nhóm câu hỏi thứ hai nói về **chiến lược nhánh Git**: nhóm làm việc trực tiếp trên nhánh chính hay tạo nhánh ngắn hạn, có nhánh phát triển riêng không, khi nào tạo release branch, xử lý hotfix thế nào, hợp nhất bằng merge commit hay squash, và hỗ trợ nhiều phiên bản đang được sử dụng ra sao.

Hai nhóm quyết định này ảnh hưởng lẫn nhau, nhưng không phải một. CI/CD mô tả năng lực và tiêu chuẩn của luồng thay đổi. Chiến lược nhánh mô tả cách nhóm tổ chức mã nguồn và điều phối các thay đổi trong Git. Nếu gộp chúng thành một khái niệm, tài liệu dễ biến một mô hình nhánh cụ thể thành yêu cầu bắt buộc của CI/CD, hoặc khiến pipeline phụ thuộc quá chặt vào tên nhánh.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, cần hiểu sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động, artifact, môi trường, cổng chất lượng, truy vết phát hành, bảo vệ bí mật, xác minh sau triển khai và rollback. Những nguyên lý đó cần giữ được ý nghĩa khi tổ chức thay đổi mô hình nhánh hoặc chuyển nền tảng quản lý mã nguồn.

Mục tiêu của bài này là xác định ranh giới giữa hai chủ đề, chỉ ra điểm giao tiếp của chúng và hướng dẫn cách thiết kế pipeline có thể hoạt động với nhiều chiến lược nhánh khác nhau.

## 2. Phân biệt nguyên lý, chiến lược và cơ chế thực thi

Có thể chia thiết kế thành bốn lớp:

| Lớp | Nội dung quyết định | Ví dụ |
|---|---|---|
| Nguyên lý CI/CD | Kết quả và tiêu chuẩn mà quy trình phải bảo đảm | Phản hồi nhanh, kiểm tra tự động, artifact có thể truy vết, phát hành có kiểm soát |
| Chiến lược nhánh | Cách tổ chức nhánh, vòng đời nhánh và quy tắc hợp nhất | Trunk-based development, GitHub Flow, GitFlow, release branch |
| Tích hợp pipeline với Git | Sự kiện nào kích hoạt job và dữ liệu nào được truyền vào pipeline | Pull request, push, merge, tag, commit SHA, target branch |
| Chính sách phát hành | Điều kiện đưa một artifact đến môi trường hoặc người dùng | Phê duyệt, canary, lịch phát hành, SLO, quyền production |

Ví dụ, nguyên lý CI yêu cầu thay đổi được kiểm tra tự động trước khi trở thành một phần của phiên bản tích hợp. Nhóm có thể thực hiện điều đó bằng pull request ngắn hạn, bằng nhánh tích hợp hoặc bằng một cơ chế merge queue. Tên và số lượng nhánh là quyết định của chiến lược nhánh; việc kiểm tra đúng nội dung thay đổi là yêu cầu CI.

Tương tự, Continuous Delivery yêu cầu phần mềm luôn ở trạng thái có thể phát hành. Điều đó không bắt buộc tổ chức phải có nhánh tên là release, staging hoặc production. Trạng thái sẵn sàng phát hành được chứng minh bằng artifact, kết quả kiểm tra, metadata, cấu hình và chính sách phát hành. Một nhóm có thể phát hành từ nhánh chính, từ tag hoặc từ nhánh release tùy cách quản lý phiên bản.

### 2.1. Nguyên lý CI/CD trả lời câu hỏi “cần bảo đảm điều gì?”

Một số nguyên lý có giá trị với hầu hết mô hình nhánh:

- Tích hợp thay đổi đủ thường xuyên để lỗi được phát hiện sớm.
- Mỗi thay đổi có thể xác định nguồn gốc bằng commit hoặc định danh tương đương.
- Kiểm tra bắt buộc được tự động hóa và có kết quả rõ ràng.
- Build có đầu vào được kiểm soát, đầu ra có thể tái tạo trong điều kiện đã định.
- Artifact được định danh rõ ràng và không bị thay thế âm thầm.
- Các môi trường triển khai cùng artifact đã được xác minh.
- Quyền truy cập và bí mật được quản lý theo nguyên tắc tối thiểu.
- Triển khai có bước xác minh, theo dõi tác động và phương án khôi phục.
- Phản hồi từ production quay lại backlog, kiểm thử và thiết kế.

Các nguyên lý này không đổi chỉ vì nhóm chuyển từ GitFlow sang trunk-based development. Có thể thay đổi thời điểm build, cách đặt tag hoặc cách phê duyệt, nhưng yêu cầu về tính đúng đắn, truy vết và an toàn vẫn phải được giữ.

### 2.2. Chiến lược nhánh trả lời câu hỏi “nhóm tổ chức thay đổi thế nào?”

Chiến lược nhánh là tập hợp quyết định về:

- Nhánh nào là nguồn tích hợp chính.
- Ai được tạo, cập nhật, hợp nhất hoặc xóa nhánh.
- Nhánh tồn tại trong bao lâu.
- Thay đổi được review và hợp nhất theo cách nào.
- Cách duy trì nhiều dòng phiên bản.
- Cách phát hành, sửa lỗi khẩn cấp và đưa bản sửa trở lại các nhánh liên quan.
- Cách giải quyết xung đột khi nhiều nhóm cùng phát triển.

Đây là chính sách làm việc với mã nguồn. Chiến lược phải phù hợp với quy mô nhóm, nhịp phát hành, kiến trúc sản phẩm và nhu cầu duy trì phiên bản.

### 2.3. Cơ chế pipeline là điểm nối giữa hai lớp

Pipeline nhận sự kiện Git và chuyển nó thành hành động có thể kiểm soát. Ví dụ:

- Pull request tạo một lần kiểm tra thay đổi trước khi hợp nhất.
- Push vào nhánh tích hợp tạo một lần xác minh trạng thái mới.
- Tag phiên bản khởi chạy quy trình đóng gói hoặc phát hành.
- Một thao tác được phê duyệt yêu cầu triển khai artifact đến môi trường đích.

Pipeline cần hiểu ngữ cảnh của sự kiện, nhưng không nên nhầm tên nhánh với bản chất của nguyên lý. Một job có thể kiểm tra pull request từ nhiều nhánh bằng cùng bộ tiêu chuẩn cơ bản; các bước đặc thù cho release có thể được bổ sung theo chính sách.

## 3. Những mô hình nhánh thường gặp

Các mô hình dưới đây là những lựa chọn tổ chức công việc. Không mô hình nào tự động bảo đảm CI/CD tốt nếu thiếu kiểm tra, truy vết và quy tắc hợp nhất phù hợp.

### 3.1. Trunk-based development

Trong trunk-based development, nhóm tích hợp thay đổi vào một nhánh chính chung với tần suất cao. Nhà phát triển có thể commit trực tiếp theo quyền được cấp hoặc dùng các nhánh ngắn hạn và pull request có vòng đời ngắn.

Đặc điểm thường gặp:

- Nhánh công việc tồn tại trong thời gian ngắn.
- Thay đổi được chia nhỏ để review và tích hợp thường xuyên.
- Nhánh chính được giữ ở trạng thái có thể build và kiểm tra.
- Feature flag giúp triển khai mã chưa bật tính năng cho toàn bộ người dùng.
- Release branch chỉ được tạo khi có nhu cầu duy trì một phiên bản riêng.

Mô hình này giảm độ lệch giữa các nhánh và giúp CI phản hồi nhanh. Tuy nhiên, nó yêu cầu kiểm thử tự động đáng tin cậy, khả năng chia nhỏ công việc, review có kỷ luật và cơ chế quản lý tính năng chưa hoàn tất.

Trunk-based development phù hợp với nhóm phát hành thường xuyên, sản phẩm có thể triển khai độc lập với việc bật tính năng và tổ chức có khả năng xử lý thay đổi nhỏ liên tục.

### 3.2. GitHub Flow

GitHub Flow là một quy trình đơn giản xoay quanh nhánh chính và các nhánh công việc ngắn hạn:

1. Tạo nhánh từ nhánh chính.
2. Thực hiện một thay đổi có phạm vi rõ ràng.
3. Mở pull request để thảo luận và chạy kiểm tra.
4. Hợp nhất sau khi đạt điều kiện.
5. Triển khai hoặc xác minh thay đổi theo chính sách của nhóm.

Mô hình này dễ hiểu, phù hợp với sản phẩm có nhịp tích hợp nhanh và không cần duy trì nhiều dòng phiên bản dài hạn. Việc triển khai sau merge có thể tự động hoặc cần phê duyệt; bản thân GitHub Flow không quy định rằng mọi lần merge phải lập tức triển khai production.

Nhóm cần làm rõ nhánh chính có luôn sẵn sàng phát hành hay không, pull request yêu cầu những kiểm tra nào và cách xử lý khi phát hiện lỗi sau khi hợp nhất.

### 3.3. GitFlow

GitFlow sử dụng một số nhánh có vai trò tương đối ổn định:

- **main** lưu các mốc phiên bản đã phát hành.
- **develop** tập hợp thay đổi cho phiên bản phát triển tiếp theo.
- Nhánh **feature/** chứa công việc tính năng.
- Nhánh **release/** chuẩn bị một bản phát hành.
- Nhánh **hotfix/** xử lý lỗi khẩn cấp trên phiên bản đã phát hành.

Mô hình này hỗ trợ quy trình phát hành theo đợt và nhiều dòng công việc song song. Nó có thể phù hợp với sản phẩm cần duy trì nhiều phiên bản, có giai đoạn ổn định hóa riêng hoặc có lịch phát hành được điều phối chặt.

Đổi lại, số nhánh và số lần hợp nhất tăng lên. Nếu nhánh develop tồn tại lâu, nhóm có thể phát hiện xung đột tích hợp muộn. Khi hotfix được đưa vào main, nhóm phải bảo đảm bản sửa cũng được đưa trở lại các nhánh phát triển hoặc release còn được hỗ trợ.

GitFlow không phải điều kiện để có CI/CD. Nếu sản phẩm có thể phát hành thường xuyên và không cần duy trì nhiều dòng phiên bản, mô hình đầy đủ có thể tạo thêm công việc điều phối không cần thiết.

### 3.4. Release branch

Một release branch được tách từ trạng thái mã đã chọn để chuẩn bị hoặc duy trì một phiên bản cụ thể. Trong thời gian ổn định hóa, nhóm có thể chỉ chấp nhận sửa lỗi, cập nhật tài liệu phát hành và thay đổi có rủi ro thấp.

Release branch hữu ích khi:

- Một phiên bản cần được kiểm thử và phát hành độc lập.
- Nhiều phiên bản cần được hỗ trợ song song.
- Nhóm cần sửa lỗi cho phiên bản cũ trong khi nhánh chính tiếp tục phát triển.
- Quá trình chứng nhận hoặc triển khai có thời gian riêng.

Cần xác định rõ chính sách đưa bản sửa từ release branch trở lại nhánh chính. Nếu không, cùng một lỗi có thể được sửa ở phiên bản cũ nhưng vẫn tồn tại trong phiên bản mới.

### 3.5. Fork-based workflow

Trong dự án mã nguồn mở hoặc tổ chức có nhiều cộng tác viên bên ngoài, người đóng góp có thể làm việc trên fork riêng rồi gửi pull request về repository gốc.

Cơ chế này tách quyền ghi mã nguồn khỏi quyền đề xuất thay đổi. Pipeline cần đặc biệt chú ý đến ranh giới tin cậy: mã từ fork không nên mặc nhiên nhận secret, token ghi hoặc quyền triển khai của repository gốc.

Fork-based workflow là cách quản lý quyền đóng góp. Các nguyên lý CI/CD như kiểm tra tự động, truy vết commit và quality gate vẫn áp dụng.

### 3.6. So sánh các lựa chọn

| Mô hình | Điểm mạnh | Chi phí hoặc rủi ro | Bối cảnh phù hợp |
|---|---|---|---|
| Trunk-based | Tích hợp nhanh, ít nhánh dài hạn, phản hồi sớm | Đòi hỏi test tốt, thay đổi nhỏ và quản lý feature flag | Phát hành thường xuyên, nhóm phối hợp sát |
| GitHub Flow | Quy trình dễ hiểu, pull request là điểm review rõ | Cần quy tắc rõ cho phát hành và duy trì phiên bản | Sản phẩm có nhánh chính sẵn sàng phát hành |
| GitFlow | Hỗ trợ release theo đợt và nhiều dòng công việc | Nhiều nhánh, hợp nhất và đồng bộ phức tạp | Sản phẩm cần giai đoạn ổn định hóa hoặc nhiều phiên bản |
| Release branch | Cô lập việc ổn định và bảo trì một phiên bản | Phải quản lý backport và vòng đời hỗ trợ | Có phiên bản cũ vẫn cần sửa lỗi |
| Fork-based | Kiểm soát quyền ghi, thuận tiện cho cộng tác bên ngoài | CI cần xử lý mã không đáng tin cậy và giới hạn secret | Dự án mở hoặc cộng tác giữa nhiều tổ chức |

## 4. Chọn chiến lược nhánh dựa trên nhu cầu sản phẩm

Không nên chọn mô hình chỉ vì nó phổ biến hoặc vì một công cụ cung cấp mẫu cấu hình sẵn. Trước khi chọn, nhóm cần trả lời một số câu hỏi.

**Nhịp phát hành là gì?** Nếu sản phẩm có thể phát hành mỗi ngày hoặc nhiều lần mỗi ngày, nhánh ngắn hạn và tích hợp thường xuyên thường giảm chi phí hợp nhất. Nếu phát hành theo phiên bản lớn, nhóm có thể cần release branch để ổn định và kiểm tra theo đợt.

**Có bao nhiêu phiên bản đang được hỗ trợ?** Nếu chỉ có một phiên bản đang chạy và nhóm có thể cập nhật nhanh, một nhánh chính có thể đủ. Nếu khách hàng dùng các phiên bản khác nhau trong thời gian dài, cần cơ chế bảo trì và backport rõ ràng.

**Thay đổi có thể triển khai độc lập với việc bật tính năng không?** Feature flag, cấu hình từ xa hoặc khả năng tương thích ngược giúp tích hợp sớm mà không buộc tính năng phải xuất hiện ngay với người dùng.

**Mức độ kiểm thử tự động ra sao?** Mô hình tích hợp thường xuyên đòi hỏi bộ kiểm tra đủ nhanh và đáng tin cậy. Nếu test chậm hoặc hay thất bại giả, nhóm cần cải thiện chất lượng phản hồi thay vì chỉ thêm nhánh dài hạn để trì hoãn tích hợp.

**Có yêu cầu phê duyệt hoặc chứng nhận riêng không?** Các yêu cầu này có thể được thực hiện bằng release gate, environment protection, hồ sơ phát hành và quy trình phê duyệt. Không nhất thiết phải tạo một nhánh riêng cho mỗi môi trường.

**Nhóm có làm việc trên nhiều repository hoặc thành phần độc lập không?** Monorepo có thể cần kiểm tra theo phạm vi thay đổi, còn nhiều repository có thể cần cơ chế đồng bộ phiên bản và hợp đồng giữa dịch vụ. Những quyết định này ảnh hưởng đến pipeline và cách phát hành, nhưng không làm thay đổi các nguyên lý CI/CD cốt lõi.

Một cách lựa chọn thực tế là bắt đầu từ số dòng phiên bản cần duy trì, tần suất phát hành và yêu cầu kiểm soát. Chọn mô hình đơn giản nhất đáp ứng được các nhu cầu đó, sau đó bổ sung quy tắc khi có bằng chứng về vấn đề thực tế.

## 5. Giữ pipeline độc lập với tên nhánh

Một lỗi thiết kế phổ biến là viết pipeline như thể tên nhánh quyết định toàn bộ hành vi của hệ thống. Ví dụ, một cấu hình có thể mặc định rằng develop luôn tương ứng staging, main luôn tương ứng production và release/* luôn được phép triển khai.

Cách gắn cứng này tạo ra nhiều vấn đề:

- Đổi tên nhánh buộc phải sửa nhiều workflow.
- Chuyển mô hình nhánh có thể làm hỏng pipeline dù nguyên lý CI/CD không đổi.
- Nhánh có tên giống môi trường nhưng nội dung chưa chắc đủ điều kiện triển khai vào môi trường đó.
- Các nhóm khác nhau khó tái sử dụng workflow.
- Một nhánh mới có thể vô tình được cấp quyền hoặc chạy job nhạy cảm do khớp pattern quá rộng.

Thiết kế tốt hơn là phân loại theo **loại sự kiện và ý định**, sau đó dùng chính sách để quyết định hành động.

Ví dụ, pipeline có thể phân biệt:

- Kiểm tra thay đổi trước khi hợp nhất.
- Xác minh trạng thái sau khi hợp nhất.
- Tạo artifact có thể phát hành.
- Phát hành một phiên bản đã được đánh dấu.
- Triển khai một artifact đã được phê duyệt.
- Xác minh dịch vụ sau triển khai.

Tên nhánh vẫn có thể là một điều kiện phụ để áp dụng chính sách. Tuy nhiên, pipeline nên nhận biết rõ event type, commit SHA, pull request target, tag, nguồn artifact và môi trường đích. Những dữ liệu đó mô tả chính xác hơn mục đích của lần chạy.

### 5.1. Ánh xạ sự kiện Git với trách nhiệm pipeline

| Sự kiện | Mục đích | Trách nhiệm pipeline thường gặp |
|---|---|---|
| Pull request được mở hoặc cập nhật | Kiểm tra thay đổi trước khi hợp nhất | Lint, unit test, phân tích tĩnh, kiểm tra bảo mật và contract test phù hợp |
| Push lên nhánh tích hợp | Xác minh trạng thái mã vừa tích hợp | Build, test tích hợp, tạo báo cáo và lưu dấu vết |
| Merge vào nhánh chính | Xác nhận phiên bản tích hợp được chấp nhận | Build artifact, gắn commit và metadata, lưu artifact |
| Push tag phát hành | Xác định phiên bản cần đóng gói hoặc phát hành | Xác minh tag, kiểm tra provenance, tạo release record hoặc khởi chạy release workflow |
| Yêu cầu triển khai được phê duyệt | Đưa artifact đã xác định đến môi trường | Kiểm tra quyền, promote artifact, triển khai và xác minh |
| Sự kiện vận hành hoặc yêu cầu rollback | Khôi phục trạng thái dịch vụ theo quy trình | Chọn artifact đã biết là ổn định, triển khai lại và xác minh |

Không phải dự án nào cũng cần tất cả sự kiện. Bảng này mô tả ranh giới trách nhiệm để nhóm chọn những sự kiện thực sự có trong quy trình của mình.

### 5.2. Kiểm tra pull request phải kiểm tra đúng nội dung sẽ hợp nhất

Pull request có thể thay đổi sau khi CI bắt đầu. Nếu pipeline chỉ kiểm tra một commit cũ nhưng hệ thống vẫn cho phép hợp nhất commit mới, kết quả xanh không còn chứng minh cho nội dung được hợp nhất.

Để tránh tình trạng đó, nhóm có thể:

- Yêu cầu kiểm tra chạy lại khi pull request có commit mới.
- Dùng merge queue hoặc cơ chế kiểm tra merge result nếu nền tảng hỗ trợ.
- Yêu cầu các kiểm tra bắt buộc hoàn tất trên trạng thái cuối cùng trước khi hợp nhất.
- Ghi lại commit SHA được kiểm tra và commit SHA được hợp nhất.
- Không dùng kết quả của một lần chạy đã lỗi thời làm bằng chứng cho phiên bản mới.

Đây là yêu cầu về tính đúng đắn của CI. Nó áp dụng với mọi mô hình nhánh có pull request.

### 5.3. Tên nhánh không phải ranh giới bảo mật

Một điều kiện như nhánh bằng main không tự chứng minh người gửi sự kiện đáng tin cậy. Pipeline cần kiểm tra nguồn sự kiện, danh tính, quyền và phạm vi truy cập.

Đặc biệt với pull request từ fork hoặc mã bên ngoài:

- Chỉ cấp quyền đọc cần thiết cho job kiểm tra.
- Không cung cấp secret có thể triển khai hoặc ghi vào repository cho mã chưa được tin cậy.
- Tách job kiểm tra mã không đáng tin cậy khỏi job phát hành có quyền cao.
- Chỉ cấp credential khi đã xác minh đúng nguồn, đúng nhánh hoặc đúng danh tính được phép.
- Hạn chế quyền ghi và quyền truy cập artifact theo từng job.

Bảo vệ bí mật là nguyên lý CI/CD. Chiến lược nhánh chỉ cung cấp một phần ngữ cảnh về nơi thay đổi được đề xuất.

## 6. Tách kiểm tra tích hợp khỏi quyết định phát hành

Một pipeline có thể chia thành các giai đoạn có trách nhiệm rõ ràng:

1. **Validate:** xác minh nội dung thay đổi.
2. **Build:** tạo đầu ra từ commit xác định.
3. **Publish:** lưu artifact cùng metadata.
4. **Promote:** đưa cùng artifact sang môi trường tiếp theo sau khi đạt điều kiện.
5. **Verify:** xác nhận hành vi sau triển khai.

Chiến lược nhánh ảnh hưởng đến thời điểm các giai đoạn được kích hoạt, nhưng không cần quyết định lại nội dung của từng nguyên lý.

Ví dụ, pull request từ nhánh ngắn hạn và pull request từ nhánh release đều có thể chạy bộ kiểm tra nền tảng. Nhánh release có thể bổ sung kiểm tra tương thích hoặc kiểm tra hồi quy cho phiên bản đang duy trì. Nếu các điều kiện phát hành khác nhau, chúng nên được thể hiện thành policy riêng và có lý do rõ ràng.

Một nguyên tắc quan trọng là **build một lần, promote cùng artifact**. Sau khi artifact đã được tạo và xác minh, việc đưa nó từ staging đến production nên tham chiếu cùng digest hoặc checksum. Không cần tạo một nhánh Git mới chỉ để biểu diễn môi trường.

Nhánh staging hoặc production nếu được dùng như nhánh cấu hình hay nhánh triển khai riêng cần được đánh giá cẩn thận. Nếu nhóm chỉ dùng chúng để biểu diễn trạng thái môi trường, có nguy cơ tạo ra hai nguồn sự thật: Git branch và trạng thái triển khai thực tế. Môi trường nên được quản lý bằng cấu hình, chính sách và lịch sử deployment có truy vết.

## 7. Ví dụ cùng một nguyên lý CI/CD với hai chiến lược nhánh

Giả sử một dịch vụ Java cần chạy unit test, integration test, build JAR và container image, sau đó triển khai staging rồi production.

### 7.1. Trường hợp A: nhánh ngắn hạn và nhánh chính

Luồng làm việc:

1. Nhà phát triển tạo nhánh ngắn hạn từ nhánh chính.
2. Pull request chạy lint, unit test, kiểm tra dependency và build kiểm tra.
3. Khi các kiểm tra bắt buộc và review đạt, pull request được hợp nhất.
4. Pipeline trên nhánh chính tạo artifact có commit SHA và digest.
5. Artifact được triển khai lên staging và chạy smoke test.
6. Sau khi được phê duyệt hoặc thỏa chính sách tự động, cùng artifact được promote lên production.
7. Hệ thống theo dõi metrics, logs, traces và các chỉ số nghiệp vụ.

### 7.2. Trường hợp B: có nhánh develop và release

Luồng làm việc:

1. Nhánh tính năng được hợp nhất vào develop sau khi kiểm tra.
2. Pipeline kiểm tra tích hợp và tạo artifact phục vụ môi trường test.
3. Khi chọn phiên bản, nhóm tạo release branch.
4. Nhánh release chạy kiểm tra hồi quy, migration và tương thích cần thiết.
5. Khi phiên bản được chấp nhận, pipeline tạo artifact phát hành và lưu metadata.
6. Artifact được triển khai theo chính sách phát hành.
7. Bản sửa trên release branch được đưa trở lại các nhánh phát triển còn liên quan.

Hai mô hình khác nhau về cách thay đổi được điều phối và thời điểm chọn phiên bản. Cả hai vẫn có thể tuân thủ cùng nguyên lý: kiểm tra tự động, artifact bất biến, truy vết commit, bảo vệ bí mật, quality gate, xác minh sau triển khai và khả năng rollback.

### 7.3. Mã giả thể hiện ranh giới giữa chiến lược và pipeline

Ví dụ dưới đây là mã giả để minh họa ý tưởng, không phải cú pháp của một nền tảng CI cụ thể:

~~~yaml
events:
  pull_request:
    purpose: validate_change
    required_checks:
      - lint
      - unit_tests
      - dependency_scan

  integration_update:
    purpose: verify_integrated_state
    required_checks:
      - build
      - integration_tests

  release_request:
    purpose: prepare_release
    required_checks:
      - regression_tests
      - artifact_provenance
      - release_approval

pipeline:
  validate_change:
    run: true

  build:
    depends_on: validate_change
    record:
      - commit_sha
      - toolchain_version

  publish:
    depends_on: build
    output:
      - immutable_artifact
      - artifact_digest

  deploy:
    input: artifact_digest
    require:
      - target_environment_policy
      - authorization

  verify:
    depends_on: deploy
    checks:
      - health
      - smoke_tests
      - service_indicators
~~~

Phần events mô tả ý định của lần chạy. Phần pipeline mô tả các năng lực dùng chung. Trong triển khai thực tế, adapter của từng nền tảng sẽ ánh xạ pull request, push, tag hoặc yêu cầu triển khai vào các loại sự kiện này.

Nếu nhóm đổi từ nhánh ngắn hạn sang GitFlow, có thể thay đổi điều kiện kích hoạt và quy trình chọn phiên bản. Các bước kiểm tra, quản lý artifact, xác minh và truy vết vẫn được tái sử dụng.

## 8. Các quyết định về hợp nhất cần được đặt đúng chỗ

Chiến lược nhánh thường đi kèm quyết định về cách hợp nhất. Những quyết định này tác động đến lịch sử Git và khả năng truy vết, nhưng không thay thế kiểm tra CI.

| Cách hợp nhất | Đặc điểm | Cần cân nhắc |
|---|---|---|
| Merge commit | Giữ lại điểm hợp nhất và lịch sử nhánh | Lịch sử thể hiện quan hệ nhánh rõ nhưng có thể nhiều commit hợp nhất |
| Squash merge | Gộp thay đổi của pull request thành một commit | Lịch sử nhánh chính gọn; cần giữ liên kết pull request và commit nguồn |
| Rebase merge | Đặt các commit của nhánh lên nền mới rồi hợp nhất | Lịch sử tuyến tính hơn; commit SHA có thể thay đổi sau rebase |

Dù chọn cách nào, pipeline cần ghi lại định danh commit hoặc trạng thái mã thực sự được build. Khi dùng squash hoặc rebase, commit trên nhánh chính có thể khác commit ban đầu của nhánh công việc. Release metadata nên lưu đủ liên kết để truy ngược về pull request và các thay đổi liên quan.

Nhóm cũng cần quyết định:

- Có yêu cầu review trước khi hợp nhất không?
- Có yêu cầu nhánh phải cập nhật với nhánh đích không?
- Có dùng merge queue để kiểm tra hàng đợi hợp nhất không?
- Ai được phép bỏ qua kiểm tra bắt buộc trong trường hợp khẩn cấp?
- Những ngoại lệ có được ghi nhận và xem xét sau đó không?

Quy tắc hợp nhất là chính sách quản trị mã nguồn. Quality gate là cơ chế kiểm tra điều kiện. Hai phần phối hợp với nhau nhưng nên được mô tả riêng.

## 9. Quản lý phiên bản, tag và hotfix

Tag thường dùng để đánh dấu một commit đại diện cho phiên bản phát hành. Một quy trình phát hành có thể yêu cầu tag theo quy ước như v2.4.1, gắn với release record và artifact được tạo ra.

Để giữ khả năng truy vết:

- Tag phát hành cần trỏ đến commit đã được kiểm tra.
- Quyền tạo tag phát hành nên được giới hạn.
- Tag quan trọng nên được bảo vệ hoặc ký nếu chính sách yêu cầu.
- Pipeline cần ghi lại tag, commit SHA, artifact digest và kết quả kiểm tra.
- Không tái sử dụng hoặc di chuyển tag phát hành đã công bố mà không có quy trình xử lý rõ ràng.

Hotfix là thay đổi nhằm xử lý vấn đề khẩn cấp trên phiên bản đang chạy. Chiến lược nhánh cần quy định hotfix bắt đầu từ commit nào, ai review, kiểm tra tối thiểu nào phải chạy và bản sửa được đưa trở lại những nhánh nào.

Dù hotfix có thể cần quy trình rút gọn, nó vẫn phải có truy vết và xác minh. Việc khẩn cấp có thể thay đổi mức phê duyệt hoặc phạm vi kiểm tra theo chính sách; không nên làm mất thông tin về mã nguồn, artifact và người thực hiện.

Rollback cũng không đồng nghĩa với checkout một nhánh Git cũ rồi build lại tùy ý. Cách khôi phục đáng tin cậy thường triển khai lại artifact trước đó đã được lưu, xác định bằng digest, và xác minh khả năng tương thích dữ liệu. Nhánh giúp quản lý mã nguồn; artifact giúp xác định chính xác đầu ra cần triển khai.

## 10. Branch protection và quality gate có trách nhiệm khác nhau

Branch protection là tập hợp quy tắc ở hệ thống quản lý Git nhằm bảo vệ nhánh quan trọng. Ví dụ:

- Yêu cầu pull request thay vì push trực tiếp.
- Yêu cầu một hoặc nhiều lượt review.
- Bắt buộc các status check đã chọn phải thành công.
- Yêu cầu nhánh được cập nhật hoặc kiểm tra bằng merge queue.
- Hạn chế người được phép tạo tag, force push hoặc xóa nhánh.
- Yêu cầu xác minh chữ ký commit nếu chính sách áp dụng.

Quality gate là điều kiện đánh giá chất lượng của thay đổi hoặc artifact. Ví dụ:

- Unit test và integration test bắt buộc thành công.
- Không có lỗ hổng vượt ngưỡng chính sách.
- Artifact có provenance và metadata hợp lệ.
- Migration vượt qua kiểm tra.
- Smoke test và các chỉ số sau triển khai đạt yêu cầu.

Branch protection có thể bắt buộc status check của CI, nhưng không thay thế nội dung kiểm tra. Ngược lại, pipeline có thể báo xanh nhưng nếu nhánh không được bảo vệ, người dùng vẫn có thể hợp nhất thay đổi bằng đường khác mà bỏ qua quy trình.

Cần xác định rõ ai quản lý từng loại quy tắc, cách thay đổi chúng và cách ghi nhận ngoại lệ.

## 11. Những trường hợp cần thiết kế kỹ hơn

### 11.1. Monorepo và kiểm tra theo phạm vi thay đổi

Trong monorepo, một commit có thể chỉ ảnh hưởng một dịch vụ hoặc một nhóm thư mục. Path filter có thể giúp giảm thời gian chạy pipeline bằng cách chỉ thực hiện những kiểm tra liên quan.

Tuy nhiên, kiểm tra theo phạm vi thay đổi phải hiểu quan hệ phụ thuộc. Thay đổi thư viện dùng chung có thể ảnh hưởng nhiều dịch vụ dù tệp của chúng không thay đổi. Cấu hình filter thiếu chính xác có thể bỏ qua kiểm tra cần thiết.

Nếu nền tảng yêu cầu một status check bắt buộc nhưng workflow bị bỏ qua hoàn toàn do path filter, pull request có thể bị kẹt hoặc không có bằng chứng kiểm tra. Có thể dùng một job điều phối luôn trả kết quả và chỉ chạy các job chuyên biệt khi phù hợp.

### 11.2. Nhiều phiên bản được hỗ trợ song song

Khi tổ chức phải sửa lỗi cho nhiều phiên bản, release branch có thể cần thiết. Cần có chính sách:

- Phiên bản nào còn được hỗ trợ?
- Bản sửa được backport theo tiêu chí nào?
- Mỗi nhánh phiên bản chạy bộ kiểm tra nào?
- Artifact và tag được đặt tên ra sao?
- Khi một lỗi được sửa ở nhánh cũ, làm thế nào bảo đảm nhánh mới cũng có bản sửa?

Không nên để việc backport chỉ phụ thuộc vào trí nhớ của cá nhân. Có thể ghi nhận quan hệ giữa pull request, commit và release trong hệ thống quản lý thay đổi.

### 11.3. Pipeline chạy đồng thời và trạng thái lỗi thời

Nhiều commit có thể được đẩy liên tiếp lên cùng nhánh. Pipeline cũ có thể vẫn chạy khi pipeline mới đã bắt đầu.

Để tránh lãng phí và nhầm kết quả:

- Dùng commit SHA làm định danh đầu vào.
- Hủy hoặc đánh dấu lần chạy lỗi thời khi có phiên bản mới, nếu phù hợp.
- Không cho phép kết quả của commit cũ đáp ứng điều kiện cho commit mới.
- Quản lý concurrency cho job triển khai để tránh hai lần phát hành ghi đè lẫn nhau.
- Lưu lại phiên bản artifact được triển khai thực tế.

### 11.4. Cấu hình pipeline được thay đổi cùng mã nguồn

Khi pull request thay đổi cả ứng dụng và workflow, pipeline có thể tự thay đổi cách kiểm tra chính pull request đó. Vì vậy, cần bảo vệ những quy tắc nền tảng như quyền cấp cho job, secret, status check bắt buộc và quy tắc phát hành.

Các thay đổi workflow nhạy cảm nên được review bởi người có trách nhiệm. Một số tổ chức dùng reusable workflow hoặc pipeline template được quản lý tập trung để giảm nguy cơ mỗi repository tự nới lỏng chính sách.

## 12. Các sai lầm khi gộp chiến lược nhánh với nguyên lý CI/CD

| Sai lầm | Vì sao gây vấn đề | Cách xử lý |
|---|---|---|
| Cho rằng CI/CD bắt buộc phải dùng GitFlow | Một mô hình nhánh bị biến thành tiêu chuẩn chung | Mô tả nguyên lý CI/CD độc lập và chọn mô hình nhánh theo nhu cầu |
| Mỗi nhánh tương ứng một môi trường | Git branch và trạng thái triển khai trở thành hai nguồn sự thật | Dùng artifact, cấu hình môi trường và deployment record |
| Chỉ chạy CI trên main | Lỗi có thể được phát hiện sau khi hợp nhất | Kiểm tra thay đổi trước khi hợp nhất và xác minh trạng thái tích hợp |
| Dùng tên nhánh làm căn cứ duy nhất cấp quyền | Tên nhánh không chứng minh nguồn sự kiện hoặc danh tính đáng tin cậy | Kiểm tra event, actor, permission và ranh giới tin cậy |
| Nhánh release bỏ qua kiểm tra cơ bản | Phiên bản phát hành có thể thiếu chất lượng nền tảng | Giữ bộ kiểm tra nền, bổ sung kiểm tra theo rủi ro phiên bản |
| Hotfix chỉ sửa ở một nhánh | Lỗi có thể tái xuất hiện ở nhánh phát triển | Quy định backport hoặc forward merge và theo dõi đến khi hoàn tất |
| Mỗi môi trường build một lần riêng | Artifact được kiểm tra có thể khác artifact production | Build một lần, promote cùng digest |
| Rollback bằng cách build lại commit cũ | Đầu ra có thể khác do dependency hoặc toolchain thay đổi | Lưu và triển khai lại artifact đã biết là ổn định |
| Bỏ qua kiểm tra khi cần phát hành gấp | Ngoại lệ có thể trở thành đường phát hành không kiểm soát | Định nghĩa quy trình khẩn cấp, lưu bằng chứng và rà soát sau phát hành |

## 13. Lộ trình tách và chuẩn hóa thiết kế

Nếu pipeline hiện tại phụ thuộc nhiều vào tên nhánh, nhóm có thể cải tiến theo các bước sau.

**Bước 1: Liệt kê các điều kiện đang gắn với tên nhánh.** Tìm các rule như main, develop, release/*, hotfix/* trong workflow và xác định mục đích thực tế của từng rule.

**Bước 2: Phân loại điều kiện.** Xác định điều kiện nào thuộc kiểm tra thay đổi, điều kiện nào thuộc tạo artifact, điều kiện nào thuộc phát hành, và điều kiện nào chỉ là quy tắc quản trị nhánh.

**Bước 3: Định nghĩa các loại sự kiện.** Chuẩn hóa cách hiểu pull request, tích hợp, tag phát hành và yêu cầu triển khai. Mỗi loại sự kiện cần có đầu vào, quyền và kết quả mong đợi rõ ràng.

**Bước 4: Tách năng lực dùng chung.** Đưa lint, test, build, scan, publish, deploy và verify vào các job hoặc workflow có thể tái sử dụng. Tránh sao chép cùng một bộ kiểm tra cho từng nhánh.

**Bước 5: Đưa khác biệt hợp lệ vào policy.** Nếu release branch cần kiểm tra bổ sung, khai báo rõ lý do, người sở hữu và điều kiện áp dụng. Không giảm tiêu chuẩn nền chỉ vì nhánh có tên khác.

**Bước 6: Kiểm tra truy vết và quyền.** Xác nhận mỗi lần chạy ghi commit SHA, event, artifact digest và môi trường; kiểm tra job không nhận quyền quá mức.

**Bước 7: Thử với một luồng thay đổi thực tế.** Chạy từ pull request đến production hoặc môi trường phát hành tương đương, sau đó thử một tình huống lỗi để xác minh cơ chế dừng rollout hoặc khôi phục.

**Bước 8: Cập nhật tài liệu.** Mô tả nguyên lý CI/CD trong tài liệu CI/CD; mô tả nhánh, merge, tag, release và hotfix trong tài liệu quản lý mã nguồn. Tài liệu tích hợp chỉ cần nêu rõ điểm giao tiếp và liên kết đến chính sách liên quan.

## 14. Checklist thiết kế

**Ranh giới khái niệm**

- [ ] Nguyên lý CI/CD được mô tả độc lập với một mô hình nhánh cụ thể.
- [ ] Chiến lược nhánh có mục tiêu, phạm vi và chủ sở hữu rõ ràng.
- [ ] Chính sách phát hành được phân biệt với quy tắc hợp nhất mã nguồn.
- [ ] Tên nhánh không bị coi là tên môi trường triển khai.

**Tích hợp Git và pipeline**

- [ ] Các loại sự kiện Git cần xử lý đã được xác định.
- [ ] Pipeline nhận commit SHA và ngữ cảnh sự kiện rõ ràng.
- [ ] Pull request được kiểm tra trên trạng thái sẽ hợp nhất.
- [ ] Kết quả của lần chạy cũ không thể thay thế kết quả của commit mới.
- [ ] Các workflow dùng chung được tái sử dụng giữa các nhánh phù hợp.

**Quản lý nhánh và phát hành**

- [ ] Nhánh chính được bảo vệ bằng quy tắc phù hợp.
- [ ] Vòng đời nhánh feature, release và hotfix được quy định.
- [ ] Cách backport hoặc forward merge được xác định.
- [ ] Tag phát hành gắn với commit đã xác minh.
- [ ] Nhiều phiên bản đang hỗ trợ có chính sách bảo trì rõ ràng.

**Bảo mật và vận hành**

- [ ] Mã từ fork hoặc nguồn chưa tin cậy không nhận secret và quyền triển khai.
- [ ] Job có quyền tối thiểu cần thiết.
- [ ] Artifact có định danh bất biến và metadata truy vết.
- [ ] Cùng artifact được promote qua các môi trường.
- [ ] Có xác minh sau triển khai và phương án khôi phục.
- [ ] Ngoại lệ khẩn cấp được ghi nhận và rà soát.

## 15. Kết luận

Nguyên lý CI/CD xác định chất lượng và khả năng của đường đi từ thay đổi mã nguồn đến phần mềm đang chạy. Chiến lược nhánh xác định cách nhóm tổ chức công việc, tích hợp thay đổi và duy trì các dòng phiên bản. Cơ chế sự kiện Git và pipeline kết nối hai phần bằng cách chuyển ngữ cảnh thay đổi thành các bước kiểm tra, build, phát hành và xác minh.

Khi tách rõ các lớp này, nhóm có thể thay đổi mô hình nhánh mà vẫn giữ được các bảo đảm CI/CD. Pipeline tập trung vào đầu vào, đầu ra, chất lượng, quyền và khả năng truy vết; chính sách nhánh tập trung vào vòng đời mã nguồn và quy tắc hợp nhất. Nhờ vậy, quy trình phát hành dễ hiểu, dễ kiểm tra và thích ứng tốt hơn khi sản phẩm hoặc tổ chức thay đổi.
