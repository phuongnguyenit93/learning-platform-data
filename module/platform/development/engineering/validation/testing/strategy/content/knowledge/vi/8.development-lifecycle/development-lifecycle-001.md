# Thiết kế hoạt động kiểm thử trong mô hình tuần tự, lặp và gia tăng

Hoạt động kiểm thử cần được thiết kế phù hợp với cách sản phẩm được phát triển. Trong mô hình tuần tự, các giai đoạn thường được tổ chức theo trình tự và có mốc bàn giao rõ ràng. Trong mô hình lặp, nhóm liên tục xem xét và cải thiện giải pháp qua nhiều chu kỳ. Trong mô hình gia tăng, sản phẩm được xây dựng và bàn giao thành các phần có giá trị theo thời gian. Trên thực tế, nhiều nhóm kết hợp các cách tiếp cận này.

Cách tổ chức phát triển ảnh hưởng đến thời điểm lập kế hoạch kiểm thử, mức độ chi tiết của tài liệu, cách chuẩn bị môi trường, tần suất hồi quy và cách đưa bằng chứng vào quyết định phát hành. Tuy nhiên, mọi mô hình đều cần xác định mục tiêu chất lượng, rủi ro, tiêu chí chấp nhận, trách nhiệm và cách xử lý lỗi. Khác biệt chủ yếu nằm ở nhịp độ, trình tự và cách phản hồi được đưa trở lại quá trình phát triển.

## 1. Phân biệt mô hình tuần tự, lặp và gia tăng

Trước khi thiết kế hoạt động kiểm thử, cần hiểu cách công việc được chia nhỏ và cách nhóm nhận phản hồi.

- **Mô hình tuần tự (sequential):** công việc đi qua các giai đoạn tương đối rõ ràng, chẳng hạn phân tích yêu cầu, thiết kế, xây dựng, kiểm thử và triển khai. Một giai đoạn thường hoàn tất một phần đầu ra trước khi giai đoạn tiếp theo bắt đầu.
- **Mô hình lặp (iterative):** nhóm thực hiện nhiều chu kỳ để làm rõ, thử nghiệm và cải thiện giải pháp. Một vòng lặp có thể xem xét lại thiết kế, cách triển khai hoặc hành vi đã có dựa trên phản hồi.
- **Mô hình gia tăng (incremental):** sản phẩm được mở rộng qua các phần bổ sung. Mỗi phần có thể cung cấp một nhóm chức năng có giá trị và được tích hợp vào sản phẩm hiện có.
- **Mô hình lặp và gia tăng:** kết hợp cải tiến qua chu kỳ với việc bổ sung chức năng theo từng phần. Đây là cách tổ chức phổ biến trong các nhóm phát triển linh hoạt.
- **Mô hình xoắn ốc hoặc theo rủi ro:** mỗi vòng tập trung xác định mục tiêu, phân tích rủi ro, xây dựng hoặc thử nghiệm giải pháp, rồi đánh giá kết quả trước vòng tiếp theo.

Hai khái niệm lặp và gia tăng không giống nhau. Lặp nhấn mạnh việc xem lại và cải thiện; gia tăng nhấn mạnh việc thêm phần chức năng mới. Một nhóm có thể lặp lại thiết kế một tính năng nhiều lần trước khi đưa nó vào một increment, hoặc bàn giao increment nhỏ rồi tiếp tục cải thiện chúng.

| Đặc điểm | Tuần tự | Lặp | Gia tăng |
|---|---|---|---|
| Cách tổ chức | Theo giai đoạn và mốc bàn giao | Theo chu kỳ học hỏi và cải thiện | Theo phần chức năng được bổ sung |
| Yêu cầu | Thường được làm rõ sớm và quản lý thay đổi theo quy trình | Có thể được điều chỉnh qua phản hồi | Được chia thành phạm vi của từng increment |
| Kiểm thử | Có thể tập trung nhiều ở giai đoạn kiểm thử, nhưng cần chuẩn bị từ sớm | Diễn ra trong mỗi vòng lặp | Diễn ra cho từng phần và toàn bộ sản phẩm tích hợp |
| Phản hồi | Thường đến tại các mốc rà soát hoặc nghiệm thu | Được thu thập thường xuyên | Được thu thập khi từng increment được tích hợp hoặc bàn giao |
| Hồi quy | Tập trung vào thay đổi và toàn bộ hệ thống ở các mốc lớn | Chạy lặp lại sau mỗi thay đổi | Bảo vệ chức năng cũ khi thêm chức năng mới |
| Rủi ro điển hình | Phát hiện muộn nếu kiểm thử bị dồn về cuối | Chu kỳ nhanh nhưng có thể thiếu kiểm soát nếu không duy trì kỷ luật | Tích lũy lỗi tích hợp hoặc nợ kiểm thử giữa các increment |

Không có mô hình nào tự động bảo đảm chất lượng. Mô hình tuần tự vẫn có thể kiểm thử sớm thông qua rà soát yêu cầu và thiết kế. Nhóm lặp và gia tăng vẫn cần kế hoạch, tiêu chí và bằng chứng; chỉ là các nội dung đó được cập nhật thường xuyên hơn.

## 2. Thiết kế kiểm thử theo vòng đời thay vì đợi đến cuối

Kiểm thử là hoạt động xuyên suốt vòng đời phát triển. Ngay khi nhóm bắt đầu hiểu vấn đề, có thể rà soát yêu cầu và xác định rủi ro. Khi kiến trúc hình thành, nhóm có thể đánh giá khả năng kiểm thử, thiết kế dữ liệu và chuẩn bị môi trường. Khi mã nguồn được xây dựng, các phép kiểm tra tự động và thủ công cung cấp phản hồi. Khi hệ thống được triển khai, giám sát và phản hồi vận hành tiếp tục bổ sung bằng chứng.

Một chuỗi hoạt động tổng quát:

1. **Khám phá và phân tích:** hiểu người dùng, mục tiêu, yêu cầu, ràng buộc và rủi ro.
2. **Thiết kế giải pháp:** rà soát kiến trúc, giao diện, dữ liệu, bảo mật và khả năng kiểm thử.
3. **Xây dựng:** thực hiện kiểm thử đơn vị, thành phần, phân tích tĩnh và kiểm tra liên tục.
4. **Tích hợp:** kiểm thử hợp đồng, tích hợp, luồng dữ liệu và hành vi giữa các dịch vụ.
5. **Xác nhận sản phẩm:** kiểm thử đầu cuối, chấp nhận, phi chức năng và các rủi ro còn lại.
6. **Phát hành và vận hành:** kiểm tra triển khai, giám sát, xử lý sự cố và thu thập phản hồi.
7. **Học hỏi và cải tiến:** phân tích lỗi, cập nhật rủi ro, cải thiện yêu cầu, thiết kế và bộ kiểm thử.

Không nhất thiết mọi hoạt động phải diễn ra theo thứ tự cứng. Một số hoạt động song song hoặc được lặp lại nhiều lần. Ví dụ, nhóm có thể thiết kế test case cho API trong khi hợp đồng API vẫn đang được rà soát; kết quả rà soát sẽ cập nhật test case trước khi triển khai.

Nguyên tắc quan trọng là xác định hoạt động nào có thể bắt đầu từ thông tin hiện có, hoạt động nào phụ thuộc đầu ra của bước khác và thời điểm cần có bằng chứng để ra quyết định.

## 3. Thiết kế hoạt động kiểm thử trong mô hình tuần tự

Trong mô hình tuần tự, các giai đoạn và mốc bàn giao thường được xác định rõ. Điều này tạo điều kiện để lập kế hoạch, phân công và chuẩn bị bộ kiểm thử theo từng giai đoạn. Thách thức lớn là nếu nhóm hiểu kiểm thử chỉ bắt đầu sau khi xây dựng hoàn tất, sai lệch trong yêu cầu hoặc thiết kế có thể được phát hiện quá muộn.

### 3.1. Rà soát yêu cầu ngay trong giai đoạn phân tích

Khi yêu cầu được thu thập, người kiểm thử có thể tham gia rà soát để phát hiện:

- Thuật ngữ mơ hồ hoặc có nhiều cách hiểu.
- Quy tắc nghiệp vụ thiếu điều kiện, giá trị biên hoặc trạng thái ngoại lệ.
- Tiêu chí chấp nhận không quan sát hoặc đo lường được.
- Yêu cầu phi chức năng chưa có ngưỡng.
- Quyền truy cập, dữ liệu nhạy cảm và yêu cầu tuân thủ chưa được nêu.
- Phụ thuộc bên ngoài hoặc điều kiện môi trường chưa được xác định.

Từ yêu cầu, nhóm có thể xây dựng ma trận truy vết sơ bộ: yêu cầu nào cần kiểm thử, ở mức nào, bằng dữ liệu nào và ai xác nhận kết quả. Các điểm chưa rõ cần được đưa vào danh sách câu hỏi hoặc giả định có chủ sở hữu.

### 3.2. Chuẩn bị kiểm thử song song với thiết kế

Khi kiến trúc và thiết kế được phát triển, nhóm kiểm thử có thể:

- Rà soát luồng dữ liệu và ranh giới tin cậy.
- Xác định điểm tích hợp và hợp đồng API.
- Đánh giá khả năng quan sát, ghi log và xử lý lỗi.
- Lập kế hoạch môi trường, dữ liệu và công cụ.
- Thiết kế kiểm thử đơn vị, tích hợp, hệ thống và chấp nhận ở mức phù hợp.
- Xác định điều kiện bắt đầu, kết thúc và tiêu chí phát hành.

Mô hình V là một cách thể hiện mối quan hệ giữa hoạt động đặc tả ở phía phát triển và mức kiểm thử tương ứng ở phía xác minh. Ví dụ, yêu cầu nghiệp vụ liên quan đến kiểm thử chấp nhận; thiết kế hệ thống liên quan đến kiểm thử hệ thống; thiết kế kiến trúc và giao diện thành phần liên quan đến kiểm thử tích hợp; thiết kế chi tiết liên quan đến kiểm thử đơn vị.

Sơ đồ V không có nghĩa mọi bài kiểm thử chỉ được thiết kế sau khi giai đoạn bên trái hoàn tất. Nhóm có thể thiết kế sớm các phép thử từ tài liệu yêu cầu và tinh chỉnh khi thiết kế chi tiết hơn.

~~~mermaid
flowchart LR
    subgraph DEV["Đặc tả và xây dựng"]
        A["Yêu cầu nghiệp vụ"]
        B["Đặc tả hệ thống"]
        C["Thiết kế kiến trúc"]
        D["Thiết kế thành phần"]
        E["Lập trình"]
        A --> B --> C --> D --> E
    end
    subgraph TEST["Xác minh và xác nhận"]
        F["Kiểm thử đơn vị"]
        G["Kiểm thử tích hợp"]
        H["Kiểm thử hệ thống"]
        I["Kiểm thử chấp nhận"]
        E --> F --> G --> H --> I
    end
    A -. "Tiêu chí chấp nhận" .-> I
    B -. "Yêu cầu hệ thống" .-> H
    C -. "Giao diện và kiến trúc" .-> G
    D -. "Logic thành phần" .-> F
~~~

### 3.3. Thực thi và quản lý mốc kiểm thử

Khi sản phẩm được tích hợp đủ để kiểm thử, nhóm thực hiện theo kế hoạch và lưu bằng chứng theo từng mốc. Kết quả nên liên kết với phiên bản bản dựng, môi trường, dữ liệu và yêu cầu liên quan.

Ở mỗi mốc, cần xác định:

- Phạm vi chức năng và phi chức năng được kiểm tra.
- Điều kiện môi trường và dữ liệu.
- Các bài kiểm thử bắt buộc đã chạy và kết quả.
- Lỗi còn mở, mức độ nghiêm trọng và ảnh hưởng.
- Yêu cầu hoặc rủi ro chưa có bằng chứng.
- Người chịu trách nhiệm xử lý và thời hạn.
- Điều kiện để tiếp tục, nghiệm thu hoặc phát hành.

Nếu có thay đổi yêu cầu sau khi thiết kế test case, nhóm phải phân tích tác động đến tài liệu, mã kiểm thử, dữ liệu và kết quả đã có. Không nên xem một test pass trước khi thay đổi là bằng chứng cho yêu cầu mới.

### 3.4. Khi mô hình tuần tự phù hợp

Cách tiếp cận tuần tự thường hữu ích khi phạm vi tương đối ổn định, có mốc nghiệm thu chính thức, cần hồ sơ truy vết rõ hoặc có quy trình phê duyệt nhiều bên. Với hệ thống có yêu cầu an toàn, hợp đồng hoặc tuân thủ nghiêm ngặt, các mốc kiểm soát và hồ sơ có thể rất quan trọng.

Dù vậy, nhóm vẫn nên tìm lỗi sớm qua rà soát và phân tích trước khi xây dựng hoàn tất. Việc dồn mọi hoạt động kiểm thử về cuối làm tăng nguy cơ phát hiện vấn đề lớn khi thời gian sửa và thay đổi đã bị giới hạn.

## 4. Thiết kế hoạt động kiểm thử trong mô hình lặp

Mô hình lặp tạo ra nhiều chu kỳ để nhóm học hỏi từ kết quả và cải thiện giải pháp. Một vòng lặp có thể tập trung làm rõ yêu cầu, thử nghiệm thiết kế, xây dựng nguyên mẫu hoặc cải thiện một chức năng đã có.

Kiểm thử trong mô hình này cần cung cấp phản hồi đủ nhanh để nhóm có thể điều chỉnh ngay trong chu kỳ. Điều đó đòi hỏi các hoạt động kiểm thử phải được chuẩn bị trước, tiêu chí được làm rõ theo từng vòng và kết quả được đưa trở lại quyết định thiết kế.

### 4.1. Xác định mục tiêu kiểm thử cho từng vòng lặp

Mỗi vòng nên có mục tiêu cụ thể. Ví dụ:

- Xác minh giả thuyết về cách người dùng hoàn thành một nhiệm vụ.
- So sánh hai cách thiết kế một luồng thao tác.
- Đánh giá khả năng xử lý dữ liệu lớn.
- Kiểm tra tính khả thi của một tích hợp.
- Giảm rủi ro về hiệu năng hoặc bảo mật trước khi đầu tư xây dựng đầy đủ.

Mục tiêu kiểm thử cần nêu câu hỏi cần trả lời, phương pháp thu thập bằng chứng và điều kiện để quyết định tiếp tục, điều chỉnh hoặc dừng hướng phát triển.

Với nguyên mẫu, có thể dùng kiểm thử thăm dò, đánh giá sử dụng, mô phỏng dữ liệu hoặc thử nghiệm kỹ thuật. Không nên coi một nguyên mẫu chứng minh được tính khả thi giao diện là bằng chứng rằng hệ thống production đã đáp ứng yêu cầu về bảo mật, độ tin cậy hoặc khả năng mở rộng.

### 4.2. Lập kế hoạch và thực hiện trong mỗi vòng

Ở đầu vòng lặp, nhóm xác định thay đổi, rủi ro, tiêu chí chấp nhận và các phép kiểm tra cần có. Trong quá trình xây dựng, người phát triển và kiểm thử phối hợp để viết, chạy và điều chỉnh kiểm thử. Cuối vòng, nhóm đánh giá kết quả, lỗi còn lại và phản hồi từ người dùng hoặc bên liên quan.

Một nhịp làm việc minh họa:

| Thời điểm | Hoạt động kiểm thử | Đầu ra |
|---|---|---|
| Trước vòng lặp | Rà soát backlog, rủi ro, tiêu chí chấp nhận và phụ thuộc | Phạm vi kiểm thử và điều kiện hoàn thành |
| Khi bắt đầu | Chuẩn bị dữ liệu, môi trường, test charter hoặc test case | Sẵn sàng kiểm thử |
| Trong vòng | Unit test, component test, phân tích tĩnh, kiểm thử tích hợp và thăm dò | Phản hồi nhanh và lỗi được ghi nhận |
| Trước khi kết thúc | Hồi quy, kiểm thử chấp nhận và kiểm tra rủi ro liên quan | Bằng chứng cho increment hoặc thay đổi |
| Cuối vòng | Rà soát lỗi, khoảng trống, phản hồi và bài học | Cập nhật backlog, rủi ro và kế hoạch vòng sau |

Các hoạt động không cần chờ đến ngày cuối mới thực hiện. Kiểm thử nên chạy khi có phần chức năng đủ sẵn sàng, để lỗi được phát hiện trong khi người tạo ra thay đổi vẫn hiểu rõ bối cảnh.

### 4.3. Duy trì hồi quy qua nhiều vòng

Khi nhóm lặp lại thiết kế hoặc mã nguồn, một thay đổi có thể làm hỏng hành vi đã được xác nhận trước đó. Vì vậy, cần duy trì bộ kiểm thử hồi quy có chọn lọc.

Bộ hồi quy thường gồm:

- Kiểm thử đơn vị và thành phần cho quy tắc ổn định.
- Kiểm thử hợp đồng và tích hợp cho các ranh giới quan trọng.
- Một số kịch bản đầu cuối đại diện cho luồng người dùng trọng yếu.
- Kiểm thử bảo mật, hiệu năng hoặc tương thích khi thay đổi tác động đến các thuộc tính đó.

Không phải mọi test case đều cần chạy sau mọi thay đổi. Có thể chọn bộ kiểm thử theo phạm vi tác động, phụ thuộc và rủi ro; nhưng trước mốc phát hành cần chạy tập kiểm tra đủ rộng theo tiêu chí đã thống nhất.

### 4.4. Khi mô hình lặp phù hợp

Mô hình lặp hữu ích khi yêu cầu chưa hoàn toàn rõ, cần thử nghiệm giả thuyết hoặc sản phẩm cần cải thiện qua phản hồi. Nó cũng phù hợp khi rủi ro kỹ thuật cần được khám phá trước khi đầu tư lớn.

Thách thức là nhóm có thể liên tục thay đổi mà không cập nhật tiêu chí, tài liệu hoặc kiểm thử. Cần ghi lại quyết định và lý do thay đổi để kết quả của vòng trước vẫn có thể được hiểu và truy vết.

## 5. Thiết kế hoạt động kiểm thử trong mô hình gia tăng

Trong mô hình gia tăng, mỗi increment bổ sung một phần chức năng vào sản phẩm. Mỗi phần cần có chất lượng đủ để tích hợp với các phần hiện có và không phá vỡ hành vi đã bàn giao.

Một increment có thể gồm một luồng người dùng hoàn chỉnh hoặc một phần năng lực kỹ thuật. Cần xác định rõ phần nào được xem là hoàn thành, phụ thuộc nào đã sẵn sàng và phần nào chưa được đưa vào phạm vi phát hành.

### 5.1. Xác định tiêu chí cho từng increment

Mỗi increment cần có:

- Mục tiêu và giá trị nghiệp vụ.
- Phạm vi chức năng được bổ sung.
- Yêu cầu và tiêu chí chấp nhận.
- Rủi ro mới và rủi ro bị ảnh hưởng.
- Phụ thuộc đến thành phần hoặc dịch vụ hiện có.
- Kiểm thử ở cấp thành phần, tích hợp và người dùng.
- Tiêu chí hồi quy cho phần sản phẩm đã tồn tại.
- Bằng chứng và điều kiện chấp nhận.

Một increment chỉ hoàn thành khi đáp ứng tiêu chí chất lượng đã thống nhất, chứ không chỉ khi mã nguồn đã được viết hoặc demo được trên máy phát triển.

### 5.2. Kiểm thử increment và sản phẩm tích hợp

Có hai phạm vi cần được quan tâm:

1. **Kiểm thử phần tăng thêm:** xác minh chức năng mới hoạt động đúng với yêu cầu của increment.
2. **Kiểm thử sản phẩm tích hợp:** xác minh chức năng mới phối hợp đúng với các phần cũ, dữ liệu và dịch vụ liên quan.

Ví dụ, khi bổ sung chức năng hoàn tiền vào hệ thống thanh toán, nhóm cần kiểm tra quy tắc hoàn tiền, quyền phê duyệt và trạng thái giao dịch mới. Đồng thời phải kiểm tra chức năng này không làm hỏng thanh toán, báo cáo, đối soát hoặc lịch sử giao dịch đã có.

### 5.3. Quản lý phụ thuộc và tích hợp thường xuyên

Nếu nhiều nhóm xây dựng các increment riêng, tích hợp muộn có thể làm lộ xung đột giao diện hoặc giả định không tương thích. Nên xác định hợp đồng giữa các thành phần sớm, dùng contract test và tích hợp thường xuyên khi có thể.

Một số điểm cần quản lý:

- Phiên bản API và chính sách tương thích ngược.
- Schema và migration dữ liệu.
- Thứ tự triển khai giữa các dịch vụ.
- Feature flag và trạng thái tính năng chưa bật.
- Dữ liệu được tạo bởi phiên bản cũ và mới.
- Cách rollback hoặc tắt increment khi có sự cố.

### 5.4. Tránh tích lũy nợ kiểm thử

Nếu mỗi increment chỉ kiểm thử chức năng mới mà không duy trì hồi quy, lỗi có thể tích lũy và chỉ xuất hiện khi sản phẩm lớn hơn. Hãy dành thời gian trong mỗi increment để cập nhật test, dữ liệu, môi trường, tài liệu và khả năng quan sát.

Có thể theo dõi nợ kiểm thử như các mục chưa được tự động hóa, bài kiểm thử không ổn định, khu vực thiếu dữ liệu, rủi ro chưa có bằng chứng hoặc kiểm tra thủ công lặp lại. Mỗi mục cần mức ưu tiên và người phụ trách.

## 6. Kết hợp mô hình lặp và gia tăng trong quy trình linh hoạt

Trong cách phát triển lặp và gia tăng, nhóm thường chia công việc thành các vòng ngắn, mỗi vòng tạo ra một increment có thể kiểm tra và đánh giá. Kiểm thử là trách nhiệm chung của nhóm và diễn ra liên tục trong vòng, không phải một công đoạn bàn giao riêng ở cuối.

### 6.1. Làm rõ yêu cầu và tiêu chí chấp nhận

Trước khi bắt đầu một hạng mục, nhóm cần hiểu mục tiêu, quy tắc nghiệp vụ, trường hợp lỗi và điều kiện hoàn thành. Người kiểm thử có thể hỗ trợ đặt câu hỏi để làm rõ tiêu chí, ví dụ:

- Người dùng nào được thực hiện hành động?
- Dữ liệu đầu vào hợp lệ và không hợp lệ là gì?
- Trạng thái trước và sau thao tác được xác định ra sao?
- Khi dịch vụ phụ không sẵn sàng thì hệ thống phản hồi thế nào?
- Có yêu cầu về hiệu năng, bảo mật hoặc khả năng tiếp cận không?

Các ví dụ chấp nhận có thể được chuyển thành kiểm thử tự động hoặc thủ công tùy mức phù hợp. Việc trao đổi sớm giúp nhóm tránh hiểu khác nhau về kết quả cần đạt.

### 6.2. Tích hợp kiểm thử vào quy trình phát triển hằng ngày

Một luồng thường gặp:

- Khi tạo hoặc cập nhật mã nguồn, chạy kiểm tra định dạng, phân tích tĩnh và unit test.
- Khi mở pull request, chạy bộ kiểm tra nhanh và các kiểm tra phụ thuộc thay đổi.
- Khi tích hợp, chạy contract test, component test và integration test.
- Khi increment sẵn sàng, chạy hồi quy liên quan và kiểm thử chấp nhận.
- Trước phát hành, chạy tập kiểm thử rộng hơn theo rủi ro và tiêu chí phát hành.

Pipeline cần phản hồi đủ nhanh để không làm gián đoạn công việc. Nếu một phép kiểm tra tốn thời gian, có thể tổ chức chạy theo lịch hoặc trước mốc phát hành, miễn là rủi ro và yêu cầu bằng chứng được quản lý rõ.

### 6.3. Định nghĩa hoàn thành (Definition of Done)

Definition of Done (DoD) là thỏa thuận về điều kiện một hạng mục hoặc increment được xem là hoàn thành. DoD có thể bao gồm:

- Tiêu chí chấp nhận đã được đáp ứng.
- Kiểm thử đơn vị và các kiểm thử phù hợp đã chạy.
- Kiểm thử tích hợp hoặc hợp đồng liên quan đạt.
- Lỗi nghiêm trọng đã được xử lý hoặc có quyết định ngoại lệ hợp lệ.
- Rủi ro còn lại và phần chưa kiểm tra được ghi nhận.
- Tài liệu, log và khả năng giám sát cần thiết đã cập nhật.
- Mã nguồn được rà soát và tích hợp theo quy trình.
- Increment có thể triển khai theo điều kiện của nhóm.

DoD cần đủ rõ để các thành viên áp dụng nhất quán. Không nên đưa những điều kiện không thể thực hiện hoặc không liên quan đến loại hạng mục. Với thay đổi nhỏ, có thể dùng một tập tiêu chí tương ứng nhưng vẫn giữ các yêu cầu chất lượng bắt buộc.

### 6.4. Definition of Ready và sự sẵn sàng kiểm thử

Definition of Ready (DoR) thường mô tả điều kiện một hạng mục đủ rõ để nhóm bắt đầu thực hiện. Đây không phải tiêu chuẩn bắt buộc cho mọi nhóm, nhưng có thể giúp tránh nhận công việc còn thiếu thông tin quan trọng.

Một hạng mục có thể sẵn sàng khi:

- Mục tiêu và người dùng liên quan đã rõ.
- Tiêu chí chấp nhận có thể kiểm chứng.
- Phụ thuộc và giả định quan trọng đã được xác định.
- Dữ liệu hoặc quyền truy cập cần thiết có phương án chuẩn bị.
- Rủi ro đáng kể đã được xem xét.

DoR không có nghĩa mọi chi tiết đều phải biết trước. Các câu hỏi còn mở cần được ghi nhận và có cách xử lý trong vòng lặp.

## 7. Lựa chọn mức kiểm thử và nhịp phản hồi theo mô hình

Mô hình phát triển ảnh hưởng đến nhịp thực hiện, nhưng không quyết định cứng lớp kiểm thử nào phải có. Nhóm nên chọn dựa trên rủi ro và thời điểm có thể thu được bằng chứng.

| Hoạt động | Tuần tự | Lặp | Gia tăng / lặp-gia tăng |
|---|---|---|---|
| Rà soát yêu cầu | Trước khi chốt baseline và khi có thay đổi | Mỗi vòng khi giả thuyết hoặc yêu cầu được cập nhật | Mỗi increment và khi thay đổi phạm vi |
| Rà soát thiết kế | Trước khi triển khai các thành phần chính | Mỗi lần cải tiến kiến trúc hoặc thiết kế | Trước khi thêm thành phần hoặc thay đổi giao diện |
| Unit test | Trong khi xây dựng và tại mốc tích hợp | Liên tục trong mỗi vòng | Với mọi thay đổi có logic liên quan |
| Contract / integration test | Tại các mốc tích hợp và trước nghiệm thu | Sau thay đổi phụ thuộc hoặc hợp đồng | Mỗi increment có ranh giới tích hợp bị ảnh hưởng |
| System / end-to-end | Theo kế hoạch hệ thống và trước phát hành | Trong các vòng phù hợp, thường xuyên hồi quy luồng trọng yếu | Cho increment tích hợp và sản phẩm tổng thể |
| Kiểm thử chấp nhận | Theo mốc nghiệm thu | Thu thập phản hồi trong các vòng | Theo giá trị và tiêu chí của từng increment |
| Phi chức năng | Theo kế hoạch, mốc rủi ro và trước phát hành | Khi giả thuyết hoặc thay đổi tác động thuộc tính chất lượng | Khi increment ảnh hưởng tải, bảo mật, dữ liệu hoặc khả năng phục hồi |
| Hồi quy | Sau thay đổi và tại mốc lớn | Sau thay đổi trong mỗi vòng | Sau từng increment và trước phát hành |

Nhóm có thể điều chỉnh tần suất theo chi phí chạy, mức độ thay đổi và khả năng tự động hóa. Điều quan trọng là không để khoảng cách giữa các lần kiểm tra vượt quá mức rủi ro có thể chấp nhận.

## 8. Quản lý thay đổi, hồi quy và cấu hình qua các vòng đời

Khi sản phẩm được phát triển qua nhiều giai đoạn hoặc increment, thay đổi ở một phần có thể ảnh hưởng đến phần khác. Cần quản lý tác động và duy trì khả năng tái tạo kết quả.

Với mỗi thay đổi, xác định:

- Yêu cầu, thành phần và giao diện bị ảnh hưởng.
- Dữ liệu và trạng thái có thể thay đổi.
- Kiểm thử hiện có cần cập nhật hoặc chạy lại.
- Rủi ro mới và rủi ro cũ bị tác động.
- Môi trường và phiên bản cần kiểm chứng.
- Cách triển khai, tương thích ngược và quay lui.

Ma trận truy vết có thể nối yêu cầu, rủi ro, thay đổi, test case, kết quả và phiên bản bản dựng. Khi yêu cầu được sửa, nhóm có thể tìm các phép thử liên quan. Khi một test fail, nhóm có thể truy ngược đến yêu cầu hoặc rủi ro mà nó bảo vệ.

Cần quản lý phiên bản của dữ liệu kiểm thử, cấu hình môi trường, feature flag và phụ thuộc. Nếu kết quả được tạo trên một cấu hình không được ghi lại, nhóm có thể không tái hiện được lỗi hoặc không chứng minh được kết quả vẫn phù hợp sau thay đổi.

## 9. Ví dụ: phát triển nền tảng đặt hàng qua nhiều increment

Giả sử một nhóm xây dựng nền tảng đặt hàng trực tuyến theo từng increment:

- **Increment 1:** xem danh mục và thêm sản phẩm vào giỏ.
- **Increment 2:** tạo đơn hàng và tính phí vận chuyển.
- **Increment 3:** thanh toán và nhận trạng thái giao dịch.
- **Increment 4:** hủy đơn, hoàn tiền và xem lịch sử.

Trong mô hình gia tăng, mỗi increment cần kiểm thử phần mới và hồi quy phần đã có. Khi thêm tính phí vận chuyển, nhóm không chỉ kiểm tra công thức mà còn xác minh giỏ hàng vẫn hoạt động và tổng tiền được truyền đúng sang bước tạo đơn.

Khi thêm thanh toán, nhóm cần kiểm thử hợp đồng với nhà cung cấp, trạng thái giao dịch, retry, callback và quyền truy cập. Đồng thời chạy lại các luồng tạo đơn, tính phí và hiển thị giỏ hàng để phát hiện lỗi tích hợp.

Khi thêm hoàn tiền, cần xác minh trạng thái đơn hàng, số tiền được hoàn, quyền phê duyệt, lịch sử giao dịch và đối soát. Các quy tắc của thanh toán trước đó vẫn cần được bảo vệ bằng hồi quy.

Nếu nhóm áp dụng cách lặp, mỗi increment có thể trải qua nhiều vòng: thử nghiệm luồng, nhận phản hồi, điều chỉnh tiêu chí, cải thiện thiết kế và chạy lại kiểm thử. Ví dụ, nhóm có thể phát hiện người dùng không hiểu trạng thái “đang xử lý” sau timeout; vòng tiếp theo sẽ cải thiện nội dung giao diện và kiểm tra lại hành vi retry để bảo đảm không tạo giao dịch trùng.

Ma trận dưới đây minh họa cách phân bổ:

| Increment | Kiểm thử phần mới | Hồi quy cần thiết | Bằng chứng trước khi chấp nhận |
|---|---|---|---|
| 1. Danh mục và giỏ hàng | Tìm kiếm, lọc, thêm/xóa sản phẩm, số lượng | Đăng nhập và hiển thị danh mục | Kết quả luồng giỏ hàng và tính đúng số lượng |
| 2. Tạo đơn | Tính tổng, phí vận chuyển, địa chỉ và xác nhận | Danh mục, giỏ hàng và dữ liệu người dùng | Đơn hàng và tổng tiền được lưu nhất quán |
| 3. Thanh toán | Contract, callback, retry, idempotency | Tạo đơn, tính phí và trạng thái giỏ hàng | Mã giao dịch, trạng thái đơn và kết quả đối soát |
| 4. Hủy và hoàn tiền | Quyền, điều kiện hủy, số tiền hoàn và lịch sử | Thanh toán, tạo đơn và báo cáo | Trạng thái, số tiền và lịch sử giao dịch nhất quán |

Trước mỗi lần phát hành, nhóm vẫn cần đánh giá toàn bộ sản phẩm trong phạm vi rủi ro phù hợp. Việc từng increment được chấp nhận không tự động chứng minh sản phẩm tích hợp cuối cùng đạt yêu cầu.

## 10. Chọn mô hình lai và điều chỉnh theo rủi ro

Nhiều dự án không theo một mô hình thuần túy. Một tổ chức có thể quản lý hợp đồng, kiến trúc và phê duyệt theo mốc tuần tự, trong khi các nhóm kỹ thuật phát triển tính năng theo vòng lặp và increment. Sản phẩm cũng có thể triển khai liên tục nhưng vẫn cần một đợt kiểm thử chấp nhận hoặc phê duyệt chính thức.

Khi kết hợp, cần xác định rõ:

- Những quyết định nào được chốt ở cấp chương trình hoặc dự án.
- Những phần nào được phép thay đổi trong từng vòng.
- Tiêu chí chất lượng chung và tiêu chí riêng của từng increment.
- Cách tích hợp kết quả từ các nhóm.
- Ai chịu trách nhiệm cho kiểm thử xuyên hệ thống.
- Bằng chứng nào bắt buộc trước mốc nghiệm thu hoặc phát hành.

Với rủi ro cao, nhóm có thể tăng mức rà soát thiết kế, kiểm thử độc lập, kiểm thử bảo mật và hồ sơ truy vết. Với tính năng ít rủi ro, có thể dùng kiểm tra tự động nhanh và đánh giá theo thay đổi. Quyết định cần dựa trên hậu quả, độ phức tạp và khả năng phát hiện khi vận hành.

## 11. Các sai lầm thường gặp khi thiết kế kiểm thử theo vòng đời

**Dồn kiểm thử về cuối mô hình tuần tự.** Lỗi yêu cầu và kiến trúc được phát hiện khi sửa đổi đã tốn kém. Hãy tham gia rà soát từ giai đoạn đầu và thiết kế kiểm thử song song với đặc tả.

**Cho rằng nhóm lặp không cần kế hoạch.** Vòng ngắn vẫn cần mục tiêu, phạm vi, dữ liệu, tiêu chí và trách nhiệm. Cập nhật kế hoạch theo vòng không đồng nghĩa bỏ kế hoạch.

**Chỉ kiểm thử chức năng mới trong increment.** Thay đổi có thể ảnh hưởng hành vi cũ. Cần hồi quy theo tác động và rủi ro.

**Tích hợp muộn.** Các thành phần được phát triển riêng có thể không tương thích khi ghép lại. Hãy xác định hợp đồng và tích hợp thường xuyên.

**Để nợ kiểm thử tích lũy.** Test không ổn định, thiếu dữ liệu hoặc thiếu kiểm tra ranh giới có thể làm giảm chất lượng qua từng vòng. Cần đưa việc xử lý vào backlog và theo dõi.

**Nhầm demo với nghiệm thu.** Một phần chức năng chạy được trong tình huống trình diễn chưa chứng minh đáp ứng mọi tiêu chí, quyền truy cập, lỗi và điều kiện vận hành.

**Không cập nhật bằng chứng khi yêu cầu thay đổi.** Test pass cho phiên bản yêu cầu cũ không xác nhận phiên bản yêu cầu mới. Cần phân tích tác động và chạy lại phép thử phù hợp.

## 12. Checklist thiết kế hoạt động kiểm thử theo vòng đời

Trước khi thống nhất cách tiếp cận, hãy kiểm tra:

- Mô hình phát triển thực tế là tuần tự, lặp, gia tăng hay kết hợp?
- Các giai đoạn, vòng lặp, increment và mốc phát hành đã rõ chưa?
- Rủi ro và tiêu chí chất lượng được xem xét từ giai đoạn nào?
- Ai tham gia rà soát yêu cầu, thiết kế, mã nguồn và kết quả?
- Các phép kiểm thử được thiết kế sớm và cập nhật khi có thay đổi chưa?
- Mỗi vòng hoặc increment có tiêu chí chấp nhận và điều kiện hoàn thành không?
- Kiểm thử phần mới có đi kèm hồi quy cho phần bị ảnh hưởng không?
- Các hợp đồng và phụ thuộc có được kiểm tra trước khi tích hợp muộn không?
- Dữ liệu, môi trường, cấu hình và phiên bản có thể tái tạo không?
- Pipeline có cung cấp phản hồi đúng thời điểm và đủ tin cậy không?
- Rủi ro còn lại, lỗi chưa xử lý và ngoại lệ có người chịu trách nhiệm không?
- Có bằng chứng phù hợp trước các mốc nghiệm thu và phát hành không?
- Kết quả vận hành và sự cố có được đưa trở lại vòng phát triển tiếp theo không?

Sơ đồ tổng quát sau thể hiện cách kiểm thử được nối với các hoạt động phát triển qua nhiều mô hình:

~~~mermaid
flowchart TD
    A["Bối cảnh, yêu cầu và rủi ro"] --> B["Lập kế hoạch và tiêu chí kiểm thử"]
    B --> C["Thiết kế và xây dựng"]
    C --> D["Kiểm thử sớm ở cấp thành phần"]
    D --> E["Tích hợp increment"]
    E --> F["Kiểm thử tích hợp, hệ thống và hồi quy"]
    F --> G["Đánh giá phản hồi và rủi ro còn lại"]
    G --> H{"Tiếp tục lặp / thêm increment?"}
    H -->|Có| B
    H -->|Không| I["Nghiệm thu và phát hành"]
    I --> J["Giám sát và phản hồi vận hành"]
    J --> A
~~~

Thiết kế kiểm thử theo vòng đời giúp nhóm chọn đúng thời điểm, mức độ và phạm vi xác minh. Mô hình tuần tự cần hoạt động rà soát và chuẩn bị sớm để tránh phát hiện muộn; mô hình lặp cần phản hồi nhanh và cập nhật liên tục; mô hình gia tăng cần kiểm thử phần mới cùng hồi quy cho sản phẩm đã có. Khi mỗi cách tiếp cận đều gắn với rủi ro, tiêu chí và bằng chứng rõ ràng, kiểm thử trở thành một phần của quá trình tạo ra sản phẩm đáng tin cậy từ đầu đến vận hành.

