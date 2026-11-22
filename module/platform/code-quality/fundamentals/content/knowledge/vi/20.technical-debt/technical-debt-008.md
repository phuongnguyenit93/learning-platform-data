# Chấp nhận, theo dõi hoặc xử lý nợ theo điều kiện rõ ràng

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích **nợ kỹ thuật (technical debt)** là gì và vì sao nó không đồng nghĩa với mọi đoạn code xấu, mọi bug hoặc mọi tính năng chưa làm.
2. Phân biệt ba quyết định có chủ đích: **chấp nhận nợ**, **theo dõi nợ** và **xử lý nợ**, dựa trên rủi ro, tác động, bằng chứng và thời hạn.
3. Xác định các **điều kiện chấp nhận**, **chỉ số quan sát**, **ngưỡng kích hoạt xử lý (trigger)**, **người chịu trách nhiệm** và **phương án quay lui** cho một khoản nợ cụ thể.
4. Ưu tiên việc xử lý nợ theo chi phí thay đổi tương lai, độ tin cậy, bảo mật, hiệu năng và mục tiêu sản phẩm, thay vì chỉ theo cảm giác “mã trông chưa đẹp”.
5. Thiết kế bước giảm thiểu rủi ro có kiểm thử trong Java khi chưa thể làm lại toàn bộ, và nhận ra khi biện pháp tạm thời không còn đủ.
6. Ghi một quyết định nợ kỹ thuật đủ rõ để người khác có thể đánh giá lại khi bối cảnh thay đổi.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Nợ kỹ thuật liên quan trực tiếp tới cả ba: một lối tắt giúp giao hàng hôm nay có thể khiến thay đổi ngày mai khó hơn; một kiến trúc phức tạp gây ra nhiều lỗi vận hành có thể tiêu tốn thời gian và sự tin cậy của người dùng.

**Thông điệp chính:** Không phải khoản nợ nào cũng phải xóa ngay. Nhưng nợ được **chấp nhận một cách có trách nhiệm** cần có phạm vi, điều kiện và người sở hữu. Nợ được **theo dõi một cách có trách nhiệm** cần có tín hiệu và ngưỡng dẫn đến hành động. Nợ được **xử lý một cách có trách nhiệm** cần có mục tiêu, cách kiểm chứng và đánh đổi rõ ràng.

## 1. Nợ kỹ thuật là gì?

**Nợ kỹ thuật** là cách diễn đạt những đánh đổi kỹ thuật hiện tại có thể làm **tăng chi phí hoặc rủi ro của công việc trong tương lai**. Ví dụ:

- Chọn cách tích hợp trực tiếp với một dịch vụ ngoài thay vì xây một adapter vì chưa biết có nhà cung cấp thứ hai hay không.
- Giữ một lớp quá nhiều trách nhiệm trong giai đoạn chuyển đổi, làm các thay đổi sau phải chạm tới nhiều logic không liên quan.
- Tạm sử dụng báo cáo đồng bộ vì dữ liệu hiện còn ít, dù biết cần phân trang hoặc xử lý nền khi quy mô tăng.
- Chưa có test tích hợp cho một adapter cũ, khiến mỗi lần nâng phiên bản thư viện phải kiểm tra thủ công và khó xác định hồi quy.
- Hai luồng nghiệp vụ có bản sao của một chính sách, làm tăng khả năng cập nhật sót khi chính sách thay đổi.

Ẩn dụ “nợ” nhấn mạnh **chi phí duy trì hoặc thay đổi** có thể tiếp tục xuất hiện, tương tự “lãi”. Tuy nhiên, đây **không phải khoản vay tài chính với lãi suất cố định**. Mức “lãi” phụ thuộc vào tần suất thay đổi, số người sử dụng, khối lượng dữ liệu, mức tải, kiến trúc và khả năng dự đoán tương lai.

Một lối tắt có thể gần như không gây tác động nếu đoạn code không đổi trong thời gian dài. Ngược lại, cùng lối tắt ấy có thể trở thành rào cản lớn khi tính năng bỗng được mở rộng cho nhiều khách hàng hoặc chịu yêu cầu pháp lý mới.

### Ba điều dễ nhầm với nợ kỹ thuật

| Hiện tượng | Có mặc nhiên là nợ kỹ thuật không? | Cách nhìn phù hợp |
| --- | --- | --- |
| Một **bug hiện hữu** làm sai số tiền thanh toán | Không nên chỉ gọi là nợ để trì hoãn | Trước hết là vấn đề đúng đắn, phải xử lý theo mức độ ảnh hưởng |
| Một **tính năng mới** khách hàng chưa được cung cấp | Không mặc nhiên | Thuộc backlog sản phẩm; có thể chịu ảnh hưởng của nợ hiện có |
| Mã ít đẹp theo sở thích cá nhân | Không tự động | Cần bằng chứng về khó hiểu, rủi ro hoặc chi phí thay đổi |
| Không có test cho đường xử lý quan trọng | Có thể là nợ với rủi ro cao | Xem mức ảnh hưởng, thay đổi thường xuyên, khả năng phát hiện hồi quy |
| Chọn cách làm đơn giản để kiểm chứng nhu cầu | Có thể là nợ có chủ đích, hoặc chỉ là lựa chọn phù hợp | Ghi giả định và điều kiện phải xem xét lại |
| Hệ thống đang chạy sai hoặc có lỗ hổng khai thác thực tế | Không nên lấy nhãn “technical debt” để giảm ưu tiên | Xử lý theo quy trình sự cố/bảo mật tương ứng |

Điều kiện quan trọng là **có sự đánh đổi cụ thể giữa lợi ích hiện tại và chi phí/rủi ro kỹ thuật trong tương lai**, chứ không chỉ “thiếu thứ gì đó”.

## 2. Vì sao không nên xử lý mọi khoản nợ ngay lập tức?

Một quyết định kỹ thuật luôn có **chi phí cơ hội**. Dành hai tuần loại bỏ abstraction chưa đẹp nghĩa là hai tuần đó không được dùng cho lỗi đang ảnh hưởng khách hàng, nâng cấp bảo mật hoặc một nhu cầu sản phẩm quan trọng.

Một số khoản nợ:
- Nằm trong tính năng sắp bị loại bỏ.
- Gây khó chịu nhưng ít thay đổi, ít người phụ thuộc.
- Chỉ trở nên đáng kể khi tải hoặc số biến thể tăng.
- Có thể kiểm soát tạm bằng giới hạn, test và quan sát.
- Cần dữ liệu thật để xác định kiến trúc đích; viết lại quá sớm có thể chọn sai hướng.

Ở chiều ngược lại, có khoản nợ **không thể chờ**:
- Dẫn tới lỗi tính tiền hoặc mất dữ liệu ở luồng quan trọng.
- Làm lộ dữ liệu hoặc bỏ qua kiểm tra quyền.
- Gây timeout/sự cố nghiêm trọng đã lặp lại.
- Khiến một thay đổi bắt buộc không thể thực hiện an toàn.
- Đã vượt giới hạn vận hành được xác nhận.

Vì thế, câu hỏi hữu ích không phải “Có nợ không?” mà là:

> **Với bằng chứng và bối cảnh hiện tại, nên chấp nhận, tiếp tục theo dõi hay xử lý khoản nợ này; điều gì sẽ khiến quyết định thay đổi?**

## 3. Ba quyết định khác nhau

### 3.1. Chấp nhận nợ có điều kiện

**Chấp nhận** nghĩa là nhóm biết hạn chế, đã đánh giá rủi ro và **chủ động không xử lý ngay**. Quyết định này không đồng nghĩa bỏ quên.

Chấp nhận có thể hợp lý khi:
- Phạm vi ảnh hưởng nhỏ và được xác định.
- Rủi ro được kiểm soát bằng biện pháp hiện có.
- Tác động khi chưa sửa thấp hơn chi phí cơ hội của sửa ngay.
- Hạn chế không vi phạm điều kiện bắt buộc về an toàn, bảo mật hoặc đúng đắn.
- Có sự kiện hoặc thời điểm để **đánh giá lại** nếu điều kiện thay đổi.

Ví dụ: một công cụ nội bộ chỉ được phép xử lý tối đa vài trăm dòng dữ liệu, được kiểm soát đầu vào và không nằm trong luồng giao dịch quan trọng. Việc chuyển ngay sang pipeline phân tán có thể là đầu tư vượt nhu cầu. Nhóm có thể chấp nhận cách xử lý đơn giản trong giới hạn đã công bố.

**Chấp nhận không có điều kiện** như “để đó khi nào rảnh sửa” không giúp người tiếp theo biết khi nào cần hành động.

### 3.2. Theo dõi nợ theo tín hiệu

**Theo dõi** phù hợp khi rủi ro phụ thuộc vào điều chưa chắc chắn, ví dụ tăng trưởng tải, số lần thay đổi chính sách hoặc tần suất lỗi.

Theo dõi có nghĩa:
- Xác định **tín hiệu quan sát được**.
- Đặt **ngưỡng hoặc sự kiện kích hoạt**.
- Giao người xem tín hiệu và ra quyết định.
- Quy định hành động khi ngưỡng xuất hiện.
- Đặt thời điểm đánh giá định kỳ nếu tín hiệu chưa đủ.

Ví dụ, API xuất báo cáo hiện đủ nhanh với tối đa 500 dòng/khách. Nhóm biết việc trả toàn bộ danh sách sẽ thành vấn đề khi khách lớn hơn, nhưng chưa có bằng chứng cần thiết kế xuất nền ngay. Có thể theo dõi **số dòng trên mỗi báo cáo, p95/p99, bộ nhớ và lỗi timeout**. Nếu một trong các điều kiện đã xác nhận xảy ra, chuyển sang kế hoạch phân trang hoặc xuất bất đồng bộ.

**Một dashboard không có chủ sở hữu hoặc không có ngưỡng hành động** chỉ là quan sát thụ động, chưa phải quản lý nợ có hiệu quả.

### 3.3. Xử lý nợ

**Xử lý** nghĩa là thực hiện thay đổi giảm hoặc loại bỏ chi phí/rủi ro của khoản nợ. Tùy trường hợp, hành động có thể là:
- Refactor để tách trách nhiệm và giảm coupling.
- Viết characterization tests, contract tests hoặc integration tests cho ranh giới thiếu bảo vệ.
- Chuyển sang API có hợp đồng rõ hơn.
- Di chuyển dữ liệu theo migration an toàn.
- Bổ sung giới hạn tài nguyên, timeout hoặc khả năng chống trùng.
- Thay đổi kiến trúc có kiểm chứng để đáp ứng tải đã tăng.
- Loại bỏ hoàn toàn phần code cũ không còn được sử dụng.

“Xử lý nợ” **không nhất thiết là viết lại toàn bộ**. Nhiều khi bước nhỏ có kiểm thử giải quyết phần gây rủi ro lớn nhất, trong khi viết lại hệ thống từ đầu sẽ mở thêm nhiều rủi ro không cần thiết.

### Bảng so sánh nhanh

| Hành động | Điều kiện phù hợp | Việc bắt buộc phải làm rõ | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Chấp nhận** | Rủi ro có thể kiểm soát, lợi ích xử lý ngay chưa đủ | Lý do, phạm vi, giới hạn, thời điểm xem lại | Ghi “accepted” rồi không ai chịu trách nhiệm |
| **Theo dõi** | Rủi ro có thể tăng, cần dữ liệu để quyết định | Metric/sự kiện, ngưỡng, người theo dõi, phản ứng | Chỉ tạo dashboard, không gắn trigger |
| **Xử lý** | Rủi ro đã đáng kể, chặn thay đổi hoặc nghĩa vụ bắt buộc | Mục tiêu, giải pháp, thử nghiệm, rollback, tiêu chí hoàn tất | Refactor diện rộng thiếu test và không đo kết quả |

## 4. Điều kiện rõ ràng gồm những gì?

Một quyết định nợ nên đủ cụ thể để người khác không phải hỏi lại “đến lúc nào thì sửa?”.

Một bộ điều kiện hữu ích có thể gồm:

1. **Phạm vi:** đoạn code, API, luồng nghiệp vụ, dữ liệu và nhóm người dùng liên quan.
2. **Giả định hiện tại:** số người dùng, kích thước dữ liệu, mức tải hoặc số biến thể chính sách.
3. **Rủi ro đã nhận diện:** điều gì có thể sai, hậu quả là gì và ai bị ảnh hưởng.
4. **Biện pháp hiện tại:** test, giới hạn đầu vào, rollback, cảnh báo, kiểm tra quyền hoặc bước vận hành thủ công.
5. **Tín hiệu:** metric, sự kiện, số lần thay đổi hoặc lỗi nào cho thấy giả định không còn đúng.
6. **Ngưỡng kích hoạt:** giá trị cụ thể hoặc sự kiện bắt buộc phải tái đánh giá/triển khai.
7. **Chủ sở hữu:** ai có trách nhiệm xem tín hiệu và quyết định; không chỉ “team” vô danh.
8. **Thời điểm:** lần xem xét tiếp theo hoặc hạn phải xử lý trước một mốc đã biết.
9. **Phương án xử lý:** hướng thay đổi dự kiến, phạm vi cần test và phụ thuộc cần phối hợp.
10. **Điều kiện đóng:** bằng chứng gì cho thấy rủi ro đã được giảm đủ, không chỉ ticket đã được chuyển trạng thái Done.

Không phải mọi khoản nợ nhỏ đều cần tài liệu dài. Nhưng **nợ có rủi ro lớn cần điều kiện rõ hơn**. Một ghi chú ngắn mà ai cũng có thể áp dụng đúng thường tốt hơn một biểu mẫu dài thiếu người duy trì.

### Ví dụ điều kiện chưa đạt

> “Code export chưa tối ưu. Theo dõi khi có thời gian. Sau này viết lại.”

Vấn đề:
- Không chỉ ra nghẽn CPU, bộ nhớ, I/O hay lỗi.
- Không có mức tải hoặc số lượng dữ liệu hiện tại.
- Không có metric, trigger, owner.
- “Viết lại” chưa có tiêu chí xác nhận.

### Ví dụ điều kiện có thể hành động

> “Endpoint xuất lịch sử đơn đang trả toàn bộ dữ liệu trong bộ nhớ; hiện được giới hạn tối đa 2.000 dòng để bảo vệ tài nguyên. Theo dõi số dòng yêu cầu và p95. Khi một tenant thường xuyên vượt 1.500 dòng, p95 vượt 400 ms trong ba ngày đo có đủ mẫu, hoặc có yêu cầu sản phẩm cần xuất trên 2.000 dòng, tạo công việc chuyển sang xuất bất đồng bộ hoặc phân trang trước khi mở rộng hạn mức. Chủ sở hữu: nhóm Orders; xem lại mỗi tháng. Không tăng hard limit mà chưa có load test và kế hoạch vận hành.”

Các con số là **giả định để học**. Hệ thống thật phải đặt ngưỡng theo SLO, bộ nhớ, workload và yêu cầu sản phẩm; không áp dụng máy móc mức 2.000 dòng hoặc 400 ms.

## 5. Phân biệt chấp nhận rủi ro với bỏ qua lỗi bắt buộc phải sửa

Nợ kỹ thuật có thể được thương lượng về thời điểm **chỉ khi tổ chức còn quyền lựa chọn**. Một lỗi nghiêm trọng trong đường thanh toán, mất dữ liệu, vi phạm phân quyền hoặc rủi ro bảo mật đã được xác định không nên bị trì hoãn bằng cách đổi nhãn thành “nợ chấp nhận được”.

Cần phân biệt:

| Tình huống | Cách xử lý ưu tiên |
| --- | --- |
| Có bằng chứng đơn hàng bị tính sai tiền | Xử lý sự cố/độ đúng đắn trước, phân tích nguyên nhân và phòng ngừa |
| Người dùng xem được đơn của tài khoản khác | Xử lý lỗ hổng phân quyền theo mức độ nghiêm trọng và quy trình bảo mật |
| Một thuật toán O(n²) nhưng dữ liệu đã được giới hạn nhỏ, không có SLO bị vi phạm | Có thể chấp nhận hoặc theo dõi với giới hạn và trigger |
| Thiếu test quanh một module ít thay đổi | Đánh giá theo tác động, tần suất thay đổi và khả năng hồi quy |
| Thư viện đã hết hỗ trợ hoặc có lỗ hổng đã biết | Ưu tiên theo mức rủi ro bảo mật và chính sách cập nhật, không chỉ độ đẹp mã |
| API cũ còn được đối tác sử dụng | Lên kế hoạch tương thích/migration, không xóa vô điều kiện |
| Tính năng dự kiến bị loại bỏ trong một tháng | Có thể giới hạn sửa, nhưng vẫn bảo đảm an toàn cho thời gian còn sử dụng |

**Đúng đắn và an toàn của người dùng không phải “phần lãi có thể tạm bỏ qua” nếu hậu quả hiện hữu.** Khi có yêu cầu pháp lý, tuân thủ hoặc kiểm soát bắt buộc, mức chấp nhận và thẩm quyền phê duyệt phải theo chính sách của tổ chức, không do một lập trình viên tự quyết.

## 6. Đánh giá rủi ro theo xác suất, hậu quả và khả năng phát hiện

Không thể ưu tiên mọi khoản nợ chỉ bằng **số dòng code xấu**. Hãy xem:

- **Hậu quả nếu rủi ro xảy ra:** mất dữ liệu, tính sai tiền, outage, ảnh hưởng một phần hay toàn bộ người dùng.
- **Khả năng xảy ra:** điều kiện nào khiến hạn chế bộc lộ; tải, thay đổi nghiệp vụ, sự kiện hiếm.
- **Khả năng phát hiện trước khi ảnh hưởng:** test, metric, canary, alert, log, đối soát.
- **Khả năng phục hồi:** có rollback, replay, backup, bù trừ hay không.
- **Tần suất thay đổi:** module được sửa mỗi tuần hay gần như không đổi.
- **Tính lan truyền:** thay một nơi có ảnh hưởng nhiều API, job hoặc service không.
- **Chi phí trì hoãn:** chờ thêm một quý có làm migration khó hơn vì dữ liệu phát sinh không?
- **Chi phí xử lý:** công sức, nguy cơ hồi quy, phụ thuộc vào nhóm khác và vận hành.

### Ma trận đánh giá định tính

| Ảnh hưởng khi lỗi xảy ra | Khả năng xảy ra thấp | Khả năng xảy ra cao |
| --- | --- | --- |
| **Thấp** | Thường có thể chấp nhận, xem lại định kỳ | Theo dõi hoặc xử lý nếu chi phí lặp tích tụ |
| **Cao** | Cần biện pháp kiểm soát mạnh và quyết định theo risk owner | Ưu tiên xử lý sớm, có thể cần xử lý ngay |

Ma trận chỉ giúp **đặt câu hỏi**, không thay thế đánh giá chuyên môn. Rủi ro bảo mật xác suất khó ước lượng nhưng hậu quả rất lớn có thể vẫn cần hành động ngay. Nếu rủi ro đã nằm trong danh sách bắt buộc khắc phục, không nên hạ ưu tiên chỉ vì gán nhãn “ít khả năng”.

### Tránh chấm điểm chính xác giả

Một bảng chấm “xác suất 3, tác động 4, tổng 12” có thể giúp so sánh nhanh, nhưng **12 không phải đơn vị rủi ro tuyệt đối**. Hai khoản nợ cùng điểm có thể có hậu quả rất khác: một gây mất dữ liệu không phục hồi, một làm chậm một màn hình ít người dùng.

Nếu dùng điểm, nên ghi **tiêu chí và lý do**, kèm thông tin không thể hiện bằng điểm số như nghĩa vụ bảo mật, deadline bên ngoài hoặc phụ thuộc của dự án khác.

## 7. Chi phí “lãi nợ”: khi nợ làm thay đổi ngày càng khó

Một chỉ dấu mạnh của nợ là **thời gian xử lý một thay đổi tương tự ngày càng tăng** vì phải đi vòng qua hạn chế cũ.

Ví dụ, quy tắc giảm giá bị sao chép trong:
- Checkout online.
- Batch import đơn từ đối tác.
- Hóa đơn.
- Báo cáo đối soát.

Mỗi lần chính sách đổi, nhóm phải tìm đủ bốn nơi, phối hợp release và xác minh chênh lệch. Khi có thêm mobile checkout, bản sao thứ năm xuất hiện. **Số nơi phải sửa** tăng, còn nguy cơ bỏ sót cũng tăng.

Có thể quan sát các tín hiệu:
- Thời gian từ yêu cầu đến merge/triển khai tăng ở khu vực đó.
- Cùng một module thường bị sửa ở nhiều file cho một quy tắc.
- Số lỗi hồi quy lặp lại sau thay đổi tương tự.
- PR phải có nhiều bước sửa thủ công hoặc các checklist phụ thuộc trí nhớ.
- Độ phủ test và thời gian kiểm chứng khiến nhóm ngại sửa.
- Onboarding mất nhiều thời gian vì các ranh giới trách nhiệm không rõ.

Đây là các dấu hiệu **liên quan**, không tự chứng minh mọi độ trễ đều do nợ. Thời gian xử lý còn phụ thuộc review, yêu cầu chưa rõ, hạ tầng CI hoặc số người làm. Hãy điều tra nguyên nhân trước khi quyết định refactor.

## 8. Khi nào nên chấp nhận nợ? Một ví dụ có giới hạn

Giả sử một công cụ báo cáo nội bộ hiện chỉ có 30 người dùng, dữ liệu khách hàng lớn nhất khoảng 500 đơn và chỉ xuất theo yêu cầu. Công cụ dùng cách đơn giản: tải các dòng đơn rồi tạo báo cáo trong bộ nhớ.

**Chấp nhận có điều kiện** có thể hợp lý nếu:
- Báo cáo không xử lý dữ liệu vượt quyền.
- Có giới hạn số dòng và kích thước để tránh cạn bộ nhớ.
- Kết quả được xác nhận đúng trên trường hợp hiện có.
- Lượng dữ liệu và độ trễ được quan sát.
- Mức phục vụ hiện tại đáp ứng nhu cầu đã xác nhận.
- Có hành vi rõ ràng nếu giới hạn bị vượt, thay vì tiếp tục cấp phát vô hạn.
- Có trigger và kế hoạch chuyển sang phân trang/async khi nhu cầu tăng.

Quyết định **không hợp lý** nếu báo cáo này đang xử lý thanh toán quan trọng, bị timeout thường xuyên hoặc lượng dữ liệu đã nhiều hơn năng lực hiện có.

Chấp nhận nợ không có nghĩa cố giấu giới hạn khỏi người dùng. Nếu xuất tối đa 2.000 dòng, API phải **nói rõ giới hạn**, cung cấp thông điệp phù hợp hoặc dẫn sang cách xuất khác. Không được âm thầm cắt còn 2.000 dòng rồi báo “đã xuất đầy đủ”.

## 9. Ví dụ Java 17: giảm rủi ro trước khi trả hết nợ

Phần này minh họa cách **chấp nhận một kiến trúc đơn giản trong phạm vi an toàn**. Ta có endpoint lấy lịch sử đơn cho một khách hàng. Hiện hệ thống chưa có luồng xuất bất đồng bộ; tạm thời chỉ cho phép số dòng nhỏ.

**Điều kiện nghiệp vụ giả định:**
- Mã khách hàng do tầng ứng dụng cung cấp sau kiểm tra quyền. Ví dụ không thực hiện authorization.
- Repository có hợp đồng **trả về tối đa số dòng được yêu cầu**, theo thứ tự ổn định phù hợp để sau này phân trang.
- Trả toàn bộ lịch sử trong giới hạn **2.000 dòng**; nếu còn nhiều hơn, **từ chối rõ ràng**, không cắt dữ liệu và báo thành công.
- Đối với quá nhiều dòng, hợp đồng tạm thời yêu cầu gọi phương thức khác hoặc liên hệ quy trình xuất dữ liệu; hướng lâu dài là xuất nền/phân trang.

### 9.1. Hợp đồng repository giới hạn dữ liệu trả về

~~~java
import java.util.List;
import java.util.Objects;

record OrderRow(String orderId, long totalVnd) {
    OrderRow {
        Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank() || totalVnd < 0) {
            throw new IllegalArgumentException("invalid order row");
        }
    }
}

@FunctionalInterface
interface OrderHistoryReader {
    /**
     * Trả tối đa limit dòng theo thứ tự ổn định của hợp đồng.
     * Với limit lớn hơn tổng số dòng hiện có, trả toàn bộ.
     */
    List<OrderRow> findFirst(String customerId, int limit);
}

final class SynchronousReportLimitExceeded extends RuntimeException {
    SynchronousReportLimitExceeded(String message) {
        super(message);
    }
}

final class SynchronousOrderReportService {
    static final int MAX_SYNCHRONOUS_ROWS = 2_000;
    private final OrderHistoryReader reader;

    SynchronousOrderReportService(OrderHistoryReader reader) {
        this.reader = Objects.requireNonNull(reader, "reader");
    }

    List<OrderRow> loadAllWithinLimit(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId is required");
        }

        // Đọc thêm 1 dòng để phát hiện kết quả bị vượt giới hạn.
        // Repository phải thực thi LIMIT ở tầng dữ liệu.
        List<OrderRow> rows = Objects.requireNonNull(
                reader.findFirst(customerId, MAX_SYNCHRONOUS_ROWS + 1),
                "reader returned null");

        if (rows.size() > MAX_SYNCHRONOUS_ROWS) {
            throw new SynchronousReportLimitExceeded(
                    "Use a paginated or asynchronous report");
        }
        return List.copyOf(rows);
    }
}
~~~

**Vì sao cách này tốt hơn tải vô hạn?**

1. **Có giới hạn rõ** thay vì cấp phát danh sách không kiểm soát.
2. **Đọc giới hạn + 1** giúp biết có thêm dữ liệu mà không trả một phần và khẳng định đó là toàn bộ.
3. Dữ liệu trả về được **copy** vào danh sách không sửa đổi, giảm khả năng caller thay đổi kết quả sau khi load.
4. Lỗi vượt giới hạn được **biểu diễn riêng**, để tầng API có thể chuyển thành phản hồi phù hợp theo hợp đồng sản phẩm.
5. Quy tắc giới hạn có tên **MAX_SYNCHRONOUS_ROWS**, giúp quan sát và đánh giá khi nhu cầu đổi.

**Đây vẫn là giải pháp tạm thời**, không phải lời khuyên xuất toàn bộ dữ liệu trong một request mãi mãi. Nó không xử lý bài toán dữ liệu lớn; nó đặt **lan can an toàn** và mô tả giới hạn để nhóm có thời gian chuyển đổi.

### 9.2. Giới hạn phải được thực thi ở tầng đọc dữ liệu

Nếu implementation của **OrderHistoryReader** làm như sau:

~~~java
// SAI nếu database có hàng triệu dòng:
// đọc tất cả rồi mới cắt danh sách.
List<OrderRow> all = databaseLoadAll(customerId);
return all.subList(0, Math.min(limit, all.size()));
~~~

thì lớp service vẫn có thể chịu tổn thất bộ nhớ/I/O trước khi kiểm tra giới hạn. Adapter thật phải giới hạn số dòng **ngay trong câu truy vấn hoặc cơ chế truy xuất**. Đồng thời phải có **thứ tự ổn định** khi chọn những dòng đầu tiên để tránh kết quả không dự đoán được.

Một ví dụ khái niệm với SQL:

~~~sql
SELECT order_id, total_vnd
FROM orders
WHERE customer_id = ?
ORDER BY created_at, order_id
LIMIT ?;
~~~

Tên bảng và cú pháp là minh họa; khả năng hỗ trợ **LIMIT**, tham số hóa và kế hoạch truy vấn tùy DBMS. Trước khi triển khai thật, cần kiểm tra chỉ mục theo bộ lọc/thứ tự, phân quyền, giới hạn response và kịch bản dữ liệu thay đổi đồng thời.

**Không nên** tin rằng phép gọi **findFirst(...)** luôn nhanh chỉ vì có LIMIT. Nếu database phải sort một tập rất lớn trước khi áp LIMIT hoặc thiếu index phù hợp, p99 vẫn có thể cao.

### 9.3. Unit test cho giới hạn và phản hồi rõ ràng

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;

class SynchronousOrderReportServiceTest {

    @Test
    void loadsSmallReportWithBoundedQuery() {
        OrderHistoryReader reader = (customerId, limit) -> {
            assertEquals("C-01", customerId);
            assertEquals(2_001, limit);
            return List.of(new OrderRow("O-001", 120_000L));
        };

        var service = new SynchronousOrderReportService(reader);

        List<OrderRow> result = service.loadAllWithinLimit("C-01");

        assertEquals(1, result.size());
        assertEquals("O-001", result.get(0).orderId());
    }

    @Test
    void refusesToClaimOversizedReportIsComplete() {
        OrderHistoryReader reader = (customerId, limit) ->
                Collections.nCopies(
                        limit, new OrderRow("O-001", 120_000L));

        var service = new SynchronousOrderReportService(reader);

        assertThrows(
                SynchronousReportLimitExceeded.class,
                () -> service.loadAllWithinLimit("C-01"));
    }

    @Test
    void rejectsMissingCustomerId() {
        OrderHistoryReader unusedReader =
                (customerId, limit) -> List.of();

        var service = new SynchronousOrderReportService(unusedReader);

        assertThrows(
                IllegalArgumentException.class,
                () -> service.loadAllWithinLimit(" "));
    }
}
~~~

Ví dụ sử dụng **JUnit Jupiter (JUnit 5)**. Test kiểm tra hợp đồng tạm thời: giới hạn truy vấn được chuyển đúng, báo cáo nhỏ được trả đầy đủ và báo cáo quá lớn không bị âm thầm cắt dữ liệu.

Nhưng test dùng stub **không chứng minh SQL adapter thật áp LIMIT**, không kiểm tra memory, số bản ghi lớn hoặc p99. Những rủi ro ấy cần integration test với database đại diện và load test theo tập dữ liệu thật.

**Một giới hạn là biện pháp giảm thiểu rủi ro; bản thân giới hạn cũng cần test và quan sát.** Khi nhu cầu đã vượt giới hạn, không nên âm thầm tăng hằng số từ 2.000 lên 20.000 chỉ để “làm xanh” yêu cầu mới mà không đánh giá tài nguyên.

## 10. Từ ví dụ Java tới quyết định nợ có điều kiện

Nhóm có thể ghi nhận khoản nợ như sau:

| Thành phần quyết định | Nội dung minh họa |
| --- | --- |
| **ID** | DEBT-EXPORT-017 |
| **Phạm vi** | Endpoint báo cáo lịch sử đơn; hiện xử lý đồng bộ |
| **Mùi mã/rủi ro** | Tập kết quả lớn làm tăng bộ nhớ, serialization, thời gian phản hồi |
| **Lợi ích khi tạm giữ** | Không đầu tư luồng xuất nền khi nhu cầu còn nhỏ |
| **Hợp đồng hiện tại** | Xuất đầy đủ đến 2.000 dòng; trên giới hạn trả lỗi có hướng dẫn |
| **Biện pháp kiểm soát** | Giới hạn ở adapter, test biên, timeout, metric rows/latency/error |
| **Dấu hiệu theo dõi** | Số dòng mỗi request, p95/p99, lỗi vượt giới hạn, heap/GC |
| **Trigger xem xét** | Tenant thường xuyên trên 1.500 dòng; hoặc p95 vượt 400 ms ba ngày liên tiếp với đủ mẫu |
| **Trigger xử lý bắt buộc** | Sản phẩm cam kết xuất hơn 2.000 dòng; lỗi cạn bộ nhớ/timeout nghiêm trọng; SLO bị vi phạm |
| **Hướng xử lý** | Pagination ổn định hoặc xuất bất đồng bộ có job ID, quyền và trạng thái |
| **Người chịu trách nhiệm** | Chủ sở hữu dịch vụ Orders/Reporting được phân công cụ thể |
| **Thời điểm đánh giá** | Hằng tháng và trước mỗi đợt mở rộng khách lớn |
| **Tiêu chí đóng** | Đáp ứng yêu cầu xuất lớn với số đo, test và phương án phục hồi đạt |

**Các ngưỡng là ví dụ**, không phải khuyến nghị phổ quát. Với môi trường thật, cần xác định “thường xuyên” là số lần/khoảng thời gian nào, “đủ mẫu” là bao nhiêu request và p95 được tính trên cửa sổ nào. Nếu không, trigger có thể bị diễn giải tùy ý.

### Ba trạng thái quyết định trong tình huống này

- **Chấp nhận** khi chưa có nhu cầu xuất lớn, số liệu tốt, giới hạn được truyền đạt và rủi ro được kiểm soát.
- **Theo dõi** khi số lượng đơn đang tăng và chưa rõ lúc nào cần mở rộng; metric phải được xem theo lịch và có ngưỡng.
- **Xử lý** trước khi ra mắt tính năng xuất lớn, hoặc khi giới hạn/SLO đã bị vượt và ảnh hưởng thực tế xuất hiện.

Không nên nhầm “theo dõi” với “chờ tới lúc xảy ra outage”. Trigger nên có **ngưỡng cảnh báo sớm** để nhóm còn thời gian thay đổi an toàn.

## 11. Trigger tốt phải gắn với hành động

Một trigger có giá trị khi nó trả lời cả **khi nào** và **sẽ làm gì**.

| Trigger yếu | Vì sao yếu? | Trigger có thể hành động |
| --- | --- | --- |
| “Khi hệ thống chậm” | Không định nghĩa chậm, ở đâu, khi nào | “p95 endpoint export vượt SLO đã thống nhất trong 3 ngày đo đủ mẫu → owner mở hạng mục cải tiến và xác định điểm nghẽn” |
| “Khi có nhiều user” | Không biết mức tải là bao nhiêu | “Số job đồng thời đạt 80% giới hạn vận hành trong cửa sổ cao điểm → chạy load test và điều chỉnh thiết kế” |
| “Khi sửa lại code này” | Không có phạm vi hay mức thay đổi | “Khi thêm nhà cung cấp thanh toán thứ hai → tách adapter và contract test trước khi tích hợp” |
| “Khi bug nhiều” | Không có định nghĩa | “Cùng một loại lỗi hồi quy xuất hiện lần thứ hai trong 1 quý → phân tích vùng test thiếu và lập kế hoạch xử lý” |
| “Trước release” | Không rõ release nào | “Trước mốc mở rộng cho 100 tenant theo kế hoạch được phê duyệt → hoàn thành test tải và phân tách workload” |
| “Khi có thời gian” | Không có người chịu trách nhiệm | “Trong kỳ hoạch định tháng tới, owner đánh giá lại nợ và đưa quyết định mới vào backlog” |

Một trigger có thể đến từ **metric**, **sự kiện nghiệp vụ**, **mốc phát hành**, **quy định mới** hoặc **sự thay đổi kiến trúc dự kiến**. Không nhất thiết mọi trigger đều là một con số.

### Ngưỡng nên có hai cấp khi cần

Với các rủi ro tăng dần, hữu ích khi phân biệt:

- **Ngưỡng cảnh báo sớm:** bắt đầu điều tra, đo, thiết kế giải pháp hoặc dành thời gian trong kế hoạch.
- **Ngưỡng hành động bắt buộc:** không tiếp tục mở rộng hoặc triển khai một tính năng cho đến khi biện pháp an toàn được chứng minh.

Ví dụ:
- **1.500 dòng**: xem xét trước khi xuất hiện nhiều khách vượt giới hạn.
- **2.000 dòng**: luồng đồng bộ hiện tại không được giả vờ xử lý đầy đủ; cần phương án khác theo hợp đồng.

Nếu hai ngưỡng đặt quá gần nhau, nhóm không đủ thời gian xử lý. Nếu quá xa, có thể mất chi phí tối ưu không cần thiết. Chọn bằng dữ liệu và thời gian thực hiện công việc, không chỉ bằng trực giác.

## 12. Theo dõi nợ khác theo dõi mọi chỉ số hệ thống

Nên chọn **metric có liên hệ nhân quả hợp lý với rủi ro** của khoản nợ.

Ví dụ một lớp có nhiều trách nhiệm sẽ không được giải quyết chỉ bằng đo CPU. Các chỉ số sát vấn đề hơn có thể là:
- Số lý do thay đổi khiến lớp bị sửa.
- Mức độ nhiều module phải chạm tới cho một yêu cầu nhỏ.
- Thời gian hoàn thành thay đổi tương tự.
- Số lỗi hồi quy phát sinh từ lớp đó.
- Số lớp/test bị ảnh hưởng bởi một chỉnh sửa.
- Độ khó kiểm thử một quy tắc riêng mà không khởi tạo toàn bộ hạ tầng.

Ngược lại, với nợ về hiệu năng, các chỉ số như **p95/p99, throughput, queue wait, connection pool wait, allocation và tỷ lệ lỗi** có thể phù hợp hơn.

### Ghi nhận quan sát có bối cảnh

Một số liệu **p95 = 600 ms** không đủ nếu không biết:
- Endpoint hoặc tác vụ nào.
- Cửa sổ đo bao lâu, số mẫu bao nhiêu.
- Tải đến và tỷ lệ lỗi.
- Phân bố kích thước dữ liệu/khách hàng.
- Cấu hình instance và phụ thuộc đang chạy.
- Giá trị SLO nào cần so sánh.

Tương tự, “một PR sửa 18 file” có thể do một refactor hợp lý, không nhất thiết do nợ. Hãy xem **lý do thay đổi** và các hệ quả thực sự.

**Không tạo dashboard chỉ để có dashboard.** Metric chỉ tạo giá trị khi có người dùng để quyết định và khả năng thực hiện hành động phù hợp.

## 13. Lập sổ theo dõi nợ kỹ thuật không biến thành kho TODO vô hạn

Một **debt register** hoặc backlog nợ kỹ thuật nên có đủ dữ liệu để xem lại, không chứa mọi lời phàn nàn về phong cách.

Mẫu ghi nhận ngắn:

~~~text
ID:
Tiêu đề:
Phạm vi và chủ sở hữu:
Quyết định hiện tại: ACCEPT / MONITOR / REPAY
Bằng chứng: [test, incident, đo tải, lịch sử thay đổi]
Rủi ro nếu giữ nguyên:
Giới hạn/biện pháp bảo vệ hiện tại:
Điều kiện còn được phép chấp nhận:
Metric hoặc sự kiện cần theo dõi:
Trigger và hành động tương ứng:
Ngày xem lại / mốc phụ thuộc:
Phương án xử lý và kiểm chứng:
Liên kết tới ticket, ADR hoặc tài liệu liên quan:
~~~

Không phải mọi trường đều cần cho một khoản nợ rất nhỏ. Với nợ ở luồng thanh toán, quyền hoặc dữ liệu, nên ghi rõ hơn để tránh người mới hiểu sai.

### Trạng thái nên biểu diễn quyết định thật

Ví dụ một workflow đơn giản:

~~~mermaid
flowchart TD
    A[Phát hiện hạn chế] --> B[Đánh giá rủi ro và bằng chứng]
    B --> C{Cần xử lý ngay?}
    C -- Có --> D[Ưu tiên xử lý và kiểm chứng]
    C -- Chưa --> E{Rủi ro có thể tăng theo điều kiện?}
    E -- Có --> F[Theo dõi metric, trigger, owner]
    E -- Không đáng kể trong phạm vi --> G[Chấp nhận có giới hạn và ngày xem lại]
    F --> H{Trigger xảy ra?}
    H -- Có --> D
    H -- Chưa --> I[Đánh giá định kỳ]
    I --> B
    G --> J{Giả định thay đổi hoặc đến kỳ xem lại?}
    J -- Có --> B
    D --> K[Đóng khi có bằng chứng đáp ứng]
~~~

Một khoản nợ **được chấp nhận** vẫn có thể **được theo dõi**. Ba nhãn trên là **quyết định ưu tiên/hành động chủ đạo**, không phải ba loại kỹ thuật loại trừ tuyệt đối. Khi bối cảnh thay đổi, trạng thái cần được cập nhật.

### Tránh tồn đọng không còn ý nghĩa

Định kỳ cần hỏi:
- Hạn chế này còn tồn tại trong code không?
- Tính năng có còn được dùng không?
- Giả định cũ có còn đúng không?
- Một thay đổi khác đã vô tình giải quyết nó chưa?
- Rủi ro có tăng/giảm không?
- Ticket có owner không?
- Trigger có tạo tín hiệu đáng tin không?

Không nên chỉ gom thêm hàng trăm ticket “clean up” không có quyết định. Một backlog quá nhiều mục mơ hồ khiến các rủi ro thật bị chìm trong nhiễu.

## 14. Phân loại nợ để chọn cách xử lý phù hợp

Không phải mọi khoản nợ đều trả bằng cùng một công việc.

| Loại nợ | Biểu hiện | Hướng xử lý có thể phù hợp |
| --- | --- | --- |
| **Thiết kế/cấu trúc** | Coupling cao, lớp nhiều trách nhiệm, phụ thuộc vòng | Refactor theo ranh giới thay đổi, tách trách nhiệm, hợp đồng |
| **Kiểm thử** | Không có test cho đường lỗi/hợp đồng quan trọng | Characterization tests, contract test, integration test |
| **Dữ liệu/schema** | Thiếu constraint, schema cũ, quy tắc lịch sử mơ hồ | Migration có kiểm chứng, dữ liệu phiên bản, đối soát |
| **Hiệu năng** | Trả toàn bộ tập dữ liệu, N+1, hot key | Đo điểm nghẽn, phân trang, batching, cache hoặc thay mô hình |
| **Vận hành** | Thiếu timeout, retry, quan sát, runbook | Bổ sung giới hạn, telemetry, kiểm soát lỗi, diễn tập |
| **Phụ thuộc/thư viện** | Phiên bản cũ, khó nâng, thiếu hỗ trợ | Nâng cấp có test, thay API, kế hoạch tương thích |
| **Tài liệu/tri thức** | Quyết định quan trọng chỉ nằm trong trí nhớ | ADR, mô tả hợp đồng, sơ đồ phụ thuộc, ví dụ vận hành |
| **Bảo mật** | Cơ chế kiểm tra yếu hoặc thiếu phân quyền | Đánh giá theo mức rủi ro và quy trình an ninh, không trì hoãn tùy tiện |

Có thể một khoản nợ thuộc nhiều loại. Ví dụ, một repository quá phức tạp vừa khó test, vừa tạo truy vấn N+1. Khi lập kế hoạch, nên xác định **nguyên nhân có tác động lớn nhất** và bằng chứng cần có sau khi sửa.

## 15. Ưu tiên khoản nợ nào trước?

Một hệ thống có thể có hàng chục khoản nợ. Để chọn, hãy đặt mỗi khoản vào bối cảnh **mục tiêu và kế hoạch thay đổi sắp tới**.

### Các yếu tố ưu tiên

1. **Mức rủi ro hiện tại:** có thể gây lỗi nghiêm trọng, gián đoạn, mất dữ liệu hoặc lộ thông tin không?
2. **Tác động đến roadmap:** một tính năng đã cam kết có bị chặn bởi cấu trúc cũ không?
3. **Chi phí phát sinh nếu chờ:** có thêm dữ liệu, caller, service hoặc migration khó hơn không?
4. **Tần suất đụng vào mã:** khu vực thay đổi hằng tuần có tạo “lãi nợ” nhiều hơn khu vực không đụng đến không?
5. **Khả năng xử lý từng phần:** có bước giảm rủi ro nhỏ, ít phụ thuộc và đem lại lợi ích sớm không?
6. **Mức chắc chắn của giải pháp:** đã có bằng chứng và hợp đồng đủ rõ hay cần spike/đo thêm?
7. **Tác động người dùng:** có nâng độ tin cậy, tốc độ hoặc khả năng phục vụ rõ ràng không?
8. **Chi phí cơ hội:** công việc này cạnh tranh với nghĩa vụ bắt buộc và vấn đề sản phẩm nào?

### Ví dụ so sánh ba khoản nợ

| Khoản nợ | Tình huống | Quyết định minh họa |
| --- | --- | --- |
| **A. Thiếu transaction đúng ở luồng trừ tồn kho** | Đã có đơn bị âm tồn kho khi xử lý đồng thời | **Xử lý ưu tiên cao**, không chỉ theo dõi |
| **B. Báo cáo đồng bộ giới hạn 2.000 dòng** | Hiện tối đa 500 dòng, không lỗi, có hard limit và metric | **Chấp nhận + theo dõi** với trigger |
| **C. Một helper cũ đặt tên khó hiểu** | Ít được dùng và sắp loại bỏ module | **Chấp nhận có thời hạn**; không đổi tên diện rộng vô ích |

Quyết định có thể thay đổi hoàn toàn nếu bối cảnh khác. Nếu B sắp phục vụ 100 khách doanh nghiệp có hàng chục nghìn đơn, nợ B cần được xử lý **trước khi triển khai tính năng**. Nếu C bất ngờ thành code path quan trọng, cần đánh giá lại.

### Không chỉ ưu tiên theo “dễ sửa”

Việc hoàn thành nhiều ticket nhỏ có thể tạo cảm giác năng suất nhưng không làm giảm rủi ro kỹ thuật quan trọng. Nên cân bằng **cải tiến nhỏ có giá trị** với những thay đổi phải thực hiện trước mốc bắt buộc.

Một khoản nợ lớn có thể được chia thành các bước nhỏ: thêm test trước, tạo adapter, chuyển một caller, đo lại, sau đó di chuyển phần còn lại. Cách này giảm rủi ro hơn so với chờ có một khoảng thời gian dài để viết lại tất cả.

## 16. “Xử lý nợ” có nhiều mức, không chỉ làm mới kiến trúc

Có thể tổ chức các mức can thiệp theo mức độ và chi phí:

| Mức can thiệp | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| **Ngăn tổn hại trước mắt** | Limit, timeout, cảnh báo, ràng buộc DB, kiểm tra quyền | Cần giảm rủi ro ngay trong khi thiết kế dài hạn chưa sẵn sàng |
| **Bao quanh bằng test** | Characterization test cho code cũ | Chuẩn bị refactor an toàn và phát hiện thay đổi ngoài ý muốn |
| **Giảm coupling từng phần** | Trích policy, đưa I/O qua interface, tách logic thuần | Có một lý do thay đổi rõ và đường di chuyển nhỏ |
| **Thay cấu trúc dữ liệu/luồng** | Phân trang, async job, batching, outbox | Đã có bằng chứng kiến trúc hiện tại không đáp ứng |
| **Thay thế hoàn toàn** | Di chuyển sang service/module mới | Khi giải pháp hiện tại không thể sửa an toàn hoặc chi phí duy trì lớn hơn nhiều |

**Bước giảm thiểu chưa đồng nghĩa đã trả hết nợ.** Với ví dụ báo cáo, hard limit giúp bảo vệ RAM nhưng người dùng có nhu cầu xuất dữ liệu lớn vẫn chưa được phục vụ. Đừng đóng ticket “đã giải quyết quy mô” chỉ vì thêm điều kiện **if (rows > limit)**.

Ngược lại, sau một bước refactor nhỏ mà rủi ro và chi phí thay đổi đã đạt mục tiêu, **không nhất thiết** phải tiếp tục đến mức viết lại toàn bộ.

## 17. Kiểm thử trước khi refactor: bảo vệ hành vi nào?

Một số code nợ khó đọc nhưng đang chứa những trường hợp biên quan trọng mà không ai còn nhớ. Trước khi thay nó, cần tìm hiểu hợp đồng thực.

### Characterization test

**Characterization test** ghi nhận hành vi đang có của một đoạn legacy để làm điểm so sánh khi sửa. Nó giúp phát hiện thay đổi ngoài dự kiến, nhưng **không chứng minh hành vi cũ luôn đúng**. Nếu code cũ tính sai số tiền, không nên biến sai lầm ấy thành hợp đồng vĩnh viễn.

Quy trình hợp lý:
1. Thu thập các trường hợp thực tế và điều kiện biên.
2. Xác nhận với nghiệp vụ hành vi nào phải giữ, hành vi nào là lỗi cần sửa.
3. Viết test cho hợp đồng đúng và ghi rõ những trường hợp đang sai.
4. Refactor từng bước, chạy test hồi quy.
5. Bổ sung integration test cho ranh giới thực mà unit test không mô phỏng.
6. Đánh giá lại bằng chứng vận hành sau khi triển khai.

### Kiểm thử những gì phụ thuộc vào loại nợ?

- **Nợ thiết kế:** test hành vi công khai, ranh giới phụ thuộc và các điều kiện biên; tránh verify mọi helper private.
- **Nợ database:** integration test với schema, transaction, index và dữ liệu đại diện.
- **Nợ phân quyền:** test người được phép, không được phép, tài nguyên thuộc người khác và đường API phụ.
- **Nợ hiệu năng:** load test với phân bố dữ liệu gần thực, p95/p99, tài nguyên và tỷ lệ lỗi.
- **Nợ giao thức:** contract test cho producer/consumer, serialization/deserialization và phiên bản.
- **Nợ dữ liệu lịch sử:** kiểm tra migration, đối soát số liệu và khả năng rollback hoặc replay.

Một PR refactor “không đổi chức năng” vẫn có thể phá **tác dụng phụ, thời điểm, thứ tự, cache hoặc transaction**. Định nghĩa “không đổi hành vi” phải gắn với hợp đồng, không chỉ giá trị trả về trong vài test đơn giản.

## 18. Nợ kỹ thuật với nhiều nhóm và phụ thuộc bên ngoài

Một khoản nợ có thể không nằm hoàn toàn trong quyền kiểm soát của một nhóm:
- Nhiều service dùng chung schema hoặc thư viện.
- Một API cần giữ tương thích cho đối tác.
- Database migration phụ thuộc lịch triển khai của nhóm vận hành.
- Module cũ còn được một ứng dụng di động đã phát hành sử dụng.
- Chính sách nghiệp vụ cần phê duyệt trước khi thay đổi.

Trong trường hợp đó, “owner” nên rõ:
- Ai **quyết định** xử lý và mức chấp nhận rủi ro.
- Ai **thực hiện** từng phần.
- Ai **phê duyệt** thay đổi hợp đồng hoặc migration.
- Ai **quan sát** tín hiệu trong thời gian chờ.

Không thể chỉ ghi “team liên quan phối hợp” rồi xem như đã có trách nhiệm.

### Khi xử lý cần migration có kiểm soát

Ví dụ thay API v1 bằng API v2:
1. Định nghĩa hợp đồng v2 và mức tương thích cần thiết.
2. Bổ sung adapter hoặc cơ chế hỗ trợ chuyển đổi.
3. Cho consumer thử theo từng nhóm.
4. Quan sát lỗi/mức sử dụng API cũ.
5. Công bố mốc dừng hỗ trợ theo chính sách.
6. Xóa đường cũ khi có bằng chứng consumer đã chuyển và có kế hoạch rollback phù hợp.

Trong thời gian chuyển, **hai phiên bản có thể cùng tồn tại có chủ đích**. Đó không nhất thiết là lặp tri thức xấu, nhưng phải có **nguồn hợp đồng chính thức**, test và điều kiện gỡ bỏ.

## 19. Theo dõi lãi nợ bằng số liệu mà không đánh mất ngữ nghĩa

Nhóm có thể muốn tính **cost of debt** bằng giờ công. Đây là một **ước lượng quản trị**, có ích nếu dùng đúng phạm vi.

Ví dụ minh họa:

- Một khu vực code khiến mỗi thay đổi mất thêm khoảng **2 giờ** để phối hợp và kiểm tra.
- Trong quý trước có **8 thay đổi cùng loại**.
- Chi phí phát sinh ước tính: **2 giờ × 8 = 16 giờ/quý**.

Nếu refactor ước tính tốn 12 giờ và giảm được phần lớn chi phí lặp, nó có thể đáng cân nhắc.

Nhưng không nên coi đây là phép tính hoàn chỉnh:
- Số lần thay đổi quý sau có thể khác.
- Hai giờ chỉ là ước tính, chưa chắc do một nguyên nhân duy nhất.
- Refactor có thể làm phát sinh lỗi, review và migration.
- Lợi ích còn gồm **giảm rủi ro** khó đổi ra giờ.
- Có thể xuất hiện yêu cầu mới khiến giải pháp khác cần thiết.

Vì vậy, số liệu giờ công nên bổ sung cho **đánh giá rủi ro và hợp đồng**, không thay thế chúng.

### Chi phí xử lý cũng có độ bất định

Ước lượng “refactor 3 ngày” có thể tăng khi phát hiện:
- Client ngoài đang dùng API.
- Dữ liệu cũ không tuân theo mô hình mới.
- Không có test hồi quy.
- Module khác phụ thuộc ngầm vào thứ tự thao tác.
- Cần migration và theo dõi sau triển khai.

Đôi khi **một spike ngắn** để đo, vẽ phụ thuộc và xác nhận hợp đồng có giá trị hơn việc cam kết giải pháp lớn trên thông tin thiếu.

## 20. Khi nào cần đánh giá lại một khoản nợ đã chấp nhận?

Ngay cả khi không có alert nào, vẫn cần đánh giá lại khi:
- Số lượng khách hàng, dữ liệu hoặc lưu lượng tăng khác giả định.
- Module bắt đầu được sửa thường xuyên hơn.
- Có yêu cầu sản phẩm mới cần thay đổi cùng khu vực.
- Thư viện hoặc nền tảng kết thúc hỗ trợ.
- Hệ thống chịu nghĩa vụ bảo mật, quyền riêng tư hoặc tuân thủ mới.
- Cơ chế vận hành/thành phần phụ thuộc thay đổi.
- Có sự cố gần xảy ra (near miss) hoặc một lỗi khó phát hiện.
- Công cụ kiểm thử mới làm chi phí xử lý nợ giảm đáng kể.
- Tính năng dự kiến loại bỏ bị giữ lại lâu hơn kế hoạch.
- Người sở hữu rời nhóm và tri thức chưa được chuyển giao.

Đây là các sự kiện có thể làm **thay đổi bài toán kinh tế và rủi ro**. Quyết định hợp lý năm trước chưa chắc còn hợp lý ở phiên bản sản phẩm hiện tại.

### Không đợi đến khi trigger trở thành sự cố

Nếu biết một migration cần bốn tuần nhưng tính năng mới sẽ ra mắt sau hai tuần, trigger “khi phát sinh lỗi thì sửa” là quá muộn. Hãy xem **lead time** của việc xử lý và thiết lập ngưỡng sớm đủ để hoàn thành trước deadline.

Với hệ thống quan trọng, có thể cần quyết định **không nhận thêm tải hoặc không ra mắt tính năng** cho tới khi rủi ro được giảm. Đây là một biện pháp kiểm soát chủ động, không phải thất bại của việc quản lý nợ.

## 21. Những sai lầm phổ biến trong quản lý nợ kỹ thuật

### 21.1. Gọi mọi điều không thích là nợ

Không có bằng chứng về rủi ro hoặc chi phí thay đổi, backlog sẽ tràn ngập các ticket về sở thích đặt tên và định dạng. Nên dùng formatter cho phần cơ học và ưu tiên những vấn đề có tác động thực.

### 21.2. Dùng nợ để hợp thức hóa bug nghiêm trọng

Sai tiền, mất dữ liệu hoặc lộ thông tin là vấn đề cần phân loại nghiêm túc. Không nên chỉ ghi “technical debt, fix later” rồi bỏ qua quy trình sự cố/bảo mật.

### 21.3. Chấp nhận nhưng không giới hạn

Một quyết định “giữ cách tải toàn bộ dữ liệu” mà không giới hạn đầu vào, không đo bộ nhớ và không có phản ứng khi vượt khả năng là chấp nhận rủi ro không rõ phạm vi.

### 21.4. Theo dõi nhưng không có chủ sở hữu

Một biểu đồ tăng chậm liên tục nhưng không có ai đánh giá và hành động sẽ chỉ ghi nhận rủi ro sau khi nó xảy ra.

### 21.5. Đặt ngưỡng nhưng không quy định hành động

“p95 trên 400 ms” là một con số. Cần biết khi nó xảy ra thì **ai làm gì**, trong thời hạn nào, có hạn chế tăng tải hay không.

### 21.6. Ưu tiên theo số dòng hoặc điểm code smell

Một lớp dài có thể ổn định, trong khi một điều kiện ngắn thiếu kiểm tra quyền có thể nguy hiểm. Độ dài và duplication score chỉ là tín hiệu cần điều tra.

### 21.7. Viết lại toàn bộ thay vì sửa nguyên nhân

Một rewrite lớn có thể tái tạo những lỗi tương tự, bỏ sót các trường hợp biên và làm mất hợp đồng hiện hữu. Nên xem có thể giảm rủi ro bằng bước nhỏ không.

### 21.8. Refactor không có test bảo vệ

Nếu không biết code cũ đang làm gì, rất khó khẳng định refactor giữ nguyên hành vi. Trước hết cần xác định hợp đồng và kiểm thử tương ứng.

### 21.9. Đóng ticket sau khi thêm một workaround

Bổ sung timeout hoặc hard limit có thể là bước giảm thiểu, nhưng không giải quyết toàn bộ yêu cầu quy mô hoặc độ bền của luồng. Phân biệt **mitigated** và **resolved** khi cần.

### 21.10. Không xem lại quyết định đã cũ

Nợ được chấp nhận khi có 100 khách không mặc nhiên còn chấp nhận được khi có 100.000 khách. Đặt lịch hoặc sự kiện đánh giá lại.

## 22. Case study: quyết định xử lý nợ ở hệ thống đơn hàng

Một nhóm quản lý dịch vụ đặt hàng có ba khoản nợ:

**Khoản A — Quy tắc phí vận chuyển lặp ở ba nơi.** Một lần thay đổi ngưỡng tháng trước đã làm preview khác checkout. Dù nhóm sửa ngay lỗi, nguy cơ lặp lại vẫn còn.

**Khoản B — Xuất lịch sử đồng bộ.** Báo cáo hiện trả tối đa 2.000 dòng, có metric và test. Một khách hàng mới dự kiến có 20.000 đơn sau đợt onboarding sắp tới.

**Khoản C — Class LegacyEmailFormatter dài và khó đọc.** Class này ít thay đổi, chỉ dùng ở tính năng đã có kế hoạch ngừng hoạt động, chưa ghi nhận lỗi phát sinh.

### Phân tích khoản A

**Bằng chứng:** Đã có lệch kết quả nghiệp vụ thực tế, và cùng quy tắc xuất hiện ở nhiều nơi.

**Quyết định:** Ưu tiên **xử lý**. Tạo một nơi sở hữu chính sách phí, test dưới/bằng/trên ngưỡng và đảm bảo các entry point dùng cùng hợp đồng. Không tự áp chính sách mới để sửa lại dữ liệu hóa đơn đã chốt.

**Điều kiện hoàn tất:** Không còn bản sao quyết định chính sách ở các luồng tạo đơn; test và dữ liệu đối soát xác nhận kết quả nhất quán.

### Phân tích khoản B

**Bằng chứng:** Dữ liệu hiện nhỏ, nhưng mốc mở rộng sắp đến vượt xa hard limit và khả năng hiện tại.

**Quyết định:** Không chờ metric “vượt 2.000” rồi mới bắt đầu. **Xử lý trước khi onboarding** bằng phân trang hoặc xuất nền, dựa trên yêu cầu khách hàng. Có thể tạm giữ giới hạn để bảo vệ service trong thời gian triển khai.

**Điều kiện hoàn tất:** Test tải trên tập dữ liệu có 20.000 đơn/khách; xác nhận quyền, dữ liệu đầy đủ, timeout, trạng thái job và hành vi khi xuất thất bại.

### Phân tích khoản C

**Bằng chứng:** Mã khó đọc nhưng ít thay đổi; kế hoạch loại bỏ tính năng có mốc cụ thể.

**Quyết định:** **Chấp nhận có thời hạn** và chỉ sửa bug hoặc bảo mật bắt buộc. Ghi rõ mốc sunset, owner và điều kiện đánh giá lại nếu thời điểm ngừng sử dụng bị lùi.

**Điều kiện xem lại:** Nếu tính năng tiếp tục hoạt động quá kế hoạch hoặc xuất hiện nhu cầu thay đổi đáng kể, đánh giá lại nợ thay vì mặc định giữ nguyên.

### Kết luận case study

Ba khoản đều có thể được gọi là nợ, nhưng **quyết định đúng không giống nhau**. A đã gây sai hành vi, B sắp chặn một cam kết sản phẩm, C có thể không đáng đầu tư lớn trước khi bị loại bỏ. Chất lượng quyết định đến từ **bằng chứng, điều kiện và trách nhiệm**, không từ việc gắn nhãn “technical debt”.

## 23. Mẫu ghi quyết định thực tế: ngắn nhưng kiểm tra được

Một ghi chú một trang có thể viết như sau:

~~~text
DEBT: REPORT-SYNC-017
Quyết định ngày: [ngày đánh giá]
Chủ sở hữu: [người/nhóm chịu trách nhiệm]

Vấn đề:
Báo cáo lịch sử đơn hiện trả danh sách trong một request đồng bộ.
Khi số dòng lớn, có nguy cơ tăng thời gian chờ và bộ nhớ.

Bằng chứng hiện tại:
[phân bố số dòng, p95/p99, tỷ lệ lỗi, load test, giới hạn tài nguyên]

Quyết định:
CHẤP NHẬN TẠM + THEO DÕI.

Điều kiện còn được chấp nhận:
- Chỉ phục vụ phạm vi sản phẩm đã xác nhận.
- Giới hạn 2.000 dòng được thực thi ở tầng truy xuất dữ liệu.
- Vượt giới hạn trả thông báo rõ, không âm thầm cắt dữ liệu.
- Không có lỗi/vi phạm SLO chưa được xử lý.

Theo dõi:
- Số dòng theo request và theo nhóm khách.
- p95/p99 endpoint, lỗi, heap/GC.
- Review mỗi tháng.

Trigger:
- Số dòng thường xuyên > 1.500 hoặc SLO xấu đi theo ngưỡng đã đặt:
  đánh giá và lên kế hoạch.
- Cam kết phục vụ khách > 2.000 dòng:
  triển khai giải pháp mới trước ngày ra mắt.
- Lỗi cạn tài nguyên hoặc rủi ro nghiêm trọng:
  xử lý theo quy trình sự cố, không chờ review định kỳ.

Hướng xử lý:
Phân trang ổn định hoặc xuất bất đồng bộ có job ID;
giữ bảo vệ quyền và kiểm soát dữ liệu.

Điều kiện đóng:
Test chức năng/tích hợp/tải đạt trên workload mục tiêu,
số liệu vận hành được theo dõi, rollback rõ ràng.
~~~

Mẫu chỉ hữu ích nếu số liệu, owner và mốc được **điền thật và cập nhật**. Đừng sao chép ngưỡng minh họa sang dự án khác mà không xác nhận ràng buộc.

## 24. Bài tập thực hành

### Bài tập 1 — Phân loại ba quyết định

Cho ba tình huống:

1. Một đoạn xử lý cũ có tên biến khó hiểu nhưng sẽ ngừng sử dụng sau 6 tuần; chưa có lỗi ghi nhận.
2. Một module thường xuyên bị lỗi hồi quy vì thiếu test; quý tới sẽ có nhiều thay đổi lớn trong module.
3. API xuất dữ liệu đang nhanh với 200 dòng, nhưng số dòng của khách lớn đã tăng lên 1.800 và giới hạn đồng bộ là 2.000.

Hãy chọn **chấp nhận, theo dõi hoặc xử lý** cho từng trường hợp và nêu **điều kiện làm thay đổi quyết định**.

*Gợi ý:* Cần xét deadline, mức rủi ro, kế hoạch thay đổi và khoảng cách tới giới hạn. Không nên dựa vào tên gọi của mùi mã.

### Bài tập 2 — Biến một TODO mơ hồ thành quyết định

TODO hiện có:

~~~java
// TODO: performance is bad; rewrite later.
~~~

Hãy viết lại thành ghi chú nợ gồm:
- Hạn chế kỹ thuật cụ thể.
- Hợp đồng người dùng bị ảnh hưởng.
- Bằng chứng cần đo.
- Người chịu trách nhiệm.
- Ngưỡng đánh giá lại.
- Hành động nếu vượt ngưỡng.
- Tiêu chí xác nhận sau xử lý.

*Gợi ý:* Nếu chưa có bằng chứng định lượng, ghi **cần đo gì và trong giai đoạn nào** thay vì tự bịa con số.

### Bài tập 3 — Rủi ro không nên để chờ

Một API cho phép người dùng truy cập tài liệu của người khác khi đoán được ID, nhưng ticket được đánh nhãn “technical debt, low priority”.

Hãy giải thích vì sao nhãn đó không phù hợp để trì hoãn, cần kiểm tra điều gì và cách phân công xử lý.

*Gợi ý:* Đây là vấn đề phân quyền ở ranh giới tài nguyên. Ưu tiên theo mức ảnh hưởng và quy trình bảo mật.

### Bài tập 4 — Viết trigger có hai ngưỡng

Một dịch vụ đọc dữ liệu đồng bộ có p95 tăng từ 120 ms lên 250 ms trong ba tháng. SLO mục tiêu là p95 không quá 400 ms. Nhóm chưa biết mức tăng do tải hay do truy vấn.

Hãy đề xuất:
- Ngưỡng **bắt đầu điều tra**.
- Ngưỡng **bắt buộc hành động/giới hạn mở rộng**.
- Cách xác định cửa sổ đo và lượng mẫu.
- Thêm những metric nào để xác định điểm nghẽn.
- Điều kiện cho phép kết luận chỉ cần tăng tài nguyên hay phải sửa truy vấn.

*Gợi ý:* Không nhất thiết đưa ngưỡng cụ thể khi chưa có dữ liệu; quan trọng là quy tắc quyết định có thể kiểm chứng.

### Bài tập 5 — Kiểm tra điều kiện đóng nợ

Nhóm refactor một service, giảm số dòng mã 30% và đóng ticket “technical debt resolved”.

Hãy trả lời:
- Giảm số dòng có chứng minh nợ đã hết không?
- Test nào bảo vệ hành vi và tác dụng phụ?
- Metric nào chứng minh chi phí thay đổi hoặc rủi ro đã giảm?
- Còn sự phụ thuộc hoặc cấu hình nào giữ nợ tồn tại không?

*Gợi ý:* Điều kiện đóng phải gắn với **mục tiêu ban đầu**, không phải một chỉ số dễ đo nhưng chưa liên hệ với rủi ro.

### Bài tập 6 — Debt register có version và owner

Một nhóm có 50 ticket nợ, 20 ticket không có owner, 15 ticket có mô tả “clean up code”, 10 ticket đã tồn tại hơn 2 năm mà chưa ai xem lại.

Hãy đề xuất quy trình 30 ngày để:
- Xác minh những ticket còn liên quan.
- Gộp hoặc đóng ticket không còn giá trị.
- Ưu tiên các rủi ro cao.
- Giao owner cho những mục cần theo dõi.
- Thiết lập lịch/trigger đánh giá lại.
- Đưa hoạt động kiểm chứng vào kế hoạch phát triển mà không chiếm toàn bộ năng lực nhóm.

*Gợi ý:* Mục tiêu không phải làm số ticket về 0 bằng cách xóa nhãn, mà là có danh sách **quyết định thực sự được quản lý**.

## 25. Tự kiểm tra kiến thức

**Câu 1.** Một đoạn code khó đọc có mặc nhiên phải refactor ngay không?

*Trả lời:* Không. Cần xem mức rủi ro, tần suất thay đổi, chi phí trì hoãn, kế hoạch sản phẩm và khả năng kiểm chứng. Có thể chấp nhận có thời hạn nếu rủi ro được kiểm soát.

**Câu 2.** Chấp nhận nợ có nghĩa là không cần theo dõi gì nữa?

*Trả lời:* Không. Quyết định chấp nhận nên có phạm vi, điều kiện vẫn còn phù hợp và mốc hoặc sự kiện đánh giá lại.

**Câu 3.** Theo dõi p95 nhưng không có người nhận cảnh báo và không có hành động khi vượt ngưỡng đã đủ chưa?

*Trả lời:* Chưa. Theo dõi phải gắn với owner, ngưỡng có ý nghĩa, thời điểm và phản ứng cụ thể.

**Câu 4.** Một khoản nợ về thiếu kiểm tra quyền có thể được giữ mãi chỉ vì chi phí sửa cao?

*Trả lời:* Không nên. Đây có thể là vấn đề bảo mật nghiêm trọng, cần phân loại và xử lý theo quy trình và mức ảnh hưởng, không lấy nhãn nợ để trì hoãn vô thời hạn.

**Câu 5.** Thêm hard limit cho một API xử lý dữ liệu lớn có đồng nghĩa đã trả hết nợ hiệu năng?

*Trả lời:* Không. Nó có thể chỉ là biện pháp giảm thiểu. Nếu sản phẩm cần xử lý lượng dữ liệu vượt limit, phải có giải pháp đáp ứng hợp đồng và test phù hợp.

**Câu 6.** Vì sao “sửa khi code này được đụng tới” là một trigger chưa đủ rõ?

*Trả lời:* Nó không nêu loại thay đổi, mức rủi ro, hành động bắt buộc và thời hạn. Một thay đổi nhỏ không liên quan chưa chắc là thời điểm phù hợp; một mốc ra mắt lớn có thể đòi hỏi xử lý trước.

**Câu 7.** Điều gì chứng minh một refactor thật sự giảm nợ?

*Trả lời:* Bằng chứng bám mục tiêu như ít nơi phải sửa khi đổi quy tắc, test và hợp đồng rõ hơn, giảm lỗi hồi quy, cải thiện chỉ số vận hành hoặc loại bỏ rủi ro đã ghi nhận — không chỉ số dòng giảm.

**Câu 8.** Nợ kỹ thuật và bug có giống nhau không?

*Trả lời:* Không hoàn toàn. Nợ mô tả đánh đổi làm tăng chi phí/rủi ro về sau; bug là hành vi hiện tại không đúng kỳ vọng. Một khoản nợ có thể gây bug, nhưng bug nghiêm trọng cần được xử lý theo tác động thật.

**Câu 9.** Vì sao một quyết định chấp nhận hợp lý hôm nay có thể sai trong sáu tháng nữa?

*Trả lời:* Do tải, dữ liệu, roadmap, ràng buộc bảo mật/tuân thủ, mức phụ thuộc và chi phí xử lý thay đổi. Quyết định phải được xem lại khi giả định không còn đúng.

**Câu 10.** Người sở hữu nợ chỉ cần được ghi tên trong ticket?

*Trả lời:* Không. Người sở hữu cần có trách nhiệm kiểm tra tín hiệu, đánh giá trigger, đưa quyết định vào kế hoạch và bảo đảm hành động được thực hiện hoặc chuyển giao rõ ràng.

## Ghi nhớ

**Chấp nhận, theo dõi hoặc xử lý nợ kỹ thuật** là ba quyết định cần dựa trên **bằng chứng, rủi ro, phạm vi và điều kiện rõ ràng**. Chấp nhận khi giới hạn hiện tại đủ an toàn và lợi ích sửa ngay chưa tương xứng; theo dõi khi tác động phụ thuộc vào tải, thay đổi hoặc mốc tương lai; xử lý khi nợ đã gây rủi ro đáng kể, chặn yêu cầu bắt buộc hoặc vượt ngưỡng đã cam kết. Mỗi quyết định nên nói rõ **ai chịu trách nhiệm, điều gì được đo, khi nào phải đánh giá lại, hành động nào sẽ xảy ra và bằng chứng nào cho phép đóng nợ**. Quản lý nợ tốt không nhằm xóa mọi mùi mã, mà nhằm bảo vệ khả năng **đáng tin cậy, dễ hiểu và dễ thay đổi** của hệ thống theo thời gian.
