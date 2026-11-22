# Điều phối fan-out, fan-in và giới hạn số tác vụ con

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích fan-out và fan-in trong một workflow serverless và nhận biết các tình huống phù hợp.
- Thiết kế workflow chạy nhiều tác vụ con song song, thu thập kết quả và tổng hợp trạng thái.
- Phân biệt chờ tất cả tác vụ, chấp nhận một phần kết quả, quorum và kết thúc sớm.
- Giới hạn số tác vụ con, mức concurrency và tốc độ gọi dịch vụ phụ thuộc để tránh quá tải.
- Xử lý timeout, retry, tác vụ trùng lặp, lỗi một phần và hủy các tác vụ còn lại.
- Triển khai handler Java cho từng tác vụ con và chọn cách phối hợp phù hợp với thời gian sống của function.

## 1. Vì sao cần fan-out và fan-in?

Một workflow thường bắt đầu bằng một yêu cầu nghiệp vụ, sau đó thực hiện một hoặc nhiều bước. Có những bước phải chạy tuần tự vì bước sau phụ thuộc kết quả bước trước. Nhưng cũng có nhiều trường hợp một bước có thể được chia thành nhiều công việc độc lập.

Ví dụ, một khách hàng tải lên 30 ảnh sản phẩm. Hệ thống cần tạo thumbnail cho từng ảnh, trích xuất metadata, quét nội dung và cập nhật trạng thái bộ sưu tập. Việc tạo thumbnail của ảnh thứ nhất không cần chờ ảnh thứ hai hoàn tất. Chạy tuần tự sẽ làm tổng thời gian tăng theo thời gian xử lý của tất cả ảnh.

**Fan-out** là thao tác phân tách một công việc thành nhiều tác vụ con có thể được xử lý độc lập hoặc song song. **Fan-in** là thao tác hội tụ: chờ, thu thập hoặc tổng hợp kết quả của các tác vụ con để workflow cha quyết định bước tiếp theo.

~~~mermaid
flowchart TD
    A[Nhận yêu cầu xử lý bộ sưu tập] --> B[Fan-out: tạo 30 tác vụ con]
    B --> C1[Tác vụ ảnh 1]
    B --> C2[Tác vụ ảnh 2]
    B --> C3[Tác vụ ảnh 3]
    B --> C4[Tác vụ ảnh ...]
    C1 --> D[Fan-in: thu thập kết quả]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E[Tổng hợp trạng thái]
    E --> F[Đánh dấu bộ sưu tập hoàn tất]
~~~

Trong mô hình serverless, mỗi tác vụ con có thể được thực thi bởi một Java function riêng, một message consumer hoặc một child workflow. Workflow engine quản lý việc tạo tác vụ, theo dõi trạng thái và điều phối fan-in. Từng function có thể chạy trên instance khác nhau; bộ nhớ của một instance không phải nơi lưu toàn bộ trạng thái của workflow.

Fan-out/fan-in thường xuất hiện trong:

- Xử lý từng dòng hóa đơn hoặc từng mục trong đơn hàng.
- Tạo thumbnail, chuyển mã hoặc phân tích nhiều file.
- Gọi nhiều dịch vụ độc lập để thu thập báo giá hoặc dữ liệu.
- Kiểm tra nhiều quy tắc độc lập trước khi phê duyệt.
- Chạy các bước xử lý theo từng khách hàng, tài khoản hoặc vùng dữ liệu.
- Tạo báo cáo từ nhiều nguồn dữ liệu rồi tổng hợp kết quả.

Không phải công việc nào cũng cần fan-out. Nếu các bước phụ thuộc tuần tự, việc chia nhỏ không tạo ra tính song song hữu ích. Nếu số tác vụ rất ít và thao tác nhanh, chi phí điều phối có thể lớn hơn lợi ích.

## 2. Mô hình fan-out/fan-in trong workflow

Một workflow cha có thể thực hiện bốn phần chính:

1. Chuẩn bị đầu vào và xác định tập đơn vị công việc.
2. Tạo hoặc lập lịch các tác vụ con.
3. Thu thập trạng thái và kết quả theo chính sách join.
4. Tổng hợp kết quả, cập nhật trạng thái nghiệp vụ và tiếp tục hoặc kết thúc.

~~~mermaid
flowchart TD
    A[Workflow cha] --> B[Chuẩn hóa đầu vào]
    B --> C[Chia thành các đơn vị công việc]
    C --> D[Fan-out với giới hạn concurrency]
    D --> E[Child workflow hoặc function]
    E --> F[Fan-in theo chính sách join]
    F --> G{Điều kiện hoàn tất?}
    G -->|Đạt| H[Tổng hợp và tiếp tục]
    G -->|Không đạt| I[Xử lý lỗi hoặc bù trừ]
    H --> J[Kết thúc workflow]
    I --> J
~~~

### 2.1. Workflow cha và tác vụ con

Workflow cha (parent workflow) chịu trách nhiệm điều phối toàn bộ nghiệp vụ. Tác vụ con (child task hoặc child workflow) chịu trách nhiệm xử lý một đơn vị công việc cụ thể. Đầu vào của child nên đủ để thực hiện công việc mà không cần biết toàn bộ trạng thái nội bộ của parent.

Ví dụ với bộ sưu tập ảnh:

- Parent nhận `collectionId`, xác định danh sách ảnh cần xử lý và tạo một công việc cho mỗi `imageId`.
- Child nhận `collectionId`, `imageId`, loại biến đổi và phiên bản cấu hình.
- Child đọc file từ object storage, tạo thumbnail, lưu kết quả và trả metadata.
- Parent thu thập trạng thái child, tính số ảnh thành công/thất bại và cập nhật bộ sưu tập.

Mỗi child nên có định danh ổn định, chẳng hạn `taskId` hoặc cặp `collectionId + imageId`. Định danh này hữu ích cho idempotency, log, retry và tra cứu trạng thái.

Không nên truyền toàn bộ file nhị phân hoặc payload lớn qua workflow state. Hãy truyền object key, URI nội bộ hoặc ID bản ghi; child tự đọc dữ liệu từ nơi lưu trữ được cấp quyền. Điều này giảm kích thước message, workflow history và chi phí serialize.

### 2.2. Fan-out tĩnh và fan-out động

**Fan-out tĩnh** xảy ra khi số nhánh và các tác vụ đã biết trước. Ví dụ, workflow luôn gọi ba dịch vụ: kiểm tra tồn kho, xác minh địa chỉ và tính thuế. Mỗi nhánh có thể chạy song song rồi join trước khi xác nhận đơn hàng.

**Fan-out động** xảy ra khi số tác vụ được xác định từ dữ liệu đầu vào hoặc lúc chạy. Ví dụ, một báo cáo có thể chứa vài chục nghìn tài khoản cần tổng hợp. Workflow đọc danh sách tài khoản rồi tạo child cho từng tài khoản hoặc từng batch.

| Đặc điểm | Fan-out tĩnh | Fan-out động |
|---|---|---|
| Số nhánh | Biết trước trong định nghĩa workflow | Xác định khi chạy |
| Ví dụ | Gọi ba dịch vụ kiểm tra độc lập | Xử lý từng file trong một thư mục |
| Khả năng thay đổi cardinality | Thấp | Cao |
| Cách giới hạn | Cấu hình từng nhánh | Giới hạn số item, batch và concurrency |
| Theo dõi | Mỗi nhánh có tên cố định | Cần item ID và correlation ID |

Dynamic fan-out thường được triển khai bằng Map state, parallel collection, child workflow hoặc queue consumer. Tên tính năng phụ thuộc nền tảng, nhưng nguyên tắc là giống nhau: mỗi phần tử hoặc batch trở thành một đơn vị thực thi độc lập, còn workflow cha quản lý việc hội tụ.

### 2.3. Fan-out không đồng nghĩa với tạo vô hạn instance

Một lỗi thiết kế thường gặp là tạo một child cho mỗi phần tử mà không giới hạn số lượng hoặc mức chạy đồng thời. Nếu đầu vào có 100.000 phần tử, workflow có thể tạo lượng lớn invocation cùng lúc và làm quá tải database, API bên thứ ba hoặc quota của tài khoản cloud.

Cần tách biệt ba khái niệm:

- **Cardinality:** tổng số tác vụ con được tạo cho một workflow.
- **Concurrency:** số tác vụ đang chạy cùng thời điểm.
- **Throughput:** số tác vụ hoàn thành trong một đơn vị thời gian.

Ví dụ, một workflow có 10.000 child nhưng chỉ cho chạy tối đa 50 child đồng thời. Cardinality là 10.000; concurrency tối đa là 50. Throughput còn phụ thuộc thời gian xử lý trung bình, tốc độ cấp phát, retry và năng lực của dịch vụ phụ thuộc.

Giới hạn concurrency không tự giới hạn tổng số child. Ngược lại, giới hạn tổng số child không bảo vệ downstream nếu nhiều workflow chạy cùng lúc. Thiết kế cần xem cả mức của một workflow và mức toàn hệ thống.

## 3. Fan-in và chính sách join

Fan-in quyết định khi nào workflow cha được tiếp tục và kết quả nào được xem là đủ. Một workflow cần chọn chính sách join theo yêu cầu nghiệp vụ; không nên mặc định mọi tác vụ phải thành công trong mọi trường hợp.

### 3.1. Join all: chờ tất cả tác vụ

Join all chỉ hoàn tất khi mọi child đã đi đến trạng thái kết thúc. Parent thu thập kết quả thành công và thất bại, sau đó áp dụng chính sách tổng hợp.

Đây là chính sách join ở mức nghiệp vụ. Một số workflow engine mặc định fail-fast: khi một nhánh lỗi, execution cha có thể chuyển sang lỗi ngay và không chờ các nhánh còn lại. Nếu cần thu thập kết quả của mọi child, hãy cấu hình xử lý lỗi ở từng nhánh để lỗi trở thành kết quả có thể tổng hợp, hoặc dùng cơ chế catch/continue phù hợp với nền tảng.

~~~mermaid
flowchart TD
    A[Fan-out 4 child] --> B[Child A]
    A --> C[Child B]
    A --> D[Child C]
    A --> E[Child D]
    B --> F{Tất cả child đã kết thúc?}
    C --> F
    D --> F
    E --> F
    F -->|Chưa| G[Chờ kết quả còn lại]
    G --> F
    F -->|Rồi| H[Tổng hợp kết quả]
~~~

Join all phù hợp khi mọi phần tử đều bắt buộc, ví dụ tạo tất cả dòng chi tiết trong một báo cáo tài chính hoặc xử lý toàn bộ file trong một batch kiểm kê.

Cần phân biệt “tất cả đã kết thúc” với “tất cả đã thành công”. Khi một child thất bại, workflow có thể:

- Thử lại child theo chính sách retry.
- Chờ child khác hoàn tất rồi trả báo cáo một phần.
- Đánh dấu workflow thất bại ngay và yêu cầu hủy các child còn lại.
- Chạy compensation cho những child đã tạo tác động nghiệp vụ.
- Chuyển workflow sang trạng thái cần can thiệp thủ công.

Chính sách phải được xác định trước để tránh workflow chờ vô hạn khi một child không bao giờ phản hồi.

### 3.2. Join any: chỉ cần một kết quả

Join any cho phép parent tiếp tục ngay khi có một child đạt điều kiện thành công. Ví dụ, tìm một trong nhiều bản sao dịch vụ có thể phục vụ yêu cầu, hoặc hỏi nhiều nguồn dữ liệu và dùng kết quả hợp lệ đầu tiên.

Sau khi có kết quả, các child còn lại có thể bị hủy nếu nền tảng hỗ trợ, hoặc tiếp tục chạy nhưng kết quả bị bỏ qua. Hủy workflow không đảm bảo một lời gọi đã gửi đến hệ thống bên ngoài sẽ dừng ngay. Các child đã bắt đầu cần hỗ trợ cancellation hoặc kiểm tra trạng thái hủy trước khi thực hiện tác động tiếp theo.

Join any cũng cần định nghĩa “thành công” là gì. Một response đến trước có thể không hợp lệ, thiếu dữ liệu hoặc không đáp ứng tiêu chí nghiệp vụ. Parent có thể cần chờ kết quả đầu tiên hợp lệ, thay vì kết quả đầu tiên bất kỳ.

### 3.3. Join theo quorum hoặc ngưỡng

Một số nghiệp vụ chỉ cần một tỷ lệ hoặc số lượng kết quả nhất định. Ví dụ, hệ thống kiểm tra nội dung có năm bộ phân loại độc lập và cần ít nhất ba kết quả đồng ý trước khi đánh dấu nội dung cần xem xét. Hoặc dịch vụ lấy giá có thể chấp nhận khi ít nhất hai trong ba nhà cung cấp trả giá hợp lệ.

Điều kiện quorum có thể được biểu diễn:

- Thành công khi số child hợp lệ đạt ít nhất `k`.
- Thất bại khi số child còn có thể thành công không đủ để đạt `k`.
- Hết thời gian nếu deadline đến trước khi đạt `k`; parent áp dụng chính sách kết thúc đã định nghĩa.

Nếu có `n` child, đã có `s` kết quả thành công và `r` child còn có khả năng thành công (đang chờ, đang chạy hoặc chờ retry), quorum `k` không còn khả thi khi `s + r < k`. Khi đó parent có thể kết thúc sớm theo chính sách.

Quorum hữu ích cho hệ thống có nhiều nguồn độc lập, nhưng không thay thế việc đánh giá chất lượng và độ tin cậy của từng nguồn. Nếu các child cùng phụ thuộc vào một dịch vụ hoặc một dữ liệu gốc, chúng không thực sự độc lập.

### 3.4. Fan-in tổng hợp kết quả

Sau khi join, parent có thể cần:

- Đếm số child thành công, thất bại và bị bỏ qua.
- Tính tổng hoặc trung bình từ kết quả.
- Ghép metadata của từng child.
- Chọn kết quả có độ ưu tiên cao nhất.
- Tạo báo cáo lỗi và danh sách item cần xử lý lại.
- Cập nhật trạng thái nghiệp vụ cuối cùng.

Không nhất thiết phải giữ mọi payload child trong bộ nhớ hoặc workflow history. Với tập kết quả lớn, child ghi kết quả vào database hoặc object storage, parent chỉ thu thập ID, trạng thái và vị trí kết quả. Một bước reduce có thể đọc dữ liệu theo batch để tổng hợp.

### 3.5. Thứ tự kết quả

Các child có thể hoàn thành theo thứ tự khác với thứ tự đầu vào. Nếu nghiệp vụ yêu cầu giữ thứ tự ban đầu, mỗi child cần mang `itemIndex` hoặc khóa sắp xếp. Parent sắp xếp kết quả theo khóa đó trước khi trả về.

Không nên giả định thứ tự hoàn thành là thứ tự xử lý. Với các tác vụ bất đồng bộ, thứ tự có thể thay đổi do độ trễ mạng, retry, scheduling hoặc thời gian xử lý khác nhau.

### 3.6. Fan-in an toàn khi dùng queue

Khi parent gửi child qua queue, message có thể đến trùng, đến sai thứ tự hoặc được giao lại sau khi worker đã xử lý xong. Vì vậy, không nên chỉ tăng một bộ đếm mỗi khi nhận message hoàn tất. Một message trùng có thể làm bộ đếm vượt số child thực tế và khiến parent đánh dấu job hoàn tất quá sớm.

Một aggregator bền vững có thể dùng bảng trạng thái child với khóa duy nhất theo `taskId`. Khi nhận kết quả, aggregator thực hiện chuyển trạng thái có điều kiện, ví dụ chỉ chuyển từ `RUNNING` sang `SUCCEEDED` hoặc `FAILED` một lần. Bộ đếm hoàn tất chỉ được cập nhật nếu lần chuyển trạng thái đó thực sự xảy ra. Việc lưu trạng thái child và cập nhật bộ đếm cần nằm trong cùng transaction hoặc dùng một cơ chế nhất quán tương đương.

Parent cũng phải biết quá trình fan-out đã kết thúc tạo child hay chưa. Nếu parent gửi 100 message nhưng aggregator chỉ thấy 99 message hoàn tất, nó chưa thể biết message cuối cùng bị chậm hay parent vẫn đang tạo thêm child. Với danh sách đã biết trước, có thể lưu `expectedCount` và toàn bộ task ID trước khi cho phép aggregator xử lý tín hiệu hoàn tất. Với danh sách được tạo theo luồng, hãy dùng cờ `dispatchClosed` hoặc bộ đếm outstanding được cập nhật nguyên tử: chỉ hoàn tất khi producer đã đóng và mọi child đã ở trạng thái kết thúc.

Khi điều kiện hoàn tất đạt, aggregator phát tín hiệu cho parent bằng một thao tác idempotent, chẳng hạn completion record có khóa duy nhất hoặc transactional outbox. Như vậy, message hoàn tất được giao lại không tạo nhiều lần chuyển trạng thái cho workflow cha.

## 4. Giới hạn cardinality và concurrency

Giới hạn số tác vụ con là một phần của thiết kế workflow, không chỉ là cấu hình vận hành. Một workflow có thể xử lý hàng trăm hoặc hàng nghìn item, nhưng hệ thống phải kiểm soát số công việc được tạo, số công việc đang chạy và tốc độ chúng gọi đến dịch vụ phụ thuộc.

### 4.1. Giới hạn theo từng workflow

Nếu workflow engine hỗ trợ Map state hoặc dynamic parallelism, hãy cấu hình mức concurrency tối đa cho nhánh map. Ví dụ, 5.000 file có thể được chia thành child nhưng chỉ cho phép 40 child chạy cùng lúc.

Một cách ước lượng sơ bộ là:

`throughput ≈ concurrency / average_duration`

Nếu mỗi child mất trung bình 2 giây và concurrency là 40, throughput lý thuyết khoảng 20 child mỗi giây. Thực tế có thể thấp hơn do thời gian scheduling, giới hạn nền tảng, retry, độ trễ database và sự cạnh tranh tài nguyên. Không dùng công thức này thay cho load test; nó chỉ giúp ước lượng ban đầu.

### 4.2. Giới hạn toàn hệ thống

Giới hạn 40 child cho mỗi workflow không có nghĩa hệ thống chỉ chạy 40 child. Nếu 100 workflow cùng chạy, tổng concurrency có thể lên đến 4.000. Khi downstream chỉ chịu được 200 request đồng thời, cấu hình theo workflow riêng lẻ vẫn có thể làm dịch vụ quá tải.

Cần phối hợp các tầng giới hạn:

- **Workflow-level concurrency:** giới hạn child chạy đồng thời trong một workflow.
- **Global concurrency:** giới hạn tổng invocation hoặc worker trên toàn dịch vụ.
- **Per-tenant concurrency:** ngăn một tenant lớn chiếm toàn bộ tài nguyên.
- **Rate limit:** giới hạn số request trong một khoảng thời gian.
- **Downstream quota:** tuân thủ giới hạn của database, API thanh toán, dịch vụ AI hoặc nhà cung cấp bên ngoài.

Nếu nền tảng không có giới hạn toàn cục dùng chung giữa các workflow, có thể dùng queue với số consumer/worker cố định, distributed semaphore hoặc cơ chế cấp token tập trung. Cơ chế phân tán cần có lease/expiry để tránh một worker chết mà giữ khóa mãi mãi.

### 4.3. Dùng queue để hấp thụ tải

Với fan-out rất lớn hoặc tải đến không đều, queue giúp tách tốc độ tạo công việc khỏi tốc độ xử lý. Parent phát một message cho mỗi item hoặc mỗi batch. Worker chỉ lấy message khi còn capacity. Queue giữ phần công việc chờ và phân phối dần.

~~~mermaid
flowchart LR
    A[Workflow cha] --> B[Chia batch]
    B --> C[Queue công việc]
    C --> D1[Java worker 1]
    C --> D2[Java worker 2]
    C --> D3[Java worker N]
    D1 --> E[Kho kết quả]
    D2 --> E
    D3 --> E
    E --> F[Fan-in hoặc aggregator]
~~~

Queue tạo buffer nhưng không tự đảm bảo fan-in. Parent vẫn cần biết có bao nhiêu item được tạo, item nào đã hoàn tất và khi nào tập công việc đã kết thúc. Có thể dùng một bảng job/item state, một workflow engine chờ tín hiệu hoàn tất hoặc một aggregator theo dõi số lượng đã xử lý.

Nếu mỗi message có thể được giao lại, worker phải idempotent. Queue depth, age of oldest message, tốc độ publish/consume và số message trong DLQ là các chỉ số cần theo dõi.

### 4.4. Chia batch để giảm overhead

Tạo một child cho từng record có thể làm tăng số invocation và state transition rất nhanh. Thay vì 100.000 child cho 100.000 dòng, có thể chia thành 1.000 batch, mỗi batch xử lý 100 dòng.

Batch size là một trade-off:

- Batch nhỏ giúp retry chính xác hơn, thời gian xử lý mỗi child ngắn và phân phối tải mịn.
- Batch lớn giảm overhead scheduling và invocation nhưng tăng bộ nhớ, thời gian xử lý và phạm vi phải retry khi batch lỗi.
- Batch quá lớn có thể chạm timeout hoặc memory limit của function.
- Batch quá nhỏ có thể làm chi phí điều phối và message lớn hơn chi phí xử lý thực tế.

Khi batch có thể thất bại một phần, kết quả nên ghi nhận trạng thái theo từng item hoặc danh sách item lỗi. Không đánh dấu toàn bộ batch thành công nếu chỉ một phần item đã xử lý xong.

### 4.5. Backpressure và phản ứng khi downstream quá tải

Backpressure là cách hệ thống làm chậm việc phát hoặc tiêu thụ công việc khi thành phần phía sau không còn capacity. Có thể thực hiện bằng cách:

- Giảm concurrency của worker.
- Tạm dừng hoặc giảm tốc độ publish.
- Đưa công việc vào queue thay vì gọi trực tiếp.
- Tôn trọng response `429` và header `Retry-After` từ API bên ngoài.
- Dùng circuit breaker để ngừng gọi dịch vụ đang lỗi liên tục trong một khoảng thời gian.
- Tách pool hoặc queue theo loại công việc để tác vụ nặng không chặn tác vụ nhẹ.

Không tăng concurrency ngay khi queue depth tăng mà chưa xem xét nguyên nhân. Nếu database đã quá tải, tăng worker chỉ làm nhiều request thất bại hơn và tạo thêm retry.

## 5. Xử lý lỗi, timeout và retry ở cấp child

Trong fan-out, mỗi child có thể có kết quả khác nhau. Parent phải theo dõi trạng thái từng child và xác định lỗi nào có thể phục hồi, lỗi nào là lỗi nghiệp vụ và lỗi nào cần can thiệp.

### 5.1. Trạng thái child rõ ràng

Một mô hình trạng thái đơn giản:

| Trạng thái | Ý nghĩa |
|---|---|
| `PENDING` | Đã tạo nhưng chưa bắt đầu |
| `RUNNING` | Đang thực thi |
| `SUCCEEDED` | Hoàn tất thành công |
| `RETRY_WAIT` | Đang chờ lần thử tiếp theo |
| `FAILED` | Thất bại sau khi hết retry hoặc lỗi không thể phục hồi |
| `CANCEL_REQUESTED` | Parent đã yêu cầu hủy |
| `CANCELLED` | Child xác nhận đã dừng |
| `TIMED_OUT` | Vượt quá thời hạn thực thi |

Các trạng thái này là ví dụ. Hệ thống có thể dùng ít trạng thái hơn, nhưng cần phân biệt tác vụ chưa chạy, đang chạy, đã hoàn tất và đã bị hủy. Trạng thái `FAILED` cũng nên lưu mã lỗi và thông tin có thể dùng để điều tra.

### 5.2. Retry từng child, không khởi chạy lại cả nhóm một cách mù quáng

Giả sử có 100 child và chỉ 3 child bị lỗi mạng tạm thời. Nếu parent khởi chạy lại toàn bộ 100 child, các tác vụ đã thành công có thể bị thực hiện lần nữa. Điều này vừa lãng phí vừa có thể tạo tác động nghiệp vụ trùng lặp.

Nên retry ở cấp child hoặc batch bị lỗi. Dùng exponential backoff, jitter và số lần thử tối đa. Phân loại lỗi:

- **Lỗi tạm thời:** timeout, lỗi mạng, `429`, `5xx` có thể được retry theo chính sách.
- **Lỗi nghiệp vụ:** dữ liệu không hợp lệ, không tìm thấy đối tượng, vi phạm điều kiện nghiệp vụ; thường cần trả kết quả thất bại thay vì retry vô hạn.
- **Lỗi cấu hình/quyền:** thiếu permission, sai endpoint hoặc secret; cần sửa cấu hình trước khi retry.
- **Lỗi không xác định:** timeout sau khi gửi yêu cầu có thể có nghĩa thao tác đã thành công nhưng phản hồi bị mất; phải kiểm tra trạng thái hoặc dùng idempotency key trước khi thử lại.

Nhiều tầng có thể tự retry: SDK, HTTP client, queue trigger và workflow engine. Nếu mỗi tầng thử lại nhiều lần, tổng số lần gọi có thể nhân lên. Cần xác định một chính sách retry tổng thể, đặt timeout nhất quán và tránh retry đồng thời ở mọi tầng.

### 5.3. Idempotency cho tác vụ con

At-least-once delivery và retry có thể khiến một child được gọi nhiều lần. Một tác vụ có tác động nghiệp vụ cần idempotency key ổn định, chẳng hạn:

`taskKey = workflowId + ":" + itemId + ":" + operationVersion`

Khi nhận request, child kiểm tra key trong kho lưu trữ bền vững. Nếu kết quả đã được ghi nhận, child trả lại kết quả cũ hoặc trạng thái hiện có. Nếu chưa, child thực hiện thao tác và ghi kết quả cùng transaction phù hợp.

Không tạo idempotency key mới mỗi lần retry, vì khi đó hệ thống không nhận ra đó là cùng một công việc. Nếu một item cần được xử lý lại do thay đổi cấu hình hoặc dữ liệu, hãy đưa version nghiệp vụ vào key để phân biệt lần xử lý mới có chủ đích.

Không dựa vào biến static hoặc cache trong bộ nhớ của Java function để chống trùng. Invocation tiếp theo có thể chạy trên instance khác hoặc sau khi instance cũ đã bị thu hồi.

### 5.4. Timeout và child chạy quá lâu

Mỗi child nên có timeout riêng; parent cũng cần deadline tổng thể. Timeout child giúp giải phóng slot concurrency và tránh workflow chờ vô hạn. Deadline parent đảm bảo nghiệp vụ có điểm kết thúc hoặc chuyển sang xử lý thủ công.

Nếu child gọi một dịch vụ bên ngoài, timeout ở client không chứng minh dịch vụ đó đã hủy công việc. Có thể request đã đến server và đang tiếp tục. Nếu thao tác có thể kéo dài, hãy dùng một job ID ở dịch vụ đích và kiểm tra trạng thái thay vì giữ HTTP request mở.

Khi timeout, child có thể được đánh dấu `TIMED_OUT`, nhưng trước khi retry hoặc compensation, cần xác minh tác động đã xảy ra hay chưa. Đây là điểm quan trọng với thanh toán, tạo vận đơn hoặc gửi lệnh đến hệ thống không hỗ trợ giao dịch phân tán.

### 5.5. Partial failure và chính sách kết thúc

Nếu 97 child thành công và 3 child thất bại, workflow có thể có nhiều chính sách:

- **All-or-nothing:** chỉ coi nghiệp vụ hoàn tất nếu mọi child thành công; các tác động đã commit cần compensation khi thất bại.
- **Partial success:** ghi nhận phần thành công, liệt kê item lỗi và cho phép retry riêng.
- **Best effort:** tác vụ phụ có thể thất bại mà không chặn nghiệp vụ chính, nhưng lỗi vẫn cần được theo dõi.
- **Quorum:** tiếp tục khi đạt ngưỡng kết quả hợp lệ.

Không dùng một trạng thái `COMPLETED` duy nhất nếu người dùng cần phân biệt hoàn tất toàn bộ và hoàn tất một phần. Có thể dùng `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `FAILED` hoặc một trạng thái nghiệp vụ tương đương.

### 5.6. Hủy các child còn lại và compensation

Nếu join any hoặc quorum đã đạt, parent có thể yêu cầu hủy child còn lại. Nếu workflow thất bại, parent cũng có thể hủy các tác vụ chưa bắt đầu hoặc đang chờ.

Hủy là một yêu cầu có thể bất đồng bộ. Child cần kiểm tra cancellation token hoặc trạng thái hủy trước các bước có tác động. Một child đang chạy lệnh bên ngoài có thể không dừng ngay; hệ thống phải có cách xác định kết quả cuối cùng.

Compensation áp dụng khi child đã tạo tác động nghiệp vụ mà quy trình cần khắc phục. Ví dụ, nếu một nhóm đơn hàng đã giữ chỗ hàng nhưng parent quyết định hủy toàn bộ batch, child tương ứng có thể cần giải phóng hàng. Compensation cũng phải idempotent và có thể thất bại; parent cần lưu trạng thái bù trừ và điểm chuyển sang xử lý thủ công.

### 5.7. Dead-letter queue

Sau khi vượt quá retry, message có thể được chuyển vào dead-letter queue (DLQ). DLQ giữ lại thông tin để điều tra và phát lại có kiểm soát. Khi xử lý DLQ:

- Xác định nguyên nhân gốc trước khi replay.
- Giữ item ID, workflow ID, event ID và số lần thử.
- Kiểm tra idempotency trước khi thực hiện lại tác động.
- Không replay hàng loạt nếu downstream vẫn đang lỗi.
- Cập nhật trạng thái child và parent sau khi xử lý thủ công hoặc replay thành công.

DLQ không phải nơi lưu công việc vô thời hạn mà không có người theo dõi. Cần cảnh báo khi message vào DLQ, quy định retention và quy trình xử lý.

## 6. Ví dụ Java cho child task và xử lý song song

Java function thường nên xử lý một đơn vị công việc rõ ràng. Workflow engine hoặc queue chịu trách nhiệm tạo nhiều invocation và quản lý trạng thái fan-out/fan-in.

### 6.1. Mô hình dữ liệu cho tác vụ con

Một message cho child có thể mang định danh workflow, item, phiên bản thao tác và correlation ID:

~~~java
import java.time.Instant;

public record WorkItem(
    String workflowId,
    String itemId,
    int itemIndex,
    String operationVersion,
    String correlationId,
    String objectKey,
    Instant deadline
) {}

public record WorkResult(
    String workflowId,
    String itemId,
    int itemIndex,
    String status,
    String resultKey,
    String errorCode
) {}
~~~

`objectKey` trỏ đến file trong object storage. `itemIndex` giúp giữ thứ tự nếu nghiệp vụ cần. `deadline` là giới hạn xử lý được parent truyền xuống; child vẫn cần kiểm tra timeout của nền tảng và timeout của lời gọi phụ thuộc.

Không gửi credential hoặc thông tin quyền truy cập trong payload. Child nên lấy quyền từ execution role/service identity của chính nó và xác thực quyền truy cập đối với đối tượng được yêu cầu.

### 6.2. Child handler có idempotency

Ví dụ dưới đây minh họa cấu trúc xử lý. Các repository và service là interface ứng dụng, cần được triển khai bằng database/object storage hoặc dịch vụ tương ứng.

~~~java
public final class ImageTaskHandler {
    private final TaskRepository tasks;
    private final ImageProcessor processor;
    private final ResultRepository results;

    public ImageTaskHandler(
            TaskRepository tasks,
            ImageProcessor processor,
            ResultRepository results) {
        this.tasks = tasks;
        this.processor = processor;
        this.results = results;
    }

    public WorkResult handle(WorkItem item) {
        String taskKey = item.workflowId()
                + ":" + item.itemId()
                + ":" + item.operationVersion();

        TaskClaim claim = tasks.claim(taskKey);

        if (claim.alreadySucceeded()) {
            return results.load(taskKey);
        }

        if (!claim.acquired()) {
            throw new TaskAlreadyRunningException(taskKey);
        }

        try {
            if (Instant.now().isAfter(item.deadline())) {
                throw new TaskDeadlineExceededException(taskKey);
            }

            String outputKey = processor.createThumbnail(item.objectKey());

            WorkResult result = new WorkResult(
                    item.workflowId(),
                    item.itemId(),
                    item.itemIndex(),
                    "SUCCEEDED",
                    outputKey,
                    null);

            results.save(taskKey, result);
            tasks.markSucceeded(taskKey);
            return result;
        } catch (RetryableTaskException ex) {
            tasks.releaseForRetry(taskKey, ex.getClass().getSimpleName());
            throw ex;
        } catch (RuntimeException ex) {
            tasks.markFailed(taskKey, ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

Ví dụ giả định `TaskRepository.claim` thực hiện thao tác nguyên tử để chỉ một invocation sở hữu task key tại một thời điểm. Trong triển khai thực tế, cần có lease hết hạn để khôi phục khi instance bị dừng đột ngột. `save result` và `mark succeeded` cần có transaction hoặc giao thức nhất quán phù hợp; nếu một bước thành công còn bước kia thất bại, lần retry phải có thể tra cứu và khôi phục kết quả.

Nếu `processor.createThumbnail` ghi ra object storage, hãy dùng output key xác định theo task key hoặc một quy tắc idempotent. Nếu mỗi lần retry tạo một file ngẫu nhiên khác nhau, có thể sinh file rác hoặc parent nhận nhiều kết quả cho cùng một item.

### 6.3. Song song trong cùng một Java invocation

Với một số ít công việc nhanh, độc lập và có giới hạn rõ ràng, Java có thể chạy song song trong cùng một invocation bằng executor giới hạn:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class LocalFanOut {
    public List<String> process(List<String> itemIds) {
        if (itemIds.isEmpty()) {
            return List.of();
        }

        int workers = Math.min(4, itemIds.size());

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        List<CompletableFuture<String>> futures = new java.util.ArrayList<>();
        try {

            for (String id : itemIds) {
                futures.add(CompletableFuture.supplyAsync(
                        () -> processOne(id), executor));
            }

            CompletableFuture<Void> all =
                    CompletableFuture.allOf(
                            futures.toArray(CompletableFuture[]::new));

            all.orTimeout(20, TimeUnit.SECONDS).join();

            return futures.stream()
                    .map(CompletableFuture::join)
                    .toList();
        } catch (RuntimeException ex) {
            futures.forEach(future -> future.cancel(true));
            executor.shutdownNow();
            throw ex;
        } finally {
            executor.shutdown();
        }
    }

    private String processOne(String itemId) {
        return "processed:" + itemId;
    }
}
~~~

Đây là concurrency cục bộ bên trong một JVM invocation, với cú pháp tương thích Java 17 trở lên. Nó có một số giới hạn:

- Tối đa bốn worker chỉ có hiệu lực trong instance này, không giới hạn concurrency của các invocation khác.
- Nếu function bị timeout hoặc instance bị thu hồi, các tác vụ đang chạy có thể bị dừng và trạng thái chưa được lưu.
- `allOf` chờ tất cả future; khi join lỗi hoặc timeout, ví dụ yêu cầu hủy future và gọi `shutdownNow`, nhưng tác vụ chỉ dừng nếu code xử lý hợp tác với interrupt. Một lời gọi đã gửi đến dịch vụ bên ngoài có thể vẫn tiếp tục.
- Executor cần được đóng đúng cách; số worker và queue phải phù hợp với CPU, memory và dịch vụ phụ thuộc.
- Không nên dùng mô hình này để thay thế workflow bền vững cho công việc dài hoặc cần retry độc lập.

Nếu cần xử lý hàng trăm item, child có thể chạy vài phút, cần retry riêng hoặc phải tiếp tục sau khi instance chết, hãy để workflow engine/queue tạo các invocation riêng. `CompletableFuture` phù hợp cho các thao tác ngắn, cục bộ trong một request; nó không phải durable workflow.

### 6.4. Pseudocode cho workflow động

Một workflow có thể được mô tả khái quát như sau:

~~~text
Workflow ProcessCollection(collectionId):
    items = LoadItems(collectionId)
    batches = SplitIntoBatches(items, batchSize = 100)

    results = Map(
        batches,
        maxConcurrency = 20,
        retry = {
            maxAttempts: 3,
            backoff: exponential,
            jitter: true
        },
        task = ProcessBatch
    )

    summary = Aggregate(results)

    if summary.failedItems == 0:
        MarkCollectionCompleted(collectionId)
    else:
        SavePartialReport(collectionId, summary)
        MarkCollectionPartiallyCompleted(collectionId)
~~~

Đây là pseudocode, không phải cú pháp của một nhà cung cấp cloud. `Map` đại diện cho dynamic fan-out có giới hạn concurrency. `Aggregate` là bước fan-in. Một workflow engine có thể lưu trạng thái của từng batch, lịch sử retry và kết quả để tiếp tục sau lỗi.

## 7. Chọn workflow engine, queue hay parallelism cục bộ

Các nền tảng cung cấp cách triển khai khác nhau. Ví dụ, AWS Step Functions có Map state và Distributed Map; Azure Durable Functions có mẫu fan-out/fan-in; Google Workflows có thể phối hợp các bước song song. Cần kiểm tra giới hạn và semantics cụ thể của nền tảng đang chọn, vì quota, giới hạn payload, số child và cách hủy có thể khác nhau.

| Cách triển khai | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| Parallel branch trong workflow | Số nhánh nhỏ và biết trước | Dễ quan sát, nhưng định nghĩa workflow gắn với các nhánh |
| Map/dynamic parallelism | Danh sách item xác định lúc chạy | Cần giới hạn concurrency và kích thước input/state |
| Child workflow | Mỗi phần việc có vòng đời và trạng thái riêng | Tăng khả năng theo dõi nhưng thêm chi phí điều phối |
| Queue + worker | Tải lớn, cần buffer và điều tiết tốc độ | Parent cần cơ chế theo dõi completion và timeout |
| Executor trong Java | Ít tác vụ ngắn, cục bộ trong một invocation | Không bền vững qua timeout hoặc instance termination |

Một workflow engine phù hợp khi cần lưu trạng thái điều phối, lịch sử từng child, timeout, retry, join và khả năng tiếp tục sau khi chờ. Queue phù hợp khi cần hấp thụ tải và worker xử lý theo capacity. Có thể kết hợp: workflow tạo job, queue phân phối child, bảng trạng thái lưu kết quả, rồi workflow nhận tín hiệu fan-in.

Không cần tạo một child workflow cho mỗi thao tác rất nhỏ nếu overhead điều phối lớn hơn công việc. Có thể gom các thao tác thành batch, nhưng vẫn cần xác định rõ cách retry và trạng thái của từng item trong batch.

## 8. Trạng thái workflow, kích thước payload và tính bền vững

Workflow engine thường lưu input, output, trạng thái và lịch sử chuyển bước. Khi fan-out số lượng lớn, dữ liệu kết quả có thể làm state/history phình to.

Các nguyên tắc hữu ích:

- Giữ workflow state nhỏ: lưu ID, trạng thái, số đếm và URI kết quả.
- Đưa payload lớn vào object storage hoặc database; child nhận tham chiếu thay vì bản sao.
- Không lặp lại cùng một dữ liệu lớn trong input của mọi child nếu có thể truyền một tham chiếu dùng chung.
- Chỉ giữ kết quả chi tiết trong thời gian cần thiết; xác định retention của execution history và log.
- Nếu cần tổng hợp hàng triệu kết quả, dùng bước reduce theo batch hoặc kho dữ liệu thay vì gom mọi kết quả vào một object trong bộ nhớ.
- Chọn checkpoint phù hợp để workflow có thể tiếp tục mà không phải xử lý lại toàn bộ công việc.

Một workflow có thể lưu kết quả của từng child, nhưng giới hạn payload và số state transition phụ thuộc nền tảng. Trước khi chọn cách chia batch hoặc số child, cần kiểm tra quota thực tế của dịch vụ điều phối và thử nghiệm với kích thước dữ liệu dự kiến.

## 9. API đồng bộ và công việc fan-out dài hạn

Một HTTP request không nên giữ kết nối mở trong lúc chờ hàng nghìn child hoàn tất. Với tác vụ dài, API có thể khởi tạo workflow rồi trả về:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/jobs/job_abc123
Retry-After: 3
Content-Type: application/json
~~~

~~~json
{
  "jobId": "job_abc123",
  "status": "RUNNING",
  "statusUrl": "/v1/jobs/job_abc123"
}
~~~

Client dùng `statusUrl` để kiểm tra trạng thái hoặc nhận callback/webhook khi công việc hoàn tất. Endpoint trạng thái có thể trả:

~~~json
{
  "jobId": "job_abc123",
  "status": "PARTIALLY_SUCCEEDED",
  "progress": {
    "total": 10000,
    "completed": 9970,
    "failed": 30
  },
  "resultUrl": "/v1/jobs/job_abc123/result"
}
~~~

Các con số progress chỉ là ví dụ. Nếu tổng số item chưa biết, có thể trả số đã xử lý và trạng thái hiện tại mà không đưa ra phần trăm giả chính xác.

Endpoint job cần authorization giống endpoint tạo job. Không để ai biết `jobId` là có thể đọc kết quả. Nếu result URL trỏ đến object storage, hãy cấp quyền tải có thời hạn hoặc proxy qua API có kiểm tra quyền. Một client có thể gửi yêu cầu hủy job; endpoint cần trả trạng thái yêu cầu hủy và chỉ báo `CANCELLED` khi hệ thống xác nhận các child đã dừng hoặc đã đạt trạng thái kết thúc theo chính sách.

## 10. Quan sát và vận hành fan-out/fan-in

Khi có hàng trăm child, log của từng function riêng lẻ không đủ để giải thích toàn bộ workflow. Mọi log và kết quả nên có các định danh tương quan:

- `workflowId`: định danh workflow cha.
- `childId` hoặc `taskId`: định danh tác vụ con.
- `itemId`: đơn vị nghiệp vụ được xử lý.
- `correlationId`: liên kết các request và sự kiện trong cùng quy trình.
- `attempt`: số lần thử của child.
- `parentId`: liên kết child workflow với parent nếu nền tảng hỗ trợ.

Các metric quan trọng:

- Tổng child được tạo, đang chờ, đang chạy và đã kết thúc.
- Concurrency hiện tại và concurrency cao nhất.
- Throughput, thời gian xử lý trung bình và percentile cao (p95/p99).
- Tỷ lệ thành công, thất bại, timeout, retry và cancellation.
- Queue depth, age of oldest message và DLQ count.
- Thời gian từ lúc fan-out đến lúc fan-in hoàn tất.
- Số workflow bị kẹt và số child vượt deadline.
- Chi phí invocation, workflow transition, message delivery, lưu trữ và truyền dữ liệu.

Cần cảnh báo khi queue tăng liên tục, tuổi message lớn, tỷ lệ retry tăng, child timeout vượt ngưỡng hoặc parent không hội tụ trong thời gian kỳ vọng. Chỉ số tổng số child thành công không đủ để phát hiện một nhóm nhỏ item bị kẹt lâu.

Log nên dùng cấu trúc và không chứa secret, token hoặc dữ liệu cá nhân không cần thiết. Nếu nhiều child chạy song song, không dựa vào thứ tự dòng log để suy ra trình tự nghiệp vụ; hãy dùng timestamp và correlation ID.

## 11. Bảo mật và công bằng tài nguyên

Fan-out có thể khuếch đại một request đầu vào thành hàng nghìn invocation. Do đó, API khởi tạo workflow cần xác thực và authorization trước khi tạo child.

Một số nguyên tắc:

- Kiểm tra quyền trên collection hoặc batch trước khi phát tán công việc.
- Child vẫn phải xác minh quyền đối với item hoặc tenant của nó; không tin ID do parent truyền nếu parent không phải nguồn tin cậy.
- Mỗi worker chỉ có quyền đọc/ghi vào bucket, bảng hoặc queue cần thiết.
- Giới hạn số item tối đa cho mỗi job và số job đồng thời trên mỗi tenant.
- Dùng rate limit cho API tạo job để tránh một client liên tục tạo hàng loạt workflow.
- Tách queue theo tenant hoặc mức ưu tiên khi cần tránh noisy neighbor.
- Xác thực chữ ký hoặc nguồn gốc message nếu queue/event có thể nhận dữ liệu từ bên ngoài.
- Bảo vệ job status và result endpoint bằng cùng chính sách quyền truy cập như dữ liệu gốc.

Giới hạn per-tenant giúp một khách hàng lớn không chiếm toàn bộ worker. Tuy nhiên, giới hạn quá thấp cũng có thể khiến tenant hợp lệ phải chờ lâu. Hãy chọn mức dựa trên SLA, quota downstream và chính sách công bằng tài nguyên.

## 12. Chi phí và hiệu năng

Fan-out có thể giảm thời gian hoàn thành bằng cách chạy song song, nhưng không có nghĩa tổng chi phí luôn giảm.

Tổng chi phí có thể gồm:

- Số lần workflow transition hoặc child execution.
- Số function invocation và thời gian compute.
- Số message publish, receive, retry và lưu trữ.
- Đọc/ghi database, object storage và dữ liệu truyền giữa dịch vụ.
- Lịch sử workflow, log, trace và metric.
- Các lần xử lý lại do retry hoặc replay.

Nếu 1.000 child chạy đồng thời, thời gian wall-clock có thể ngắn hơn chạy tuần tự, nhưng tổng compute vẫn phụ thuộc tổng thời gian CPU/IO của từng child. Concurrency quá cao có thể làm downstream throttling, tăng retry và cuối cùng tăng cả latency lẫn chi phí.

Để tối ưu:

1. Đo thời gian và tài nguyên của một child trước khi chọn batch size.
2. Chạy load test với số workflow đồng thời dự kiến.
3. Đặt concurrency theo giới hạn thấp nhất trong chuỗi phụ thuộc.
4. Giảm payload và chỉ lưu kết quả cần thiết.
5. Chọn batch size cân bằng giữa overhead và phạm vi retry.
6. Theo dõi cost per completed item và cost per successful workflow.
7. Điều chỉnh theo số liệu thực tế thay vì chỉ tăng worker khi thấy chậm.

## 13. Quy trình thiết kế một workflow fan-out/fan-in

Có thể dùng trình tự sau:

1. **Xác định đơn vị công việc.** Mỗi child xử lý một item hay một batch? Child có tác động nghiệp vụ nào?
2. **Đo cardinality.** Mỗi workflow có bao nhiêu child trong trường hợp bình thường và cực đại? Có giới hạn đầu vào không?
3. **Chọn cách fan-out.** Dùng nhánh tĩnh, Map/dynamic parallelism, child workflow hay queue.
4. **Đặt concurrency và rate limit.** Xem cả giới hạn theo workflow, toàn hệ thống, tenant và downstream.
5. **Định nghĩa chính sách join.** Chờ tất cả, kết quả đầu tiên hợp lệ, quorum hay partial success?
6. **Định nghĩa trạng thái và kết quả.** Mỗi child có ID, trạng thái, attempt, error code và result reference.
7. **Thiết kế retry và idempotency.** Retry child lỗi tạm thời; dùng khóa ổn định cho tác động nghiệp vụ.
8. **Thiết kế timeout và cancellation.** Có deadline cho child và parent; xác định điều gì xảy ra khi child đã gọi dịch vụ bên ngoài.
9. **Thiết kế compensation.** Xác định hành động bù trừ, tính idempotent và điểm cần xử lý thủ công.
10. **Thiết kế fan-in và aggregation.** Không giữ payload quá lớn trong state; giữ thứ tự bằng item index nếu cần.
11. **Thiết kế observability và bảo mật.** Truyền correlation ID, đặt metric/cảnh báo, giới hạn quyền và số job.
12. **Kiểm thử lỗi và tải.** Mô phỏng duplicate, timeout, child chậm, downstream throttling, DLQ và hủy job giữa chừng.

## 14. Những lỗi thiết kế thường gặp

- **Tạo một child cho mọi record mà không giới hạn:** dễ vượt quota và làm quá tải downstream. Đặt cardinality limit, batch và concurrency.
- **Nhầm concurrency với throughput:** tăng số child đang chạy không đảm bảo số child hoàn thành mỗi giây tăng tương ứng.
- **Chờ tất cả mà không có timeout:** một child bị kẹt có thể giữ workflow cha mãi mãi.
- **Retry toàn bộ fan-out khi chỉ vài child thất bại:** lặp lại tác động đã thành công và tăng chi phí. Retry riêng child lỗi.
- **Không có idempotency:** message giao lại có thể tạo thanh toán, file hoặc bản ghi trùng.
- **Gom mọi kết quả vào workflow state:** payload lớn có thể vượt giới hạn và làm lịch sử execution phình to.
- **Giả định child hoàn thành theo thứ tự đầu vào:** thứ tự hoàn thành phụ thuộc scheduling và độ trễ.
- **Hủy parent rồi cho rằng mọi child đã dừng:** lời gọi bên ngoài có thể vẫn tiếp tục. Cần cancellation protocol và trạng thái xác nhận.
- **Không có fan-in state:** queue có thể xử lý hết message nhưng parent vẫn không biết job đã hoàn tất.
- **Không giới hạn theo tenant:** một job lớn có thể chiếm hết tài nguyên của các tenant khác.
- **Không theo dõi DLQ và job quá hạn:** child thất bại bị bỏ quên, parent không thể hội tụ.
- **Dùng executor cục bộ cho workflow dài:** instance bị thu hồi có thể làm mất công việc đang chạy và không có trạng thái bền vững.

## 15. Tự kiểm tra

**Câu 1.** Fan-out và fan-in là gì?

**Gợi ý trả lời:** Fan-out chia một công việc thành nhiều tác vụ con độc lập hoặc song song. Fan-in chờ, thu thập và tổng hợp kết quả để workflow cha quyết định bước tiếp theo.

**Câu 2.** Cardinality khác concurrency như thế nào?

**Gợi ý trả lời:** Cardinality là tổng số child được tạo trong workflow; concurrency là số child chạy cùng lúc. Một workflow có thể có 10.000 child nhưng giới hạn chỉ 50 child hoạt động đồng thời.

**Câu 3.** Khi nào nên dùng join all, join any hoặc quorum?

**Gợi ý trả lời:** Join all dùng khi mọi child đều bắt buộc. Join any dùng khi chỉ cần một kết quả hợp lệ. Quorum dùng khi nghiệp vụ chấp nhận một số lượng hoặc tỷ lệ kết quả tối thiểu.

**Câu 4.** Vì sao không nên retry toàn bộ fan-out khi chỉ một vài child thất bại?

**Gợi ý trả lời:** Child đã thành công có thể bị chạy lại, gây tốn chi phí và tác động trùng. Nên retry riêng child hoặc batch lỗi với idempotency key ổn định.

**Câu 5.** Vì sao giới hạn concurrency theo workflow chưa đủ để bảo vệ database?

**Gợi ý trả lời:** Nhiều workflow có thể chạy đồng thời; concurrency tổng bằng tổng child của tất cả workflow. Cần giới hạn toàn hệ thống, per-tenant và tuân thủ capacity của downstream.

**Bài tập tình huống:** Một job cần tạo thumbnail cho 12.000 ảnh. Mỗi child mất trung bình 3 giây, database chịu được tối đa 120 lần ghi đồng thời và mỗi tenant chỉ được chạy tối đa 30 child song song. Hãy đề xuất cách chia batch, concurrency, chính sách retry, join và trạng thái job. Xác định cách xử lý nếu 20 ảnh lỗi sau ba lần thử và client gửi yêu cầu hủy khi 70% ảnh đã hoàn tất.

**Gợi ý:** Chia ảnh thành batch vừa phải hoặc tạo child theo từng ảnh với concurrency bị giới hạn. Mức 30 child mỗi tenant không vượt giới hạn 120 ghi đồng thời nếu chỉ có một tenant; khi nhiều tenant chạy cùng lúc vẫn cần global limit và rate limit theo database. Retry riêng ảnh lỗi với backoff và idempotency key dựa trên job ID, image ID và phiên bản xử lý. Fan-in có thể trả trạng thái `PARTIALLY_SUCCEEDED` kèm danh sách 20 ảnh lỗi nếu nghiệp vụ chấp nhận kết quả một phần. Khi hủy, dừng phát child mới, yêu cầu child đang chạy kiểm tra cancellation và ghi nhận trạng thái đã hoàn tất, đã hủy hoặc không thể hủy. Không xóa kết quả đã tạo; nếu nghiệp vụ yêu cầu hoàn tác, xác định compensation riêng.

## Kết luận

Fan-out giúp chia một workflow thành nhiều tác vụ con; fan-in thu thập kết quả và quyết định khi nào nghiệp vụ có thể tiếp tục. Thiết kế cần xác định rõ cardinality, concurrency, throughput, chính sách join, timeout, retry và idempotency. Queue, batch và giới hạn theo workflow/toàn hệ thống giúp kiểm soát tải; trạng thái bền vững, correlation ID và aggregation theo batch giúp vận hành quy trình lớn. Trong serverless, nên dùng workflow engine hoặc queue cho công việc phân tán và kéo dài, còn parallelism cục bộ trong Java chỉ phù hợp với một số ít tác vụ ngắn trong cùng invocation.
