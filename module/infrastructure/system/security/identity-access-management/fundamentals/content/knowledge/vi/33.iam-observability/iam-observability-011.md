# Identity store health: theo dõi sức khỏe kho danh tính trong IAM

## 1. Sức khỏe kho danh tính không chỉ là “còn kết nối được”

Identity store là nơi lưu những dữ liệu danh tính mà hệ thống IAM sử dụng, chẳng hạn định danh tài khoản, trạng thái hoạt động, thuộc tính người dùng, membership hoặc các liên kết với nguồn danh tính khác.

Tùy kiến trúc, kho này có thể là directory, cơ sở dữ liệu ứng dụng, kho danh tính của nhà cung cấp xác thực hoặc một tập hợp nhiều hệ thống. Không mặc định rằng mọi identity store đều lưu mật khẩu, phiên và toàn bộ quyền truy cập ở cùng một nơi.

Identity store health mô tả khả năng kho danh tính cung cấp dữ liệu đúng, đủ mới, trong thời gian chấp nhận được cho những luồng cần nó. Một kết nối mạng thành công chỉ xác nhận được một phần rất nhỏ của yêu cầu đó.

Ví dụ, ứng dụng hợp đồng của An Bình vẫn đọc được directory, nhưng một replica chưa nhận thay đổi khóa tài khoản. Người đã nghỉ việc có thể vẫn xuất hiện là đang hoạt động ở một điểm đọc. Kho vẫn trả lời nhanh, nhưng dữ liệu phục vụ quyết định bảo mật chưa đáp ứng yêu cầu.

Ở chiều ngược lại, dữ liệu có thể chính xác nhưng truy vấn quá chậm khiến đăng nhập, đánh giá quyền hoặc cấp phát tài khoản bị timeout. Vì vậy, cần quan sát đồng thời khả năng phục vụ, hiệu năng, tính đúng và độ mới.

## 2. Đặt kho danh tính vào đúng luồng phụ thuộc

Một kiến trúc minh họa:

~~~mermaid
flowchart LR
    A[Nguồn vòng đời danh tính] --> B[Luồng đồng bộ và cấp phát]
    B --> C[Kho danh tính chính]
    C --> D[Replica hoặc điểm đọc]
    D --> E[Dịch vụ xác thực và đánh giá quyền]
    E --> F[Ứng dụng và tài nguyên]
    D --> G[Cache thuộc tính hoặc membership]
    G --> E
~~~

Sơ đồ này không yêu cầu mọi hệ thống phải có đủ các thành phần. Nó giúp đặt câu hỏi: dữ liệu nào đi qua đâu trước khi ảnh hưởng tới truy cập?

Trước khi dựng dashboard, cần xác định:

| Câu hỏi | Vì sao cần biết |
| --- | --- |
| Nguồn nào có thẩm quyền cho từng thuộc tính? | Tránh coi bản sao là nguồn quyết định cuối cùng |
| Luồng nào đọc trực tiếp và luồng nào dùng cache? | Hiểu vì sao ứng dụng vẫn hoạt động khi kho gặp lỗi |
| Điểm nào nhận thay đổi khóa tài khoản hoặc membership? | Định vị độ trễ của thay đổi bảo mật |
| Những replica nào phục vụ vùng hoặc ứng dụng nào? | Tránh tổng hợp che khuất một vùng bị lỗi |
| Thành phần nào ghi và thành phần nào chỉ đọc? | Chọn probe và quyền vận hành phù hợp |
| Khi phụ thuộc lỗi, từng luồng xử lý ra sao? | Hiểu tác động tới khả năng truy cập và kiểm soát quyền |

Đăng nhập thành công không chứng minh mọi thao tác kho danh tính đều khỏe. Phiên cũ, cache hoặc một nhà cung cấp danh tính khác có thể giúp người dùng tiếp tục sử dụng một phần hệ thống.

Tương tự, lỗi đăng nhập không tự chứng minh kho danh tính hỏng. Nguyên nhân còn có thể nằm ở cấu hình client, yếu tố xác thực, mạng, chính sách hoặc bước tạo phiên.

## 3. Các mặt cần quan sát

Có thể chia việc quan sát thành những mặt bổ sung cho nhau:

| Mặt sức khỏe | Điều cần xác nhận | Ví dụ tín hiệu |
| --- | --- | --- |
| Khả năng phục vụ | Thao tác cần thiết có hoàn tất được không? | Tỷ lệ lỗi, timeout, mất kết nối |
| Độ trễ | Kết quả đến có kịp cho luồng gọi không? | Phân bố latency theo thao tác |
| Tài nguyên và hàng đợi | Thành phần có gần giới hạn vận hành không? | Kết nối, hàng đợi, bộ nhớ, dung lượng |
| Tính đúng của dữ liệu | Kết quả có phù hợp với trạng thái mong đợi không? | Kiểm tra bản ghi, schema, membership |
| Độ mới và hội tụ | Thay đổi được truyền tới nơi cần dùng nhanh đến đâu? | Lag đồng bộ, tuổi backlog, probe phiên bản |
| Khả năng vận hành và phục hồi | Có thể duy trì và khôi phục hệ thống không? | Chứng chỉ, backup, kết quả diễn tập phục hồi |

Không nên biến tất cả thành một đèn xanh mà không giải thích điều kiện. Một kho có thể đọc tốt nhưng ghi lỗi; một replica có thể phục vụ truy vấn nhưng quá cũ; một dịch vụ có thể khỏe ở một vùng và mất khả năng phục vụ ở vùng khác.

Nếu cần trạng thái tổng hợp, trạng thái đó phải đi kèm nguyên nhân và phạm vi. “Degraded do replica vùng A chậm nhận thay đổi” hữu ích hơn “health = 70”.

## 4. Phân biệt liveness, readiness và kiểm tra chức năng

Ba loại kiểm tra thường trả lời các câu hỏi khác nhau:

| Kiểm tra | Câu hỏi | Giới hạn |
| --- | --- | --- |
| Liveness | Tiến trình còn hoạt động theo tiêu chí nội bộ không? | Không chứng minh đã truy cập được dữ liệu cần thiết |
| Readiness | Instance có nên nhận loại lưu lượng dự kiến không? | Phụ thuộc vào những điều kiện thực sự được kiểm tra |
| Functional probe | Một thao tác đại diện có trả đúng kết quả không? | Chỉ bao phủ đường và dữ liệu đã chọn |

Một endpoint health trả HTTP thành công không tự chứng minh nó đã kiểm tra identity store. Cần biết endpoint đó kiểm tra những gì, sử dụng đường kết nối nào và có đi qua cache hay không.

Functional probe có thể đọc một bản ghi tổng hợp đã biết bằng đúng đường mà một dịch vụ cần sử dụng. Kết quả mong đợi không chỉ là “không ném lỗi”, mà còn gồm đúng định danh, đúng trạng thái hoặc đúng phiên bản kiểm tra.

Tuy nhiên, đọc một bản ghi nhỏ không chứng minh truy vấn membership phức tạp cũng khỏe. Có thể cần một số probe đại diện cho các loại thao tác quan trọng, với tải và phạm vi được kiểm soát.

Probe nên dùng danh tính riêng với quyền tối thiểu. Tránh dùng tài khoản quản trị toàn hệ thống chỉ để biết một phép đọc cơ bản có thành công hay không.

Nếu cần kiểm tra ghi, chỉ dùng đối tượng tổng hợp trong vùng được dành riêng và quy trình đã xác định. Không sửa thuộc tính của người dùng thật, tự tạo quyền nhạy cảm hoặc thay đổi membership production để kiểm tra sức khỏe.

Probe cũng phải có timeout, giới hạn tần suất và kiểm soát số lượng. Khi kho đã quá tải, hàng nghìn probe bổ sung có thể làm tình hình tệ hơn.

## 5. Đo thao tác thay vì chỉ đo kết nối

Một identity store có thể hỗ trợ nhiều thao tác với chi phí và ý nghĩa khác nhau:

- Đọc theo định danh chính xác.
- Tìm kiếm theo bộ lọc.
- Đọc membership hoặc quan hệ nhóm.
- Kiểm tra thông tin xác thực nếu kiến trúc sử dụng chức năng đó tại kho.
- Tạo, cập nhật, vô hiệu hóa hoặc xóa bản ghi.
- Nhận và áp dụng thay đổi đồng bộ.

Nên tách latency và kết quả theo những nhóm thao tác có ý nghĩa. Một truy vấn tìm kiếm lớn không nên làm khó đọc biểu đồ của phép tra cứu đơn giản.

Cần phân biệt ba lớp kết quả:

| Lớp | Ví dụ |
| --- | --- |
| Kết nối và giao thức | Không kết nối được, timeout, lỗi từ máy chủ |
| Kết quả thao tác | Tìm thấy, không tìm thấy, từ chối thao tác theo quyền của client |
| Ý nghĩa nghiệp vụ | Bản ghi được trả có đúng tài khoản và trạng thái cần dùng không? |

“Không tìm thấy” có thể là kết quả hoàn toàn hợp lệ khi tra cứu một định danh không tồn tại. Chỉ coi đó là lỗi tính đúng khi có căn cứ bản ghi đáng lẽ phải tồn tại trong phạm vi và tại thời điểm được kiểm tra.

Một thao tác bị từ chối do client không có quyền cũng không đồng nghĩa kho bị mất khả năng phục vụ. Cần theo dõi riêng để nhận ra cấu hình credential hoặc quyền của dịch vụ gặp vấn đề.

Retry có thể che giấu lỗi ban đầu nhưng làm tăng độ trễ và tải. Nên quan sát cả kết quả của lần gọi phía ứng dụng và các lần thử tới kho, với tên rõ ràng để không đếm lẫn hai đơn vị.

## 6. Đọc latency, lỗi và saturation cùng nhau

Latency trung bình dễ che các lượt rất chậm. Các phân vị như p95 hoặc p99 giúp thấy phần đuôi của phân bố, nhưng phải ghi rõ phạm vi thao tác và cách đo.

Cần phân biệt:

- Thời gian client chờ lấy kết nối.
- Thời gian gửi và nhận qua mạng.
- Thời gian xử lý tại kho nếu có phép đo tương ứng.
- Thời gian toàn bộ thao tác ở phía ứng dụng, gồm retry nếu có.

Một truy vấn tại server có thể nhanh nhưng ứng dụng vẫn chậm vì chờ connection pool. Nếu chỉ nhìn server, nhóm vận hành có thể kiểm tra nhầm nơi.

Cũng không nên chỉ báo cáo latency của những lượt thành công rồi bỏ qua timeout. Một biểu đồ p99 đẹp có thể cùng tồn tại với tỷ lệ thất bại lớn. Cần xem latency và kết quả theo cùng một bối cảnh.

Các tín hiệu tài nguyên thường giúp giải thích biến động:

| Tín hiệu | Hướng kiểm tra |
| --- | --- |
| Số kết nối sử dụng gần giới hạn | Rò rỉ kết nối, pool quá nhỏ hoặc số client tăng |
| Thời gian chờ pool tăng | Chậm ở phụ thuộc hoặc cạnh tranh tài nguyên |
| Hàng đợi tăng liên tục | Tốc độ đến vượt khả năng xử lý |
| CPU cao cùng truy vấn tìm kiếm chậm | Bộ lọc, chỉ mục hoặc tải truy vấn thay đổi |
| Dung lượng lưu trữ gần đầy | Nguy cơ lỗi ghi, log hoặc hoạt động nền |
| Lỗi sau một đợt triển khai | Cấu hình kết nối, schema, chứng chỉ hoặc hành vi truy vấn thay đổi |

Các quan sát này là điểm bắt đầu điều tra, không phải kết luận tự động. Cần đối chiếu thời gian, phạm vi và thay đổi triển khai.

Không lấy trung bình các giá trị p99 của nhiều instance để gọi đó là p99 toàn hệ thống. Muốn có phân vị chung, cần phương pháp tổng hợp phù hợp với dạng dữ liệu latency đã thu thập.

## 7. Độ mới dữ liệu và độ trễ truyền thay đổi

Trong IAM, dữ liệu cũ có thể làm chậm cả việc cấp quyền hợp lệ lẫn việc chặn quyền không còn hợp lệ.

Một lần vô hiệu hóa tài khoản có thể đi qua các mốc:

| Mốc | Thời gian minh họa |
| --- | --- |
| Nguồn vòng đời xác nhận tài khoản phải bị vô hiệu hóa | 09:00:00 |
| Kho chính ghi nhận trạng thái mới | 09:00:20 |
| Replica phục vụ ứng dụng phản ánh trạng thái mới | 09:01:10 |
| Điểm kiểm soát của ứng dụng quan sát và áp dụng thay đổi | 09:02:00 |

Từ các mốc này:

~~~text
Độ trễ nguồn đến kho chính = 20 giây

Độ trễ kho chính đến replica = 50 giây

Độ trễ từ nguồn đến mốc áp dụng đã quan sát = 120 giây
~~~

Ba đại lượng không thay thế cho nhau. Lag replication thấp không chứng minh toàn bộ quy trình vô hiệu hóa tài khoản đã hoàn tất.

Mốc cuối cũng phải được định nghĩa cẩn thận. Ứng dụng không cho tạo phiên mới có thể khác với việc các phiên hoặc token đã phát hành trước đó không còn được chấp nhận. Tác động thực tế phụ thuộc vào cơ chế phiên, cache và đánh giá quyền.

Dấu thời gian giữa các máy có thể lệch. Khi dùng chúng để tính lag, cần biết chất lượng đồng bộ thời gian và cách xử lý sai lệch. Trong một số hệ thống, phiên bản thay đổi hoặc vị trí xử lý sự kiện giúp đối chiếu thứ tự tốt hơn, nhưng phải dùng đúng cơ chế mà hệ thống cung cấp.

Không lấy thời điểm một file được sửa làm đại diện cho lúc dữ liệu bảo mật có hiệu lực nếu hai mốc đó không cùng ý nghĩa.

## 8. Replication khỏe chưa chắc dữ liệu đã đúng ở mọi điểm đọc

Một replica có thể nhận heartbeat nhưng chưa áp dụng được một nhóm thay đổi. Một luồng đồng bộ có thể tiếp tục chạy trong khi một bản ghi lỗi bị bỏ lại.

Các câu hỏi cần đặt ra gồm:

- Replica đã nhận tới đâu và đã áp dụng tới đâu?
- Có thay đổi nào đang thất bại hoặc bị bỏ qua?
- Tuổi của thay đổi cũ nhất chưa xử lý là bao nhiêu?
- Thay đổi xóa hoặc vô hiệu hóa có được truyền đầy đủ không?
- Định tuyến có đưa ứng dụng tới một điểm đọc quá cũ không?
- Sau gián đoạn, việc đồng bộ bù có hoàn tất theo quy tắc không?

“Sự kiện gần nhất được xử lý cách đây vài giây” không đủ chứng minh không có backlog cũ. Một pipeline có thể xử lý các sự kiện mới trong khi một số sự kiện quan trọng bị kẹt ở nơi khác.

Tương tự, hàng đợi rỗng không chứng minh dữ liệu đúng nếu sự kiện chưa từng được phát ra, bị mất trước hàng đợi hoặc đã bị loại bỏ mà không xử lý.

Để kiểm tra hội tụ, có thể dùng dữ liệu tổng hợp với phiên bản mong đợi và quan sát ở từng điểm đọc. Phải biết probe đang đọc replica nào và có bị cache che khuất hay không.

Với những thay đổi nhạy cảm như giảm quyền hoặc khóa tài khoản, cần đặt mục tiêu độ mới theo tác động của sự chậm trễ. Không mặc định một mục tiêu duy nhất phù hợp cho mọi thuộc tính.

## 9. Cache và failover có thể che khuất sự cố

Cache thường giúp giảm tải và duy trì hiệu năng, nhưng làm việc diễn giải sức khỏe phức tạp hơn.

Nếu cache còn dữ liệu, phần lớn request có thể thành công trong lúc kho không truy cập được. Sự cố chỉ bộc lộ khi cache hết hạn, gặp danh tính mới hoặc cần đọc dữ liệu chưa từng lưu.

Cần quan sát thêm tỷ lệ hit, miss, tuổi dữ liệu và hành vi khi refresh thất bại. Một cache hit không tự chứng minh dữ liệu đủ mới cho quyết định bảo mật hiện tại.

Negative cache cũng cần được tính tới: một kết quả “không tồn tại” đã lưu có thể khiến tài khoản mới được tạo chưa được nhận diện trong một khoảng thời gian.

Failover phải xét khả năng phục vụ và độ mới của điểm thay thế. Chuyển sang replica trả lời nhanh nhưng thiếu các thay đổi thu hồi quyền có thể tạo ra trạng thái bảo mật không mong muốn.

Không mặc định rằng khi identity store lỗi thì ứng dụng được phép bỏ qua kiểm tra tài khoản hoặc mở rộng quyền. Hành vi khi phụ thuộc lỗi cần được thiết kế trước cho từng luồng, với phạm vi, giới hạn thời gian và khả năng kiểm toán rõ ràng.

Ngay cả lựa chọn từ chối truy cập khi không đủ dữ liệu cũng cần được hiểu về tác động vận hành. Mục tiêu là thực thi chính sách đã xác định trong điều kiện lỗi, thay vì tùy hứng thay đổi chính sách khi có sự cố.

## 10. Luồng ghi và đồng bộ thuộc vòng đời danh tính

Chỉ kiểm tra đọc sẽ bỏ sót những vấn đề ở luồng ghi.

Ví dụ, người dùng hiện có vẫn đăng nhập được, nhưng quy trình tạo tài khoản mới bị kẹt. Hoặc thay đổi membership đã được phê duyệt nhưng chưa tới kho đích. Hệ thống nhìn có vẻ ổn nếu dashboard chỉ theo dõi đăng nhập thành công.

Các tín hiệu hữu ích cho luồng cấp phát và cập nhật gồm:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Số thay đổi đang chờ xử lý | Khối lượng chưa hoàn tất |
| Tuổi thay đổi cũ nhất | Có yêu cầu bị tồn đọng lâu hay không |
| Thời gian từ nguồn đến đích | Độ trễ đầu cuối của một loại cập nhật |
| Lỗi theo nhóm nguyên nhân | Schema, mapping, quyền ghi hoặc phụ thuộc |
| Số lần retry | Mức độ bất ổn và tải bổ sung |
| Số bản ghi cần đối soát | Khoảng cách giữa trạng thái mong đợi và thực tế |

Cần tách loại thay đổi: tạo mới, sửa thuộc tính, thêm quyền, giảm quyền, vô hiệu hóa và xóa. Cùng một độ trễ có thể có mức tác động khác nhau với từng loại.

Sau khi retry hoặc chạy bù, cần biết thao tác có tạo bản ghi trùng hay áp dụng lại thay đổi không còn phù hợp không. Định danh ổn định, quy tắc xử lý lặp và đối soát giúp giảm những rủi ro này.

Không tự coi trạng thái “đã gửi yêu cầu tới đích” là “đã hoàn tất cập nhật”. Đặt tên mốc đo theo bằng chứng thực sự có được.

## 11. Tính đúng của dữ liệu và schema

Kho vẫn có thể trả lời thành công nhưng cung cấp dữ liệu không phù hợp cho IAM.

Một số dạng vấn đề gồm:

- Định danh bị ánh xạ nhầm hoặc trùng trong phạm vi cần duy nhất.
- Thuộc tính bắt buộc bị thiếu.
- Membership không phản ánh thay đổi đã được xác nhận.
- Giá trị trạng thái không được dịch đúng giữa nguồn và đích.
- Thay đổi schema làm bộ lọc của ứng dụng không còn hoạt động như dự kiến.
- Kết quả bị giới hạn hoặc phân trang nhưng client hiểu nhầm là đã đủ.
- Một bước đồng bộ ghi đè thuộc tính do nguồn khác có thẩm quyền quản lý.

Không cần đọc toàn bộ dữ liệu cá nhân để phát hiện mọi vấn đề. Có thể kết hợp kiểm tra schema, số lượng tổng hợp, dữ liệu tổng hợp và đối soát có mục tiêu theo quyền được cấp.

Khi kiểm tra membership hoặc thuộc tính, cần hiểu ngữ nghĩa của kho: nhóm lồng nhau, phạm vi tìm kiếm hoặc các quy tắc suy ra có thể ảnh hưởng tới kết quả. Không tự coi một phép đọc đơn giản là toàn bộ quyền có hiệu lực.

Những phép kiểm tra tính đúng nên có trạng thái mong đợi rõ ràng. Nếu không biết bản ghi đúng phải trông như thế nào, khác biệt giữa hai hệ thống chỉ là dấu hiệu cần giải thích, chưa phải bằng chứng hệ thống nào sai.

## 12. Bảo vệ dữ liệu quan sát và đường truy cập

Quan sát identity store thường chạm tới thông tin nhạy cảm về con người và quyền. Cần thu thập đủ để vận hành mà không biến hệ thống quan sát thành bản sao không kiểm soát của kho danh tính.

Metrics nên dùng các chiều có số lượng giới hạn, chẳng hạn nhóm thao tác, môi trường, vai trò điểm đọc và nhóm kết quả.

Ví dụ tên minh họa:

~~~text
iam_identity_store_operations_total{
    operation="lookup",
    outcome="timeout",
    environment="production",
    store_role="read_replica"
}

iam_identity_store_pending_changes

iam_identity_store_oldest_pending_change_age_seconds
~~~

Tên metrics cần đi kèm định nghĩa: đang đếm thao tác phía client hay phía server, tuổi backlog được tính ở đâu và những trường hợp nào bị loại khỏi phép đo.

Không đưa email, định danh cá nhân, bộ lọc truy vấn nguyên văn, token hoặc thông tin xác thực vào nhãn metrics. Log chẩn đoán cũng không nên ghi toàn bộ bản ghi danh tính hoặc request kết nối.

Nếu cần dữ liệu chi tiết để điều tra, dùng tham chiếu phù hợp trong audit log có kiểm soát truy cập. Khả năng liên kết các bản ghi không đồng nghĩa mọi người xem dashboard được quyền xem danh tính tương ứng.

Các phụ thuộc kỹ thuật cũng cần được quan sát: chứng chỉ sắp hết hạn, thay đổi trust, DNS, đồng hồ hệ thống, credential của connector và quyền truy cập mạng. Một lỗi xác thực kết nối do credential của dịch vụ hết hiệu lực có thể làm kho trông như ngừng hoạt động dù bản thân kho vẫn phục vụ client khác.

## 13. Backup và khả năng phục hồi là một phần sức khỏe vận hành

“Backup chạy thành công” chỉ nói rằng một tác vụ đã báo thành công theo tiêu chí của nó. Nó chưa chứng minh dữ liệu có thể được khôi phục đầy đủ và phục vụ các luồng IAM cần thiết.

Cần biết bản backup gần nhất, phạm vi được bảo vệ, khả năng giải mã hoặc truy cập dữ liệu phục hồi và kết quả của các lần diễn tập khôi phục.

Hai mục tiêu thường cần làm rõ là thời gian phục hồi chấp nhận được và mức mất dữ liệu chấp nhận được. Giá trị phù hợp phụ thuộc vào vai trò của kho và tác động khi dữ liệu danh tính bị thiếu hoặc cũ.

Phục hồi một snapshot cũ có thể đưa trở lại tài khoản đã bị vô hiệu hóa hoặc membership đã được thu hồi sau thời điểm snapshot. Vì vậy, khôi phục kỹ thuật chưa đủ để đưa kho trở lại phục vụ truy cập ngay lập tức.

Quy trình phục hồi cần xem xét đối soát với nguồn có thẩm quyền, áp dụng những thay đổi bảo mật còn thiếu và xác nhận trạng thái trước khi đưa các điểm đọc trở lại luồng sản xuất.

Diễn tập nên diễn ra trong phạm vi được kiểm soát, tránh để kho phục hồi cũ tự đồng bộ hoặc phục vụ xác thực ngoài dự kiến. Dữ liệu backup và credential phục hồi cũng cần được bảo vệ tương ứng với mức nhạy cảm của kho gốc.

## 14. Ví dụ đọc một dashboard có nhiều tín hiệu

An Bình dùng một probe đọc những bản ghi tổng hợp đã biết qua đường tra cứu của dịch vụ. Trong cửa sổ quan sát, 10.000 lượt được phân loại:

| Kết quả | Số lượt |
| --- | ---: |
| Trả đúng kết quả mong đợi | 9.900 |
| Timeout | 70 |
| Lỗi không phục vụ được | 20 |
| Thao tác hoàn tất nhưng thiếu bản ghi đáng lẽ phải tồn tại | 10 |

Nếu chỉ xem các thao tác hoàn tất ở mức giao thức, nhóm có thể tính:

~~~text
(9.900 + 10) / 10.000 = 99,1%
~~~

Nhưng tỷ lệ lượt trả đúng kết quả mong đợi của probe là:

~~~text
9.900 / 10.000 = 99,0%
~~~

Đây là hai phép đo khác nhau. Ví dụ giả định toàn bộ bản ghi probe có trạng thái mong đợi rõ và cùng nằm trong phạm vi kiểm tra; không áp dụng cách coi “không tìm thấy” là lỗi cho mọi truy vấn thực tế.

Cùng lúc, dashboard cho thấy p99 tăng ở một vùng, độ tuổi thay đổi chờ xử lý tăng và nguồn đồng bộ vẫn phát heartbeat. Nhóm không kết luận pipeline khỏe chỉ từ heartbeat.

Họ đối chiếu các điểm đọc và phát hiện một replica chậm áp dụng thay đổi. Sau đó, nhóm kiểm tra ảnh hưởng tới các cập nhật vô hiệu hóa tài khoản và membership tại đúng những ứng dụng sử dụng replica đó.

Việc phần lớn người dùng vẫn đăng nhập được được xem là một tín hiệu về phạm vi tác động, không phải bằng chứng sự cố không quan trọng.

## 15. Cảnh báo và điều tra theo tác động

Cảnh báo nên nói rõ điều gì bị ảnh hưởng và bước kiểm tra đầu tiên. Có thể phân biệt cảnh báo mất khả năng phục vụ với cảnh báo dữ liệu quá cũ hoặc cập nhật bảo mật chưa hội tụ.

Những tình huống cần chú ý gồm:

- Thao tác quan trọng có tỷ lệ lỗi hoặc latency vượt mục tiêu trong cửa sổ đã định.
- Thay đổi giảm quyền hoặc vô hiệu hóa tồn đọng quá lâu.
- Replica phục vụ lưu lượng nhưng không đạt yêu cầu độ mới.
- Backlog tăng liên tục hoặc một số bản ghi lỗi không được xử lý.
- Functional probe trả kết quả không đúng.
- Nguồn quan sát ngừng gửi dữ liệu.
- Chứng chỉ hoặc credential phục vụ kết nối gần tới mốc cần xử lý.
- Khả năng phục hồi chưa được xác nhận trong chu kỳ vận hành đã quy định.

Không có ngưỡng latency hoặc lag duy nhất phù hợp với mọi kho. Cần gắn mục tiêu với loại thao tác, luồng phụ thuộc và hậu quả của dữ liệu cũ.

Một trình tự điều tra có thể gồm:

1. Xác định phạm vi: vùng, điểm đọc, thao tác và client nào bị ảnh hưởng.
2. Kiểm tra chất lượng telemetry, tránh nhầm mất dữ liệu với không có lỗi.
3. Đối chiếu khả năng kết nối, kết quả thao tác và tính đúng của dữ liệu.
4. Kiểm tra pool, hàng đợi, tài nguyên, replication và luồng đồng bộ.
5. Đối chiếu các thay đổi triển khai, cấu hình, schema và credential gần thời điểm bắt đầu.
6. Đánh giá tác động tới đăng nhập, cấp phát và thay đổi thu hồi quyền.
7. Thực hiện biện pháp phục hồi đã được xác định và xác nhận lại trên đường sử dụng thực tế.

Khởi động lại hàng loạt, chuyển replica hoặc giảm điều kiện kiểm tra bảo mật đều có thể làm thay đổi tác động của sự cố. Hành động khắc phục cần dựa trên nguyên nhân và trạng thái dữ liệu, không chỉ dựa trên mong muốn làm đèn health chuyển xanh.

## 16. Các tình huống kiểm tra phép đo

| Tình huống | Điều cần quan sát được |
| --- | --- |
| Tiến trình còn chạy nhưng kết nối kho lỗi | Phân biệt được liveness và phụ thuộc thực sự |
| Cache còn dữ liệu khi kho mất kết nối | Nhận ra phạm vi đang được cache che phủ |
| Lookup nhanh nhưng đọc membership chậm | Tách được các nhóm thao tác |
| Truy vấn không tìm thấy định danh không tồn tại | Không tự coi kết quả hợp lệ là lỗi kho |
| Probe thiếu bản ghi đã biết | Có tín hiệu tính đúng, không chỉ trạng thái giao thức |
| Replica đọc được nhưng chậm nhận cập nhật | Có tín hiệu độ mới tại đúng điểm đọc |
| Heartbeat còn nhưng một thay đổi cũ bị kẹt | Thấy tuổi backlog và lỗi từng nhóm cập nhật |
| Retry tăng sau một đợt triển khai | Thấy tải bổ sung và tác động đầu cuối |
| Khóa tài khoản ở nguồn | Theo dõi được các mốc truyền và áp dụng đã định |
| Khôi phục snapshot cũ | Kiểm tra được các thay đổi bảo mật còn thiếu |
| Hệ thống thu thập bị gián đoạn | Hiển thị thiếu dữ liệu thay vì mặc định khỏe |
| Kiểm tra nhãn metrics và log | Không có credential hoặc dữ liệu danh tính thừa |

Một kho danh tính khỏe cần phục vụ được các thao tác IAM bằng dữ liệu có ý nghĩa và đủ mới cho quyết định đang thực hiện. Quan sát theo đường đi của dữ liệu giúp nhóm vận hành hiểu được không chỉ kho có trả lời hay không, mà còn liệu trạng thái danh tính có đang hỗ trợ đúng việc xác thực, cấp quyền và kết thúc quyền truy cập hay không.
