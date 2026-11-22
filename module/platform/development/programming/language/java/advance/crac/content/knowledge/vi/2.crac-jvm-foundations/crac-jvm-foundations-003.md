# Thông tin thực thi và ảnh hưởng của JIT đến hiệu năng sau restore

Khi một ứng dụng Java được khôi phục từ checkpoint bằng CRaC (Coordinated Restore at Checkpoint), tiến trình tiếp tục từ trạng thái đã được lưu thay vì khởi động một JVM mới từ đầu. Vì vậy, hiệu năng sau restore phụ thuộc vào trạng thái mà JVM đã tích lũy trước checkpoint. Một phần quan trọng của trạng thái đó là dữ liệu profiling và mã máy do JIT compiler tạo ra.

Điều này giải thích vì sao hai checkpoint của cùng một ứng dụng có thể cho kết quả hiệu năng khác nhau: checkpoint được tạo ngay sau khi ứng dụng khởi động thường chứa ít trạng thái JIT đã được làm nóng; checkpoint được tạo sau khi ứng dụng xử lý workload đại diện có thể giữ lại nhiều phương thức đã biên dịch và dữ liệu profiling hữu ích.

## 1. JVM đang giữ những trạng thái nào khi checkpoint?

CRaC phối hợp với JVM để đưa tiến trình về trạng thái có thể checkpoint, xử lý các tài nguyên cần chuẩn bị, rồi lưu ảnh trạng thái tiến trình theo cơ chế được nền tảng hỗ trợ. Khi restore thành công, tiến trình tiếp tục từ ảnh trạng thái đó. Những thành phần quan trọng đối với hiệu năng gồm:

| Thành phần | Vai trò | Ý nghĩa sau restore |
| --- | --- | --- |
| Java heap | Lưu object, cache trong bộ nhớ, dữ liệu ứng dụng và các cấu trúc runtime | Các object đã tồn tại có thể tiếp tục được sử dụng; ứng dụng không phải tạo lại toàn bộ trạng thái trong heap như khi khởi động mới. |
| Class metadata và trạng thái class loading | Lưu thông tin lớp đã nạp, method metadata, constant pool và các dữ liệu liên quan | Những lớp đã được nạp trước checkpoint thường không cần nạp lại từ đầu. Lớp được nạp muộn vẫn có thể phát sinh công việc sau restore. |
| Thread stack và trạng thái thực thi | Lưu ngữ cảnh thực thi của các thread tại thời điểm checkpoint hợp lệ | JVM có thể tiếp tục từ trạng thái đã lưu theo quy tắc của CRaC và nền tảng. Tài nguyên gắn với thread vẫn phải tuân thủ vòng đời checkpoint/restore. |
| JIT code cache | Chứa mã máy native được JIT compiler tạo ra cho các phương thức đã biên dịch | Nếu bản JVM và nền tảng CRaC hỗ trợ khôi phục vùng nhớ này, mã máy đã biên dịch có thể được sử dụng ngay sau restore. |
| Profiling data và bộ đếm runtime | Ghi nhận độ nóng của method, vòng lặp, kiểu object tại call site và hành vi nhánh | JIT có thể tiếp tục sử dụng dữ liệu đã tích lũy để quyết định phương thức nào cần biên dịch hoặc tối ưu lại. |

JIT code cache là vùng nhớ chứa mã máy thực thi trực tiếp trên CPU. Nó khác với bytecode trong file `.class`: bytecode là đầu vào của JVM, còn mã JIT là kết quả biên dịch phụ thuộc vào JVM và kiến trúc CPU. Profiling data cũng quan trọng vì JIT dùng dữ liệu quan sát được khi chạy để chọn chiến lược tối ưu.

Trong các bản HotSpot CRaC tương thích, code cache và dữ liệu profiling là một phần trạng thái bộ nhớ của tiến trình và có thể được giữ trong ảnh checkpoint. Tuy nhiên, không nên coi việc giữ nguyên mọi mã JIT là bảo đảm chung cho mọi bản JDK, hệ điều hành và cách triển khai CRaC. Hãy xác nhận hành vi trên đúng bản JVM, hệ điều hành và kiến trúc CPU đang triển khai. Mã máy đã biên dịch cũng chỉ phù hợp với môi trường CPU tương thích; restore sang môi trường có tập lệnh hoặc đặc tính phần cứng khác có thể không được hỗ trợ.

Checkpoint không lưu trạng thái vật lý của CPU như cache L1/L2/L3, branch predictor hay TLB. Các trạng thái phần cứng này sẽ được hình thành lại khi tiến trình tiếp tục chạy. Tương tự, không nên giả định mọi tài nguyên bên ngoài như kết nối cơ sở dữ liệu, socket hoặc file handle đều có thể được dùng nguyên trạng; ứng dụng cần quản lý chúng theo lifecycle hook của CRaC.

## 2. JIT compiler tạo ra mã thực thi như thế nào?

JVM có thể thực thi bytecode bằng interpreter trước khi quyết định biên dịch một phương thức thành mã máy. Với HotSpot bật tiered compilation, quá trình thường diễn ra qua nhiều mức:

1. **Interpreter:** thực thi bytecode và thu thập thông tin về hành vi của chương trình. Phương thức ít được gọi thường ở giai đoạn này.
2. **C1 compiler:** biên dịch nhanh hơn, thường được dùng ở các mức tối ưu trung gian. Một số mức C1 tập trung vào thu thập profiling data.
3. **C2 compiler:** thực hiện các tối ưu sâu hơn cho những phương thức được xác định là nóng, dựa trên dữ liệu profiling đã thu thập.

JVM không chỉ đếm số lần gọi method. Nó còn quan sát các vòng lặp, kiểu object thường xuất hiện tại một vị trí gọi, nhánh điều kiện và các hành vi runtime khác. Khi một vòng lặp trở nên nóng, JVM có thể dùng On-Stack Replacement (OSR) để chuyển phần thực thi đang chạy trong vòng lặp sang mã đã biên dịch mà không cần đợi method được gọi lại từ đầu.

Profiling giúp JIT đưa ra giả định có cơ sở. Ví dụ, nếu một call site thường xuyên nhận object thuộc cùng một kiểu, compiler có thể tối ưu đường thực thi cho kiểu đó và đặt guard để kiểm tra giả định. Nếu workload thay đổi khiến giả định không còn đúng, JVM có thể deoptimize mã đã tối ưu, quay về mức thực thi ít tối ưu hơn, cập nhật profile rồi biên dịch lại khi cần.

Vì vậy, trạng thái JIT không chỉ là câu trả lời cho câu hỏi “method nào đã được biên dịch?”. Nó còn bao gồm mức biên dịch, dữ liệu profiling, các giả định tối ưu hóa và trạng thái code cache. Những yếu tố này cùng quyết định JVM sẽ thực thi nhanh đến đâu sau restore.

## 3. Vì sao JIT ảnh hưởng đến hiệu năng sau restore?

### 3.1. Checkpoint được tạo khi ứng dụng còn lạnh

Nếu checkpoint được tạo ngay sau khi ứng dụng hoàn tất khởi tạo, phần lớn method nghiệp vụ có thể chưa đủ nóng để JIT biên dịch. Sau restore, ứng dụng có thể nhận request sớm hơn so với một lần khởi động JVM thông thường vì nhiều trạng thái ứng dụng đã được lưu, nhưng các method chưa được làm nóng vẫn phải đi qua interpreter hoặc các mức biên dịch ban đầu.

Khi traffic tăng, JVM tiếp tục thu thập profiling data và biên dịch các method nóng. Trong giai đoạn này, request đầu tiên hoặc một nhóm request đầu tiên có thể chậm hơn request ở trạng thái ổn định. CPU cũng có thể tăng do compiler thread làm việc song song với các thread xử lý request.

### 3.2. Checkpoint được tạo sau khi workload đại diện đã làm nóng ứng dụng

Nếu ứng dụng đã xử lý các luồng nghiệp vụ đại diện trước checkpoint, những method nóng có thể đã được biên dịch và code cache có thể chứa mã máy tương ứng. Khi trạng thái đó được khôi phục thành công, các method này có cơ hội tiếp tục chạy bằng mã đã biên dịch ngay từ những request đầu tiên.

Profiling data được giữ lại cũng giúp JVM không phải quan sát lại toàn bộ hành vi từ đầu trước khi đưa ra một số quyết định biên dịch. Đây là lý do checkpoint sau warm-up có thể giảm độ trễ giai đoạn đầu và rút ngắn thời gian đạt throughput ổn định.

Tuy nhiên, lợi ích chỉ áp dụng cho phần workload đã được làm nóng và trạng thái JIT thực sự được giữ lại. Một endpoint readiness đơn giản có thể chỉ kiểm tra ứng dụng còn sống mà không đi qua các method nghiệp vụ, truy vấn dữ liệu, serialization hoặc template rendering quan trọng. Chạy readiness endpoint nhiều lần vì thế không đồng nghĩa với việc đã làm nóng toàn bộ ứng dụng.

### 3.3. Workload sau restore khác workload trước checkpoint

JIT tối ưu dựa trên hành vi quan sát được. Nếu warm-up chỉ chạy một loại request nhưng production sau restore nhận nhiều loại request khác, profile trước checkpoint có thể không đại diện cho workload thật. JVM có thể phải cập nhật profile, deoptimization một số method hoặc biên dịch lại để thích nghi.

Ví dụ, một method trước checkpoint gần như luôn nhận `ArrayList`, nhưng sau restore thường xuyên nhận nhiều implementation của `List`. Mã được tối ưu theo giả định kiểu hẹp có thể không còn hiệu quả như trước. Guard có thể phát hiện trường hợp không phù hợp và kích hoạt deoptimization; JVM sau đó có thể biên dịch phiên bản khác dựa trên dữ liệu mới.

### 3.4. Code cache và hàng đợi biên dịch có giới hạn

Code cache có dung lượng hữu hạn. Nếu ứng dụng có nhiều method nóng hoặc sinh nhiều phiên bản mã biên dịch, code cache có thể chịu áp lực. Khi đó JVM có thể phải dọn mã cũ, ngừng một số hoạt động biên dịch hoặc không thể tạo thêm mã theo cách mong muốn. Một checkpoint được tạo sau thời gian warm-up dài không mặc nhiên tốt hơn nếu warm-up tạo ra quá nhiều mã ít hữu ích.

Hàng đợi biên dịch và số lượng compiler thread cũng ảnh hưởng đến thời điểm mã mới sẵn sàng. Việc gửi nhiều request warm-up trong thời gian ngắn không chứng minh rằng tất cả method cần thiết đã được biên dịch xong. Nên quan sát log biên dịch và hiệu năng thực tế trước khi quyết định thời điểm checkpoint.

### 3.5. Môi trường thực thi sau restore có thể làm thay đổi kết quả

Ngay cả khi code cache được giữ lại, hiệu năng còn phụ thuộc vào CPU, giới hạn tài nguyên container, mức tải của máy, GC, cache của ứng dụng, kết nối mạng và dịch vụ bên ngoài. CPU cache và branch predictor cần được làm nóng lại; kết nối tài nguyên có thể phải mở lại qua restore hook; dữ liệu bên ngoài có thể đã thay đổi.

Do đó, nếu request chậm sau restore, không nên kết luận ngay rằng JIT đã mất. Cần tách ảnh hưởng của JIT khỏi class loading, GC, I/O, resource reconnection, CPU throttling và trạng thái cache bên ngoài.

## 4. So sánh hai chiến lược tạo checkpoint

| Tiêu chí | Checkpoint sớm, ít warm-up | Checkpoint sau warm-up đại diện |
| --- | --- | --- |
| Thời gian chuẩn bị checkpoint | Thường ngắn hơn | Dài hơn do cần chạy workload warm-up và chờ JVM ổn định |
| Trạng thái JIT | Có thể còn nhiều method ở interpreter hoặc mức biên dịch thấp | Có thể có nhiều method quan trọng đã được biên dịch và có profile hữu ích |
| Request ngay sau restore | Có thể xuất hiện giai đoạn tăng tốc dần khi JIT tiếp tục làm việc | Có cơ hội đạt hiệu năng tốt sớm hơn đối với các đường xử lý đã được làm nóng |
| CPU sau restore | Có thể tăng do profiling và biên dịch tiếp | Có thể giảm phần công việc biên dịch ban đầu; vẫn có thể biên dịch nếu workload mới xuất hiện |
| Rủi ro chính | Warm-up sau restore làm tăng độ trễ ban đầu | Warm-up không đại diện hoặc quá dài có thể lãng phí tài nguyên và tạo profile không phù hợp |

Không có chiến lược tốt nhất cho mọi ứng dụng. Nếu mục tiêu chính là giảm thời gian đưa service vào trạng thái sẵn sàng, checkpoint sớm có thể phù hợp. Nếu mục tiêu là giảm latency của request đầu tiên sau restore, checkpoint sau warm-up đại diện thường đáng thử hơn. Quyết định nên dựa trên SLO và phép đo của workload thực tế.

## 5. Thiết kế warm-up trước checkpoint

Warm-up nên đi qua những đường xử lý có ý nghĩa với traffic production. Với một dịch vụ Java, có thể cân nhắc các nhóm thao tác sau:

- Gọi các endpoint nghiệp vụ quan trọng với dữ liệu đại diện, bao gồm cả nhánh thành công và các nhánh thường gặp.
- Thực thi các luồng serialization/deserialization, mapping object, validation và xử lý dữ liệu có chi phí CPU đáng kể.
- Chạy các truy vấn hoặc thao tác truy cập dữ liệu thường dùng nếu chúng cần làm nóng cache ứng dụng hoặc chuẩn bị trạng thái runtime. Tài nguyên kết nối vẫn phải tuân thủ lifecycle của CRaC.
- Chạy các luồng tạo template, biểu thức, regex hoặc cấu trúc xử lý được khởi tạo lười nếu chúng nằm trên đường request quan trọng.
- Dùng phân bố dữ liệu và tỷ lệ request gần với thực tế để profiling data phản ánh hành vi dự kiến sau restore.

Warm-up cần tránh tạo side effect ngoài ý muốn. Nếu một luồng nghiệp vụ ghi dữ liệu, gửi thông báo hoặc tạo giao dịch, hãy dùng dữ liệu kiểm thử và cơ chế cô lập phù hợp. Không nên gọi một luồng production chỉ để biên dịch JIT nếu thao tác đó gây thay đổi dữ liệu thật.

Một quy trình thực tế có thể gồm các bước:

1. Khởi động ứng dụng và hoàn tất các bước chuẩn bị trạng thái cần thiết.
2. Chạy tập request warm-up đại diện, với số lượng và concurrency gần với giai đoạn traffic đầu tiên sau restore.
3. Quan sát JIT compilation để xác định các method quan trọng có đang tiếp tục được biên dịch hay không.
4. Đo latency và throughput trong một khoảng ổn định. Không chọn checkpoint chỉ dựa trên số lần gọi warm-up.
5. Đưa ứng dụng về trạng thái an toàn cho checkpoint, xử lý tài nguyên theo hướng dẫn CRaC của ứng dụng, rồi tạo checkpoint.
6. Restore nhiều lần trong môi trường tương thích và đo lại cùng workload để xác nhận lợi ích có thể lặp lại.

Không cần cố biên dịch mọi method trong ứng dụng. Các method hiếm khi chạy có thể không ảnh hưởng đến SLO. Warm-up quá rộng hoặc quá lâu làm tăng thời gian chuẩn bị, CPU và có thể làm tăng kích thước trạng thái cần lưu mà không đem lại lợi ích tương xứng.

## 6. Quan sát trạng thái JIT

Có thể dùng các công cụ của HotSpot để xem JVM biên dịch method khi nào và code cache đang được sử dụng ra sao. Tùy bản JDK, một số tùy chọn hoặc diagnostic command có thể khác nhau; hãy kiểm tra khả năng hỗ trợ trên đúng runtime đang chạy.

### Theo dõi log biên dịch

Có thể bật unified logging khi chạy JVM:

```bash
java -Xlog:jit+compilation=debug -jar application.jar
```

Log giúp nhận biết method nào được biên dịch và thời điểm biên dịch. Khi cần quan sát chi tiết hơn trên HotSpot, có thể dùng tùy chọn:

```bash
java -XX:+PrintCompilation -jar application.jar
```

Các dòng log thường thể hiện compile id, mức biên dịch và tên method. Khi so sánh trước checkpoint và sau restore, hãy tập trung vào những method nằm trên đường xử lý quan trọng. Nếu các method đó được biên dịch trước checkpoint và không xuất hiện một đợt biên dịch lại lớn sau restore, đây là một dấu hiệu cho thấy trạng thái JIT đã được giữ lại; vẫn cần kết hợp với phép đo latency và throughput.

### Kiểm tra code cache

Với HotSpot có hỗ trợ diagnostic command tương ứng, có thể chạy:

```bash
jcmd <pid> Compiler.codecache
```

Kết quả giúp quan sát dung lượng code cache và mức sử dụng tại thời điểm kiểm tra. Có thể đối chiếu trước checkpoint và sau restore để tìm dấu hiệu code cache bị thay đổi đáng kể hoặc chịu áp lực. Nếu command không có trên bản runtime đang dùng, kiểm tra danh sách command bằng `jcmd <pid> help` và chọn công cụ tương đương được bản JDK hỗ trợ.

### Dùng Java Flight Recorder

Java Flight Recorder (JFR) có thể ghi nhận sự kiện liên quan đến compilation cùng các sự kiện CPU, GC, class loading và thread. Khi bật các sự kiện phù hợp, JFR giúp xác định độ trễ sau restore có trùng với giai đoạn JIT biên dịch nhiều hay không. Đây là cách hữu ích để phân biệt công việc compiler với các nguyên nhân khác như GC pause hoặc I/O chậm.

Không nên chỉ dựa vào một chỉ số như số method đã biên dịch. Một method có thể được biên dịch nhưng không nằm trên đường request quan trọng; ngược lại, một số method chưa biên dịch vẫn có thể không đáng kể với hiệu năng tổng thể.

## 7. Đo lường để xác định ảnh hưởng thực tế

Một phép thử có ích nên tách riêng thời gian restore, thời gian request đầu tiên, giai đoạn warm-up sau restore và hiệu năng ổn định. Có thể thiết kế ba trường hợp:

| Trường hợp | Cách chuẩn bị | Câu hỏi cần trả lời |
| --- | --- | --- |
| JVM khởi động mới | Khởi động ứng dụng bình thường rồi gửi traffic | Mức tham chiếu khi không dùng checkpoint/restore là bao nhiêu? |
| CRaC checkpoint sớm | Tạo checkpoint khi ứng dụng mới khởi tạo xong, chưa chạy warm-up nghiệp vụ | CRaC rút ngắn thời gian sẵn sàng nhưng còn bao nhiêu chi phí JIT sau restore? |
| CRaC checkpoint đã warm-up | Chạy workload đại diện, quan sát compilation rồi tạo checkpoint | Giữ lại trạng thái JIT có cải thiện latency đầu tiên và thời gian đạt hiệu năng ổn định không? |

Trong mỗi trường hợp, nên ghi nhận:

- Thời gian từ lúc bắt đầu restore đến khi ứng dụng nhận request thành công.
- Latency p50, p95 và p99 của nhóm request đầu tiên, trong giai đoạn chuyển tiếp và khi đã ổn định.
- Throughput và CPU usage trong cùng các khoảng thời gian.
- Số lượng và thời điểm JIT compilation, các method quan trọng được biên dịch ở mức nào.
- Tình trạng code cache, GC, class loading và thời gian khôi phục tài nguyên bên ngoài.

Giữ nguyên phiên bản JDK, JVM flags, CPU hoặc loại máy, giới hạn container, dữ liệu đầu vào, concurrency và cấu hình dịch vụ phụ thuộc giữa các lần đo. Lặp lại nhiều lần để tránh kết luận từ một lần restore có tải nền bất thường. Nếu có thể, chạy cùng workload sau restore trên cùng host và so sánh theo từng cửa sổ thời gian.

Đặc biệt, không gộp thời gian restore với latency của request đầu tiên. Restore có thể nhanh nhưng request đầu tiên vẫn chậm vì JIT, class initialization hoặc resource reconnect. Ngược lại, JIT có thể được giữ nguyên nhưng request vẫn chậm do CPU bị giới hạn hoặc dịch vụ bên ngoài phản hồi chậm.

## 8. Cách đọc một số dấu hiệu thường gặp

| Dấu hiệu quan sát | Nguyên nhân JIT có thể liên quan | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Request đầu chậm, các request sau nhanh dần | Method chưa được biên dịch trước checkpoint; JIT tiếp tục làm nóng sau restore | Log compilation, method nóng và CPU của compiler thread |
| Sau restore có nhiều compilation event | Checkpoint được tạo trước khi warm-up hoàn tất, workload mới xuất hiện hoặc mã cũ bị deoptimize | So sánh method và mức biên dịch trước/sau restore; kiểm tra workload có thay đổi không |
| Method đã biên dịch nhưng latency vẫn cao | JIT không phải nút thắt chính, hoặc profile trước checkpoint không còn phù hợp | GC, I/O, resource reconnect, CPU throttling, cache và dịch vụ phụ thuộc |
| Code cache gần đầy hoặc có dấu hiệu không thể biên dịch thêm | Áp lực code cache có thể hạn chế tối ưu hóa tiếp theo | Code cache statistics, compilation log và cấu hình JVM |
| Chỉ một số endpoint chậm sau restore | Warm-up chưa đi qua các đường xử lý của endpoint đó hoặc endpoint dùng dữ liệu/kiểu object khác | Trace method của endpoint, class loading và profile tại call site |

Các dấu hiệu trên chỉ là hướng điều tra. Muốn kết luận JIT là nguyên nhân, cần đối chiếu log compilation với số đo request và loại trừ các yếu tố runtime khác.

## 9. Những hiểu nhầm cần tránh

**“CRaC loại bỏ hoàn toàn JIT warm-up.”** Không đúng. CRaC có thể khôi phục trạng thái JIT đã tồn tại, nhưng method chưa nóng trước checkpoint vẫn có thể cần profiling và biên dịch sau restore. Kết quả còn phụ thuộc vào bản JVM và nền tảng.

**“Sau restore phải warm-up lại toàn bộ ứng dụng.”** Không nhất thiết. Nếu code cache và profiling data được khôi phục hợp lệ, nhiều method đã nóng có thể tiếp tục sử dụng trạng thái trước checkpoint. Chỉ cần warm-up bổ sung khi workload mới, giả định tối ưu hóa thay đổi hoặc trạng thái runtime cho thấy cần thiết.

**“Đã warm-up một lần thì mọi request sau restore đều nhanh.”** Không đúng. Warm-up chỉ đại diện cho các đường xử lý và phân bố dữ liệu đã chạy. Endpoint ít dùng, nhánh hiếm hoặc kiểu dữ liệu mới vẫn có thể phát sinh chi phí sau restore.

**“Checkpoint lưu cả trạng thái cache của CPU.”** Không đúng. Ảnh checkpoint lưu trạng thái tiến trình theo cơ chế của nền tảng; cache phần cứng, branch predictor và TLB không phải trạng thái bộ nhớ tiến trình được giữ nguyên.

**“Warm-up càng lâu thì checkpoint càng tốt.”** Không đúng. Warm-up cần đại diện cho workload và tạo ra lợi ích đo được. Warm-up quá dài có thể tốn CPU, kéo dài quy trình chuẩn bị và tạo profile không phù hợp với traffic thực tế.

## 10. Kết luận

Hiệu năng JIT sau CRaC restore phụ thuộc chủ yếu vào trạng thái biên dịch và profiling đã có tại thời điểm checkpoint, khả năng bản JVM giữ lại trạng thái đó, và mức độ giống nhau giữa workload trước checkpoint với workload sau restore. Checkpoint sớm thường giúp giảm phần khởi tạo ứng dụng nhưng có thể để lại chi phí JIT warm-up cho giai đoạn sau restore. Checkpoint sau warm-up đại diện có thể giúp request quan trọng đạt hiệu năng tốt sớm hơn, miễn là mã JIT được khôi phục hợp lệ và workload thực tế tương đồng.

Vì vậy, hãy chọn warm-up theo SLO, quan sát compilation và code cache trên đúng runtime CRaC đang dùng, rồi kiểm chứng bằng phép đo riêng cho request đầu tiên và giai đoạn ổn định. Phép đo thực tế mới cho biết phần cải thiện đến từ JIT, từ trạng thái ứng dụng được khôi phục hay từ các yếu tố runtime khác.
