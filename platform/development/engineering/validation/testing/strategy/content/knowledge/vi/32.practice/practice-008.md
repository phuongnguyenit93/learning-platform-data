# Ước lượng nguồn lực với giới hạn thời gian được giao

## 1. Bài toán ước lượng trong kiểm thử

Trong một dự án, nhóm kiểm thử thường nhận một mốc phát hành hoặc thời hạn cố định trong khi phạm vi công việc, nhân lực và môi trường đều có giới hạn. Câu hỏi thực tế không chỉ là “cần bao nhiêu ngày để kiểm thử?” mà còn là: với thời gian còn lại, nhóm có thể kiểm tra những rủi ro nào, cần những kỹ năng nào, phụ thuộc nào có thể làm chậm tiến độ và bằng chứng nào phải có trước khi ra quyết định phát hành?

Ước lượng nguồn lực là quá trình dự báo công sức, năng lực và thời gian cần để hoàn thành một phạm vi kiểm thử đã xác định. Khi thời hạn được giao là cố định, ước lượng phải giúp nhóm xây dựng phương án khả thi, ưu tiên công việc và chỉ ra rõ phần nào có thể hoàn thành, phần nào cần giảm phạm vi hoặc cần thêm nguồn lực.

Ba khái niệm cần phân biệt:

- **Công sức (effort):** tổng lượng lao động cần thiết, thường tính bằng giờ hoặc ngày công. Ví dụ, 40 giờ công tương đương 5 ngày công nếu quy ước một ngày làm việc có 8 giờ.
- **Thời lượng (duration):** khoảng thời gian trên lịch từ lúc bắt đầu đến khi hoàn tất. Một công việc 40 giờ công không nhất thiết hoàn tất trong 5 ngày lịch nếu có người làm bán thời gian, chờ môi trường hoặc phụ thuộc vào nhóm khác.
- **Năng lực khả dụng (capacity):** lượng thời gian thực tế nhóm có thể dành cho công việc trong khoảng thời gian đó, sau khi trừ nghỉ phép, họp, hỗ trợ vận hành và các cam kết khác.

Không được cộng số người rồi mặc định tiến độ giảm theo tỷ lệ. Công việc có phụ thuộc tuần tự, cần kỹ năng chuyên biệt hoặc phải chờ môi trường không thể được rút ngắn chỉ bằng cách bổ sung người. Ước lượng tốt phải thể hiện cả công sức, lịch thực tế, giả định và độ bất định.

## 2. Xác định đầu vào trước khi ước lượng

Trước khi đưa ra con số, hãy xác định rõ bài toán. Một ước lượng không có phạm vi và giả định chỉ là một dự đoán khó kiểm chứng.

Các đầu vào tối thiểu gồm:

| Đầu vào | Cần làm rõ |
|---|---|
| Thời hạn | Ngày bắt đầu, mốc hoàn tất, thời điểm cần kết quả để ra quyết định |
| Phạm vi thay đổi | Chức năng mới, sửa lỗi, module bị ảnh hưởng, tích hợp và migration |
| Rủi ro | Mức độ ảnh hưởng nếu lỗi xảy ra và khả năng lỗi xuất hiện |
| Mức kiểm thử | Unit, API, UI, integration, regression, performance, security hoặc exploratory |
| Tiêu chí hoàn tất | Điều kiện vào/ra, test bắt buộc, mức lỗi còn mở và bằng chứng cần lưu |
| Nhân sự | Số người, kỹ năng, mức tham gia, lịch nghỉ và công việc đã cam kết |
| Môi trường và dữ liệu | Thời điểm sẵn sàng, quyền truy cập, dữ liệu, dịch vụ phụ thuộc |
| Phụ thuộc | Build từ nhóm phát triển, xác nhận nghiệp vụ, nhà cung cấp hoặc phê duyệt |
| Lịch sử | Dữ liệu thực tế từ các lần kiểm thử tương tự, nếu có |

Nếu thiếu thông tin, hãy ghi giả định và mức ảnh hưởng của nó. Ví dụ: “Ước lượng giả định môi trường tích hợp sẵn sàng vào thứ Hai; nếu trễ một ngày, phần kiểm thử tích hợp sẽ dịch chuyển tương ứng.” Cách ghi này giúp người nhận hiểu điều kiện để con số còn đúng.

### 2.1. Chốt phạm vi có thể kiểm thử

Chia phạm vi thành các luồng nghiệp vụ và hạng mục có thể ước lượng. Tránh một mục quá lớn như “kiểm thử toàn bộ hệ thống”. Với luồng tạo đơn, có thể tách thành:

1. Kiểm tra validation và quy tắc tính giá.
2. Kiểm tra API tạo đơn và phân quyền.
3. Kiểm tra lưu dữ liệu, transaction và migration liên quan.
4. Kiểm tra tích hợp tồn kho và thanh toán.
5. Kiểm tra luồng hồi quy sau khi sửa lỗi.
6. Kiểm tra smoke test sau triển khai và theo dõi chỉ số.

Mỗi hạng mục nên có đầu ra xác định, người phụ trách và điều kiện bắt đầu. Phạm vi loại trừ cũng cần được ghi lại, chẳng hạn kiểm thử tải quy mô lớn không nằm trong đợt này do môi trường chưa được cấp.

## 3. Ước lượng công sức từ công việc nhỏ

Kỹ thuật dễ áp dụng nhất là phân rã công việc (work breakdown). Chia công việc thành phần đủ nhỏ để người có chuyên môn có thể ước lượng dựa trên hoạt động cụ thể. Với kiểm thử, các hoạt động thường gồm:

- Phân tích yêu cầu, thay đổi và rủi ro.
- Thiết kế test, review test và chuẩn bị dữ liệu.
- Chuẩn bị môi trường, tài khoản và công cụ.
- Thực thi test thủ công hoặc tự động.
- Phân tích kết quả, ghi nhận lỗi và trao đổi với nhóm phát triển.
- Kiểm thử lại bản sửa và chạy regression bị ảnh hưởng.
- Tổng hợp bằng chứng, đánh giá rủi ro và báo cáo.

Ví dụ, một hạng mục “kiểm thử API tạo đơn” có thể được phân rã:

| Hoạt động | Ước lượng công sức |
|---|---:|
| Phân tích hợp đồng và rủi ro | 2 giờ |
| Thiết kế trường hợp và dữ liệu | 3 giờ |
| Chuẩn bị môi trường, xác thực | 1 giờ |
| Thực thi các trường hợp chính và biên | 4 giờ |
| Ghi nhận, xác minh lỗi và kiểm thử lại | 3 giờ |
| Lưu bằng chứng và báo cáo | 1 giờ |
| **Tổng** | **14 giờ** |

Đây là ví dụ minh họa, không phải định mức chung. Ước lượng cần dựa vào độ phức tạp, chất lượng yêu cầu, mức độ ổn định của môi trường và dữ liệu lịch sử của nhóm.

Không quên công việc gián tiếp. Họp làm rõ yêu cầu, chờ build, review test, phân tích lỗi và báo cáo đều tiêu tốn thời gian. Nếu chỉ tính thời gian bấm chạy test, kế hoạch sẽ thường xuyên thiếu hụt.

## 4. Chọn kỹ thuật ước lượng phù hợp

Không có một kỹ thuật luôn chính xác. Chọn cách phù hợp với độ rõ của phạm vi, dữ liệu lịch sử và mức độ bất định.

### 4.1. Ước lượng tương tự (analogous)

So sánh công việc mới với một hạng mục hoặc lần phát hành đã thực hiện. Ví dụ, lần trước kiểm thử một API có 8 trường hợp mất 2 ngày công; lần này API có độ phức tạp tương đương nhưng thêm một tích hợp, nhóm có thể dùng kết quả cũ làm điểm xuất phát rồi điều chỉnh.

Ưu điểm là nhanh và dễ trao đổi. Hạn chế là kết quả phụ thuộc vào việc chọn đúng công việc tương tự. Cần ghi rõ điểm giống, điểm khác và dữ liệu lịch sử được dùng.

### 4.2. Ước lượng theo tham số (parametric)

Dùng đơn giá hoặc năng suất quan sát được để tính. Ví dụ, nếu nhóm đã đo được trung bình cần 30 phút để thiết kế, thực thi và ghi bằng chứng cho một trường hợp API đơn giản, 20 trường hợp tương tự có thể cần khoảng 10 giờ công trước khi điều chỉnh độ phức tạp.

Không áp dụng một tốc độ trung bình cho mọi loại test. Một test kiểm tra trường bắt buộc đơn giản khác xa test transaction, phân quyền hoặc tích hợp thanh toán. Cần phân nhóm theo loại công việc và cập nhật tham số bằng dữ liệu thực tế.

### 4.3. Ước lượng ba điểm (three-point)

Với công việc có bất định, ước lượng ba giá trị:

- **O (Optimistic):** công sức nếu điều kiện thuận lợi và không gặp trở ngại đáng kể.
- **M (Most likely):** công sức có khả năng xảy ra nhất theo hiểu biết hiện tại.
- **P (Pessimistic):** công sức nếu có các trở ngại hợp lý như lỗi môi trường, yêu cầu cần làm rõ hoặc phải kiểm thử lại nhiều lần.

Một cách tính PERT thường dùng là:

\[
E = \frac{O + 4M + P}{6}
\]

Ví dụ một hạng mục có O = 4 giờ, M = 6 giờ và P = 14 giờ:

\[
E = \frac{4 + 4(6) + 14}{6} = 7 \text{ giờ}
\]

Giá trị này là kỳ vọng theo giả định của phương pháp, không phải cam kết rằng công việc chắc chắn hoàn tất trong 7 giờ. Nếu các ước lượng ba điểm có chất lượng thấp, kết quả tính toán cũng không thể chính xác hơn đầu vào.

### 4.4. Ước lượng nhóm

Planning poker, wideband Delphi hoặc buổi rà soát chéo giúp nhiều người đưa ra đánh giá độc lập trước khi thống nhất. Cách làm này hữu ích khi công việc cần nhiều chuyên môn hoặc một người dễ bỏ sót phụ thuộc.

Hãy yêu cầu người ước lượng nêu cơ sở, giả định và điều gì có thể làm con số thay đổi. Không lấy trung bình máy móc khi các con số chênh lệch lớn; hãy tìm hiểu vì sao người này dự đoán 4 giờ còn người khác dự đoán 3 ngày.

## 5. Tính năng lực khả dụng trong thời hạn cố định

Sau khi có công sức dự kiến, tính năng lực thực tế của nhóm trong khoảng thời gian được giao.

Một cách tính đơn giản:

\[
\text{Capacity} = \sum(\text{ngày làm việc khả dụng} \times \text{giờ tập trung mỗi ngày})
\]

Giờ tập trung mỗi ngày phải phản ánh thời gian thực sự dành cho công việc kiểm thử. Nếu một người làm việc 8 giờ mỗi ngày nhưng dành 2 giờ cho họp, hỗ trợ và công việc chung, năng lực lập kế hoạch có thể chỉ khoảng 6 giờ mỗi ngày.

Ví dụ: nhóm có 3 người trong 5 ngày làm việc. Mỗi người có 6 giờ tập trung mỗi ngày. Năng lực danh nghĩa là:

\[
3 \times 5 \times 6 = 90 \text{ giờ công}
\]

Nếu một người nghỉ một ngày, trừ tiếp 6 giờ, còn 84 giờ công. Nếu một người chỉ có 50% thời gian tham gia, chỉ tính phần năng lực thực tế tương ứng.

Capacity là giới hạn nguồn lực, không phải lời hứa hoàn thành. Nhóm còn phải tính phụ thuộc tuần tự, kỹ năng, thời gian chờ và phần dự phòng. Ba người có tổng 90 giờ công không có nghĩa một nhiệm vụ 30 giờ có thể hoàn tất trong một ngày nếu chỉ một người có quyền truy cập hoặc kỹ năng cần thiết.

### 5.1. Phân biệt năng lực và mức sử dụng

Không nên lập kế hoạch sử dụng 100% năng lực danh nghĩa. Công việc kiểm thử thường phát sinh trao đổi, phân tích lỗi, chờ build và hỗ trợ khẩn cấp. Dành toàn bộ thời gian cho các task đã biết sẽ làm kế hoạch rất dễ vỡ.

Có thể bắt đầu bằng một tỷ lệ tập trung thận trọng dựa trên lịch sử nhóm, sau đó điều chỉnh bằng dữ liệu thực tế. Không có một tỷ lệ dự phòng cố định phù hợp cho mọi đội. Nhóm có nhiều phụ thuộc và yêu cầu chưa ổn định cần khoảng đệm lớn hơn nhóm làm trên sản phẩm ổn định với pipeline tốt.

## 6. Lập lịch theo phụ thuộc và kỹ năng

Tổng công sức không bằng thời lượng lịch. Hãy xác định công việc nào có thể chạy song song và công việc nào phải chờ.

Ví dụ:

~~~mermaid
flowchart TD
    A["Chốt yêu cầu và rủi ro"] --> B["Thiết kế test"]
    A --> C["Chuẩn bị môi trường"]
    B --> D["Review test và dữ liệu"]
    C --> E["Xác minh môi trường"]
    D --> F["Thực thi kiểm thử"]
    E --> F
    F --> G["Phân tích lỗi và kiểm thử lại"]
    G --> H["Đánh giá bằng chứng"]
    H --> I["Báo cáo và quyết định"]
~~~

Thiết kế test và chuẩn bị môi trường có thể diễn ra song song sau khi phạm vi được chốt. Thực thi chỉ bắt đầu khi test, dữ liệu và môi trường đều sẵn sàng. Nếu một bước nằm trên đường găng (critical path), việc chậm bước đó sẽ làm trễ mốc cuối.

Khi phân công, xem xét:

- Kỹ năng domain và khả năng phân tích yêu cầu.
- Kỹ năng API, UI, database, automation, performance hoặc security.
- Quyền truy cập môi trường và khả năng xử lý dữ liệu.
- Người có thể review độc lập và người ra quyết định.
- Rủi ro một người trở thành điểm nghẽn vì nắm kiến thức hoặc quyền truy cập duy nhất.

Có thể phân công theo cặp hoặc có người dự phòng cho hạng mục quan trọng. Việc này vừa giảm rủi ro phụ thuộc cá nhân vừa giúp review chất lượng.

## 7. Ưu tiên phạm vi khi thời gian không đủ

Khi công sức ước lượng lớn hơn năng lực khả dụng, không nên âm thầm cắt bớt test hoặc giảm tiêu chí đạt. Hãy ưu tiên dựa trên rủi ro và đưa ra các lựa chọn minh bạch.

Một cách phân loại thực dụng:

| Nhóm | Đặc điểm | Cách xử lý khi thời gian hạn chế |
|---|---|---|
| Bắt buộc | Rủi ro cao, yêu cầu pháp lý/hợp đồng, luồng cốt lõi hoặc gate phát hành | Giữ trong phạm vi; nếu không thể hoàn tất, báo rõ rủi ro và đề xuất dừng |
| Quan trọng | Rủi ro đáng kể, ảnh hưởng nhiều người dùng hoặc module | Ưu tiên sau nhóm bắt buộc; có thể giảm độ rộng nhưng giữ các trường hợp rủi ro chính |
| Có thể trì hoãn | Rủi ro thấp, ít thay đổi, có biện pháp phát hiện khác | Chuyển sang đợt sau khi có người chấp nhận và lịch thực hiện |

Có thể dùng ma trận xác suất và tác động để xếp hạng, nhưng cần kết hợp hiểu biết nghiệp vụ. Một lỗi ít xảy ra nhưng gây mất dữ liệu hoặc giao dịch sai vẫn có thể phải kiểm thử trước.

Các cách giảm phạm vi nên được xem xét theo thứ tự có căn cứ:

1. Loại bỏ test trùng lặp hoặc ít giá trị phát hiện.
2. Tập trung vào các luồng và dữ liệu biên có rủi ro cao.
3. Tái sử dụng test tự động đáng tin cậy đã có, sau khi xác minh phù hợp với thay đổi.
4. Chuyển test ít rủi ro sang đợt tiếp theo và ghi nhận rủi ro còn lại.
5. Đề nghị thêm nguồn lực hoặc điều chỉnh mốc nếu phần bắt buộc vẫn không thể hoàn thành.

Không giảm kiểm thử bảo mật, dữ liệu hoặc giao dịch trọng yếu chỉ để làm đẹp tiến độ. Nếu nhóm không thể cung cấp đủ bằng chứng, báo cáo phải thể hiện “chưa đủ bằng chứng” thay vì đánh dấu đạt.

## 8. Xử lý độ bất định và dự phòng

Ước lượng là dự báo có điều kiện. Các nguồn bất định thường gặp trong kiểm thử gồm:

- Yêu cầu chưa rõ hoặc thay đổi sau khi thiết kế test.
- Build bàn giao trễ hoặc liên tục có lỗi chặn.
- Môi trường không ổn định, dữ liệu thiếu hoặc quyền truy cập chưa được cấp.
- Lỗi phát hiện cần nhiều vòng phân tích và sửa.
- Người có kỹ năng chuyên biệt vắng mặt.
- Phụ thuộc bên ngoài phản hồi chậm hoặc không có sandbox.

Hãy ghi lại từng rủi ro, khả năng, tác động, dấu hiệu cảnh báo và hành động dự phòng. Ví dụ: nếu môi trường staging chưa sẵn sàng trước một mốc đã định, nhóm có thể chạy unit/API test trên môi trường tích hợp trước, nhưng vẫn giữ integration test bắt buộc làm điều kiện phát hành.

Khoảng dự phòng nên gắn với rủi ro cụ thể. Tránh cộng một tỷ lệ tùy ý vào mọi hạng mục rồi coi đó là bảo đảm. Nếu chưa có dữ liệu lịch sử, có thể lập kịch bản thấp, cơ sở và cao:

| Kịch bản | Giả định | Cách dùng |
|---|---|---|
| Thuận lợi | Build ổn định, môi trường sẵn sàng, ít lỗi | Cho biết mức hoàn thành tốt nhất có thể |
| Cơ sở | Điều kiện như dự kiến, có một số lỗi và vòng kiểm thử lại | Làm căn cứ lập kế hoạch chính |
| Bất lợi | Trễ môi trường, thay đổi yêu cầu hoặc nhiều lỗi nghiêm trọng | Xác định điểm cần giảm phạm vi, bổ sung nguồn lực hoặc dời mốc |

Khi điều kiện thay đổi, cập nhật ước lượng phần việc còn lại. Không cộng toàn bộ công sức đã làm vào phần còn lại hoặc tiếp tục dùng con số ban đầu khi giả định không còn đúng.

## 9. Ví dụ thực hành: lập kế hoạch trong năm ngày

Giả sử nhóm kiểm thử được giao 5 ngày làm việc để đánh giá một thay đổi trong luồng đặt hàng. Phạm vi gồm API tạo đơn, tính phí, kiểm tra tồn kho, ghi dữ liệu và một smoke test sau triển khai.

Nhóm có 3 người:

- QA A có thể dành 6 giờ tập trung mỗi ngày.
- QA B có thể dành 6 giờ tập trung mỗi ngày.
- QA C có thể dành 4 giờ tập trung mỗi ngày do còn hỗ trợ một sản phẩm khác.

Năng lực danh nghĩa:

\[
(6 + 6 + 4) \times 5 = 80 \text{ giờ công}
\]

Nhóm dành 8 giờ công cho họp làm rõ, hỗ trợ phát sinh và điều phối. Năng lực có thể lập kế hoạch cho các task đã xác định là 72 giờ công.

### 9.1. Ước lượng công việc

| Hạng mục | Công sức dự kiến |
|---|---:|
| Phân tích thay đổi và rủi ro | 5 giờ |
| Thiết kế test và review | 9 giờ |
| Chuẩn bị dữ liệu, môi trường | 6 giờ |
| Unit/API và kiểm tra hợp đồng | 12 giờ |
| Integration test database và tồn kho | 12 giờ |
| Kiểm thử luồng đặt hàng đầu cuối | 8 giờ |
| Kiểm thử lại và regression theo lỗi | 12 giờ |
| Smoke test và đánh giá vận hành | 4 giờ |
| Báo cáo và lưu bằng chứng | 4 giờ |
| **Tổng** | **72 giờ** |

Tổng công sức bằng năng lực khả dụng, vì vậy kế hoạch không có nhiều chỗ cho sai lệch. Nhóm cần kiểm tra xem ước lượng có dựa trên dữ liệu đáng tin cậy không, các task có phụ thuộc tuần tự nào và có thể chuẩn bị môi trường song song với thiết kế test hay không.

### 9.2. Phân bổ người và lịch

Một phương án phân bổ có thể là:

| Ngày | QA A | QA B | QA C |
|---|---|---|---|
| 1 | Phân tích rủi ro, thiết kế test API | Rà soát database và migration | Kiểm tra môi trường, dữ liệu |
| 2 | Hoàn thiện test API, review | Thiết kế và chuẩn bị integration test | Hỗ trợ dữ liệu, kiểm tra quyền |
| 3 | Thực thi API và hợp đồng | Integration test database/tồn kho | Kiểm thử luồng đầu cuối |
| 4 | Kiểm thử lại lỗi API, regression | Kiểm thử transaction và dữ liệu | Kiểm thử lại luồng nghiệp vụ |
| 5 | Tổng hợp bằng chứng, smoke test | Đánh giá rủi ro dữ liệu | Báo cáo, rà soát tiêu chí phát hành |

Đây là lịch minh họa. Người thực hiện phải có kỹ năng và quyền truy cập phù hợp; các task cần cùng môi trường phải được điều phối để không ghi đè dữ liệu của nhau. Nếu test đầu cuối phụ thuộc API và database test, cần có điều kiện bàn giao rõ trước khi QA C bắt đầu.

### 9.3. Xử lý khi phát sinh vượt kế hoạch

Giả sử ngày thứ ba, môi trường tích hợp chậm một ngày và nhóm phát hiện thêm lỗi transaction cần kiểm tra. Không nên chỉ yêu cầu mọi người làm thêm giờ. Hãy cập nhật:

1. Phần công việc đã hoàn thành và bằng chứng hiện có.
2. Phần còn lại, công sức ước lượng mới và task đang bị chặn.
3. Rủi ro của các hạng mục có thể trì hoãn.
4. Tác động tới đường găng và mốc phát hành.
5. Các phương án: bổ sung người có kỹ năng phù hợp, chuyển test ít rủi ro, dùng môi trường thay thế đã được xác nhận hoặc điều chỉnh mốc.

Nếu integration test transaction là gate bắt buộc, nhóm không được bỏ qua chỉ vì môi trường trễ. Có thể chuẩn bị test và dữ liệu trong lúc chờ, nhưng cần báo rõ rằng kết quả phát hành chưa đủ cho tới khi gate đó được thực hiện.

## 10. Theo dõi sai lệch và cập nhật ước lượng

Trong quá trình thực hiện, so sánh kế hoạch với thực tế theo từng hạng mục:

- Công sức đã dùng so với ước lượng ban đầu.
- Công việc đã hoàn thành và đầu ra có thể kiểm chứng.
- Thời gian chờ do phụ thuộc.
- Số lỗi phát hiện, thời gian phân tích và số vòng kiểm thử lại.
- Thay đổi phạm vi và giả định không còn đúng.
- Năng lực còn lại của từng người trong thời hạn.

Một bảng theo dõi đơn giản:

| Hạng mục | Ước lượng ban đầu | Thực tế đã dùng | Còn lại dự kiến | Trạng thái |
|---|---:|---:|---:|---|
| Thiết kế test API | 8 giờ | 7 giờ | 1 giờ | Đang review |
| Integration database | 12 giờ | 5 giờ | 10 giờ | Bị chặn môi trường |
| Luồng đầu cuối | 8 giờ | 0 giờ | 8 giờ | Chờ integration |

Trong ví dụ, integration database dự kiến còn 10 giờ thay vì 7 giờ ban đầu. Nhóm cần cập nhật tổng công sức còn lại và xem có vượt capacity hay không. Không nên che giấu sai lệch bằng cách sửa ước lượng gốc; hãy giữ số ban đầu và ghi lại dự báo mới để cải thiện chất lượng ước lượng cho lần sau.

Khi báo cáo tiến độ, dùng đầu ra và bằng chứng thay vì chỉ báo phần trăm. “Đã hoàn thành 80%” không cho biết 20% còn lại có phải là test transaction bắt buộc hay chỉ là kiểm tra ít rủi ro.

## 11. Trao đổi phương án với bên giao thời hạn

Khi phạm vi không vừa với thời gian hoặc nguồn lực, người phụ trách kiểm thử cần trình bày lựa chọn và hệ quả. Một cuộc trao đổi hiệu quả nên nêu:

1. Thời hạn và năng lực khả dụng đã tính.
2. Phạm vi bắt buộc và lý do dựa trên rủi ro.
3. Phần có thể hoàn thành trong thời gian hiện tại.
4. Phần cần thêm người, kỹ năng, môi trường hoặc thời gian.
5. Rủi ro còn lại nếu trì hoãn hoặc bỏ qua từng hạng mục.
6. Người có thẩm quyền quyết định chấp nhận rủi ro.

Ví dụ cách trình bày:

> Với năng lực hiện tại, nhóm có thể hoàn thành kiểm thử API, luồng đặt hàng chính và kiểm tra dữ liệu trong mốc năm ngày. Kiểm thử tải đầy đủ chưa nằm trong năng lực của đợt này. Kiểm thử transaction và migration vẫn là gate bắt buộc. Nếu cần bổ sung kiểm thử tải trước phát hành, cần thêm môi trường và nguồn lực hoặc điều chỉnh thời hạn. Việc chấp nhận phát hành khi chưa có kết quả tải phải do người có thẩm quyền quyết định và ghi nhận rủi ro.

Tránh cam kết chắc chắn khi đầu vào còn bất định. Hãy nói rõ con số là ước lượng, phạm vi và điều kiện đi kèm. Khi nhận chỉ đạo thay đổi phạm vi, cập nhật kế hoạch và ghi lại quyết định để mọi bên hiểu cùng một trạng thái.

## 12. Những sai lầm thường gặp

- **Nhầm công sức với thời lượng:** cộng giờ công rồi suy ra ngày hoàn tất mà bỏ qua phụ thuộc và thời gian chờ. Lập lịch dựa trên capacity và đường găng.
- **Tính đủ 8 giờ tập trung mỗi ngày:** bỏ qua họp, hỗ trợ, nghỉ và công việc chung. Dùng năng lực khả dụng thực tế.
- **Ước lượng một hạng mục quá lớn:** khó xác định phần nào gây sai lệch. Phân rã theo hoạt động và đầu ra.
- **Quên kiểm thử lại và báo cáo:** chỉ tính lần chạy đầu tiên. Bao gồm phân tích lỗi, regression, bằng chứng và giao tiếp.
- **Chia đều công việc theo số người:** bỏ qua kỹ năng, quyền truy cập và phụ thuộc. Phân công theo năng lực và tạo người dự phòng.
- **Thêm người để rút ngắn mọi task:** tăng trao đổi và xung đột tài nguyên, không rút ngắn công việc tuần tự. Xác định task có thể song song trước.
- **Dùng buffer tùy ý:** che khuất rủi ro cụ thể. Gắn dự phòng với bất định và giả định.
- **Cắt test trọng yếu để giữ ngày phát hành:** tạo cảm giác hoàn tất nhưng thiếu bằng chứng. Trình bày rủi ro và xin quyết định đúng thẩm quyền.
- **Không cập nhật dự báo:** kế hoạch không còn phản ánh thực tế khi môi trường hoặc phạm vi thay đổi. Ước lượng lại phần còn lại và lưu lịch sử.
- **Báo tiến độ bằng phần trăm:** không thể hiện chất lượng hoặc rủi ro của phần chưa xong. Báo theo kết quả, gate và bằng chứng.

## 13. Checklist ước lượng khi thời hạn đã cố định

- Thời hạn, mốc cần kết quả và tiêu chí hoàn tất đã rõ.
- Phạm vi được chia thành các hạng mục đủ nhỏ, có đầu ra và người phụ trách.
- Rủi ro được xếp hạng và test bắt buộc được xác định.
- Ước lượng gồm phân tích, thiết kế, chuẩn bị, thực thi, kiểm thử lại và báo cáo.
- Công sức, thời lượng và năng lực khả dụng được tính riêng.
- Nghỉ phép, họp, hỗ trợ và công việc cam kết khác đã được trừ khỏi capacity.
- Phụ thuộc, đường găng, kỹ năng và quyền truy cập đã được kiểm tra.
- Giả định, bất định và khoảng dự phòng được ghi rõ.
- Phương án ưu tiên khi vượt năng lực đã được chuẩn bị.
- Người có thẩm quyền biết rủi ro còn lại và quyết định chấp nhận hoặc điều chỉnh.
- Tiến độ được cập nhật bằng kết quả thực tế và bằng chứng.
- Sau đợt kiểm thử, sai lệch giữa ước lượng và thực tế được ghi nhận để cải thiện lần sau.

Ước lượng nguồn lực trong thời hạn cố định là hoạt động quản lý rủi ro và ra quyết định. Khi nhóm phân biệt công sức với thời lượng, tính đúng năng lực khả dụng, ưu tiên theo tác động và cập nhật dự báo dựa trên thực tế, kế hoạch kiểm thử sẽ minh bạch hơn. Nếu phạm vi không thể hoàn thành an toàn trong thời gian được giao, bằng chứng và các phương án rõ ràng giúp người chịu trách nhiệm chọn cách xử lý có hiểu biết.
