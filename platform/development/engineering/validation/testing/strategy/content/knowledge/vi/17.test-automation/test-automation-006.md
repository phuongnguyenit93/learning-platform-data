# Thử nghiệm nhỏ trước khi mở rộng phạm vi

## 1. Vì sao cần thử nghiệm nhỏ trước khi mở rộng tự động hóa?

Tự động hóa kiểm thử có thể rút ngắn thời gian phản hồi, tăng khả năng lặp lại và hỗ trợ nhóm phát hiện lỗi sớm. Tuy nhiên, xây dựng một bộ kiểm thử lớn ngay từ đầu cũng có thể tạo ra chi phí đáng kể: lựa chọn sai công cụ, kiến trúc khó bảo trì, kiểm thử chập chờn, dữ liệu không ổn định, pipeline quá chậm hoặc các kịch bản không phản ánh rủi ro thực tế.

Một thử nghiệm nhỏ giúp nhóm kiểm tra giả định quan trọng bằng phạm vi giới hạn trước khi đầu tư rộng. Thử nghiệm cần đủ đại diện để bộc lộ vấn đề kỹ thuật và vận hành, nhưng đủ nhỏ để có thể hoàn thành, đánh giá và điều chỉnh nhanh. Kết quả của nó giúp quyết định nên mở rộng, thay đổi cách làm, thử phương án khác hay dừng đầu tư.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, thử nghiệm nhỏ không chỉ là viết vài script để chứng minh công cụ chạy được. Cần kiểm tra toàn bộ lát cắt của quy trình tự động hóa: chọn mục tiêu có giá trị, chuẩn bị dữ liệu và môi trường, thiết kế kiểm thử, chạy trong pipeline, thu thập bằng chứng, xử lý lỗi, duy trì và đánh giá chi phí. Một thử nghiệm thành công phải cho thấy nhóm có thể vận hành giải pháp một cách đáng tin cậy trong điều kiện gần với công việc thực tế.

Ví dụ, trước khi tự động hóa hàng trăm luồng giao diện, nhóm có thể chọn một hành trình đăng nhập quan trọng, tạo dữ liệu riêng, chạy trên trình duyệt được hỗ trợ trong CI, thu thập ảnh và log khi thất bại, rồi đo thời gian chạy và tỷ lệ chập chờn qua nhiều lần thực thi. Kết quả cho biết vấn đề nằm ở công cụ, ứng dụng, dữ liệu, môi trường hay cách thiết kế test.

## 2. Phân biệt thử nghiệm nhỏ, proof of concept và pilot

Các nhóm có thể dùng thuật ngữ khác nhau, nhưng nên thống nhất mục đích của từng hoạt động:

| Hoạt động | Câu hỏi chính | Phạm vi và đầu ra |
|---|---|---|
| Proof of concept (PoC) | Giải pháp hoặc kỹ thuật có khả thi về mặt nguyên lý không? | Thử một năng lực hoặc rủi ro kỹ thuật cụ thể; đầu ra là kết luận khả thi và giới hạn |
| Thử nghiệm nhỏ (small experiment) | Giả định quan trọng có đúng trong bối cảnh sản phẩm và nhóm này không? | Một lát cắt đại diện từ thiết kế đến thực thi; đầu ra là dữ liệu để ra quyết định |
| Pilot | Nhóm có thể vận hành giải pháp trong công việc thực tế với phạm vi được kiểm soát không? | Một nhóm, dịch vụ hoặc tập hành trình giới hạn; đầu ra là quy trình đã được kiểm chứng và kế hoạch mở rộng |
| Mở rộng (scale-out) | Có thể nhân rộng mà vẫn giữ chất lượng và chi phí trong giới hạn không? | Tăng dần phạm vi, số nhóm, hệ thống hoặc loại kiểm thử với các cổng đánh giá |

PoC có thể chỉ xác minh rằng một thư viện điều khiển trình duyệt hoạt động. Thử nghiệm nhỏ cần chứng minh thêm rằng thư viện đó có thể kiểm tra một hành trình thực tế, xử lý dữ liệu, chạy ổn định và tạo kết quả dễ chẩn đoán. Pilot đi xa hơn khi đưa cách làm vào lịch phát triển hoặc pipeline của một nhóm trong thời gian đủ để quan sát công sức bảo trì.

Không nên gọi một demo chạy một lần là pilot thành công. Một lần chạy xanh chỉ cho thấy một trường hợp đã chạy thành công tại một thời điểm. Độ tin cậy cần được đánh giá qua nhiều lần chạy, nhiều trạng thái dữ liệu và các tình huống thất bại có kiểm soát.

## 3. Xác định vấn đề và giả thuyết trước khi chọn công cụ

### 3.1. Bắt đầu từ vấn đề kiểm thử

Trước khi chọn framework hoặc nền tảng, hãy xác định vấn đề hiện tại. Có thể nhóm đang gặp:

- Hồi quy thủ công mất nhiều thời gian sau mỗi thay đổi.
- Lỗi ở API hoặc hợp đồng được phát hiện muộn.
- Một hành trình nghiệp vụ quan trọng thường bị lỗi nhưng ít được kiểm tra.
- Kiểm thử chạy trên máy cá nhân nhưng không tái lập được trong CI.
- Nhiều nhóm tạo script trùng lặp và không có chuẩn dữ liệu chung.
- Kết quả kiểm thử khó hiểu, thiếu log hoặc không chỉ ra nguyên nhân thất bại.
- Bộ kiểm thử hiện có chậm, chập chờn hoặc tốn nhiều công sức duy trì.

Mô tả vấn đề bằng dữ liệu khi có thể. Ví dụ: “Hồi quy thanh toán mất khoảng ba giờ cho mỗi đợt phát hành, thực hiện thủ công bởi hai người và thường chỉ kiểm tra luồng thành công.” Câu mô tả này tạo cơ sở so sánh với thử nghiệm tự động sau đó.

### 3.2. Viết giả thuyết có thể kiểm chứng

Một giả thuyết tốt nêu thay đổi dự kiến, kết quả mong đợi và cách đo. Có thể dùng mẫu:

> Nếu **[nhóm/phạm vi]** áp dụng **[cách tự động hóa]** cho **[hành vi hoặc rủi ro]**, thì **[kết quả có thể đo]** sẽ cải thiện mà **[giới hạn chất lượng/chi phí]** vẫn được đáp ứng, vì **[lý do]**.

Ví dụ:

> Nếu tự động hóa một tập nhỏ API trọng yếu trong pipeline pull request, nhóm có thể phát hiện lỗi hợp đồng trước khi tích hợp, giữ thời gian phản hồi dưới mục tiêu của pipeline và duy trì tỷ lệ kiểm thử chập chờn ở mức chấp nhận được.

Giả thuyết không nên chỉ là “dùng công cụ X sẽ tốt hơn”. Cần nêu “tốt hơn” nghĩa là gì: phát hiện lỗi sớm hơn, giảm thời gian thực thi, giảm thao tác lặp, tăng khả năng bao phủ rủi ro hay cải thiện khả năng tái lập.

### 3.3. Tách giả định và điều đã biết

Ghi riêng những điều đã được xác nhận và những điều đang giả định. Ví dụ, nhóm có thể biết API có môi trường sandbox nhưng chưa biết sandbox có cho phép tạo lỗi timeout ổn định hay không. Có thể biết pipeline hỗ trợ container nhưng chưa biết thời gian khởi tạo có phù hợp với ngưỡng phản hồi.

Ưu tiên thử nghiệm các giả định có ảnh hưởng lớn đến quyết định đầu tư. Nếu một giả định sai sẽ khiến giải pháp không thể triển khai hoặc chi phí tăng mạnh, cần kiểm tra nó sớm.

## 4. Chọn phạm vi nhỏ nhưng đủ đại diện

### 4.1. Chọn một lát cắt có giá trị

Phạm vi thử nghiệm nên nhỏ nhưng có ý nghĩa với sản phẩm. Có thể chọn:

- Một hành trình người dùng quan trọng.
- Một API có nhiều consumer hoặc thay đổi thường xuyên.
- Một quy tắc nghiệp vụ có rủi ro cao.
- Một luồng hồi quy được thực hiện lặp lại nhiều lần.
- Một nhóm kiểm thử có môi trường và dữ liệu tương đối ổn định.
- Một thành phần đang gây thời gian chờ hoặc lỗi tích hợp.

Không nhất thiết chọn chức năng dễ nhất. Nếu chỉ chọn trường hợp đơn giản, thử nghiệm có thể thành công nhưng không cung cấp thông tin về khả năng xử lý các vấn đề thực tế. Cũng không nên chọn toàn bộ hệ thống phức tạp ngay từ đầu vì khó xác định nguyên nhân khi thất bại.

### 4.2. Tiêu chí chọn phạm vi

| Tiêu chí | Câu hỏi | Lý do |
|---|---|---|
| Giá trị/rủi ro | Nếu có lỗi, tác động đến người dùng hoặc nghiệp vụ thế nào? | Ưu tiên hành vi đáng được kiểm tra thường xuyên |
| Tần suất lặp | Kịch bản có được chạy thường xuyên không? | Tự động hóa có cơ hội giảm thao tác lặp và tạo giá trị tích lũy |
| Độ ổn định | Quy tắc và giao diện đã đủ ổn định chưa? | Tránh đo chi phí bảo trì quá lớn do yêu cầu thay đổi liên tục |
| Khả năng kiểm thử | Có thể chuẩn bị dữ liệu, trạng thái và môi trường không? | Bảo đảm thử nghiệm có thể tái lập |
| Tính đại diện | Kịch bản có phản ánh công nghệ, phụ thuộc và khó khăn thực tế không? | Kết quả có giá trị khi mở rộng |
| Khả năng đo | Có thể đo thời gian, độ ổn định, chất lượng và công sức không? | Tạo căn cứ ra quyết định |
| Phạm vi ảnh hưởng | Nếu test lỗi hoặc chạy sai, có gây tác động không mong muốn không? | Giữ thử nghiệm an toàn và dễ khôi phục |

### 4.3. Giới hạn phạm vi và tiêu chí loại trừ

Ghi rõ điều gì nằm trong và ngoài thử nghiệm. Ví dụ, thử nghiệm tự động hóa API đặt hàng có thể bao gồm tạo đơn, xác thực và kiểm tra trạng thái; chưa bao gồm tải cực đại, hệ thống thanh toán thật hoặc dữ liệu khách hàng thật.

Nêu lý do loại trừ và cách kiểm soát rủi ro liên quan. Không để người đọc suy ra rằng những phần chưa thử đã được xác nhận. Nếu một phụ thuộc thật không sẵn sàng, có thể dùng simulator để kiểm tra một phần hành vi nhưng phải ghi rõ giới hạn và lên kế hoạch kiểm tra tích hợp thật khi phù hợp.

## 5. Thiết kế thử nghiệm từ đầu đến cuối

Một thử nghiệm nhỏ nên bao gồm toàn bộ những thành phần cần thiết để vận hành kiểm thử tự động:

1. Xác định yêu cầu, rủi ro và tiêu chí chấp nhận.
2. Chọn một tập kịch bản đại diện và dữ liệu cần thiết.
3. Chọn tầng kiểm thử, công cụ và cấu trúc mã phù hợp.
4. Chuẩn bị môi trường có thể tái lập.
5. Tích hợp chạy tự động vào pipeline hoặc lịch chạy.
6. Thu thập kết quả và bằng chứng khi đạt hoặc thất bại.
7. Đo độ ổn định, tốc độ, chi phí và công sức bảo trì.
8. Đánh giá kết quả so với giả thuyết và quyết định bước tiếp theo.

### 5.1. Chọn loại kiểm thử

| Loại kiểm thử | Phù hợp khi | Rủi ro cần lưu ý |
|---|---|---|
| Unit test | Logic nhỏ, quy tắc tính toán hoặc chuyển trạng thái | Có thể phụ thuộc quá nhiều vào chi tiết nội bộ và bỏ qua tích hợp |
| Component/repository test | Cần xác nhận thành phần với database hoặc phụ thuộc cụ thể | Cần quản lý môi trường, schema và dữ liệu |
| API test | Giao diện có hợp đồng rõ, cần phản hồi nhanh | Cần kiểm tra cả ngữ nghĩa, quyền, lỗi và tác dụng phụ |
| Contract test | Nhiều dịch vụ phát hành độc lập và cần bảo vệ tương thích | Hợp đồng có thể không bao phủ toàn bộ hành vi đầu cuối |
| UI/end-to-end test | Cần xác nhận một số hành trình người dùng trọng yếu | Dễ chậm và chập chờn nếu phụ thuộc môi trường hoặc selector không ổn định |
| Performance test | Có mục tiêu tải, độ trễ hoặc tài nguyên cần xác nhận | Kết quả không có ý nghĩa nếu môi trường và mô hình tải không đại diện |

Chọn tầng có phản hồi nhanh và ổn định nhất có thể cho rủi ro cần kiểm tra. Không tự động hóa giao diện chỉ vì người dùng tương tác qua giao diện; nhiều quy tắc có thể được xác nhận đáng tin cậy hơn ở tầng API hoặc thành phần.

### 5.2. Chọn số lượng kịch bản

Một thử nghiệm ban đầu thường chỉ cần một tập nhỏ kịch bản, nhưng cần có cả đường thành công và một số tình huống quan trọng như dữ liệu biên, quyền, lỗi phụ thuộc hoặc trạng thái không hợp lệ. Số lượng cụ thể tùy độ phức tạp; mục tiêu là kiểm tra giả thuyết chứ không đạt một con số test tùy ý.

Nên ưu tiên kịch bản có kết quả mong đợi rõ ràng và có thể tái lập. Nếu kịch bản cần phán đoán của con người hoặc yêu cầu còn thay đổi, có thể giữ hoạt động đó ở dạng thủ công trong thử nghiệm đầu tiên.

### 5.3. Xác định kết quả mong đợi

Mỗi test cần kiểm tra kết quả có ý nghĩa với yêu cầu. Tránh chỉ xác nhận trang tải được hoặc API trả mã thành công. Ví dụ, với thanh toán, cần kiểm tra trạng thái giao dịch, số lượng giao dịch, số tiền và khả năng đối soát theo hợp đồng.

Assertion quá yếu khiến test xanh giả; assertion quá chặt vào chi tiết không được cam kết khiến test dễ vỡ khi implementation thay đổi mà hành vi vẫn đúng. Cần cân bằng giữa tính chính xác và khả năng bảo trì.

## 6. Chọn công cụ và kiến trúc vừa đủ

Thử nghiệm nhỏ là cơ hội kiểm tra công cụ trong bối cảnh thực tế. Tiêu chí chọn có thể gồm:

- Hỗ trợ ngôn ngữ, giao thức, nền tảng và loại kiểm thử cần thiết.
- Khả năng tích hợp với hệ thống build, CI/CD và quản lý mã nguồn.
- Cách tạo, quản lý và dọn dữ liệu kiểm thử.
- Khả năng chạy song song, báo cáo, lưu artifact và chẩn đoán lỗi.
- Độ ổn định, tốc độ, khả năng mở rộng và tính tương thích.
- Kỹ năng hiện có của nhóm và chi phí đào tạo.
- Chi phí giấy phép, hạ tầng, bảo trì và hỗ trợ.
- Khả năng thay thế hoặc di chuyển nếu công cụ không còn phù hợp.

Không nên chọn chỉ vì công cụ phổ biến hoặc có nhiều tính năng. Một công cụ phù hợp là công cụ giải quyết được vấn đề cần thử, có thể vận hành bởi nhóm và không tạo chi phí ẩn vượt quá giá trị.

### 6.1. Giữ kiến trúc thử nghiệm đơn giản

Trong giai đoạn đầu, chỉ tạo những lớp dùng chung khi đã có nhu cầu lặp lại rõ ràng. Có thể bắt đầu với:

- Cấu hình môi trường được tách khỏi mã kiểm thử.
- Hàm hoặc fixture tạo dữ liệu và dọn dữ liệu.
- Một cách thống nhất để gọi API hoặc thao tác giao diện.
- Assertion diễn đạt kết quả nghiệp vụ.
- Cơ chế chụp log, ảnh hoặc trace khi thất bại.
- Lệnh chạy cục bộ và cấu hình pipeline có thể lặp lại.

Tránh xây dựng một framework lớn với nhiều lớp trừu tượng trước khi biết nhóm cần gì. Abstraction quá sớm có thể che giấu hành vi, làm khó debug và tăng chi phí thay đổi.

### 6.2. Quản lý mã nguồn và cấu trúc

Đặt test gần thành phần hoặc trong repository kiểm thử theo quy ước nhóm. Mã test cần được review như mã sản phẩm: có tên rõ, dữ liệu xác định, assertion có ý nghĩa và không phụ thuộc thứ tự chạy. Thay đổi test cần gắn với yêu cầu hoặc lý do cụ thể.

Ví dụ cấu trúc tối giản:

```text
tests/
  api/
    orders.create.spec.ts
  fixtures/
    test-data.ts
  helpers/
    api-client.ts
  config/
    environments.ts
  reports/
```

Đây chỉ là ví dụ. Chọn cấu trúc phù hợp ngôn ngữ và framework hiện có, tránh tạo thư mục hoặc lớp không cần thiết cho phạm vi thử nghiệm.

## 7. Chuẩn bị môi trường và dữ liệu có thể tái lập

### 7.1. Môi trường

Môi trường thử nghiệm cần ghi rõ phiên bản ứng dụng, dịch vụ phụ thuộc, cấu hình, feature flag và giới hạn tài nguyên. Có thể dùng container, môi trường tạm thời hoặc sandbox nếu phù hợp. Không mặc định môi trường cục bộ giống CI hoặc sản xuất.

Nên có health check và cơ chế chờ dịch vụ sẵn sàng thay vì dùng sleep cố định. Khi test thất bại, cần biết môi trường có khỏe không để phân biệt lỗi sản phẩm với lỗi hạ tầng.

### 7.2. Dữ liệu

Dữ liệu nên được tạo theo từng test hoặc test run, có định danh riêng và có thể dọn dẹp. Tránh phụ thuộc vào một bản ghi dùng chung có trạng thái thay đổi. Test cần có thể chạy nhiều lần và chạy song song mà không ảnh hưởng nhau.

Không dùng dữ liệu cá nhân hoặc dữ liệu sản xuất chưa được phê duyệt. Secret và credential phải lấy từ cơ chế quản lý phù hợp, không ghi cứng trong repository hoặc log.

### 7.3. Phụ thuộc ngoài

Với phụ thuộc không ổn định hoặc tốn phí, có thể dùng mock, fake hoặc simulator trong một số test. Tuy nhiên, cần duy trì ít nhất một số kiểm tra tích hợp thật khi rủi ro yêu cầu. Ghi rõ phần nào được mô phỏng và phần nào đã được xác nhận với dịch vụ thật.

## 8. Đưa thử nghiệm vào pipeline một cách có kiểm soát

### 8.1. Chọn điểm chạy phù hợp

Có thể bắt đầu bằng lệnh chạy thủ công trong CI hoặc pipeline riêng trước khi đưa vào cổng bắt buộc. Khi đã đủ ổn định, chọn điểm chạy:

- Pull request: test nhanh, ổn định, phản hồi sớm.
- Sau khi tích hợp: kiểm thử API, hợp đồng hoặc thành phần có phụ thuộc.
- Theo lịch: bộ kiểm thử dài, kiểm thử tải hoặc kiểm tra môi trường chuyên biệt.
- Trước phát hành: tập hồi quy trọng yếu và các kiểm tra bắt buộc.
- Sau triển khai: smoke test và kiểm tra hành trình quan trọng.

Không đưa một bộ test chậm hoặc chưa ổn định vào cổng chặn pull request ngay từ đầu. Trước hết cần đo thời gian, xác định nguyên nhân thất bại và thiết lập cách xử lý.

### 8.2. Làm cho kết quả dễ chẩn đoán

Khi test thất bại, pipeline nên cung cấp:

- Tên test và bước assertion thất bại.
- Phiên bản commit/build và môi trường.
- Log đã làm sạch, ảnh hoặc trace cần thiết.
- Dữ liệu thử nghiệm hoặc định danh để tái hiện.
- Thời gian chạy và trạng thái phụ thuộc.
- Liên kết tới yêu cầu, lỗi hoặc hồ sơ kiểm thử liên quan.

Một pipeline chỉ báo “test failed” mà không có bằng chứng sẽ khiến nhóm mất thời gian tái hiện. Tuy nhiên, không lưu toàn bộ dữ liệu nhạy cảm chỉ để debug; cần lọc và giới hạn quyền truy cập artifact.

### 8.3. Chính sách retry và flaky test

Không dùng retry vô hạn để làm cho pipeline xanh. Nếu cần retry nhằm xác định lỗi chập chờn, ghi lại cả lần thất bại ban đầu và kết quả retry. Theo dõi tỷ lệ flaky, phân loại nguyên nhân và đặt thời hạn xử lý.

Nếu tạm cách ly test không ổn định, ghi rõ rủi ro mất bao phủ, người phụ trách và thời điểm đưa lại vào pipeline. Không âm thầm bỏ qua kiểm thử quan trọng.

## 9. Đo lường kết quả thử nghiệm

Đánh giá thử nghiệm dựa trên nhiều chiều, không chỉ số lượng test đã viết.

| Nhóm đo | Chỉ số hoặc bằng chứng | Câu hỏi cần trả lời |
|---|---|---|
| Giá trị kiểm thử | Lỗi được phát hiện, rủi ro được xác nhận, yêu cầu có bằng chứng | Test có kiểm tra điều quan trọng không? |
| Độ ổn định | Tỷ lệ pass/fail lặp lại, tỷ lệ flaky, lỗi môi trường | Kết quả có đáng tin và tái lập được không? |
| Tốc độ | Thời gian khởi tạo, thời gian chạy, thời gian phản hồi pipeline | Nhóm nhận phản hồi có đủ nhanh không? |
| Khả năng chẩn đoán | Thời gian xác định nguyên nhân, chất lượng artifact | Khi thất bại, nhóm có biết cần làm gì không? |
| Chi phí | Thời gian viết, review, bảo trì, xử lý flaky và hạ tầng | Tổng chi phí có phù hợp với giá trị không? |
| Khả năng duy trì | Số người có thể sửa, tài liệu, độ phức tạp, phụ thuộc công cụ | Giải pháp có phụ thuộc vào một cá nhân không? |
| Tác động quy trình | Thời gian hồi quy, lỗi lọt ra, mức sử dụng của nhóm | Cách làm có cải thiện quy trình thực tế không? |

### 9.1. Đo đường cơ sở trước thử nghiệm

Nếu muốn đánh giá cải thiện, cần ghi mức nền trước khi áp dụng. Ví dụ: thời gian thực hiện hồi quy thủ công, số người tham gia, số lỗi thường phát hiện, thời gian chờ kết quả và tỷ lệ bỏ qua do thiếu thời gian.

Nếu không có dữ liệu lịch sử, có thể đo trong một khoảng thời gian đại diện trước thử nghiệm. Ghi rõ cách đo và giới hạn. Không so sánh một lần chạy tự động với một ước lượng thủ công không có căn cứ.

### 9.2. Đo độ ổn định qua nhiều lần chạy

Chạy thử nghiệm qua nhiều commit, thời điểm hoặc trạng thái dữ liệu phù hợp. Một test chạy xanh một lần không chứng minh nó ổn định. Cần theo dõi:

- Số lần chạy và số lần thành công/thất bại.
- Số lần thất bại do sản phẩm, môi trường, dữ liệu hoặc test.
- Tỷ lệ flaky và cách phân loại.
- Thời gian chạy trung vị và các lần chạy chậm bất thường.
- Số lần cần can thiệp thủ công.

Không nên đặt một ngưỡng pass rate chung áp dụng cho mọi thử nghiệm. Ngưỡng chấp nhận cần dựa trên rủi ro, loại test, môi trường và mục tiêu của pipeline. Với kiểm thử cổng phát hành, một lần thất bại thực sự có thể cần chặn dù tỷ lệ tổng thể rất cao.

### 9.3. Đánh giá chi phí vòng đời

Tổng chi phí không chỉ là thời gian viết test ban đầu. Cần tính cả:

- Thiết kế và review kịch bản.
- Chuẩn bị môi trường, dữ liệu và tài khoản.
- Bảo trì khi yêu cầu hoặc giao diện thay đổi.
- Điều tra flaky test và lỗi môi trường.
- Nâng cấp framework, runtime và dependency.
- Lưu trữ artifact, hạ tầng CI và giấy phép.
- Đào tạo và hỗ trợ các nhóm sử dụng.

So sánh chi phí này với giá trị giảm thao tác lặp, phát hiện lỗi sớm, giảm rủi ro và tăng khả năng phát hành. Không kỳ vọng mọi test đều hoàn vốn nhanh; ưu tiên những test chạy thường xuyên và bảo vệ hành vi có giá trị cao.

## 10. Tiêu chí quyết định sau thử nghiệm

Trước khi bắt đầu, thống nhất cách nhóm sẽ ra quyết định. Có thể dùng bốn kết quả:

| Quyết định | Khi phù hợp | Hành động tiếp theo |
|---|---|---|
| Mở rộng | Giả thuyết được hỗ trợ, kết quả ổn định, giá trị rõ và chi phí duy trì chấp nhận được | Tăng phạm vi từng bước, giữ các chỉ số và cổng đánh giá |
| Điều chỉnh rồi thử lại | Ý tưởng có giá trị nhưng công cụ, dữ liệu, kiến trúc hoặc quy trình còn điểm yếu có thể sửa | Xác định vấn đề, người phụ trách, phạm vi thử lại và tiêu chí mới |
| Thử phương án khác | Một giả định nền tảng không đúng hoặc giải pháp hiện tại không đáp ứng yêu cầu | So sánh công cụ/tầng kiểm thử/kiến trúc khác với cùng mục tiêu đo |
| Dừng | Giá trị thấp, rủi ro không kiểm soát được hoặc chi phí vượt lợi ích | Ghi lý do, giữ bài học và lựa chọn cách xác nhận khác |

Không coi dừng thử nghiệm là thất bại. Nếu thử nghiệm cho thấy một framework không phù hợp trước khi nhóm đầu tư hàng trăm test, đó là thông tin có giá trị.

### 10.1. Cổng mở rộng

Chỉ mở rộng khi các điều kiện quan trọng đã được đáp ứng. Ví dụ:

- Test bao phủ hành vi hoặc rủi ro đã chọn và có assertion có ý nghĩa.
- Môi trường và dữ liệu có thể tái lập, không gây ảnh hưởng ngoài phạm vi.
- Kết quả ổn định qua số lần chạy đủ đại diện.
- Thời gian phản hồi phù hợp với vị trí chạy trong pipeline.
- Khi thất bại, nhóm có thể xác định nguyên nhân với bằng chứng.
- Có người sở hữu và quy trình bảo trì.
- Chi phí hạ tầng và công sức nằm trong giới hạn đã thống nhất.
- Rủi ro còn lại và phần chưa bao phủ được ghi rõ.

Các ngưỡng định lượng cần được xác định trước theo bối cảnh. Không tự đặt một con số đẹp sau khi đã thấy kết quả để hợp thức hóa quyết định mở rộng.

## 11. Mở rộng theo từng giai đoạn

Sau khi thử nghiệm ban đầu đạt, mở rộng từng bước để kiểm soát rủi ro và học từ mỗi giai đoạn.

### Giai đoạn 1: Một lát cắt đại diện

Chọn một hành trình hoặc API quan trọng, xây dựng test, môi trường, dữ liệu và pipeline cơ bản. Mục tiêu là chứng minh cách làm có thể chạy và tạo bằng chứng.

### Giai đoạn 2: Mở rộng trong cùng thành phần

Thêm các trường hợp biên, lỗi, quyền và trạng thái liên quan. Kiểm tra liệu kiến trúc test có tái sử dụng được mà không tạo abstraction quá phức tạp. Đo tác động đến thời gian chạy và bảo trì.

### Giai đoạn 3: Thêm một thành phần hoặc nhóm khác

Kiểm tra khả năng dùng lại quy ước, fixture, báo cáo và pipeline ở một bối cảnh hơi khác. Đây là bước quan trọng để biết giải pháp có thể mở rộng ngoài nhóm ban đầu hay không.

### Giai đoạn 4: Chuẩn hóa và quản trị

Khi đã có đủ bằng chứng, chuẩn hóa hướng dẫn, quy ước đặt tên, quản lý dữ liệu, cách xử lý flaky test, review mã và trách nhiệm sở hữu. Đầu tư framework dùng chung chỉ khi có nhu cầu lặp lại thực tế.

### Giai đoạn 5: Tối ưu và rà soát định kỳ

Theo dõi giá trị, độ ổn định, tốc độ và chi phí. Loại bỏ test lỗi thời, sửa test chập chờn, điều chỉnh tầng kiểm thử và cập nhật theo rủi ro mới. Mở rộng không phải là tăng số lượng test vô hạn; mục tiêu là duy trì tập kiểm thử có giá trị.

## 12. Ví dụ thực tế

### Ví dụ A: Thử nghiệm tự động hóa API đặt hàng

Một nhóm thường kiểm tra thủ công API tạo đơn hàng trước mỗi lần phát hành. Nhóm chọn ba kịch bản: tạo đơn hợp lệ, từ chối khi thiếu tồn kho và gửi lại cùng idempotency key. Họ tạo dữ liệu riêng, chạy trên môi trường tích hợp và đưa test vào pipeline pull request.

Nhóm đo thời gian chạy, tỷ lệ flaky, số lỗi được phát hiện và thời gian điều tra khi thất bại. Sau nhiều lần chạy, test ổn định và phát hiện một lỗi trạng thái trước khi tích hợp. Nhóm quyết định mở rộng thêm kiểm tra mã giảm giá và quyền người dùng. Kiểm thử thanh toán thật vẫn được giữ ở sandbox theo kế hoạch riêng.

### Ví dụ B: Thử nghiệm tự động hóa giao diện

Một nhóm muốn giảm hồi quy thủ công cho luồng đăng nhập. Thay vì tự động hóa toàn bộ ứng dụng, nhóm chọn một luồng đăng nhập và một luồng đăng xuất trên trình duyệt được hỗ trợ. Họ dùng selector dựa trên vai trò/nhãn, tài khoản riêng theo test run và dọn session sau mỗi lần chạy.

Test chạy trong CI với ảnh chụp và log khi thất bại. Trong tuần đầu, một số lần chạy lỗi do dữ liệu tài khoản dùng chung và thời gian chờ cố định. Nhóm sửa việc cô lập tài khoản và thay sleep bằng chờ trạng thái cụ thể. Chỉ sau khi kết quả ổn định, nhóm mới thêm trường hợp khóa tài khoản và hết hạn phiên.

### Ví dụ C: Thử nghiệm kiểm thử hợp đồng giữa hai dịch vụ

Provider đơn hàng và consumer thanh toán được phát triển bởi hai nhóm độc lập. Nhóm chọn một tương tác quan trọng gồm request tạo giao dịch và response chứa mã giao dịch, trạng thái và số tiền. Consumer tạo contract test; provider xác minh hợp đồng trong pipeline.

Thử nghiệm phát hiện provider định đổi kiểu trường số tiền mà không cập nhật consumer. Nhờ có bằng chứng contract, hai nhóm thống nhất giữ kiểu cũ trong giai đoạn chuyển tiếp và lập kế hoạch phiên bản mới. Sau khi mở rộng, nhóm bổ sung các tương tác lỗi và webhook.

### Ví dụ D: Thử nghiệm kiểm thử hồi quy trên dữ liệu di trú

Một nhóm cần xác nhận chuyển đổi hồ sơ khách hàng. Thử nghiệm nhỏ chọn một tập dữ liệu tổng hợp có bản ghi chuẩn, trường rỗng, ký tự đặc biệt và định dạng cũ. Script tự động chạy chuyển đổi, đối chiếu số lượng và kiểm tra các trường trọng yếu.

Kết quả ban đầu cho thấy một quy tắc chuẩn hóa làm mất số 0 đầu của mã bưu chính. Nhóm sửa quy tắc và bổ sung assertion. Trước khi mở rộng sang dữ liệu lớn, nhóm kiểm tra thời gian chạy, khả năng khôi phục, log sai lệch và cách xử lý bản ghi lỗi. Dữ liệu thật chỉ được sử dụng khi có phê duyệt và kiểm soát phù hợp.

## 13. Mẫu kế hoạch thử nghiệm nhỏ

Có thể dùng mẫu sau để thống nhất mục tiêu, cách đo và quyết định:

```yaml
experiment:
  id: AUTO-EXP-004
  title: "Tự động hóa kiểm thử API tạo đơn hàng"
  owner: "Order team test lead"
  duration: "2 tuần"

problem:
  statement: "Hồi quy API đặt hàng đang được thực hiện thủ công và thường bị rút gọn khi thời gian phát hành gấp."
  baseline: "Ghi thời gian, người tham gia và số kịch bản thực hiện trong các đợt gần nhất."

hypothesis:
  statement: "Một tập API test nhỏ trong CI sẽ phát hiện lỗi luồng đặt hàng sớm hơn mà vẫn giữ phản hồi nhanh và ổn định."

scope:
  included:
    - "Tạo đơn hợp lệ"
    - "Thiếu tồn kho"
    - "Retry cùng idempotency key"
  excluded:
    - "Tải cực đại"
    - "Thanh toán trên hệ thống thật"

measures:
  - "Thời gian chạy và thời gian phản hồi pipeline"
  - "Số lần chạy, tỷ lệ flaky và nguyên nhân thất bại"
  - "Lỗi/rủi ro được phát hiện"
  - "Thời gian bảo trì và điều tra"

success_criteria:
  - "Các kịch bản trọng yếu có assertion nghiệp vụ rõ ràng"
  - "Kết quả tái lập qua số lần chạy đã thống nhất"
  - "Artifact đủ để điều tra thất bại"
  - "Chi phí duy trì nằm trong giới hạn nhóm chấp nhận"

risks:
  - "Dữ liệu dùng chung gây ảnh hưởng giữa các test"
  - "Môi trường tích hợp không ổn định"

decision:
  options: [expand, adjust_and_retry, try_alternative, stop]
  review_date: "2027-02-15"
```

Đây là mẫu minh họa, không phải cấu hình mặc định. Mục tiêu, thời lượng, ngưỡng và người sở hữu phải được xác định theo lịch phát hành và điều kiện thực tế. Nếu tiêu chí định lượng chưa có cơ sở, ghi rõ cách thu thập baseline trước khi đặt ngưỡng.

## 14. Quản lý rủi ro trong quá trình thử nghiệm

Thử nghiệm nhỏ vẫn có thể gây tác động nếu script sửa dữ liệu, gọi dịch vụ thật hoặc chạy trong pipeline dùng chung. Cần đánh giá rủi ro trước khi thực hiện:

- **Tác dụng phụ:** test có tạo đơn, gửi email, thanh toán hoặc thay đổi dữ liệu dùng chung không?
- **Phạm vi chạy:** pipeline có thể chạy trên nhánh hoặc môi trường không phù hợp không?
- **Bí mật:** credential và token được cấp, lưu và thu hồi như thế nào?
- **Tài nguyên:** test có gây tải hoặc chiếm dụng tài nguyên vượt mức không?
- **Dữ liệu:** dữ liệu có nhạy cảm, có thể nhận diện người dùng hoặc cần xóa sau thử nghiệm không?
- **Thất bại giữa chừng:** nếu script dừng, trạng thái dữ liệu và tài nguyên có được dọn dẹp không?
- **Rollback:** có thể hoàn nguyên thay đổi hoặc tắt pipeline nhanh không?

Giới hạn thử nghiệm bằng tài khoản, namespace, môi trường và dữ liệu riêng. Dùng feature flag hoặc sandbox cho hành động có tác dụng phụ. Đặt timeout, giới hạn tốc độ và bước cleanup. Có cơ chế dừng nếu test bắt đầu tác động ngoài phạm vi.

Nếu thử nghiệm thất bại, không tự động chạy lại các thao tác không idempotent. Trước tiên xác định lần chạy trước đã tạo tác dụng phụ nào và trạng thái dữ liệu hiện tại.

## 15. Những sai lầm thường gặp

- **Chọn công cụ trước khi xác định vấn đề:** thử nghiệm chứng minh công cụ có thể chạy nhưng không chứng minh giải quyết nhu cầu.
- **Chọn phạm vi quá dễ:** kết quả tốt nhưng không đại diện cho kiến trúc, dữ liệu hoặc rủi ro thực tế.
- **Chọn phạm vi quá lớn:** khó cô lập nguyên nhân và khó đánh giá chi phí.
- **Đo số lượng test thay vì giá trị:** nhiều script không đồng nghĩa nhiều rủi ro được kiểm soát.
- **Chỉ chạy một lần:** không có bằng chứng về độ ổn định và khả năng tái lập.
- **Không có baseline:** không thể kết luận quy trình đã nhanh hơn hoặc tiết kiệm hơn.
- **Assertion yếu:** test xanh dù hành vi nghiệp vụ sai.
- **Xây framework quá sớm:** abstraction và cấu hình tăng trước khi có nhu cầu dùng lại.
- **Không tính chi phí bảo trì:** chỉ đo thời gian viết ban đầu và bỏ qua flaky test, nâng cấp, dữ liệu và hạ tầng.
- **Đưa test chưa ổn định vào cổng bắt buộc:** làm chậm nhóm và tạo động lực bỏ qua kiểm tra.
- **Không ghi giới hạn:** người khác hiểu nhầm thử nghiệm đã xác nhận những phần nằm ngoài phạm vi.
- **Mở rộng tất cả cùng lúc:** khó biết yếu tố nào làm chất lượng hoặc chi phí thay đổi.
- **Không có người sở hữu:** test trở thành tài sản không ai sửa khi thất bại.
- **Không dừng khi giả thuyết bị bác bỏ:** tiếp tục đầu tư vì đã bỏ công ban đầu thay vì dựa vào bằng chứng.

## 16. Checklist trước khi mở rộng tự động hóa

### Trước thử nghiệm

- [ ] Vấn đề và baseline hiện tại được mô tả.
- [ ] Giả thuyết có kết quả đo được.
- [ ] Phạm vi đủ đại diện nhưng có giới hạn rõ.
- [ ] Yêu cầu, rủi ro và tiêu chí chấp nhận được xác định.
- [ ] Loại kiểm thử và công cụ được chọn theo nhu cầu.
- [ ] Môi trường, dữ liệu, credential và phụ thuộc được chuẩn bị.
- [ ] Người sở hữu và thời gian đánh giá được thống nhất.
- [ ] Rủi ro tác dụng phụ và phương án dừng/cleanup được xem xét.

### Trong thử nghiệm

- [ ] Test chạy được cục bộ và trong môi trường CI mục tiêu.
- [ ] Kết quả mong đợi phản ánh yêu cầu nghiệp vụ.
- [ ] Có bằng chứng khi đạt và khi thất bại.
- [ ] Đã chạy đủ lần để đánh giá độ ổn định theo kế hoạch.
- [ ] Flaky test và lỗi môi trường được phân loại, không che bằng retry vô hạn.
- [ ] Thời gian chạy, thời gian chờ và công sức bảo trì được ghi nhận.
- [ ] Dữ liệu và tài nguyên được cô lập, dọn dẹp đúng cách.

### Trước quyết định mở rộng

- [ ] Kết quả được so sánh với giả thuyết và baseline.
- [ ] Giá trị kiểm thử và rủi ro được kiểm soát có bằng chứng.
- [ ] Độ ổn định, tốc độ và khả năng chẩn đoán đáp ứng mục tiêu.
- [ ] Chi phí vòng đời và năng lực duy trì được đánh giá.
- [ ] Giới hạn và phần chưa bao phủ được ghi rõ.
- [ ] Có người sở hữu, hướng dẫn và quy trình xử lý thất bại.
- [ ] Quyết định mở rộng, điều chỉnh, thử phương án khác hoặc dừng có căn cứ.
- [ ] Nếu mở rộng, phạm vi tiếp theo và cổng đánh giá đã được xác định.

## Kết luận

Thử nghiệm nhỏ trước khi mở rộng giúp nhóm kiểm tra giá trị và rủi ro của tự động hóa bằng dữ liệu thực tế. Bắt đầu từ vấn đề, giả thuyết và phạm vi đại diện; xây dựng một lát cắt từ môi trường, dữ liệu, test đến pipeline và bằng chứng; đo chất lượng, tốc độ, độ ổn định cùng chi phí; sau đó quyết định mở rộng, điều chỉnh, thử phương án khác hoặc dừng. Mở rộng từng bước với người sở hữu và tiêu chí đánh giá rõ ràng giúp tự động hóa trở thành năng lực bền vững thay vì một tập script khó duy trì.
