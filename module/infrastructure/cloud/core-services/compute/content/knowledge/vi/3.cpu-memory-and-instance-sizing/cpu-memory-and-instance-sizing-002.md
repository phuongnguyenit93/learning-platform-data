# Xung nhịp, hiệu năng đơn luồng và mức độ song song của ứng dụng

Khi chọn cấu hình máy tính toán trên đám mây, số lượng vCPU chỉ cho biết một phần năng lực xử lý. Hai máy ảo có cùng số vCPU vẫn có thể cho thời gian phản hồi và thông lượng rất khác nhau nếu bộ xử lý có kiến trúc, xung nhịp, khả năng tăng tốc, bộ nhớ đệm hoặc cơ chế chia sẻ CPU khác nhau. Tương tự, tăng số lõi không chắc làm một request đơn lẻ hoàn tất nhanh hơn nếu phần lớn công việc của request phải chạy tuần tự.

Đối với **CLOUD_CORE_SERVICES_COMPUTE**, cần hiểu mối quan hệ giữa xung nhịp, hiệu năng đơn luồng và mức độ song song để chọn đúng loại instance, phân bổ CPU hợp lý và tối ưu chi phí vận hành. Các quyết định này ảnh hưởng trực tiếp đến thời gian phản hồi, số request xử lý mỗi giây, thời gian hoàn tất job và khả năng mở rộng của ứng dụng.

## 1. Xung nhịp CPU biểu thị điều gì?

CPU thực thi công việc theo các chu kỳ đồng hồ. **Xung nhịp (clock frequency)** cho biết số chu kỳ đồng hồ trong một giây, thường được biểu thị bằng MHz hoặc GHz. Ví dụ, 3 GHz tương ứng khoảng ba tỷ chu kỳ mỗi giây.

Xung nhịp không phải số lệnh CPU hoàn tất mỗi giây. Trong một chu kỳ, CPU có thể phát hành hoặc hoàn tất nhiều lệnh tùy kiến trúc và điều kiện thực thi; một số lệnh lại cần nhiều chu kỳ. Hiệu năng còn phụ thuộc vào số lệnh hoàn tất trung bình trên mỗi chu kỳ, thường được gọi là **IPC (instructions per cycle)**, cùng khả năng khai thác song song bên trong lõi, cache, bộ nhớ và các thành phần khác.

Một cách hình dung đơn giản cho phần công việc CPU-bound của một luồng là:

\[
\text{Hiệu năng gần đúng} \propto \text{Xung nhịp} \times \text{IPC}
\]

Đây là mô hình giải thích, không phải công thức dự đoán chính xác thời gian chạy. IPC thay đổi theo chương trình, dữ liệu, kiến trúc CPU và trạng thái hệ thống. Vì vậy, không thể kết luận một CPU nhanh hơn chỉ vì thông số GHz cao hơn.

### 1.1. Base frequency và turbo/boost frequency

CPU hiện đại thường điều chỉnh tần số theo tải, nhiệt độ, giới hạn điện năng và số lõi đang hoạt động:

- **Base frequency:** mức tần số cơ sở được nhà sản xuất công bố theo điều kiện và giới hạn công suất quy định.
- **Turbo/boost frequency:** mức tần số có thể đạt trong một khoảng thời gian hoặc với một số lõi khi còn dư ngân sách nhiệt và điện năng.
- **Effective frequency:** tần số thực tế trong khoảng quan sát, chịu ảnh hưởng của tải, giới hạn công suất, nhiệt độ và trạng thái tiết kiệm năng lượng.

Mức boost tối đa thường không có nghĩa mọi lõi đều duy trì mức đó liên tục. Một workload đơn luồng có thể được boost cao hơn workload dùng toàn bộ lõi, bởi tải đa luồng tạo ra nhiều nhiệt và tiêu thụ điện năng hơn. Khi hệ thống chạm giới hạn nhiệt hoặc công suất, CPU có thể giảm tần số (thermal/power throttling).

Trong môi trường đám mây, khách hàng có thể không được xem đầy đủ thông tin nhiệt độ hay giới hạn điện năng của host. Một số loại instance cung cấp CPU hiệu năng ổn định hơn, một số loại cho phép burst trong giới hạn nhất định. Cần xem đặc tính của loại máy và metric mà nhà cung cấp công bố, thay vì giả định vCPU luôn chạy ở một mức GHz cố định.

### 1.2. Vì sao cùng GHz nhưng hiệu năng khác nhau?

Hai CPU chạy cùng tần số có thể xử lý cùng chương trình với tốc độ khác nhau do:

- **Kiến trúc vi xử lý:** độ rộng thực thi, khả năng dự đoán nhánh, thực thi ngoài thứ tự và thiết kế pipeline khác nhau.
- **IPC:** số lệnh hoàn tất mỗi chu kỳ phụ thuộc loại lệnh và dữ liệu.
- **Cache:** dung lượng và độ trễ của L1, L2, L3 ảnh hưởng khả năng lấy dữ liệu mà không phải truy cập RAM.
- **Bộ nhớ:** độ trễ, băng thông và cách CPU truy cập RAM ảnh hưởng workload có tập dữ liệu lớn.
- **Tập lệnh:** các phần mở rộng SIMD hoặc accelerator có thể tăng tốc những phép toán phù hợp.
- **Giới hạn vận hành:** CPU có thể bị giới hạn công suất, nhiệt độ hoặc lịch cấp CPU của nền tảng ảo hóa.

Ví dụ, một ứng dụng xử lý chuỗi và rẽ nhánh nhiều có thể hưởng lợi từ IPC, cache và dự đoán nhánh tốt. Một ứng dụng tính toán ma trận có thể hưởng lợi từ vector instruction và băng thông bộ nhớ. Vì vậy, kết quả benchmark của một chương trình không đại diện cho mọi loại ứng dụng.

## 2. Hiệu năng đơn luồng

**Hiệu năng đơn luồng (single-thread performance)** mô tả khả năng một luồng thực thi hoàn thành công việc. Một luồng có thể chứa nhiều lệnh đang được CPU xử lý song song ở cấp vi kiến trúc, nhưng luồng đó vẫn có một luồng điều khiển tuần tự: lệnh phụ thuộc vào kết quả trước phải chờ kết quả đó.

Hiệu năng đơn luồng đặc biệt quan trọng khi một phần đáng kể công việc nằm trên đường thực thi tuần tự hoặc khi một tác vụ có ít cơ hội chia nhỏ. Ví dụ:

- Một request API thực hiện nhiều bước xử lý nối tiếp trước khi trả kết quả.
- Một giao dịch cần đọc trạng thái, kiểm tra điều kiện và cập nhật dữ liệu theo thứ tự.
- Một đoạn mã xử lý tuần tự dữ liệu lớn mà chưa được thiết kế để chia thành các phần độc lập.
- Một luồng điều phối hoặc event loop có một đoạn xử lý CPU nặng làm chặn các tác vụ khác.

Với các trường hợp này, tăng số lõi có thể giúp xử lý nhiều request hoặc job đồng thời, nhưng không nhất thiết giảm thời gian chạy của một request riêng lẻ. Nếu đường xử lý chính bị giới hạn bởi một luồng, CPU có hiệu năng đơn luồng cao hơn thường có ích hơn việc chỉ tăng số vCPU.

### 2.1. Những yếu tố quyết định tốc độ của một luồng

Hiệu năng đơn luồng phụ thuộc đồng thời vào xung nhịp thực tế, IPC, cache, độ trễ bộ nhớ và cấu trúc chương trình. Các điểm thường gặp gồm:

- **Phụ thuộc dữ liệu:** lệnh sau phải đợi kết quả lệnh trước, khiến CPU khó khai thác nhiều lệnh song song.
- **Cache miss:** dữ liệu không có trong cache khiến luồng phải chờ RAM hoặc tầng lưu trữ bộ nhớ thấp hơn.
- **Branch misprediction:** CPU dự đoán sai nhánh và phải loại bỏ một phần công việc đã thực hiện theo dự đoán.
- **Khóa và đồng bộ:** một luồng chờ lock hoặc chờ luồng khác thì không tận dụng được năng lực tính toán của lõi.
- **CPU throttling hoặc scheduling delay:** luồng bị giới hạn thời gian chạy hoặc phải chờ được cấp CPU.

Do đó, khi một luồng chạy chậm, cần phân biệt nó đang thực sự tính toán, chờ dữ liệu, chờ khóa hay chờ lịch CPU. Nâng GHz chỉ giúp trực tiếp trong một số trường hợp CPU-bound.

### 2.2. Workload nhạy hiệu năng đơn luồng

| Workload | Vì sao đơn luồng quan trọng | Chỉ số cần quan sát |
| --- | --- | --- |
| API có logic tuần tự | Một request phải đi qua chuỗi bước xử lý nối tiếp | Thời gian xử lý CPU mỗi request, p95/p99 latency |
| Một số tác vụ cơ sở dữ liệu | Một truy vấn hoặc một phần thực thi có thể bị giới hạn bởi một luồng | Query latency, CPU time, execution plan |
| Nén/giải nén hoặc mã hóa đơn luồng | Một luồng xử lý khối dữ liệu theo trình tự | Thời gian hoàn tất, MB/s mỗi luồng |
| Runtime hoặc event loop | Công việc CPU dài trên luồng điều phối có thể làm chậm nhiều tác vụ khác | Event-loop lag, thời gian chạy callback |
| Tác vụ điều khiển và điều phối | Có phần logic tuần tự trước hoặc sau các tác vụ song song | Thời gian hoàn tất phần tuần tự |

Đây là xu hướng chứ không phải quy tắc tuyệt đối. Nhiều cơ sở dữ liệu, thư viện mã hóa và runtime có thể song song hóa một phần công việc. Cần đo chính ứng dụng và phiên bản thư viện đang dùng.

## 3. Mức độ song song của ứng dụng

**Song song (parallelism)** là khả năng thực hiện nhiều phần công việc cùng một thời điểm, thường bằng nhiều lõi hoặc nhiều bộ xử lý. Ứng dụng có thể chia dữ liệu thành các phần độc lập, xử lý nhiều request đồng thời hoặc chạy các worker riêng.

Cần phân biệt hai khái niệm:

- **Concurrency (đồng thời):** nhiều tác vụ cùng tiến triển trong một khoảng thời gian; hệ thống có thể luân phiên giữa chúng trên một lõi.
- **Parallelism (song song):** nhiều tác vụ thực sự được thực thi cùng thời điểm trên nhiều năng lực xử lý.

Một ứng dụng bất đồng bộ có thể quản lý hàng nghìn kết nối đồng thời mà không cần tạo một luồng CPU cho mỗi kết nối. Nếu các tác vụ chủ yếu chờ mạng hoặc đĩa, mô hình này có thể tiết kiệm tài nguyên. Nhưng khi mỗi tác vụ thực hiện tính toán CPU nặng, muốn tăng tốc bằng nhiều lõi thì công việc cần được phân chia và chạy song song phù hợp.

### 3.1. Hai kiểu song song phổ biến

**Task parallelism** chia ứng dụng thành các tác vụ khác nhau có thể chạy đồng thời. Ví dụ, một dịch vụ có thể xác thực request, ghi log và xử lý nghiệp vụ bằng các thành phần độc lập, miễn là quan hệ phụ thuộc và thứ tự dữ liệu được bảo đảm.

**Data parallelism** chia một tập dữ liệu thành nhiều phần rồi áp dụng cùng một phép xử lý lên từng phần. Ví dụ, hệ thống phân tích chia một tập bản ghi thành nhiều partition để các worker xử lý đồng thời, sau đó tổng hợp kết quả.

| Kiểu song song | Ví dụ | Điểm cần kiểm soát |
| --- | --- | --- |
| Task parallelism | Nhiều worker xử lý các loại job độc lập | Phụ thuộc giữa tác vụ, lock, hàng đợi và giới hạn worker |
| Data parallelism | Chia tập dữ liệu thành partition để tính toán | Cân bằng kích thước partition, chi phí gom kết quả, dữ liệu dùng chung |
| Request parallelism | Nhiều request API được xử lý đồng thời | Connection pool, giới hạn concurrency, áp lực lên dependency |
| SIMD/vectorization | Một lệnh xử lý nhiều phần tử dữ liệu cùng loại | Căn chỉnh dữ liệu, kiểu dữ liệu và hỗ trợ tập lệnh |

### 3.2. Không phải công việc nào cũng song song hóa được

Một phần chương trình có thể phụ thuộc vào kết quả của phần trước. Ví dụ, tính phần tử tiếp theo của một chuỗi đệ quy có thể cần kết quả phần tử hiện tại. Việc chia nhỏ công việc cũng tạo thêm chi phí: tạo task, lập lịch, đồng bộ, trao đổi dữ liệu và tổng hợp kết quả.

Một ứng dụng có thể có nhiều thread nhưng không đạt tốc độ tương ứng với số lõi vì:

- Các thread tranh chấp cùng một lock hoặc cập nhật dữ liệu dùng chung.
- Công việc bị lệch tải, một worker nhận phần nặng hơn và trở thành nút thắt.
- Chi phí tạo thread, context switch và đồng bộ lớn.
- Nhiều thread cùng truy cập bộ nhớ làm bão hòa băng thông RAM hoặc cache.
- Một phần tuần tự của chương trình giới hạn tốc độ tổng thể.

Tăng số thread vô hạn có thể làm hiệu năng giảm do oversubscription. Với workload CPU-bound, số worker nên được thử nghiệm quanh số lõi xử lý khả dụng và điều chỉnh theo đặc tính thực tế. Với workload I/O-bound, số tác vụ đồng thời có thể lớn hơn số lõi, nhưng phải giới hạn theo khả năng của dependency và connection pool.

## 4. Định luật Amdahl và giới hạn tăng tốc

Định luật Amdahl mô tả giới hạn tăng tốc khi chỉ một phần chương trình có thể chạy song song. Nếu \(P\) là tỷ lệ công việc có thể song song hóa và \(N\) là số bộ xử lý thực thi song song, tốc độ tăng tối đa lý tưởng so với chạy trên một bộ xử lý được ước tính:

\[
S(N) = \frac{1}{(1-P) + \frac{P}{N}}
\]

Trong đó, \(1-P\) là phần công việc phải chạy tuần tự. Công thức giả định các bộ xử lý có năng lực tương đương và bỏ qua chi phí đồng bộ, giao tiếp, lập lịch, tranh chấp bộ nhớ cũng như các nút thắt khác. Hệ thống thực tế thường đạt thấp hơn giới hạn lý tưởng.

Ví dụ, nếu 80% thời gian thực thi có thể song song hóa (\(P=0.8\)) và dùng 4 lõi (\(N=4\)):

\[
S(4) = \frac{1}{0.2 + \frac{0.8}{4}} = 2.5
\]

Ứng dụng chỉ tăng tốc lý tưởng 2,5 lần, dù số lõi tăng từ một lên bốn. Khi tăng lên 8 lõi:

\[
S(8) = \frac{1}{0.2 + \frac{0.8}{8}} \approx 3.33
\]

Lợi ích tăng thêm đã giảm rõ rệt. Nếu phần tuần tự lớn, thêm lõi sẽ nhanh chóng có hiệu quả biên thấp. Khi đó, tối ưu thuật toán hoặc rút ngắn phần tuần tự có thể đem lại lợi ích lớn hơn việc mua instance nhiều vCPU hơn.

Một góc nhìn khác là định luật Gustafson: khi quy mô bài toán tăng cùng năng lực xử lý, nhiều lõi có thể giúp hoàn thành bài toán lớn hơn trong thời gian gần tương đương. Điều này phù hợp với batch, mô phỏng và phân tích dữ liệu, nơi có thể tăng số bản ghi hoặc kích thước dữ liệu xử lý song song. Tuy nhiên, phải tính cả chi phí đọc dữ liệu, tổng hợp và lưu kết quả.

## 5. Lõi vật lý, logical CPU, SMT và vCPU

Khi chọn instance, cần hiểu các đơn vị CPU được công bố có thể không tương đương nhau.

- **Lõi vật lý (physical core):** một lõi xử lý phần cứng trong CPU.
- **Logical CPU/hardware thread:** một ngữ cảnh thực thi logic mà hệ điều hành có thể lập lịch. Công nghệ SMT (Simultaneous Multithreading) cho phép một lõi vật lý duy trì nhiều hardware thread.
- **vCPU:** đơn vị CPU ảo được máy ảo hoặc nhà cung cấp đám mây trình bày cho hệ điều hành khách. Cách ánh xạ vCPU vào hardware thread, lõi vật lý hoặc phần năng lực CPU phụ thuộc nền tảng và loại instance.

SMT có thể cải thiện mức sử dụng tài nguyên của lõi khi một thread bị chờ dữ liệu hoặc không khai thác hết các đơn vị thực thi. Tuy nhiên, hai logical CPU trên cùng một lõi vẫn chia sẻ nhiều tài nguyên vật lý. Vì vậy, hai logical CPU không nhất thiết cho thông lượng bằng hai lõi vật lý độc lập.

Tương tự, không nên mặc định một vCPU luôn tương đương một lõi vật lý. Hãy kiểm tra định nghĩa vCPU, loại instance, thế hệ CPU và cam kết hiệu năng của nhà cung cấp. Nếu ứng dụng cần năng lực xử lý ổn định, hãy xem xét loại instance có CPU chuyên dụng hoặc mức cô lập cao hơn khi dịch vụ đó cung cấp.

## 6. Chọn instance theo đặc tính xử lý

Một cách chọn cấu hình thực tế là xác định ứng dụng cần tốc độ cho một luồng, thông lượng tổng thể hay khả năng xử lý nhiều tác vụ đồng thời.

| Đặc tính workload | Hướng lựa chọn CPU | Lý do |
| --- | --- | --- |
| Đường xử lý tuần tự, nhạy latency | Ưu tiên hiệu năng đơn luồng và tần số duy trì tốt | Một request khó tận dụng thêm lõi nếu phần lớn công việc nối tiếp |
| Nhiều request CPU-bound độc lập | Cân bằng hiệu năng mỗi lõi và số lõi | Thêm lõi có thể tăng số request xử lý đồng thời |
| Batch có thể chia partition | Ưu tiên số lõi và băng thông bộ nhớ phù hợp | Nhiều worker có thể xử lý các phần dữ liệu riêng |
| Workload I/O-bound | Ưu tiên đủ CPU cho xử lý, sau đó kiểm tra mạng, storage và concurrency | Tăng CPU không giúp nhiều nếu thời gian chủ yếu chờ I/O |
| Workload có tải burst | Xem xét khả năng burst, giới hạn và cơ chế credit của instance | Cần phân biệt hiệu năng ngắn hạn với năng lực duy trì dài hạn |
| Workload cần hiệu năng ổn định | Xem xét loại CPU, mức cô lập và cam kết của nhà cung cấp | Giảm biến động do chia sẻ hoặc giới hạn tài nguyên |

Các nhóm instance thường gặp gồm:

- **General purpose:** cân bằng CPU và bộ nhớ, phù hợp ứng dụng web, dịch vụ nghiệp vụ và môi trường phát triển.
- **Compute optimized:** tập trung vào năng lực CPU trên mỗi instance, phù hợp xử lý tính toán, batch và ứng dụng cần nhiều CPU.
- **Memory optimized:** dành nhiều bộ nhớ cho workload có working set lớn; cần kiểm tra CPU đi kèm có đủ đáp ứng tải hay không.
- **Accelerated computing:** cung cấp GPU hoặc bộ tăng tốc chuyên dụng cho workload có thể tận dụng chúng.

Tên nhóm và cấu hình cụ thể thay đổi theo nhà cung cấp. Không nên chọn loại máy chỉ từ tên nhóm; hãy đối chiếu số vCPU, dung lượng RAM, kiến trúc CPU, mạng, lưu trữ và giới hạn hiệu năng.

### 6.1. Xem xét kiến trúc CPU và khả năng tương thích

Các instance có thể sử dụng kiến trúc x86-64 hoặc Arm. Kiến trúc khác nhau có thể có hiệu năng, hiệu suất năng lượng và chi phí khác nhau. Trước khi chuyển kiến trúc, cần xác minh:

- Hệ điều hành, runtime, thư viện native và dependency có hỗ trợ kiến trúc đích không.
- Container image có manifest đa kiến trúc hoặc được build đúng kiến trúc không.
- Các thư viện mã hóa, nén, xử lý số hoặc SIMD có đường thực thi phù hợp không.
- Benchmark trên dữ liệu đại diện có đạt mục tiêu latency và throughput không.
- Chi phí chuyển đổi, kiểm thử, triển khai và vận hành có nằm trong ngân sách không.

Không có kiến trúc nào luôn nhanh hơn cho mọi ứng dụng. Hiệu năng phụ thuộc thế hệ CPU, compiler, thư viện và kiểu workload cụ thể.

## 7. Đo hiệu năng đơn luồng và song song

Để chọn instance, cần benchmark theo hai chiều: tốc độ của một luồng và khả năng tăng throughput khi tăng số worker.

### 7.1. Chuẩn bị bài kiểm tra đại diện

Một benchmark có giá trị nên dùng cùng phiên bản ứng dụng, cấu hình runtime, tập dữ liệu và điều kiện tải. Dữ liệu phải đủ lớn để phản ánh hành vi cache và bộ nhớ thực tế. Với ứng dụng có thời gian khởi động hoặc JIT compilation, cần có giai đoạn warm-up trước khi ghi số liệu.

Nên tách hai nhóm kiểm tra:

1. **Single-worker test:** chạy một worker hoặc một request tại một thời điểm để đo thời gian xử lý đơn lẻ và mức sử dụng CPU.
2. **Concurrency sweep:** tăng dần số worker hoặc request đồng thời để đo throughput, latency phân vị, mức sử dụng CPU và điểm bão hòa.

Khi so sánh các instance, ghi rõ kiến trúc CPU, loại instance, số vCPU, memory, giới hạn CPU nếu có, thời gian chạy và các thành phần dependency. Chạy lặp lại nhiều lần để nhận diện biến động.

### 7.2. Các chỉ số cần theo dõi

| Chỉ số | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| CPU utilization | Mức sử dụng CPU trong khoảng đo | Nhận biết tải CPU tổng thể; cần kết hợp với số liệu theo từng lõi/thread |
| Per-thread CPU time | Thời gian CPU mà từng thread tiêu thụ | Xác định một thread có trở thành nút thắt không |
| Effective frequency | Tần số hoạt động thực tế nếu nền tảng cho phép quan sát | Nhận diện giảm xung do giới hạn hoặc thay đổi trạng thái |
| Run queue / CPU wait | Số tác vụ chờ được cấp CPU hoặc thời gian chờ lập lịch | Nhận biết thiếu năng lực CPU hoặc tranh chấp |
| Throughput | Số request, job hoặc bản ghi xử lý mỗi giây | Đo năng lực tổng thể |
| p50/p95/p99 latency | Phân vị thời gian phản hồi | Đánh giá trải nghiệm và độ ổn định |
| CPU throttling/steal | Thời gian bị giới hạn hoặc chờ CPU ở tầng ảo hóa, nếu có metric | Phát hiện giới hạn CPU và tranh chấp |
| Cost per unit | Chi phí trên mỗi request, job hoặc đơn vị dữ liệu | So sánh hiệu quả kinh tế giữa các cấu hình |

CPU utilization 100% trên một lõi có thể là dấu hiệu của một luồng tuần tự bão hòa, dù tổng CPU của instance còn thấp. Ngược lại, CPU utilization cao trên tất cả lõi cùng throughput tăng có thể là dấu hiệu ứng dụng đang khai thác song song tốt. Nếu CPU thấp nhưng latency cao, cần điều tra chờ mạng, storage, lock hoặc dependency.

### 7.3. Tránh benchmark gây hiểu nhầm

- Không dùng một bài tính toán tổng hợp duy nhất để đại diện cho API, cơ sở dữ liệu và batch.
- Không so sánh kết quả trong khi một máy đang warm cache và máy kia đang cold cache.
- Không bỏ qua thời gian khởi động, JIT, garbage collection hoặc quá trình tải dữ liệu.
- Không chỉ đo throughput; cần đo p95/p99 và tỷ lệ lỗi ở cùng mức tải.
- Không tăng concurrency vượt quá khả năng dependency rồi quy toàn bộ suy giảm cho CPU.
- Không kết luận từ một lần chạy ngắn nếu instance có cơ chế burst hoặc giới hạn theo thời gian.

## 8. Ví dụ: API tuần tự kết hợp worker song song

Giả sử một dịch vụ nhận request, xác thực dữ liệu, tính phí và lưu kết quả. Trong mỗi request, bước kiểm tra quy tắc và tính toán chính chạy tuần tự. Sau khi lưu kết quả, dịch vụ phát sự kiện để các worker xử lý gửi thông báo và cập nhật báo cáo.

Kiến trúc có hai dạng tải:

- Đường request chính nhạy với thời gian xử lý của một luồng. CPU có hiệu năng đơn luồng tốt có thể giảm thời gian xử lý mỗi request.
- Nhóm worker xử lý nhiều sự kiện độc lập. Thêm lõi và tăng số worker có thể tăng throughput, miễn là database và message broker còn đủ năng lực.

Nếu chỉ tăng số vCPU, thời gian xử lý tuần tự của một request có thể gần như không đổi. Nếu chỉ chọn CPU có hiệu năng đơn luồng cao nhưng quá ít lõi, hàng đợi worker có thể tích lũy trong giờ cao điểm. Cấu hình tốt cần cân bằng hiệu năng mỗi lõi, số lõi, bộ nhớ và năng lực của dependency.

Quy trình thử nghiệm có thể là:

1. Đo thời gian CPU của đường request chính với một request tại một thời điểm.
2. Đo throughput và p95/p99 khi tăng số request đồng thời.
3. Đo riêng số sự kiện worker xử lý mỗi giây và độ dài backlog.
4. Tăng số worker theo từng bước, theo dõi CPU, lock, connection pool và độ trễ database.
5. So sánh nhiều loại instance bằng cùng bộ dữ liệu và cùng tiêu chí SLO.
6. Chọn cấu hình có chi phí trên mỗi request hoặc mỗi sự kiện thấp nhất trong khi vẫn đáp ứng mục tiêu latency và thông lượng.

## 9. Tối ưu phần mềm trước khi tăng số lõi

Nếu ứng dụng chưa tận dụng được nhiều lõi, tăng vCPU có thể chỉ làm tăng chi phí. Một số hướng cải thiện thường hiệu quả:

- Rút ngắn phần tuần tự trên đường xử lý quan trọng.
- Chia tác vụ độc lập thành partition có kích thước hợp lý.
- Giảm lock contention bằng cách giảm dữ liệu dùng chung hoặc dùng cấu trúc phù hợp.
- Dùng thread pool thay vì tạo thread mới cho từng tác vụ ngắn.
- Điều chỉnh batch size để cân bằng chi phí lập lịch và độ trễ.
- Tránh oversubscription; đặt giới hạn worker theo CPU khả dụng và khả năng dependency.
- Dùng vectorization hoặc thư viện tối ưu khi workload xử lý mảng số liệu phù hợp.
- Chuyển phần chờ I/O sang mô hình bất đồng bộ khi runtime và ứng dụng hỗ trợ.

Khi tối ưu, cần kiểm tra tính đúng đắn của đồng bộ và thứ tự dữ liệu. Một chương trình chạy nhanh hơn nhưng tạo race condition, mất cập nhật hoặc xử lý sự kiện sai thứ tự không phải là cải thiện có thể chấp nhận.

## 10. Quy trình chọn cấu hình CPU cho workload

Có thể áp dụng quy trình sau khi thiết kế hoặc điều chỉnh instance:

1. **Xác định mục tiêu dịch vụ:** latency p95/p99, throughput, thời gian hoàn tất job, tỷ lệ lỗi và ngân sách.
2. **Phân loại workload:** CPU-bound hay I/O-bound; nhạy đơn luồng hay có thể song song; tải ổn định hay burst.
3. **Đo baseline:** thu thập thời gian CPU theo thread, mức sử dụng từng lõi, throughput, latency và metric dependency.
4. **Kiểm tra giới hạn nền tảng:** định nghĩa vCPU, loại CPU, mức cô lập, burst credit, quota và khả năng quan sát.
5. **Chọn một vài cấu hình đại diện:** so sánh hiệu năng mỗi lõi, số lõi, bộ nhớ và chi phí.
6. **Chạy benchmark có kiểm soát:** thử một worker rồi tăng concurrency theo từng mức.
7. **Tìm điểm bão hòa:** xác định thời điểm throughput không tăng tương xứng nhưng latency, hàng đợi hoặc lỗi bắt đầu tăng.
8. **Đánh giá chi phí:** tính chi phí trên đơn vị công việc hoàn thành, bao gồm cả capacity dự phòng cần thiết.
9. **Triển khai có theo dõi:** áp dụng theo từng nhóm workload, kiểm tra SLO và giữ phương án quay lại cấu hình trước.

Một cấu hình phù hợp không nhất thiết có số vCPU lớn nhất. Nó là cấu hình đáp ứng đặc tính xử lý của ứng dụng, duy trì SLO ở tải dự kiến và có chi phí vận hành hợp lý.

## 11. Những nguyên tắc cần ghi nhớ

1. GHz đo số chu kỳ mỗi giây, không trực tiếp đo số lệnh hoàn tất hay thời gian chạy ứng dụng.
2. Hiệu năng đơn luồng phụ thuộc vào tần số thực tế, IPC, cache, bộ nhớ và cấu trúc chương trình.
3. Thêm lõi chủ yếu giúp tăng khả năng xử lý song song; nó không tự động rút ngắn phần công việc tuần tự.
4. Concurrency và parallelism là hai khái niệm khác nhau; nhiều tác vụ đồng thời không đồng nghĩa tất cả chạy cùng lúc.
5. SMT và vCPU không mặc nhiên tương đương lõi vật lý độc lập.
6. Định luật Amdahl giải thích vì sao phần tuần tự giới hạn lợi ích khi tăng số lõi.
7. Benchmark phải dùng workload đại diện và đo cả throughput, latency phân vị, độ ổn định lẫn chi phí.
8. Chọn CPU cần đặt trong bối cảnh bộ nhớ, mạng, lưu trữ và dependency của toàn hệ thống.

Khi nắm được xung nhịp, hiệu năng đơn luồng và mức độ song song, đội kỹ thuật có thể xác định ứng dụng cần lõi nhanh hơn, nhiều lõi hơn hay cần tối ưu cách chia công việc. Đây là cơ sở để chọn instance phù hợp, mở rộng tải có kiểm soát và duy trì hiệu năng trên hạ tầng đám mây.
