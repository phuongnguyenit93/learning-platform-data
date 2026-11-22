# Postmortem và cải thiện độ tin cậy sau sự cố

Khi một dịch vụ trên Google Cloud gặp sự cố, ưu tiên đầu tiên của đội vận hành là bảo vệ người dùng và khôi phục dịch vụ. Sau khi hệ thống ổn định, công việc vẫn chưa kết thúc. Nhóm cần hiểu điều gì đã xảy ra, vì sao các lớp bảo vệ không ngăn được tác động, quyết định nào đã giúp khôi phục hệ thống và thay đổi nào sẽ làm giảm khả năng sự cố lặp lại. Một buổi họp chỉ để kể lại sự cố không tạo ra nhiều giá trị nếu kết quả không chuyển thành hành động có người chịu trách nhiệm và có cách xác minh.

Postmortem là tài liệu và quy trình học hỏi sau sự cố. Một postmortem tốt mô tả tác động, dòng thời gian, nguyên nhân và các yếu tố góp phần, cách phát hiện và ứng phó, điều đã làm tốt, điều cần cải thiện cùng các hành động tiếp theo. Cách tiếp cận không đổ lỗi giúp thành viên trao đổi trung thực về điều kiện hệ thống, công cụ, quy trình và quyết định đã dẫn đến kết quả. Mục tiêu là cải thiện hệ thống và cách làm việc để giảm rủi ro trong tương lai.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài này, chúng ta sử dụng các tín hiệu từ Cloud Monitoring, Cloud Logging, Error Reporting và Cloud Trace để phân tích sự cố, viết postmortem và chuyển bài học thành cải tiến độ tin cậy.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích mục đích và nguyên tắc của postmortem không đổ lỗi.
- Phân biệt khôi phục dịch vụ, phân tích nguyên nhân và cải tiến dài hạn.
- Xây dựng dòng thời gian sự cố từ metrics, logs, traces và lịch sử thay đổi.
- Phân tích nguyên nhân trực tiếp cùng các yếu tố góp phần mà không quy trách nhiệm cá nhân.
- Viết postmortem có phạm vi, tác động, phát hiện, ứng phó, bài học và hành động rõ ràng.
- Ưu tiên action items theo mức giảm rủi ro và công sức thực hiện.
- Kết nối kết quả postmortem với SLI, SLO, error budget, runbook và thực hành kiểm thử khả năng phục hồi.

## 1. Postmortem là gì và vì sao cần thực hiện?

Postmortem là bản ghi có cấu trúc về một sự cố đã xảy ra và những gì tổ chức học được từ sự cố đó. Tài liệu này giúp các nhóm có chung một cách hiểu dựa trên bằng chứng, tránh phụ thuộc vào trí nhớ hoặc một lời giải thích đơn giản. Postmortem cũng tạo đầu vào cho kế hoạch cải thiện độ tin cậy, quản lý rủi ro và chia sẻ kiến thức giữa các nhóm.

Một postmortem hữu ích trả lời các câu hỏi:

- Người dùng và hệ thống nào bị ảnh hưởng?
- Sự cố bắt đầu và kết thúc khi nào? Tác động thay đổi ra sao?
- Tín hiệu nào cho thấy hệ thống bất thường? Ai hoặc hệ thống nào phát hiện đầu tiên?
- Nhóm đã thực hiện những hành động nào để giảm tác động và khôi phục dịch vụ?
- Cơ chế nào đã hoạt động đúng? Cơ chế nào thiếu, chậm hoặc không đủ rõ?
- Điều kiện kỹ thuật, kiến trúc, vận hành và tổ chức nào cùng góp phần tạo ra sự cố?
- Những thay đổi nào có thể giảm xác suất, thời gian phát hiện hoặc mức độ ảnh hưởng của sự cố tương tự?

Postmortem không phải là cuộc họp tìm người chịu lỗi. Một hệ thống production thường có nhiều lớp phụ thuộc: mã nguồn, cấu hình, quyền IAM, mạng, cơ sở dữ liệu, pipeline, cơ chế triển khai, cảnh báo và quy trình trực vận hành. Một sự cố thường xuất hiện khi nhiều điều kiện cùng hội tụ. Chỉ tập trung vào hành động cuối cùng của một cá nhân sẽ bỏ qua các điều kiện hệ thống đã làm cho hành động đó có thể gây tác động.

### Sự cố nào nên có postmortem?

Tổ chức nên định nghĩa tiêu chí rõ ràng. Những tình huống thường đáng thực hiện postmortem gồm:

- Dịch vụ ngừng hoạt động hoặc suy giảm đáng kể so với SLO.
- Nhiều người dùng hoặc một nhóm khách hàng quan trọng không thể hoàn thành luồng nghiệp vụ.
- Sự cố kéo dài, tái diễn hoặc cần nhiều nhóm phối hợp xử lý.
- Mất dữ liệu, dữ liệu sai lệch, vi phạm bảo mật hoặc ảnh hưởng tuân thủ.
- Một lần triển khai, thay đổi cấu hình hoặc thao tác vận hành gây tác động production đáng kể.
- Một sự cố suýt gây ảnh hưởng lớn (near miss), dù chưa có người dùng bị ảnh hưởng.

Không phải mọi lỗi nhỏ đều cần một tài liệu dài. Với sự cố nhỏ, có thể dùng bản ghi ngắn hoặc mục học hỏi trong ticket. Với sự cố nghiêm trọng, cần quy trình đầy đủ, người phụ trách và theo dõi hành động đến khi hoàn tất.

## 2. Nguyên tắc postmortem không đổ lỗi

Postmortem không đổ lỗi (blameless postmortem) tập trung vào điều kiện và thông tin mà người tham gia có tại thời điểm ra quyết định. Khi một thao tác dẫn đến sự cố, hãy hỏi vì sao thao tác đó có vẻ hợp lý trong bối cảnh lúc ấy, công cụ nào đã cung cấp thông tin, giới hạn nào tồn tại và hệ thống có cơ chế bảo vệ nào.

Ví dụ, câu “kỹ sư triển khai sai cấu hình” không giải thích được vì sao cấu hình sai có thể đi qua pipeline. Một phân tích hữu ích hơn sẽ xem xét:

- Pipeline có kiểm tra schema và giá trị cấu hình không?
- Có môi trường staging phản ánh đủ production không?
- Có canary hoặc rollout theo tỷ lệ để giới hạn tác động không?
- Người triển khai có thể xem trước thay đổi và nhận biết rủi ro không?
- Cơ chế rollback có sẵn, đã được kiểm thử và đủ nhanh không?
- Cảnh báo có phát hiện tác động trước khi người dùng báo lỗi không?

Không đổ lỗi không có nghĩa là bỏ qua trách nhiệm. Nhóm vẫn cần người sở hữu hành động, tiêu chuẩn vận hành, kiểm soát truy cập và quyết định quản lý rủi ro. Khác biệt nằm ở chỗ postmortem không gán lỗi cá nhân thay cho việc cải thiện điều kiện hệ thống.

### Ngôn ngữ nên dùng

| Tránh viết | Nên viết |
|---|---|
| Kỹ sư X làm hỏng production | Cấu hình mới được áp dụng mà không có bước xác thực tương ứng |
| Đội vận hành không chú ý cảnh báo | Cảnh báo dùng ngưỡng không phản ánh tác động người dùng và không có người nhận rõ ràng |
| Nhà phát triển quên kiểm thử | Pipeline chưa có kiểm thử bao phủ tình huống phụ thuộc bị timeout |
| Người trực xử lý quá chậm | Runbook không chỉ rõ bước giảm tải an toàn; nhóm cần thời gian xác định hành động phù hợp |
| Không được phép mắc lỗi này | Thiết kế cần thêm rào chắn để một lỗi đơn lẻ không gây ảnh hưởng diện rộng |

Hãy mô tả hành động, điều kiện, tín hiệu và kết quả. Tránh suy đoán động cơ hoặc năng lực của người tham gia.

## 3. Vòng đời xử lý sự cố và thời điểm postmortem

Postmortem bắt đầu sau khi tình huống đã đủ ổn định để nhóm có thể phân tích. Trong lúc sự cố đang diễn ra, nhóm tập trung vào phát hiện, điều phối, giảm tác động và khôi phục. Việc ghi chú dòng thời gian có thể diễn ra song song, nhưng không nên để việc viết tài liệu làm chậm hoạt động ứng phó.

~~~mermaid
flowchart TD
    A["Phát hiện tín hiệu bất thường"]
    B["Khai báo incident và đánh giá mức độ"]
    C["Điều phối, truyền thông và phân công"]
    D["Giảm tác động / khôi phục dịch vụ"]
    E["Xác nhận hệ thống ổn định"]
    F["Thu thập bằng chứng và dựng timeline"]
    G["Phân tích nguyên nhân và yếu tố góp phần"]
    H["Viết postmortem và thống nhất action items"]
    I["Theo dõi, kiểm chứng và chia sẻ bài học"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

Một số tổ chức dùng vai trò incident commander để điều phối, operations lead để thực hiện thay đổi kỹ thuật và communications lead để cập nhật trạng thái cho người liên quan. Với nhóm nhỏ, một người có thể đảm nhận nhiều vai trò, nhưng cần nói rõ ai đang điều phối và ai có quyền quyết định thay đổi production.

### Phân biệt ba giai đoạn

**Khôi phục:** giảm hoặc ngăn tác động, đưa dịch vụ về trạng thái chấp nhận được. Có thể dùng rollback, tắt tính năng, chuyển traffic, tăng capacity hoặc tạm dừng một luồng xử lý.

**Phân tích:** dựng lại những gì đã xảy ra dựa trên log, metrics, traces, sự kiện triển khai và ghi chú của người ứng phó. Xác định nguyên nhân trực tiếp và các điều kiện góp phần.

**Cải tiến:** chuyển phát hiện thành thay đổi có thể kiểm chứng, ví dụ thêm kiểm tra trước khi deploy, cải thiện alert, giới hạn blast radius hoặc diễn tập rollback.

Một workaround khôi phục dịch vụ có thể là giải pháp tạm thời. Postmortem cần ghi rõ workaround đó có rủi ro hoặc giới hạn nào và hành động tiếp theo để xử lý nguyên nhân còn tồn tại.

## 4. Thu thập bằng chứng và dựng dòng thời gian

Trí nhớ của người tham gia có thể khác nhau, đặc biệt trong sự cố kéo dài hoặc nhiều nhóm phối hợp. Hãy dựng timeline từ nguồn dữ liệu có timestamp và phân biệt rõ sự kiện đã xác minh với giả thuyết.

### Nguồn dữ liệu trên Google Cloud

| Nguồn | Bằng chứng có thể cung cấp | Câu hỏi hỗ trợ |
|---|---|---|
| Cloud Monitoring | Request count, latency, error rate, CPU, memory, instance count, alert incident | Tác động bắt đầu khi nào và tăng ra sao? |
| Cloud Logging | Application logs, platform logs, structured events | Thành phần nào phát lỗi? Có mẫu lỗi chung nào? |
| Error Reporting | Nhóm exception và xu hướng lỗi | Lỗi ứng dụng nào tăng bất thường? |
| Cloud Trace | Trace và span của request | Thời gian bị tiêu tốn ở service hoặc dependency nào? |
| Cloud Audit Logs | Thay đổi IAM, cấu hình hoặc thao tác quản trị | Tài nguyên nào đã được thay đổi, bởi principal nào và qua method nào? |
| CI/CD và artifact registry | Lịch sử build, deploy, image digest, rollout | Bản phát hành nào xuất hiện trước sự cố? |
| Hệ thống nghiệp vụ | Số đơn hàng, giao dịch, message hoặc tác vụ thất bại | Người dùng và dữ liệu bị ảnh hưởng ở quy mô nào? |
| Incident notes | Quyết định, thao tác, người phụ trách và thời điểm | Nhóm đã thử gì và kết quả ra sao? |

Cloud Audit Logs hữu ích khi cần xác định thay đổi trên tài nguyên Google Cloud. Tuy nhiên, không phải mọi loại log đều được bật hoặc có cùng thời hạn lưu giữ. Hãy xác nhận phạm vi log hiện có, quyền truy cập và khoảng thời gian trước khi kết luận rằng không có thay đổi.

### Các bước dựng timeline

1. Xác định khoảng thời gian sự cố, bao gồm thời điểm bất thường đầu tiên và thời điểm tác động chấm dứt.
2. Chọn một múi giờ chuẩn, thường dùng UTC trong tài liệu sự cố; ghi rõ nếu nguồn dữ liệu dùng múi giờ khác.
3. Thu thập alert, metric, log, trace, audit log, deploy event và ghi chú ứng phó.
4. Ghi lại sự kiện quan trọng: thay đổi, cảnh báo, báo cáo người dùng, quyết định giảm tác động, rollback và xác nhận khôi phục.
5. Đối chiếu timestamp giữa các nguồn. Phân biệt thời điểm sự kiện xảy ra, thời điểm hệ thống nhận log và thời điểm người trực nhìn thấy thông báo.
6. Đánh dấu mục nào là sự kiện đã xác minh, mục nào là ước lượng hoặc giả thuyết.

Ví dụ timeline:

| Thời điểm (UTC) | Sự kiện | Nguồn | Mức chắc chắn |
|---|---|---|---|
| 09:02 | Revision mới bắt đầu nhận traffic | Cloud Run / deploy history | Đã xác minh |
| 09:05 | P95 latency tăng trên ngưỡng cảnh báo | Cloud Monitoring | Đã xác minh |
| 09:07 | Error rate của API tăng | Cloud Monitoring | Đã xác minh |
| 09:10 | Nhóm trực xác nhận incident | Incident notes | Đã xác minh |
| 09:16 | Traffic được chuyển về revision trước | Deploy history | Đã xác minh |
| 09:21 | Error rate trở về mức nền | Cloud Monitoring | Đã xác minh |
| 09:28 | Luồng tạo đơn hàng được kiểm tra thành công | Kiểm tra nghiệp vụ | Đã xác minh |

Không dùng timeline minh họa như dữ kiện của một sự cố thật. Trong postmortem thực tế, mỗi mốc cần có nguồn và độ chắc chắn tương ứng.

### Giữ bằng chứng có thể kiểm tra

Lưu truy vấn Logs Explorer, biểu đồ Monitoring, trace ID, revision hoặc image digest liên quan và liên kết đến ticket incident. Không sao chép payload chứa token, thông tin cá nhân hoặc dữ liệu khách hàng vào postmortem. Nếu cần bằng chứng nhạy cảm, tham chiếu đến kho lưu trữ có kiểm soát truy cập theo quy trình bảo mật của tổ chức.

## 5. Đánh giá tác động và phạm vi sự cố

Mức độ nghiêm trọng không chỉ được quyết định bởi thời gian hệ thống không hoạt động. Một sự cố có thể làm một phần người dùng gặp latency cao, một số giao dịch bị xử lý trùng hoặc dữ liệu không nhất quán dù API vẫn trả về HTTP 200.

Hãy mô tả tác động theo những chiều phù hợp:

- **Người dùng:** nhóm khách hàng, khu vực, tenant hoặc luồng nghiệp vụ bị ảnh hưởng.
- **Chức năng:** tính năng nào bị lỗi, suy giảm hoặc không thể sử dụng.
- **Thời gian:** thời điểm bắt đầu, kết thúc, khoảng gián đoạn và khoảng phục hồi một phần.
- **Quy mô:** số request, giao dịch, tài khoản hoặc tác vụ bị ảnh hưởng; dùng số liệu có nguồn.
- **Dữ liệu:** mất dữ liệu, trùng lặp, sai lệch hoặc chậm cập nhật nếu có.
- **Cam kết dịch vụ:** SLI/SLO nào bị vi phạm và error budget tiêu thụ bao nhiêu.
- **Tác động thứ cấp:** backlog, chi phí tăng, hỗ trợ khách hàng hoặc công việc thủ công phát sinh.

Phân biệt giữa **thời gian phát sinh sự cố**, **thời gian người dùng bị ảnh hưởng** và **thời gian đội vận hành nhận biết**. Ba khoảng này không nhất thiết trùng nhau. Ví dụ, một dependency có thể suy giảm từ 09:00, cảnh báo chỉ kích hoạt lúc 09:05 và nhóm phát hiện lúc 09:08. Sự khác biệt này giúp xác định cơ hội cải thiện detection và response.

Nếu không có số liệu chính xác, ghi rõ ước tính, phương pháp tính và giới hạn. Không tạo con số chỉ để báo cáo có vẻ đầy đủ.

## 6. Phân tích nguyên nhân và các yếu tố góp phần

Phân tích nguyên nhân cần giải thích chuỗi điều kiện dẫn đến tác động. “Một lần deploy gây lỗi” thường chỉ là điểm khởi đầu. Cần tìm hiểu thay đổi đó tương tác với dependency, cấu hình, traffic, dữ liệu và cơ chế bảo vệ như thế nào.

### Nguyên nhân trực tiếp và yếu tố góp phần

- **Nguyên nhân trực tiếp:** sự kiện hoặc trạng thái kỹ thuật ngay trước khi lỗi biểu hiện, ví dụ connection pool cạn khiến request không thể truy cập cơ sở dữ liệu.
- **Yếu tố góp phần:** điều kiện làm tăng khả năng xảy ra hoặc tăng mức độ tác động, ví dụ timeout quá dài, không có giới hạn concurrency, alert chỉ theo dõi CPU hoặc rollback chưa được tự động hóa.
- **Điều kiện nền:** đặc điểm kiến trúc hoặc quy trình lâu dài, ví dụ service dùng chung một database, kiểm thử staging không đại diện cho production hoặc quyền thay đổi cấu hình không có bước review.
- **Lỗ hổng phát hiện:** tín hiệu có tồn tại nhưng không đủ nhạy, không có cảnh báo, cảnh báo không có người nhận hoặc runbook thiếu hướng dẫn.

Không cần ép mọi sự cố vào một “root cause” duy nhất. Nhiều sự cố là kết quả của một chuỗi điều kiện độc lập. Hãy ghi rõ mức độ chắc chắn và những câu hỏi còn mở.

### Phân tích Five Whys

Five Whys là kỹ thuật đặt câu hỏi “vì sao” nhiều lần để đi từ biểu hiện đến điều kiện hệ thống sâu hơn. Đây là công cụ gợi mở, không phải quy tắc bắt buộc phải dừng ở đúng năm câu hỏi.

Ví dụ:

1. Vì sao request tạo đơn hàng timeout? Vì service không lấy được connection từ pool.
2. Vì sao pool hết connection? Vì nhiều request giữ connection lâu hơn bình thường.
3. Vì sao thời gian giữ connection tăng? Vì một truy vấn database chậm sau thay đổi schema.
4. Vì sao thay đổi schema tạo truy vấn chậm? Vì kế hoạch truy vấn production không được kiểm tra với lượng dữ liệu đại diện.
5. Vì sao kiểm tra không phát hiện? Vì pipeline chỉ chạy kiểm thử chức năng với dataset nhỏ và không có kiểm tra hiệu năng cho truy vấn quan trọng.

Kết quả gợi ý nhiều hành động: kiểm tra query plan, thêm performance test với dữ liệu đại diện, đặt timeout và giới hạn connection, đồng thời cảnh báo pool saturation. Chỉ ghi “cần cẩn thận hơn khi deploy” không giải quyết các điều kiện đã tạo ra sự cố.

### Cây nguyên nhân và bằng chứng

Có thể dùng sơ đồ nguyên nhân để mô tả nhiều yếu tố cùng góp phần:

~~~mermaid
flowchart TD
    A["Request tạo đơn hàng timeout"]
    B["Connection pool cạn"]
    C["Truy vấn database chậm"]
    D["Dataset staging nhỏ"]
    E["Thiếu performance check"]
    F["Timeout và pool limit chưa phù hợp"]
    G["Alert không theo dõi pool wait time"]
    A --> B
    B --> C
    C --> D
    D --> E
    B --> F
    A --> G
~~~

Sơ đồ này chỉ có giá trị khi mỗi quan hệ được hỗ trợ bằng bằng chứng. Nếu chưa xác nhận, đánh dấu là giả thuyết và ghi rõ cách kiểm tra.

### Tránh kết luận vượt quá bằng chứng

Không kết luận một thay đổi là nguyên nhân chỉ vì nó xảy ra gần thời điểm sự cố. Hãy so sánh với metrics trước và sau, revision hoặc image digest, cấu hình, logs, traces và các yếu tố bên ngoài. Nếu chưa xác định được nguyên nhân, postmortem vẫn có thể hoàn thành với kết luận “chưa xác định” cùng action item để thu thập tín hiệu hoặc kiểm thử giả thuyết.

## 7. Viết postmortem có cấu trúc

Một mẫu tài liệu nhất quán giúp người đọc nhanh chóng hiểu sự cố và tìm được hành động. Độ dài phụ thuộc mức độ phức tạp; ưu tiên thông tin có ích và bằng chứng có thể kiểm tra.

### Các phần nên có

| Phần | Nội dung |
|---|---|
| Tiêu đề và metadata | Tên incident, ngày, service, owner, mức độ nghiêm trọng |
| Tóm tắt | Một đoạn mô tả điều gì xảy ra và tác động chính |
| Impact | Người dùng, chức năng, dữ liệu, thời gian và SLO bị ảnh hưởng |
| Detection | Tín hiệu đầu tiên, thời gian phát hiện và khoảng trễ |
| Timeline | Sự kiện, quyết định, thao tác và nguồn bằng chứng |
| Root cause / contributing factors | Nguyên nhân trực tiếp, điều kiện góp phần và mức chắc chắn |
| Response | Biện pháp giảm tác động, khôi phục và kết quả |
| What went well | Cơ chế hoặc hành động đã giúp giảm tác động |
| What could be improved | Khoảng trống trong thiết kế, công cụ hoặc quy trình |
| Action items | Hành động cụ thể, owner, priority, due date và cách xác minh |
| Follow-up | Liên kết ticket, trạng thái, người duyệt và ngày xem xét lại |

### Mẫu postmortem

~~~markdown
# Postmortem: [Tên sự cố]

## Thông tin chung
- Incident ID:
- Service / project:
- Ngày xảy ra:
- Severity:
- Incident commander:
- Postmortem owner:
- Trạng thái tài liệu:

## Tóm tắt
[Điều gì xảy ra, tác động chính và cách khôi phục.]

## Tác động
- Người dùng / chức năng bị ảnh hưởng:
- Thời gian bắt đầu và kết thúc:
- Số liệu và nguồn:
- SLI / SLO / error budget:
- Tác động dữ liệu hoặc nghiệp vụ:

## Phát hiện
- Tín hiệu đầu tiên:
- Thời điểm phát hiện:
- Khoảng trễ phát hiện:
- Cảnh báo hoặc báo cáo người dùng:

## Timeline (UTC)
| Time | Event | Evidence |
|---|---|---|
| | | |

## Nguyên nhân và yếu tố góp phần
- Nguyên nhân trực tiếp:
- Yếu tố kỹ thuật:
- Yếu tố quy trình / tổ chức:
- Lỗ hổng phát hiện hoặc khôi phục:
- Giả thuyết còn mở:

## Ứng phó và khôi phục
- Biện pháp giảm tác động:
- Thời điểm khôi phục:
- Kiểm tra xác nhận:

## Điều đã làm tốt
- 

## Điều cần cải thiện
- 

## Action items
| Action | Risk reduced | Priority | Owner | Due date | Verification |
|---|---|---|---|---|---|
| | | | | | |

## Tài liệu liên quan
- Dashboard:
- Logs Explorer query:
- Trace:
- Change / deployment:
- Incident record:
~~~

Không đưa thông tin xác thực, payload nhạy cảm hoặc dữ liệu cá nhân vào mẫu. Dùng liên kết đến nguồn có quyền truy cập phù hợp.

## 8. Ví dụ: sự cố latency tăng sau khi triển khai Cloud Run

Tình huống giả định: một service orders-api chạy trên Cloud Run bắt đầu có latency cao và một phần request trả lỗi sau khi phát hành revision mới. Người dùng không thể hoàn tất một số thao tác tạo đơn hàng.

### Tóm tắt

Revision mới thay đổi cách truy vấn đơn hàng và làm tăng thời gian giữ connection tới Cloud SQL. Khi traffic tăng, connection pool đạt giới hạn. Request bắt đầu chờ connection, dẫn đến latency cao và timeout. Nhóm trực chuyển traffic về revision trước; sau khi rollback, error rate giảm và dịch vụ phục hồi.

### Dữ liệu cần xác minh

- Cloud Monitoring: request count, request latency, error count, instance count và các metric kết nối database nếu có.
- Cloud Logging: exception lấy connection, timeout và structured log theo request ID.
- Cloud Trace: thời gian của span gọi database so với các span khác.
- Cloud Run: revision, thời điểm chuyển traffic và cấu hình concurrency.
- Cloud SQL: connection count, query latency và tài nguyên database.
- CI/CD: commit, build, image digest, test result và người phê duyệt thay đổi.

### Timeline minh họa

| Thời điểm UTC | Sự kiện |
|---|---|
| 09:02 | Revision mới nhận traffic |
| 09:05 | P95 latency vượt ngưỡng |
| 09:07 | Error rate tăng, nhóm trực nhận alert |
| 09:10 | Incident được khai báo, nhóm xác nhận ảnh hưởng luồng tạo đơn hàng |
| 09:16 | Traffic chuyển về revision trước |
| 09:21 | Error rate giảm về baseline |
| 09:28 | Kiểm tra tạo đơn hàng thành công, incident được chuyển sang theo dõi |

### Nguyên nhân và yếu tố góp phần

- Truy vấn mới làm thời gian giữ connection tăng với dữ liệu production.
- Kiểm thử trước phát hành không có dataset đại diện và không kiểm tra tải truy vấn.
- Alert theo dõi error rate và latency nhưng chưa có tín hiệu sớm về connection pool saturation.
- Rollback có thể thực hiện được nhưng runbook chưa chỉ rõ điều kiện và người quyết định chuyển traffic.

### Action items có thể tạo

| Hành động | Loại cải tiến | Cách xác minh |
|---|---|---|
| Thêm performance test cho truy vấn quan trọng với dữ liệu đại diện | Preventive | Pipeline chạy test và chặn release khi vượt ngưỡng |
| Đặt timeout truy vấn và giới hạn connection phù hợp | Preventive / containment | Load test xác nhận pool không bị giữ vô hạn |
| Thêm dashboard cho connection count, pool wait và query latency | Detective | Dashboard hiển thị tín hiệu trước khi error rate tăng |
| Viết và diễn tập runbook rollback Cloud Run revision | Recovery | Diễn tập đo thời gian khôi phục |
| Rollout theo tỷ lệ và kiểm tra SLI trước khi tăng traffic | Blast radius reduction | Thử nghiệm canary có điều kiện dừng tự động |

Đây là ví dụ minh họa, không phải số liệu của một hệ thống thực. Trong incident thật, chỉ đưa vào tài liệu những kết luận đã được xác minh từ nguồn dữ liệu.

## 9. Biến bài học thành action items có thể hoàn thành

Action items là phần quyết định postmortem có tạo ra cải thiện hay không. Một hành động tốt mô tả thay đổi cụ thể, lý do, người sở hữu và bằng chứng để xác nhận hoàn thành.

Một action item nên có:

- **Hành động:** động từ rõ ràng và kết quả mong đợi.
- **Rủi ro được giảm:** giảm xác suất, giảm blast radius, phát hiện sớm hơn hoặc khôi phục nhanh hơn.
- **Priority:** mức ưu tiên dựa trên mức độ rủi ro và tác động.
- **Owner:** một người hoặc một vai trò chịu trách nhiệm điều phối hoàn thành.
- **Due date:** ngày cần hoàn tất hoặc ngày xem xét lại.
- **Verification:** test, metric, dashboard, diễn tập hoặc bằng chứng xác nhận.
- **Tracking link:** ticket hoặc work item để theo dõi trạng thái.

### Phân loại hành động

| Loại | Mục tiêu | Ví dụ |
|---|---|---|
| Preventive | Giảm khả năng sự cố xảy ra | Thêm kiểm tra schema hoặc performance test |
| Detective | Phát hiện nhanh hơn | Alert theo SLI và dashboard theo dependency |
| Containment | Giới hạn tác động | Rate limit, bulkhead, quota hoặc canary |
| Recovery | Khôi phục nhanh hơn | Rollback tự động, backup restore đã diễn tập |
| Learning | Cải thiện khả năng hiểu hệ thống | Runbook, tài liệu dependency và đào tạo trực ca |

Không phải mọi hành động đều cần thay đổi code. Một runbook rõ ràng, quyền truy cập khẩn cấp được chuẩn bị trước hoặc diễn tập phục hồi có thể giảm MTTR đáng kể.

### Viết action item cụ thể

| Mơ hồ | Cụ thể và có thể xác minh |
|---|---|
| Cải thiện monitoring | Tạo alert cho P95 latency của orders-api vượt SLO trong 10 phút và kiểm tra notification trong diễn tập |
| Tăng test | Thêm load test truy vấn đơn hàng với dataset đại diện vào pipeline trước release |
| Tối ưu database | Đo query plan, thêm index đã được xác minh và so sánh P95 query latency trước/sau |
| Cải thiện rollback | Viết runbook rollback revision, xác định người phê duyệt và diễn tập trong staging mỗi quý |
| Cẩn thận hơn khi deploy | Bật canary 5% traffic, kiểm tra error ratio và latency trước khi tăng traffic |

Tránh tạo hàng chục action item nhỏ chỉ để thể hiện mức độ hoạt động. Chọn số lượng hành động có khả năng hoàn thành, ưu tiên những thay đổi giảm rủi ro lớn nhất. Các hành động chưa thể làm ngay cần có owner và thời điểm xem xét lại; không để chúng biến mất sau khi cuộc họp kết thúc.

## 10. Ưu tiên theo SLO và error budget

SLO giúp nhóm định nghĩa mức độ tin cậy cần cung cấp. SLI là phép đo phản ánh trải nghiệm hoặc kết quả của người dùng, ví dụ tỷ lệ request thành công hoặc latency của request hợp lệ. Error budget là phần lỗi cho phép theo mục tiêu SLO trong một khoảng thời gian.

Sau sự cố, hãy kiểm tra:

- SLI nào bị ảnh hưởng và mức độ vi phạm.
- Error budget tiêu thụ trong sự cố và xu hướng của toàn kỳ.
- Sự cố có làm tốc độ tiêu thụ error budget tăng nhanh không.
- Có cần tạm dừng phát hành rủi ro cao để tập trung cải thiện độ tin cậy không.
- Action item nào giúp giảm khả năng vi phạm SLO tiếp theo.

Ví dụ, nếu SLO yêu cầu 99,9% request hợp lệ thành công trong một tháng, error budget tương ứng là 0,1% số request trong kỳ. Một sự cố làm nhiều request thất bại có thể tiêu thụ phần lớn ngân sách trong thời gian ngắn. Nhóm cần dùng số liệu thực tế để tính mức tiêu thụ; không lấy thời gian downtime làm đại diện cho mọi SLI nếu SLO được định nghĩa theo request.

Error budget không phải chỉ số để trừng phạt đội phát triển. Nó là công cụ cân bằng tốc độ thay đổi và độ tin cậy. Khi ngân sách bị tiêu thụ nhanh, nhóm có cơ sở để ưu tiên sửa lỗi, giảm rủi ro phát hành và đầu tư vào resilience.

## 11. Cải thiện hệ thống sau sự cố

Những cải tiến bền vững thường tập trung vào nhiều lớp thay vì chỉ sửa dòng code gây lỗi.

### Thiết kế để giới hạn blast radius

- Dùng canary hoặc progressive delivery để một thay đổi mới chỉ ảnh hưởng một phần traffic ban đầu.
- Dùng feature flag để tắt nhanh tính năng có vấn đề mà không cần phát hành lại toàn bộ service.
- Tách dependency quan trọng bằng timeout, retry có giới hạn, circuit breaker và bulkhead phù hợp.
- Áp dụng quota, rate limit và concurrency limit để tải đột biến không làm sụp đổ toàn hệ thống.
- Thiết kế retry có exponential backoff và jitter; tránh retry đồng loạt làm tăng tải lên dependency đang lỗi.
- Dùng queue và dead-letter handling cho tác vụ bất đồng bộ khi nghiệp vụ cho phép.

### Cải thiện khả năng phát hiện

- Đo SLI gần với trải nghiệm người dùng thay vì chỉ theo dõi CPU hoặc memory.
- Đặt alert có người nhận, ngưỡng và hướng dẫn hành động rõ ràng.
- Gắn correlation ID và trace context vào log để rút ngắn điều tra.
- Theo dõi dependency, queue age, connection pool, saturation và lỗi theo từng service.
- Kiểm tra cảnh báo bằng diễn tập hoặc mô phỏng lỗi, không chỉ xác nhận cấu hình đã được tạo.

### Cải thiện khả năng phục hồi

- Chuẩn bị rollback và xác định điều kiện kích hoạt.
- Kiểm thử backup restore, failover và disaster recovery theo lịch.
- Đặt timeout và health check phù hợp.
- Xác minh ứng dụng khởi động lại, xử lý message trùng và phục hồi từ dependency gián đoạn.
- Duy trì runbook cho các thao tác khẩn cấp, kèm quyền truy cập đã chuẩn bị.

### Cải thiện quy trình thay đổi

- Kiểm tra cấu hình và policy trước khi áp dụng.
- Yêu cầu review phù hợp với mức độ rủi ro.
- Dùng immutable artifact và ghi lại image digest hoặc revision.
- Tự động kiểm tra sau deploy bằng synthetic checks hoặc smoke tests.
- Dừng rollout khi SLI suy giảm hoặc alert quan trọng kích hoạt.

Không có một cơ chế nào loại bỏ mọi sự cố. Mục tiêu là làm cho lỗi dễ phát hiện, tác động được giới hạn và dịch vụ có thể phục hồi trong thời gian chấp nhận được.

## 12. Theo dõi hiệu quả của postmortem

Đừng đo chất lượng postmortem bằng số trang hoặc số action item. Hãy đánh giá xem tổ chức có giảm rủi ro và cải thiện khả năng ứng phó hay không.

Một số chỉ số có thể theo dõi:

| Chỉ số | Ý nghĩa | Cách diễn giải |
|---|---|---|
| Time to detect (TTD) | Thời gian từ lúc tác động bắt đầu đến lúc phát hiện | TTD giảm có thể cho thấy monitoring tốt hơn |
| Time to acknowledge | Thời gian từ cảnh báo đến khi có người xác nhận | Đánh giá routing và quy trình trực |
| Time to mitigate | Thời gian đến khi tác động được giảm đáng kể | Đánh giá khả năng containment |
| Time to restore | Thời gian đến khi dịch vụ phục hồi | Đánh giá rollback và recovery |
| SLO attainment | Mức đạt SLO trong kỳ | Đánh giá trải nghiệm người dùng |
| Repeat incident rate | Tỷ lệ sự cố tái diễn cùng nhóm nguyên nhân | Đánh giá hiệu quả cải tiến |
| Action completion rate | Tỷ lệ action items hoàn thành đúng hạn | Đánh giá việc theo dõi sau postmortem |
| Action effectiveness | Hành động có làm giảm tín hiệu rủi ro không | Kiểm chứng qua test, metric hoặc diễn tập |

Các chỉ số thời gian cần có định nghĩa thống nhất. Ví dụ, time to mitigate có thể tính đến lúc error rate giảm, trong khi time to restore tính đến lúc tất cả luồng nghiệp vụ được xác nhận hoạt động. Ghi rõ mốc bắt đầu và kết thúc để so sánh giữa các incident có ý nghĩa.

Repeat incident rate cần phân loại theo service, failure mode hoặc contributing factor. Hai sự cố cùng service nhưng nguyên nhân khác nhau không nhất thiết là tái diễn cùng một vấn đề.

## 13. Tổ chức buổi review và chia sẻ bài học

Buổi review nên có facilitator giúp giữ cuộc thảo luận dựa trên bằng chứng và không chuyển thành tranh luận cá nhân. Người tham gia có thể gồm người ứng phó, chủ sở hữu service, đại diện SRE, database hoặc network team và người phụ trách nghiệp vụ nếu tác động liên quan.

Gợi ý agenda:

1. Nhắc lại mục tiêu buổi review và nguyên tắc không đổ lỗi.
2. Xác nhận phạm vi và tác động của incident.
3. Đi qua timeline dựa trên bằng chứng.
4. Phân tích nguyên nhân trực tiếp và các yếu tố góp phần.
5. Xác định điều đã làm tốt và điều cần cải thiện.
6. Ưu tiên action items, chỉ định owner và cách xác minh.
7. Xác định người cập nhật tài liệu và thời điểm review lại.

Nếu có bất đồng về nguyên nhân, ghi lại các giả thuyết cùng bằng chứng còn thiếu. Không cần ép nhóm thống nhất một câu chuyện khi dữ liệu chưa đủ. Có thể tạo action item để thêm telemetry hoặc thực hiện thử nghiệm tái hiện.

Postmortem cần được chia sẻ với những nhóm có thể học được từ sự cố. Với sự cố bảo mật hoặc dữ liệu nhạy cảm, tuân thủ phạm vi truy cập và quy trình xử lý riêng; bản chia sẻ rộng có thể loại bỏ chi tiết nhạy cảm nhưng vẫn giữ bài học kỹ thuật cần thiết.

## 14. Bài tập thực hành: viết postmortem cho sự cố Cloud Run

Giả sử orders-api triển khai revision mới. Sau vài phút, P95 latency tăng, error rate tăng và một số request tạo đơn hàng thất bại. Nhóm trực rollback revision và dịch vụ trở lại bình thường. Một số thông tin ban đầu:

- Cloud Monitoring cho thấy latency bắt đầu tăng ngay sau thời điểm revision mới nhận traffic.
- Cloud Logging ghi nhận lỗi chờ connection database.
- Cloud Trace cho thấy span truy vấn database kéo dài hơn baseline.
- Lịch sử deploy xác nhận image digest mới đã được phát hành.
- Nhóm chưa xác định liệu truy vấn mới, cấu hình pool hay tải tăng là yếu tố chính.

Thực hiện các nhiệm vụ:

1. Viết tóm tắt incident trong 3–5 câu, phân biệt điều đã xác minh và điều còn là giả thuyết.
2. Tạo timeline với thời điểm deploy, tín hiệu metric, log đầu tiên, thời điểm khai báo incident, rollback và xác nhận khôi phục.
3. Liệt kê tác động tới người dùng và các SLI có thể bị ảnh hưởng. Nếu chưa có số liệu, ghi rõ cần thu thập dữ liệu nào.
4. Dùng Five Whys để phát triển ít nhất hai nhánh giả thuyết về query latency và connection pool.
5. Xác định một nguyên nhân trực tiếp và ít nhất ba yếu tố góp phần, nhưng chỉ kết luận khi có bằng chứng.
6. Viết action items thuộc các nhóm preventive, detective, containment và recovery.
7. Với mỗi action item, ghi owner, priority, due date và cách xác minh.
8. Chọn một metric hoặc SLI để đánh giá xem hành động đã giảm rủi ro hay chưa.
9. Tổ chức buổi review ngắn theo agenda ở trên và ghi lại câu hỏi chưa được giải đáp.

### Tiêu chí đánh giá

- Timeline có timestamp, nguồn bằng chứng và phân biệt sự kiện với giả thuyết.
- Tác động được mô tả từ góc nhìn người dùng và có số liệu hoặc giới hạn rõ.
- Phân tích giải thích được điều kiện hệ thống, không quy lỗi cho cá nhân.
- Action items cụ thể, có owner và cách kiểm chứng.
- Kết quả được kết nối với SLO, alert, runbook hoặc cải tiến kiến trúc.

## 15. Checklist postmortem

- [ ] Incident có phạm vi và owner rõ ràng.
- [ ] Tóm tắt mô tả sự kiện, tác động và trạng thái khôi phục.
- [ ] Tác động được định lượng hoặc ghi rõ phần chưa có số liệu.
- [ ] Timeline dùng múi giờ thống nhất và có nguồn bằng chứng.
- [ ] Metrics, logs, traces, audit logs và lịch sử thay đổi đã được xem xét khi phù hợp.
- [ ] Nguyên nhân trực tiếp và yếu tố góp phần được phân biệt.
- [ ] Giả thuyết chưa xác minh được ghi rõ.
- [ ] Ngôn ngữ không đổ lỗi và tập trung vào điều kiện hệ thống.
- [ ] Điều làm tốt và điều cần cải thiện đều được ghi nhận.
- [ ] Action items có owner, priority, due date và verification.
- [ ] Hành động được liên kết với SLI, SLO hoặc mục tiêu giảm rủi ro.
- [ ] Tài liệu và bằng chứng không chứa secret hoặc dữ liệu nhạy cảm.
- [ ] Postmortem được chia sẻ với đúng nhóm và có lịch theo dõi.
- [ ] Action items được xem lại sau khi hoàn tất để xác nhận hiệu quả.

## Câu hỏi tự kiểm tra

**1. Mục tiêu chính của postmortem không đổ lỗi là gì?**

Hiểu các điều kiện kỹ thuật và tổ chức đã dẫn đến sự cố, sau đó cải thiện hệ thống để giảm xác suất, mức độ tác động hoặc thời gian phục hồi.

**2. Vì sao không nên chỉ ghi “lỗi do deploy”?**

Vì deploy thường chỉ là một sự kiện trong chuỗi nguyên nhân. Cần phân tích thay đổi tương tác với traffic, dependency, kiểm thử, rollout, alert và rollback như thế nào.

**3. Cloud Monitoring và Cloud Logging hỗ trợ postmortem ra sao?**

Monitoring cung cấp xu hướng và mức độ tác động theo thời gian; Logging cung cấp sự kiện chi tiết để xác định thành phần và lỗi cụ thể. Cloud Trace bổ sung thời gian và quan hệ giữa các thao tác.

**4. Action item tốt cần có những thông tin nào?**

Hành động cụ thể, rủi ro được giảm, mức ưu tiên, owner, hạn hoàn thành, cách xác minh và liên kết theo dõi.

**5. Error budget giúp nhóm quyết định điều gì sau sự cố?**

Nó cho biết mức tiêu thụ ngân sách lỗi và hỗ trợ cân bằng phát hành tính năng với đầu tư cải thiện độ tin cậy.

**6. Khi chưa xác định được root cause, có nên trì hoãn postmortem không?**

Không nhất thiết. Có thể ghi rõ điều đã xác minh, giả thuyết còn mở và action items để thu thập dữ liệu hoặc kiểm tra giả thuyết.

## Tài liệu tham khảo

- [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [Google SRE Workbook: Postmortem](https://sre.google/workbook/postmortem/)
- [Google SRE: Managing Incidents](https://sre.google/workbook/managing-incidents/)
- [Google Cloud: Incident response](https://cloud.google.com/architecture/framework/operational-excellence/incident-response)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://docs.cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://docs.cloud.google.com/trace/docs)
- [Cloud Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit)

## Kết luận

Postmortem giúp tổ chức chuyển một sự cố đã qua thành hiểu biết và thay đổi có thể kiểm chứng. Bằng cách mô tả tác động, dựng timeline từ nguồn dữ liệu, phân tích nguyên nhân cùng các yếu tố góp phần và giữ cách tiếp cận không đổ lỗi, nhóm có thể nhìn thấy những điểm yếu trong kiến trúc, monitoring và quy trình. Action items cần có owner, mức ưu tiên và tiêu chí xác minh; sau đó được kết nối với SLI, SLO, error budget, runbook và kiểm thử khả năng phục hồi. Độ tin cậy tăng lên khi các bài học sau sự cố thực sự làm cho hệ thống dễ phát hiện, giới hạn tác động và khôi phục hơn.
