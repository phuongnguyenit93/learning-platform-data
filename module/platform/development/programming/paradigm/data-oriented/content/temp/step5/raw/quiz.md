Trọng tâm nào thể hiện rõ tư duy data-oriented programming khi thiết kế một dịch vụ?
A. Ưu tiên dạng dữ liệu, luồng biến đổi và mẫu truy cập trước khi định cấu trúc xử lý.
B. Xây hệ phân cấp class theo hành vi trước rồi mới xác định nhu cầu truy cập dữ liệu.
C. Sử dụng shared mutable object chung để giảm số đối số cần truyền giữa các module.
D. Truyền dữ liệu dạng Map linh hoạt và để từng consumer tự xác định các bất biến.
Đáp án đúng: A

Khi tách hàm tính giá khỏi đối tượng đơn hàng, lợi ích thiết kế nào sát nhất với mục tiêu data-oriented?
A. Truy cập database trong hàm tính để dùng trạng thái mới nhất của lần gọi.
B. Dùng singleton lưu bảng giá để giảm số tham số của phép tính.
C. Truyền Map động để giữ chữ ký hàm ổn định khi thêm field mới.
D. Kiểm thử phép tính từ đầu vào rõ ràng, không cần dựng vòng đời đối tượng.
Đáp án đúng: D

Một API nhận bản ghi giao dịch với amount và currency, hợp đồng dữ liệu nào an toàn hơn?
A. Lấy currency theo locale máy chạy khi trường của giao dịch vắng mặt.
B. Lưu amount dưới dạng chuỗi và parse tại nơi sử dụng theo từng consumer.
C. Để consumer tự suy luận loại tiền tệ dựa trên giá trị amount.
D. Quy định kiểu, đơn vị, trường bắt buộc và từ chối tổ hợp không hợp lệ.
Đáp án đúng: D

Khi mô hình hóa trạng thái thanh toán, cách nào giúp tránh tổ hợp trường mâu thuẫn?
A. Dùng từng biến thể trạng thái với bộ dữ liệu hợp lệ tương ứng.
B. Dùng nhiều cờ boolean và kiểm tra tổ hợp cờ tại từng thao tác.
C. Dùng String để biểu diễn trạng thái và so sánh trong từng method.
D. Dùng một record chứa trường nullable và suy ra trạng thái theo null.
Đáp án đúng: A

Một Java record chứa List<Item> được tạo từ danh sách mutable; kết luận nào chính xác?
A. Danh sách và phần tử tự thành bất biến sâu nhờ khai báo record.
B. Record không tự sao chép đối tượng mutable mà trường tham chiếu tới.
C. Accessor của record tạo bản sao List phòng thủ ở mỗi lần gọi.
D. Canonical constructor của record thực hiện deep copy các Item.
Đáp án đúng: B

Một phép chuẩn hóa địa chỉ cần giữ nguyên dữ liệu nguồn để phục vụ audit; thiết kế nào phù hợp?
A. Chuẩn hóa trực tiếp nguồn rồi tạo bản audit sau khi ghi thay đổi.
B. Đưa kết quả vào shared map thay cho dữ liệu nguồn để các consumer dùng chung.
C. Tạo kết quả chuẩn hóa mới từ đầu vào, giữ nguyên bản ghi nguồn đã nhận.
D. Sửa field nguồn trong lúc xử lý rồi hoàn tác sau response.
Đáp án đúng: C

Vì sao không nên thay mọi domain object bằng mảng primitive chỉ vì theo đuổi data-oriented design?
A. Mảng primitive có thể làm mờ hợp đồng; chỉ nên đổi layout sau khi đo.
B. Mảng primitive giúp giảm boxing nên tự thích hợp với phần lớn domain model.
C. Dùng mảng primitive khiến các cấu trúc dữ liệu tự có hợp đồng chặt chẽ hơn.
D. JIT có thể gom toàn bộ object graph thành một mảng liên tục.
Đáp án đúng: A

Một hàm nhận dữ liệu khách hàng và tự đọc thời gian hiện tại; điều gì cản trở kiểm thử xác định?
A. Value object được so sánh bằng equals khi được dùng làm cache key.
B. Kết quả phụ thuộc nguồn thời gian ẩn, không chỉ phụ thuộc tham số đầu vào.
C. Lời gọi qua interface khiến hành vi thay đổi ngay cả khi implementation giữ nguyên.
D. Đối tượng kết quả có identity mới mỗi khi hàm được gọi lại.
Đáp án đúng: B

Một báo cáo cần đối chiếu trạng thái kho ở hai thời điểm; cách biểu diễn nào hỗ trợ nhất?
A. Để các báo cáo cùng trỏ vào map mutable và gắn timestamp lúc truy vấn.
B. Ghi đè state trong cache nhưng giữ lại trường version của bản ghi.
C. Lưu tổng tồn hiện tại và tỷ lệ biến động của tháng gần nhất.
D. Lưu snapshot có phiên bản hoặc phát lại chuỗi sự kiện đáng tin cậy.
Đáp án đúng: D

Trường hợp nào phù hợp khi dùng Optional làm kiểu trả về của phép tìm kiếm?
A. Khi lỗi database cần được chuyển thành Optional.empty để caller xử lý thống nhất.
B. Khi cần biểu diễn kết quả có thể vắng mặt và buộc caller xử lý trường hợp đó.
C. Khi serializer cần đưa từng field nullable của entity vào Optional.
D. Khi phải biểu diễn nguyên nhân lỗi chi tiết nhưng không muốn thêm kiểu Result.
Đáp án đúng: B

Khi thêm một trường tùy chọn vào sự kiện được nhiều consumer sử dụng, cách nào an toàn hơn?
A. Tái sử dụng trường cũ cho ý nghĩa mới mà giữ nguyên tên để tránh sửa consumer.
B. Đưa field mới vào danh sách required trước khi kiểm chứng phiên bản consumer.
C. Đổi tên trường cũ mà không giữ alias cho những consumer hiện hành.
D. Kiểm tra tương thích consumer và quy định hành vi khi trường vắng mặt.
Đáp án đúng: D

Một bộ xử lý đơn hàng yêu cầu quantity phải dương; vị trí nào nên bảo vệ bất biến dữ liệu?
A. Đặt validation tại UI nhập liệu như điểm kiểm tra nghiệp vụ chính.
B. Log số lượng âm sau khi dữ liệu đã được ghi để phục vụ audit.
C. Đối chiếu quantity tại bước kết xuất hóa đơn sau khi đã tính tổng.
D. Tại ranh giới tạo hoặc nhận dữ liệu đáng tin cậy trước khi chạy nghiệp vụ.
Đáp án đúng: D

Một bản ghi chứa đồng thời subtotal, discount và total nhưng ba giá trị thường lệch nhau; hướng nào giảm trạng thái dư thừa?
A. Cho các trường được cập nhật riêng và đồng bộ lại ở cuối transaction.
B. Đặt total ở từng layer rồi định kỳ hòa giải giá trị giữa các bản sao.
C. Lưu dữ liệu nguồn rồi dẫn xuất total theo một quy tắc thống nhất.
D. Lưu bản sao total ở một listener riêng rồi đồng bộ theo lịch.
Đáp án đúng: C

Khi một cấu trúc dùng làm map key, value semantics đòi hỏi điều gì?
A. Dùng identity khi hai instance có dữ liệu bằng nhau nhưng được tạo riêng.
B. Tạo hashCode từ field mutable để phân biệt các phiên bản key.
C. Gắn random ID vào hashCode cho từng instance cùng nội dung.
D. Equality và hashing ổn định theo các trường định nghĩa giá trị.
Đáp án đúng: D

Chia sẻ cấu hình immutable giữa nhiều worker giúp giảm rủi ro gì?
A. Worker không thể sửa cùng một cấu hình đang được các worker khác đọc.
B. Các giao dịch database tự được tuần tự hóa khi cùng đọc immutable config.
C. Lời gọi network thành non-blocking do nhiều worker dùng một config.
D. Các worker phản hồi đúng thứ tự request vì dùng chung một snapshot.
Đáp án đúng: A

Một tính toán cập nhật hàng triệu phần tử rồi công bố kết quả cuối cùng; giải pháp cân bằng nào hợp lý?
A. Tạo persistent snapshot mới sau mỗi phép cộng thay vì kết hợp một lượt.
B. Dùng buffer mutable cục bộ khi tính và công bố snapshot đã đóng băng.
C. Dùng một mảng chung và khóa theo toàn bộ quá trình mỗi request ghi.
D. Tạo wrapper object cho từng giá trị để lưu vết trong suốt phép tính.
Đáp án đúng: B

Array of Structures (AoS) thường mô tả cách bố trí nào?
A. Các thuộc tính được giữ trong từng cột riêng, liên kết bằng index.
B. Một hàng dữ liệu được chia thành các bảng theo từng kiểu thuộc tính.
C. Mỗi phần tử chứa các index trỏ tới nhiều mảng thuộc tính dùng chung.
D. Mỗi phần tử mảng đại diện một bản ghi gồm các thuộc tính liên quan.
Đáp án đúng: D

Structure of Arrays (SoA) có đặc điểm nào hữu ích khi duyệt riêng tọa độ x của nhiều điểm?
A. Mỗi điểm lưu đầy đủ các tọa độ trong một instance theo kiểu AoS.
B. Giá trị x nằm cùng mảng, giúp duyệt cột mà không đọc các trường khác.
C. Mỗi tọa độ được giữ trong object riêng và liên kết qua references.
D. Mỗi cột được sao chép sang cột khác trước phép tính để giữ index.
Đáp án đúng: B

Với bài toán liên tục tính tổng một trường trên hàng triệu bản ghi, layout nào thường thuận lợi hơn về locality?
A. Danh sách object đầy đủ, được duyệt tuần tự qua các references.
B. Danh sách linked list với mỗi node cấp phát và chứa next reference.
C. Mảng tham chiếu tới những record được cấp phát phân tán trên heap.
D. Dãy liên tiếp của field cần đọc, chẳng hạn cột primitive kiểu SoA.
Đáp án đúng: D

Một giao diện cần hiển thị đầy đủ mọi thuộc tính của từng bản ghi theo thứ tự; điều gì có thể khiến AoS thuận tiện?
A. Giao diện thực hiện phép tổng hợp theo một cột của hàng triệu bản ghi.
B. Các thuộc tính bản ghi được truy cập gần nhau khi đọc theo từng hàng.
C. AoS làm các cột độc lập nằm liên tiếp theo từng kiểu dữ liệu.
D. AoS tránh boxing ngay cả khi field trong record là wrapper type.
Đáp án đúng: B

Vì sao việc đọc bộ nhớ theo thứ tự liên tiếp thường có lợi cho throughput?
A. Tận dụng cache line và prefetch hơn truy cập bộ nhớ phân tán.
B. Đọc liên tiếp giúp bỏ qua các phép kiểm tra điều kiện trong vòng lặp.
C. Prefetch làm GC không phải quét những object được truy cập liên tiếp.
D. Truy cập tuyến tính loại bỏ việc nạp cache line từ RAM vào CPU.
Đáp án đúng: A

Một vòng lặp qua linked list có nhiều cache miss; nguyên nhân nào hợp lý nhất?
A. Việc lần theo reference có thể truy cập các node nằm rải rác trong bộ nhớ.
B. Pointer chasing thường kích hoạt page fault do các node chứa con trỏ.
C. Linked list có pointer metadata nhưng các node vẫn ở sát nhau trên heap.
D. JVM gom các node liên kết vào một mảng khi tối ưu truy cập next.
Đáp án đúng: A

Hai thread cập nhật hai bộ đếm độc lập nhưng cùng cache line và throughput giảm; hiện tượng nào cần kiểm tra?
A. CPU coherence yêu cầu các thread lấy monitor cho hai counter độc lập.
B. Hai counter tạo retained memory do dùng chung vùng cache line.
C. False sharing gây trao đổi cache line giữa các lõi khi ghi.
D. JIT bỏ qua việc lưu cache line khi counter có kiểu primitive.
Đáp án đúng: C

Tại sao một phiên bản SoA không chắc nhanh hơn AoS trong mọi ứng dụng?
A. SoA cần cấp phát một object wrapper riêng cho từng phần tử của các cột.
B. GC không quản lý được nhiều mảng riêng nằm cạnh nhau trong cùng heap.
C. Chi phí chuyển đổi và kiểu truy cập thực tế có thể lớn hơn lợi ích cache.
D. AoS được JIT vector hóa tốt hơn khi dữ liệu được truy cập ngẫu nhiên.
Đáp án đúng: C

Khi đo kích thước một cấu trúc chứa nhiều object trên HotSpot, yếu tố nào không nên bỏ qua?
A. Object headers, alignment, references và các object được cấp phát riêng.
B. Số method và số field private quyết định toàn bộ kích thước instance.
C. Độ dài tên class được cộng vào object header của mỗi instance.
D. Kích thước bằng tổng số byte của field mà không tính object header.
Đáp án đúng: A

Với phép cộng hàng triệu số nguyên, lợi ích nào có thể có khi thay List<Integer> bằng int[]?
A. Giảm boxing và lượng object/reference cần đi qua khi duyệt dữ liệu.
B. Phép cộng int[] dùng overflow semantics khác Integer sau khi unbox.
C. Phép tăng phần tử int[] là read-modify-write atomic với nhiều thread.
D. JIT bắt buộc thực thi mọi vòng lặp int[] bằng lệnh vector.
Đáp án đúng: A

Khi refactor từ object graph sang mảng primitive, rủi ro nào phải được kiểm tra?
A. GC tự giữ liên kết chỉ số giữa nhiều cột sau khi mảng mở rộng.
B. Mảng phẳng khiến giá trị cột mất thông tin kiểu tại runtime.
C. Phải duy trì mapping chỉ số và bất biến liên kết giữa các cột dữ liệu.
D. Các cột có thể dùng ID ngẫu nhiên thay cho index chung mà không cần mapping.
Đáp án đúng: C

Persistent data structure hỗ trợ snapshot nhiều phiên bản hiệu quả bằng cơ chế nào?
A. Các phiên bản sửa chung một buffer nhưng gắn timestamp khác nhau.
B. Mỗi thay đổi sao chép nguyên object graph để tạo lại mọi node.
C. Lưu duy nhất phiên bản mới nhất và chuyển các phiên bản khác sang log.
D. Chia sẻ phần cấu trúc không đổi giữa các phiên bản và tạo node cần thay.
Đáp án đúng: D

Một hệ thống dùng nhiều array lồng nhau và bị cache miss khi truy cập ngẫu nhiên; cách điều tra nào phù hợp?
A. Tăng số wrapper object để dữ liệu được phân phối đều qua các thế hệ GC.
B. Tăng heap để giảm cache miss mà không phân tích pointer chasing.
C. Profile mẫu truy cập và thử bố trí phẳng trước khi quyết định.
D. Dùng reflection cho mọi phép truy cập để JIT tự điều chỉnh layout.
Đáp án đúng: C

Tại sao tạo nhiều object trung gian trong vòng lặp nóng có thể ảnh hưởng hiệu năng?
A. JVM giữ tất cả object tạm trong old generation để có thể tái sử dụng.
B. Object tạm có thể tăng allocation rate và áp lực garbage collection.
C. Mỗi lệnh new gây một GC pause trước khi object được sử dụng.
D. Các object trung gian tự được ghi ra bộ nhớ native thay vì Java heap.
Đáp án đúng: B

Batch processing thường cải thiện throughput của thao tác ghi database vì lý do nào?
A. Giảm số lần round-trip hoặc chi phí cố định cho mỗi nhóm thao tác.
B. Batch cung cấp semantics exactly-once cho từng lần ghi database.
C. Batch phối hợp thứ tự commit giữa các database độc lập mà không cần transaction.
D. Batch bỏ qua validation từng row nhưng vẫn giữ nguyên kết quả ghi.
Đáp án đúng: A

Một pipeline gom batch quá lớn và làm p99 latency tăng; điều chỉnh nào đúng hướng?
A. Tăng batch size để giảm I/O ngay cả khi request phải chờ lâu hơn.
B. Chờ đủ kích thước batch định trước rồi mới cho request đầu chạy.
C. Đo lại kích thước batch cùng timeout gom dữ liệu theo latency SLO.
D. Đánh giá batch size qua CPU time mà không đo thời gian chờ queue.
Đáp án đúng: C

Trong Entity Component System (ECS), entity thường đóng vai trò gì?
A. Một base class chứa trọn state và hành vi cho từng kiểu thực thể.
B. Một hàng dữ liệu chứa toàn bộ thuộc tính của một game object.
C. Một định danh liên kết các component mô tả trạng thái của thực thể.
D. Một container gắn các method xử lý dữ liệu vào đối tượng tương ứng.
Đáp án đúng: C

Trong ECS, component nên chủ yếu biểu diễn điều gì?
A. Dữ liệu thuộc một khía cạnh thực thể để các system xử lý.
B. Một object chứa state và logic xử lý cho một thực thể cụ thể.
C. Một cấu hình query chọn tập entity để system được lên lịch.
D. Một service truy vấn storage để nạp trạng thái của thực thể.
Đáp án đúng: A

Một system trong ECS thường thực hiện công việc nào?
A. Một factory sinh loại entity mới khi component được cập nhật.
B. Một cấu hình mô tả archetype để chọn entity đưa vào hệ xử lý.
C. Một scheduler sắp xếp toàn bộ system theo thứ tự khởi tạo entity.
D. Chọn entity có component cần thiết rồi xử lý dữ liệu tương ứng.
Đáp án đúng: D

Archetype storage trong ECS thường nhóm entity dựa trên đặc điểm nào?
A. Cùng thời điểm tạo entity để giảm phân mảnh trong vùng lưu trữ.
B. Nhóm theo tập kiểu component đang gắn trên entity.
C. Cùng nhóm entity tag do developer khai báo thay cho tập component.
D. Cùng worker phụ trách entity nhằm giảm chuyển dữ liệu giữa worker.
Đáp án đúng: B

Một ECS dùng sparse set để lưu component; ưu điểm phổ biến là gì?
A. Dùng bộ nhớ GPU làm nơi lưu trực tiếp cho component của mỗi entity.
B. Thay entity identifier bằng pointer tới đối tượng component hiện có.
C. Tra cứu thành viên hiệu quả và duyệt dense storage cho kiểu component đó.
D. Phép xóa trong dense storage giữ nguyên thứ tự insertion của entity.
Đáp án đúng: C

So với hệ phân lớp entity kế thừa sâu, composition bằng component giải quyết điều gì?
A. Tạo subclass cho từng tổ hợp component và override method xử lý.
B. Định nghĩa tập component trong base class và bật cờ những phần đang dùng.
C. Ghép khả năng bằng component, tránh tạo lớp con cho mọi tổ hợp.
D. Component tự thực thi nghiệp vụ mà không cần một system riêng điều phối.
Đáp án đúng: C

Với archetype ECS, việc thêm component mới cho entity có thể tốn chi phí nào?
A. Có thể phải chuyển dữ liệu entity sang vùng lưu trữ archetype khác.
B. Component layout được tái biên dịch khi entity chuyển archetype lúc chạy.
C. Entity giữ nguyên vị trí trong storage và chỉ đổi tên archetype metadata.
D. Thêm component yêu cầu tạo identity entity mới thay vì chuyển dữ liệu lưu trữ.
Đáp án đúng: A

Một physics system cần cập nhật vị trí theo vận tốc, truy vấn entity nào phù hợp nhất?
A. Entity có cả Position và Velocity, không cần xét các component khác.
B. Entity có Position nhưng Velocity được phép suy ra từ ID hiện tại.
C. Entity có Physics tag nhưng thiếu Position vẫn nằm trong tập xử lý.
D. Entity có Velocity mới thay đổi, bỏ qua Position của các tick trước.
Đáp án đúng: A

Một engine ECS muốn replay một mô phỏng; yếu tố nào quan trọng để kết quả có thể lặp lại?
A. Dùng HashMap iteration order làm lịch chạy ổn định cho mọi runtime.
B. Dựa vào cùng CPU model để không cần giữ random seed và input order.
C. Thay scheduler theo số worker mà không khóa thứ tự cập nhật component.
D. Xác định thứ tự cập nhật, input, nguồn random và các quy tắc đồng bộ.
Đáp án đúng: D

Khi tái sử dụng entity ID sau khi xóa, lỗi nào dễ xuất hiện nếu giữ reference cũ?
A. Entity ID cũ có thể bị JVM dùng lại làm object reference sau GC.
B. Reference cũ có thể trỏ nhầm entity mới nếu không kiểm tra generation.
C. Mã ID bị cắt số bit khi chuyển từ sparse index sang native buffer.
D. ID mới tự nhận lại component của thực thể cũ sau khi entity bị xóa.
Đáp án đúng: B

Hai system ECS cập nhật cùng Position component song song; điều kiện nào cần bảo vệ?
A. Chia system thành các module mã nguồn riêng để tránh data race.
B. SoA bảo đảm mỗi cột chỉ có một thread ghi trong suốt thời gian xử lý.
C. Phải xác định quyền ghi, thứ tự hoặc đồng bộ để tránh cập nhật mất dữ liệu.
D. Component tự bảo vệ các thao tác cập nhật đồng thời x và y bằng layout.
Đáp án đúng: C

Một game có hàng trăm nghìn entity nhưng chỉ ít entity thay đổi; hướng tối ưu nào cần đánh giá?
A. Duyệt lại toàn bộ entity trong mỗi system để tận dụng tuần tự bộ nhớ.
B. Dùng singleton làm bộ nhớ component và ghi vào nó qua từng entity.
C. Thêm trường dự phòng vào component để đồng bộ hóa số bytes mỗi entity.
D. Truy vấn theo component và theo dõi nhóm dữ liệu thay đổi khi có lợi.
Đáp án đúng: D

Một ECS chạy query giống nhau mỗi frame; cải tiến nào cần cân nhắc?
A. Cache query và archetype phù hợp, nhưng phải vô hiệu hóa khi thay đổi.
B. Cache danh sách entity ID vĩnh viễn vì kết quả query theo archetype ổn định.
C. Dùng reflection lập lại query plan mỗi tick để tránh stale metadata.
D. Dùng entity ID ranges để lọc thay cho điều kiện component thực tế.
Đáp án đúng: A

Trong ECS, khi system A đọc output của system B trong cùng tick, thiết kế lịch chạy phải làm gì?
A. Chạy system A và B trên thread khác nhau để không tranh chấp scheduler.
B. Xác định system dependency và thứ tự chạy phù hợp trước khi song song hóa.
C. Chạy cùng lúc và dùng giá trị ghi cuối cùng làm kết quả của system A.
D. Dùng một global buffer nhận output của hai system và áp dụng thứ tự đến.
Đáp án đúng: B

Một nhóm chuyển mô hình nhân vật sang ECS, nhưng mỗi entity chứa quá nhiều component ít dùng; đâu là hướng phân tích?
A. Gộp component vào một object chung để system đọc theo từng bản ghi.
B. Tăng worker theo số entity mà giữ nguyên layout của component.
C. Đo nhu cầu truy cập để tách tập dữ liệu nóng khỏi dữ liệu hiếm dùng.
D. Chuyển component ít dùng thành field của base entity để giảm số query.
Đáp án đúng: C

Khi nào ECS có thể là lựa chọn quá phức tạp cho ứng dụng nghiệp vụ?
A. Khi mỗi frame xử lý nhiều entity bằng cùng pipeline component ổn định.
B. Khi hệ thống thường xuyên truy vấn tập con entity theo những component khác nhau.
C. Khi entity có thể thêm bớt component trong thời gian chạy theo yêu cầu.
D. Khi chỉ có vài form CRUD đơn giản và chi phí quản trị ECS không đem lại lợi ích.
Đáp án đúng: D

Một hệ ECS lưu trạng thái để khôi phục game, dữ liệu nào cần được quan tâm?
A. Dùng tên Java class và cấu hình mặc định thay cho trạng thái component.
B. Lưu danh sách system đã chạy nhưng không ghi lại giá trị component.
C. Entity identity, component data và quy tắc phiên bản hóa schema.
D. Lưu raw address của component để tái tạo trong JVM sau khi restart.
Đáp án đúng: C

Vì sao chuyển một component lớn thành các component nhỏ hơn đôi khi cải thiện locality?
A. Tách field khiến JIT cấp phát thêm register cho mọi phép truy cập.
B. Tập system có thể chỉ đọc dữ liệu cần thiết thay vì kéo theo field không dùng.
C. Component nhỏ được JIT giữ toàn bộ trong register suốt vòng đời entity.
D. Thay đổi thành phần entity không còn tốn chi phí chuyển archetype.
Đáp án đúng: B

Xử lý theo lô dữ liệu độc lập có thể cải thiện thông lượng nhờ điều gì?
A. Giảm overhead điều phối và tận dụng truy cập dữ liệu liên tiếp khi phù hợp.
B. Batching cho phép hàng đợi tăng theo throughput mà không cần giới hạn.
C. Gom batch thay thế validation từng record bằng kiểm tra dữ liệu tổng.
D. Gom batch giúp bỏ qua thao tác ghi những bản ghi có khóa giống nhau.
Đáp án đúng: A

Điều kiện nào thường thuận lợi cho SIMD khi xử lý một mảng số?
A. Mỗi lane cần thực hiện một HTTP call riêng để lấy hệ số tính.
B. Các phần tử độc lập được xử lý bằng cùng một phép toán.
C. Giá trị của phần tử sau phụ thuộc kết quả vừa tính ở phần tử trước.
D. Mỗi lane truy cập dữ liệu qua nhiều tầng pointer của một object graph.
Đáp án đúng: B

Khi một vòng lặp Java có dạng đơn giản, kết luận nào về SIMD là chính xác?
A. JIT vector hóa vòng lặp dù dữ liệu có phụ thuộc giữa các iteration.
B. Chuyển sang Stream sẽ khiến các phép map chạy qua vector lane.
C. Việc vector hóa còn tùy JIT, phụ thuộc dữ liệu, layout và phần cứng.
D. Linked list dễ vector hóa hơn mảng do mỗi node có con trỏ next.
Đáp án đúng: C

Một vòng lặp xử lý từng phần tử theo nhiều nhánh điều kiện khác nhau; rủi ro cho SIMD là gì?
A. Điều kiện rẽ nhánh được xử lý như scalar nên không cần mask ở vector lane.
B. Lệnh if khiến JIT không còn xác định được độ dài mảng ở runtime.
C. CPU mặc định chọn cùng nhánh cho mọi lane để tránh giảm hiệu năng.
D. Divergent control flow có thể giảm hiệu quả vectorization.
Đáp án đúng: D

Với kernel xử lý số, vai trò của memory alignment và layout là gì?
A. Alignment là yếu tố quyết định scheduler gán thread tới CPU core.
B. Các mảng nằm sát nhau khiến phép tính integer tự tăng độ rộng bit.
C. Có thể ảnh hưởng hiệu quả đọc/ghi vector và thông lượng bộ nhớ.
D. Layout cho phép bỏ qua kiểm tra biên cả khi index vẫn có thể vượt giới hạn.
Đáp án đúng: C

Một vòng lặp cộng dồn có phụ thuộc giữa các vòng lặp liên tiếp; hướng nào đúng?
A. JIT tự tạo các bản accumulator độc lập dù thuật toán có phụ thuộc.
B. Thay accumulator bằng kiểu số rộng hơn giúp loại bỏ phụ thuộc vòng lặp.
C. Chạy parallel reduction giúp giữ nguyên thứ tự cộng của phiên bản tuần tự.
D. Phân tích dependence và tính kết hợp của phép toán trước khi vector hóa.
Đáp án đúng: D

Vì sao tổng số thực bằng xử lý SIMD có thể khác tổng tuần tự chút ít?
A. Thứ tự cộng dấu phẩy động khác nhau có thể đổi kết quả làm tròn.
B. JIT chuyển mọi phép cộng float thành phép cộng int trong vector lane.
C. SIMD tự giảm độ chính xác của mọi phép cộng xuống kiểu float16.
D. IEEE 754 chuyển mọi NaN thành số 0 trước các phép tính vector.
Đáp án đúng: A

Benchmark một vòng lặp SIMD trên JDK hiện đại nên làm gì để tránh số liệu ảo?
A. Đo lần chạy đầu để đại diện cho steady-state khi JIT chưa warm-up.
B. Kiểm soát warm-up, tiêu thụ kết quả và so sánh input giống nhau.
C. Dùng kết quả từ một input hợp lệ rồi bỏ các test biên khi đo throughput.
D. Đo GC mà không chạy kernel để tránh nhiễu từ compilation.
Đáp án đúng: B

Khi một pipeline chỉ có 10% thời gian ở kernel có thể tăng tốc bằng SIMD, giới hạn nào cần xem xét?
A. Thông lượng toàn pipeline tăng theo tốc độ kernel mà không cần xét phần khác.
B. Các giai đoạn I/O được rút ngắn theo tỷ lệ tăng tốc kernel.
C. Thêm SIMD khiến các stage không vector hóa phải tăng chi phí đồng bộ.
D. Theo Amdahl, phần thời gian còn lại giới hạn tốc độ tăng của toàn pipeline.
Đáp án đúng: D

Một thư viện Java cần chạy trên x86 và ARM với độ rộng vector khác nhau; cách nào phù hợp?
A. Chọn một vector width cố định từ x86 và áp dụng nguyên cho ARM.
B. Biên dịch một bản cho mọi CPU và giả định các vector features như nhau.
C. Kiểm tra CPU và giữ đường scalar cho nền tảng không hỗ trợ.
D. Bỏ scalar path và yêu cầu caller padding mọi input theo vector width.
Đáp án đúng: C

Một nhóm muốn dùng Vector API chưa được chuẩn hóa trong runtime mục tiêu; nguyên tắc nào đúng?
A. Cô lập phần thử nghiệm, đánh giá tương thích phiên bản và duy trì fallback.
B. Giữ API incubating trong core library và kiểm thử trên một bản JDK đã chọn.
C. Module incubating được runtime tự nạp từ classpath dù chưa cấu hình.
D. Đưa API thử nghiệm vào public contract rồi xử lý thay đổi ở mỗi release.
Đáp án đúng: A

Khi vector hóa một phép xử lý mảng, chiến lược xử lý phần tử dư nào cần có?
A. Xử lý số phần tử không chia hết cho vector width bằng đường thích hợp.
B. Cắt phần tử tail khỏi kết quả rồi ghi log để dùng ở lần gọi sau.
C. Padding dữ liệu rồi trả cả phần tử padding như giá trị hợp lệ.
D. Dùng kernel vector cho phần đủ lane và bỏ qua n mod vector width.
Đáp án đúng: A

Một nhóm quyết định đổi AoS thành SoA để tăng tốc nhưng chưa đo workload; bước nào hợp lý nhất?
A. Đổi layout trước khi có baseline rồi so sánh throughput sau release.
B. Profile mẫu truy cập nóng, cache miss và tập input đại diện.
C. So sánh allocation count của hai bản nhưng không đo cache miss và latency.
D. Dùng số field của mỗi class làm dự đoán duy nhất về data locality.
Đáp án đúng: B

Một phiên bản tối ưu dùng mảng primitive nhanh hơn nhưng khó bảo trì và thường phát sinh lỗi mapping; đánh giá nào cần làm?
A. Lấy microbenchmark làm tiêu chí chính khi quyết định giữ layout mới.
B. Bỏ validation trong bản tối ưu để giảm overhead của phép ghi mảng.
C. Cân đối lợi ích thực tế với invariant, độ phức tạp và khả năng kiểm thử.
D. Thêm mapping table mutable toàn cục để sửa nhanh các lỗi index.
Đáp án đúng: C

Một ứng dụng cần cập nhật từng trường lẻ ở nhiều nơi nhưng SoA làm code khó đọc; cách điều chỉnh nào hợp lý?
A. Để caller trực tiếp ghi vào các cột theo index mà không qua API.
B. Che layout bằng API cập nhật bản ghi và bảo vệ các bất biến.
C. Mỗi cập nhật tạo lại cả dataset từ nguồn thay vì sửa bản ghi.
D. Biến các cột thành field static để nhiều module cùng sửa trực tiếp.
Đáp án đúng: B

Khi thay đổi layout dữ liệu nhưng kết quả nghiệp vụ phải giữ nguyên, kiểm thử nào hữu ích nhất?
A. Đối chiếu kết quả và bất biến của hai bản trên cùng dữ liệu đầu vào.
B. So sánh throughput nhưng không kiểm tra các trường hợp đầu vào biên.
C. Benchmark dữ liệu nhỏ rồi giả định kết quả giống nhau trên toàn dataset.
D. Kiểm thử compile và số allocation nhưng bỏ qua kiểm thử tính đúng.
Đáp án đúng: A

Một service có p99 latency tăng sau khi gom batch dù throughput tăng; giải thích hợp lý nào cần kiểm tra?
A. Chỉ đo throughput tổng thay vì thời gian chờ trước xử lý batch.
B. Chờ gom batch có thể kéo dài latency của request đầu nhóm.
C. Batch xử lý đồng thời sẽ xóa thời gian chờ queue của từng request.
D. Gom batch khiến queue wait bằng CPU time của mỗi request.
Đáp án đúng: B

Một hệ thống ECS tăng số worker nhưng throughput không tăng; điều gì nên được đo?
A. Tăng số worker theo số entity đến khi CPU đạt 100% mà không profile.
B. Contention, data locality, memory bandwidth và phần xử lý tuần tự.
C. Phân tích độ sâu kế thừa của component để đo memory bandwidth.
D. Đo riêng thời gian truy vấn archetype nhưng bỏ qua lock contention.
Đáp án đúng: B

Một hệ thống đa nền tảng cân nhắc dùng SIMD nhưng yêu cầu kết quả số học nhất quán; bước nào cần ưu tiên?
A. Dùng kết quả từ một CPU làm ground truth chính xác cho mọi kiến trúc.
B. Chạy correctness test trên đầu vào bình thường và benchmark trên dữ liệu biên.
C. Cho phép tolerance quá rộng khiến các lỗi số học dễ bị che khuất.
D. Quy định sai số chấp nhận và kiểm thử biên trên từng kiến trúc.
Đáp án đúng: D
