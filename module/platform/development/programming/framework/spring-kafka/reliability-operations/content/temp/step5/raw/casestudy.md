Một dịch vụ tạo hóa đơn dùng @KafkaListener đọc sự kiện thanh toán; handler ghi database thành công nhưng container bị kill trước khi commit offset nên cùng sự kiện được xử lý lại sau restart.
Nhóm đồng bộ kho sử dụng Kafka consumer với auto commit; offset được ghi trước khi tác vụ cập nhật tồn kho hoàn tất và một lần crash khiến thông điệp chưa xử lý không được đọc lại.
Ứng dụng xử lý đơn qua listener record-level; khi bật AckMode.BATCH cho container, một bản ghi cuối batch lỗi làm những bản ghi trước có nguy cơ được phát lại theo điểm commit.
Đội triển khai AckMode.RECORD để giảm xử lý lại; mỗi bản ghi phải ghi database chậm khiến throughput và tần suất commit offset không còn phù hợp SLA.
Nhóm xử lý giao dịch theo lô bằng batch listener; một record sai dữ liệu làm toàn bộ batch không hoàn tất và nhóm không biết offset nào đã có side effect.
Ứng dụng dùng Acknowledgment trong @KafkaListener ở AckMode.MANUAL; một nhánh return sớm không gọi acknowledge nên consumer đọc lại cùng thông điệp sau rebalance.
Đội gọi acknowledge trước khi lưu transaction nghiệp vụ; database lỗi sau đó nhưng offset đã có thể được commit và sự kiện thanh toán không được xử lý lại.
Nhóm bật AckMode.MANUAL_IMMEDIATE trong container; listener nghĩ acknowledge ở worker bất kỳ có tác dụng ngay như trên thread consumer và thứ tự commit thay đổi.
Ứng dụng có hai handler nội bộ cho một record Kafka; handler thứ nhất xử lý xong rồi listener acknowledge trước khi handler thứ hai thất bại, làm dữ liệu chỉ cập nhật một phần.
Đội dùng ack.nack để thử lại record trong một listener; lô dữ liệu lớn bị chặn trong lúc trì hoãn và các record hợp lệ phía sau không được tiến hành đúng giờ.
Nhóm dùng nack với batch listener; một vị trí thất bại không tương ứng index của batch ban đầu sau biến đổi dữ liệu và các offset được xử lý không như dự kiến.
Ứng dụng bật asyncAcks cho manual acknowledgments; các tác vụ xử lý hoàn thành lệch thứ tự và container phải giữ gap offset trước khi tiếp tục poll.
Đội chạy xử lý song song nhiều record từ cùng partition; record offset cao được hoàn thành trước nhưng một record thấp treo khiến toàn bộ vùng commit bị chặn.
Nhóm cấu hình enable.auto.commit=true cùng kỳ vọng Spring container kiểm soát commit; hành vi runtime không phù hợp ranh giới xử lý nghiệp vụ mà nhóm thiết kế.
Ứng dụng xử lý đơn với commitSync; broker phản hồi commit chậm làm listener giữ thread lâu và consumer tiến sát giới hạn thời gian poll.
Đội chuyển sang commitAsync để tăng throughput; một lỗi commit không được quan sát khiến offset sau restart thấp hơn bản ghi đã xử lý, dẫn tới xử lý trùng.
Nhóm kiểm tra callback commit bất đồng bộ chỉ bằng log DEBUG; sự cố coordinator từ chối commit kéo dài nhưng dashboard vẫn báo processing thành công.
Ứng dụng đọc topic có nhiều partition; metric chỉ hiển thị một offset chung theo topic nên đội vận hành không biết partition nào đang bị tụt lại.
Đội tăng số partition cho topic xử lý đơn; thứ tự của các sự kiện cùng khách thay đổi khi key không được giữ nhất quán giữa producer cũ và mới.
Nhóm lưu offset đã xử lý trong database riêng; offset consumer group do Kafka quản lý và offset do ứng dụng lưu không khớp sau một lần recovery.
Ứng dụng gửi update tồn kho đến Kafka rồi hiển thị thành công ngay; producer future chưa hoàn thành và broker không nhận bản ghi trong sự cố mạng.
Đội phát một record với key rỗng khi tạo giao dịch; các sự kiện tiếp theo cùng orderId có key đúng nên thứ tự xử lý trên partition không được bảo đảm.
Nhóm đọc nhiều topic trong một @KafkaListener; đội support chỉ lưu offset mà bỏ topic và partition nên không thể định danh chính xác bản ghi thất bại.
Ứng dụng ghi lại offset của record đã giải mã lỗi; khi thay đổi partition count và reset consumer group, điểm tiếp tục xử lý không còn tương ứng logic vận hành cũ.
Đội dùng ConsumerSeekAware để điều chỉnh vị trí đọc khi khởi động; một nhánh seek tới latest làm bỏ qua dữ liệu cần backfill của khách mới.
Nhóm đặt auto.offset.reset=earliest trên nhóm đã tồn tại; đội kỳ vọng đọc lại toàn bộ nhưng consumer vẫn tiếp tục từ offset committed cũ.
Ứng dụng dùng auto.offset.reset=latest cho consumer group mới; các giao dịch đã tồn tại trong topic trước lần triển khai đầu không bao giờ được đồng bộ.
Đội cấu hình auto.offset.reset=none nhằm tránh bỏ sót; một partition không có offset committed khiến listener không thể khởi động sau khi retention xóa dữ liệu cũ.
Nhóm dùng KafkaListenerEndpointRegistry để tạm dừng một listener; một số record đã được poll vẫn còn đang xử lý và người vận hành tưởng dừng là đã hoàn toàn an toàn.
Ứng dụng nhận record từ topic log-compacted; khi seek về earliest, các bản ghi đã bị compaction không còn nên replay không thể tái tạo mọi sự kiện lịch sử.
Đội reset offset consumer group lúc đang có pod chạy; các pod cũ tiếp tục commit sau reset làm vị trí đọc không còn đúng kế hoạch khôi phục.
Nhóm chuyển group.id của listener khi phát hành phiên bản mới; tất cả record còn trong retention có thể được đọc lại và nghiệp vụ ghi trùng nếu state không độc lập.
Ứng dụng sử dụng cùng group.id cho hai dịch vụ có nhiệm vụ khác nhau; Kafka chia partition giữa hai dịch vụ thay vì cho cả hai nhận toàn bộ thông điệp.
Đội cấu hình consumer trong nhiều môi trường với cùng cluster và group ID; môi trường staging có lúc nhận record production làm hỏng dữ liệu đối soát.
Nhóm để dữ liệu Kafka chỉ được giữ ba ngày; một consumer bị dừng cả tuần và committed offset đã nằm ngoài retention nên không thể đọc lại các bản ghi cũ.
Ứng dụng có listener trả lỗi khi gặp record poison; committed offset không tiến và consumer lặp lại cùng bản ghi khiến độ trễ mọi record sau ngày càng tăng.
Đội dùng batch listener chỉ xác minh số record đầu vào; khi có tombstone với payload null, handler coi là dữ liệu hỏng và ngừng cả luồng cập nhật cache.
Nhóm muốn so sánh lag trên một partition với số đơn chưa xử lý; bản ghi đã được poll nhưng task async đang chờ khiến lag đo từ committed offset không phản ánh chính xác trạng thái nghiệp vụ.
Ứng dụng dùng Kafka consumer ở nhiều thread từ một bean duy nhất; thao tác poll, commit và seek đồng thời trên KafkaConsumer làm hành vi không an toàn.
Đội chuyển xử lý sang worker pool rồi gọi Acknowledgment ở callback; khi rebalance xảy ra trước callback, consumer generation đã thay đổi và offset không còn commit như dự kiến.
Nhóm ghi dấu xử lý thành công ngay khi record được deserialized; transaction nghiệp vụ sau đó rollback nhưng replay không được phát vì marker đã tồn tại.
Ứng dụng nhận sự kiện có header retryCount do upstream đặt; một client gửi giá trị quá lớn làm handler bỏ qua xử lý dù record chưa từng được thử trên consumer.
Đội có hai KafkaListener cùng subscribe một topic trong cùng group; sự kiện được phân chia giữa listener khác loại và một số payload đi tới handler không tương thích.
Nhóm sử dụng ack mode dựa theo thời gian để cân bằng throughput; lúc lưu lượng thấp có độ trễ commit dài khiến nhiều bản ghi được phát lại khi restart.
Ứng dụng dùng offset commit sau khi gọi HTTP bên ngoài; HTTP trả timeout khi đã ghi side effect và record được phát lại tạo hai yêu cầu cùng nghiệp vụ.
Đội xử lý tất cả record bằng một transaction database kéo dài qua batch; một record lỗi ở cuối rollback database nhưng offset và các lời gọi bên ngoài đã tiến.
Nhóm xử lý lỗi bằng DefaultErrorHandler với FixedBackOff; một dịch vụ ngoài ngừng một giờ làm listener retry trên cùng partition và các giao dịch hợp lệ bị giữ.
Ứng dụng cấu hình DefaultErrorHandler retry số lần cố định; lỗi tạm thời kéo dài hơn tổng backoff nên thông điệp được chuyển DLT dù hệ thống đối tác phục hồi ngay sau đó.
Đội đặt ExponentialBackOff cho lỗi mạng; thời gian trì hoãn dài làm phân vùng đơn hàng backlog nhiều ngày và ảnh hưởng thời hạn giao hàng.
Nhóm retry một record lỗi do phiên bản schema không tương thích; việc thử lại nhiều lần không thay đổi dữ liệu và làm các sự kiện tốt phía sau bị chặn.
Ứng dụng bỏ qua mọi loại exception trong bộ phân loại retry; lỗi xác thực SMTP vĩnh viễn được thử liên tục và tài khoản service bị khóa.
Đội thay cấu hình retryable exceptions trên listener; lỗi timeout bị bọc trong MessagingException làm bộ phân loại chọn nhầm chính sách không retry.
Nhóm triển khai DefaultErrorHandler với DeadLetterPublishingRecoverer; khi gửi message tới DLT thất bại do broker không sẵn sàng, trạng thái bản ghi gốc không rõ.
Ứng dụng dùng DeadLetterPublishingRecoverer cho message lỗi; DLT không có đủ partition tương ứng nguồn nên việc định tuyến message thất bại khi nguồn mở rộng.
Đội lấy tên DLT bằng cách nối hậu tố vào topic nguồn; một topic có tên đặc biệt không phù hợp quy tắc topic ở cluster đích và thông điệp không đến nơi.
Nhóm cấu hình producer gửi DLT bằng serializer chỉ hỗ trợ JSON; payload lỗi deserialization là byte array gốc khiến việc publish DLT tiếp tục lỗi.
Ứng dụng gặp DeserializationException trước khi listener nhận record; không có ErrorHandlingDeserializer nên handler lỗi theo cấp listener không thấy payload để chuyển DLT.
Đội bật ErrorHandlingDeserializer nhưng bỏ cấu hình delegate deserializer phù hợp; mọi record đều lỗi giải mã và DLT tăng nhanh ngay sau deploy.
Nhóm lưu message lỗi vào DLT cùng với header chứa raw exception stack; dữ liệu nhạy cảm từ payload hoặc metadata xuất hiện trong topic có ACL rộng.
Ứng dụng có DLT consumer tự động replay ngay sau khi nhận; message poison chưa được sửa nên liên tục quay về main topic và tạo vòng lặp.
Đội dùng DLT làm kho lưu vô thời hạn cho lỗi đơn hàng; topic retention bị thay đổi và message cần xử lý thủ công đã hết hạn trước khi được điều tra.
Nhóm lập dashboard cho DLT chỉ theo số record đến; một partition DLT có consumer chết nhưng dữ liệu lỗi mới vẫn tích tụ mà cảnh báo không được kích hoạt.
Ứng dụng có nhiều source topics cùng dùng chung DLT; header nguồn bị mất khi chuyển tiếp làm đội vận hành không biết phải replay về topic nào.
Đội thiết lập dead letter topic dùng schema mới; DLT consumer cũ không giải mã được bản ghi lỗi và cả quy trình hỗ trợ thủ công bị gián đoạn.
Nhóm thử lại message trên DLT với cùng key nhưng khác partition nguồn; các sự kiện sau đã được xử lý và message replay làm trạng thái order bị lùi.
Ứng dụng chuyển DLT record về main topic sau khi sửa code; record được phát với timestamp mới khiến các chính sách deduplication theo thời gian không còn phù hợp.
Đội dùng @RetryableTopic cho lỗi API đối tác; việc chuyển sang retry topics làm thứ tự sự kiện cùng orderId khác với consumer xử lý chặn trước đây.
Nhóm cấu hình @RetryableTopic với nhiều khoảng backoff; số lượng retry topics theo chính sách tăng nhiều khiến giới hạn quota topic của cluster bị vượt.
Ứng dụng chạy cả DefaultErrorHandler blocking retries và @RetryableTopic; một message trải qua nhiều lớp retry nên số lần gọi API đối tác cao hơn dự toán.
Đội chuyển thông điệp qua non-blocking retry topics; header thời gian thử lại bị bỏ trong một custom producer và message được xử lý sớm hơn lịch dự kiến.
Nhóm bật retry topic cho listener batch; cấu hình retry không tương thích cách tiêu thụ batch đang sử dụng và một nhóm message không được xử lý như mong muốn.
Ứng dụng thiết lập retry topics dùng cùng group ID convention chưa được kiểm; một lần deploy thay group cấu hình làm message còn trong retry topic không còn được consumer hiện tại đọc.
Đội cấu hình retry topic cho lỗi 429 từ đối tác; hàng nghìn message cùng lịch retry quay về đối tác và gây làn sóng rate limit mới.
Nhóm có listener trên DLT để kiểm tra lỗi cuối; listener DLT cũng ném exception và service không có quy trình xác định bản ghi nào đã được lưu để điều tra.
Ứng dụng gửi mail từ KafkaListener và gặp lỗi sau khi SMTP accepted; việc retry record tạo thư trùng dù offset cuối cùng chỉ commit một lần.
Đội muốn bỏ qua record không hợp lệ mà không làm đứng partition; một lệnh skip không ghi reason và không tạo dấu vết hỗ trợ đối soát.
Nhóm dùng errorChannel trong flow trước KafkaListener; exception chưa đến CommonErrorHandler của container nên bản ghi không đi đúng retry/DLT policy dự kiến.
Ứng dụng sử dụng CommonErrorHandler với handler tùy biến; code ném lại exception đã xử lý khiến cùng record vừa bị publish DLT vừa bị retry lần nữa.
Đội cần phân biệt lỗi deserialization và validation nghiệp vụ; tất cả được ghi dưới nhãn processing_failed và đội hỗ trợ không biết trường hợp nào cần sửa schema.
Nhóm sử dụng @KafkaListener với RecordFilterStrategy để bỏ event không liên quan; khi filter và acknowledgment phối hợp sai, offset không tiến hoặc message bị xử lý lại.
Ứng dụng tạo logic dedup chỉ trong memory cache; pod restart xóa cache và record replay từ Kafka tiếp tục tạo dữ liệu trùng trong database.
Đội đặt idempotency key là customerId thay vì transactionId; nhiều giao dịch hợp lệ cùng khách bị coi trùng và không được ghi nhận.
Nhóm đánh dấu event đã xử lý trước khi gọi API thanh toán; API trả lỗi tạm thời làm các lần retry bị bỏ dù giao dịch chưa hoàn tất.
Ứng dụng dùng bảng processed_events trong PostgreSQL; hai pod cùng nhận duplicate từ các nguồn khác nhau và cả hai vượt qua bước kiểm tra trước khi ghi marker.
Đội dùng unique constraint cho eventId; một exception do trùng bản ghi xảy ra sau khi đã gọi hệ thống ngoài và quy trình không thể hoàn tác side effect.
Nhóm chọn key dedup từ header Message-ID do đối tác cấp; đối tác retry với ID mới cho cùng nghiệp vụ làm deduplication không nhận diện trùng.
Ứng dụng chỉ giữ marker xử lý trong ba ngày; Kafka retention dài hơn nên một lần replay sự kiện cũ đi qua marker đã hết hạn và cập nhật số dư lần nữa.
Đội sử dụng idempotent consumer cho điều chỉnh tồn kho; logic cập nhật có phép cộng số lượng nên replay cùng lệnh làm tồn kho sai nếu marker không nguyên tử với phép cập nhật.
Nhóm muốn exactly-once trong một hệ thống thu tiền; Kafka transaction xử lý consume-transform-produce nhưng lệnh gọi ngân hàng ngoài Kafka vẫn có khả năng xảy ra hai lần.
Ứng dụng phát sự kiện Kafka và ghi database trong cùng method @Transactional; đội nghĩ hai hệ thống có một atomic commit nhưng sự cố giữa hai resource tạo trạng thái lệch.
Đội triển khai transactional outbox ghi đơn và event vào một transaction DB; publisher outbox gửi thành công rồi crash trước khi đánh dấu published và event được phát lại.
Nhóm dùng inbox lưu dấu eventId trong transaction xử lý; eventId thiếu namespace theo nguồn làm hai publisher khác nhau va chạm khóa và mất giao dịch hợp lệ.
Ứng dụng theo dõi đơn cập nhật bằng event version; một message replay đến muộn ghi đè trạng thái mới do consumer không kiểm version nghiệp vụ.
Đội thay producer idempotence của Kafka để giảm duplicate; nhiều process vẫn gửi cùng event nghiệp vụ với hai producer khác nhau và dữ liệu trùng ở downstream.
Nhóm bật enable.idempotence cho Kafka producer; hệ thống đánh đồng chống duplicate do retry producer với exactly-once của cả luồng lưu database và API ngoài.
Ứng dụng cấu hình acks=1 cho sự kiện giao dịch; leader broker xác nhận rồi lỗi trước khi replica ghi nhận khiến một số bản ghi đã báo thành công không còn.
Đội đặt acks=all nhưng topic min.insync.replicas quá thấp; một số broker lỗi đồng thời khiến mức bảo vệ dữ liệu không đạt mục tiêu vận hành.
Nhóm tăng min.insync.replicas vào giờ bảo trì; khi số replica còn sống thấp hơn ngưỡng, producer báo NotEnoughReplicasException và luồng ghi sự kiện dừng.
Ứng dụng ghi sự kiện với replication factor bằng một cho topic quan trọng; một broker hỏng làm dữ liệu đã xác nhận không còn replica dự phòng.
Đội đặt delivery.timeout.ms thấp hơn tổng thời gian chờ mạng và retry; KafkaTemplate trả lỗi khi hệ thống vẫn đang tái bầu leader và việc ghi có kết quả khó xác định.
Nhóm cấu hình retries của producer lớn nhưng request.timeout.ms ngắn; bản ghi có thể được broker nhận trước khi producer retry và team không đối soát được trạng thái cuối.
Ứng dụng dùng KafkaTemplate.send trả CompletableFuture; controller trả HTTP 201 ngay sau khi submit mà không quan sát SendResult hoặc exception từ broker.
Đội xử lý lỗi trong callback KafkaTemplate bằng cách gửi lại ngay; producer trước có thể đã ghi bản gốc và tạo duplicate logic khi callback không nhận acknowledgment.
Nhóm gắn eventId vào header để tra cứu log; một nhánh gửi sự kiện từ batch job không thêm header và team không đối chiếu được hai bản trùng.
Ứng dụng dùng producer key mặc định không có orderId; cùng đơn hàng được gửi vào nhiều partition và consumer không bảo đảm thứ tự cập nhật.
Đội tăng max.in.flight.requests.per.connection để tăng thông lượng; khi idempotence bị tắt và có retry, thứ tự bản ghi cùng partition có thể không còn như thời điểm gửi.
Nhóm kiểm tra ordering ở producer với một partition; sau mở rộng lên nhiều partition, key phân vùng không nhất quán giữa hai ứng dụng làm event cùng order lệch thứ tự.
Ứng dụng gửi batch Kafka qua nhiều producer với cùng transactional.id; một producer mới làm phiên trước bị fenced và các giao dịch đang xử lý thất bại đột ngột.
Đội cấu hình transactionIdPrefix cố định giống nhau cho mọi pod Spring Kafka; khi scale, các transactional producers cạnh tranh identity và nhận ProducerFencedException.
Nhóm triển khai KafkaTransactionManager trong luồng đọc-xử lý-ghi; một listener khác ngoài container transaction vẫn commit offset riêng và phá vỡ giả định exactly-once.
Ứng dụng cần EOS consume-process-produce bằng transaction Kafka; team chỉ giao dịch ở producer nhưng offset đầu vào không được đưa vào cùng transaction.
Đội cấu hình read_committed cho consumer kiểm toán; một topic có nhiều transaction đang mở làm độ trễ dữ liệu hiển thị cao hơn mức lag offset thô.
Nhóm dùng isolation.level=read_uncommitted trong consumer downstream; những record được viết trong transaction Kafka đã abort vẫn bị đọc và kích hoạt thao tác nghiệp vụ.
Ứng dụng có producer transaction dài khi gọi REST đối tác; transaction.timeout.ms trên broker hết hạn khiến toàn bộ record trong giao dịch bị abort sau khi lời gọi ngoài đã thành công.
Đội bắt đầu Kafka transaction rồi gọi một API thanh toán lâu; transaction coordinator không còn giữ được transaction nhưng hệ thống ngoài đã xử lý số tiền.
Nhóm gọi KafkaTemplate.send trong transaction đồng bộ với database; commit DB thành công nhưng Kafka commit thất bại và hệ thống không thể tự rollback dữ liệu DB đã lưu.
Ứng dụng commit Kafka transaction trước khi commit database; DB sau đó vi phạm unique constraint khiến sự kiện đã xuất bản không có dữ liệu tương ứng.
Đội sử dụng ChainedKafkaTransactionManager từ dự án cũ; khi nâng cấp, cơ chế phối hợp transaction và cảnh báo lỗi tài nguyên không còn giống kỳ vọng.
Nhóm áp @Transactional cho method nhận Kafka record trong listener; exception bị catch rồi nuốt làm container nghĩ xử lý thành công dù transaction database đã bị rollback-only.
Ứng dụng xử lý record qua Kafka transaction rồi gọi asynchronous side effect; side effect chạy sau commit và khi lỗi không nằm trong phạm vi bảo đảm exactly-once.
Đội gửi message DLT bên trong Kafka transaction; một exception khác rollback giao dịch làm DLT record cũng bị abort và bộ phận vận hành không thấy sự kiện lỗi.
Nhóm dùng AfterRollbackProcessor cho listener transaction; một record liên tục ném lỗi khiến toàn bộ transaction Kafka bị rollback và các message hợp lệ đứng chờ.
Ứng dụng chuyển retry record tới DLT sau rollback; team không lưu lại bản gốc có đủ key và headers nên không thể phát lại đúng giao dịch.
Đội dùng ProducerFencedException như lỗi có thể retry đơn giản; các transactional instance đang bị fencing liên tục và không ổn định sau rolling deploy.
Nhóm cấu hình transaction.id prefix không gắn identity instance; pod mới trong rollout khiến producer pod cũ nhận lỗi dù pod cũ vẫn đang hoàn tất batch.
Ứng dụng dùng exactly-once processing trong Kafka Streams thông qua processing.guarantee; một downstream HTTP consumer vẫn xử lý lại khi đọc từ điểm offset khác.
Đội xử lý state store của Kafka Streams và xuất kết quả ra topic; reset ứng dụng mà không xét changelog/repartition topics khiến state và output trở nên không đồng nhất.
Nhóm tưởng EOS bảo đảm mỗi người dùng nhận đúng một email; Kafka transactional commit vẫn không thể điều khiển nhà cung cấp SMTP đã chấp nhận thư.
Ứng dụng ghi bảng số dư và gửi sự kiện outbox trong một transaction; quy trình replay không kiểm version nên duplicate đến sau event mới làm số dư bị ghi đè.
Đội muốn chuyển từ at-least-once sang exactly-once; các consumer hiện tại chứa tác động ngoài Kafka và không có idempotency ở tầng nghiệp vụ.
Nhóm kiểm tra một record Kafka đã commit; hệ thống xử lý chi tiết bằng tác vụ nền chưa hoàn tất nhưng dashboard báo completed chỉ dựa vào offset.
Ứng dụng áp retry trong transaction Kafka cho một lỗi transient; việc retry sau abort cùng partition làm thời gian giữ transaction và khả năng xử lý giảm mạnh.
Đội gửi nhiều output events trong một Kafka transaction; một topic đích tạm thiếu quyền write khiến cả nhóm output bị rollback và service không xuất kết quả.
Nhóm sử dụng một KafkaTemplate với transactional producer cho cả batch và request REST; cách quản lý transaction context khác nhau khiến một số lần send lỗi không có transaction.
Ứng dụng áp producer transaction cho sự kiện kiểm toán; khi transaction khởi tạo lỗi do broker coordinator không sẵn sàng, yêu cầu nghiệp vụ bị dừng dù database vẫn có thể ghi.
Đội duy trì một transactional producer qua thời gian idle dài; broker hết hạn transactional ID và lượt gửi tiếp theo bắt đầu bằng lỗi khởi tạo producer.
Nhóm dùng transaction để chuyển dữ liệu từ topic A sang topic B; một xử lý bên ngoài ghi file đã xong trước khi transaction abort và file cần được đối soát thủ công.
Ứng dụng dùng DB transaction chứa bước publish Kafka sau cùng; khi publish thành công nhưng database commit chậm và thất bại, hai bên nhận trạng thái khác nhau.
Đội giả định rebalance chỉ xảy ra khi pod chết; scale up consumer group trong giờ tải cao làm partition được thu hồi giữa một batch đang xử lý.
Nhóm dùng eager rebalance assignment strategy; thêm một consumer instance làm các partition tạm dừng toàn bộ và SLA xử lý đơn bị vượt.
Ứng dụng bật cooperative-sticky assignment cho consumer group; team vẫn xử lý partition revoked như thể mọi partition đều được thu hồi, gây ngừng không cần thiết.
Đội cấu hình ConsumerAwareRebalanceListener để lưu checkpoint; callback chặn lâu vì gọi API ngoài nên rebalance và thời gian phục hồi của cả group kéo dài.
Nhóm quản lý consumer bằng static membership qua group.instance.id; hai pod cùng sử dụng identity khi rollout và liên tục đá nhau ra khỏi group.
Ứng dụng dùng group.instance.id được gắn theo hostname ngẫu nhiên; mỗi lần restart thành viên cũ chưa hết hạn và membership mới làm phân công không ổn định.
Đội giảm session.timeout.ms để phát hiện pod chết nhanh; jitter mạng ngắn khiến coordinator coi consumer còn sống là mất và rebalance liên tục.
Nhóm tăng session timeout để tránh rebalance; consumer thực sự đã ngừng xử lý nhưng partition bị giữ lâu và record mới không được phân cho pod khác.
Ứng dụng xử lý một record hơn max.poll.interval.ms; consumer bị loại khỏi group dù heartbeat vẫn chạy và callback commit offset không còn hợp lệ.
Đội tăng max.poll.records khi bắt đầu chiến dịch; thời gian xử lý batch vượt max.poll.interval.ms khiến toàn bộ group rebalance trong lúc các record chưa hoàn tất.
Nhóm dùng Spring Kafka concurrency lớn hơn số partition topic; nhiều consumer container không có partition và tài nguyên tăng mà throughput không cải thiện.
Ứng dụng có 12 partition nhưng 3 pod đều tạo 12 concurrent consumers; nhiều consumer idle trong khi database connection pool bị chia nhỏ và tăng overhead.
Đội cần giữ thứ tự event theo userId; message được xử lý bằng executor worker chung ngoài consumer thread khiến cùng partition có các tác vụ hoàn thành đảo thứ tự.
Nhóm phát record vào pool từ KafkaListener rồi return ngay; container commit offset trước khi tác vụ con ghi dữ liệu và một lần restart gây mất xử lý.
Ứng dụng dừng listener thông qua KafkaListenerEndpointRegistry để bảo trì; một số tác vụ async còn chạy sau khi partition đã được giao cho pod mới.
Đội chạy nhiều replica với Kubernetes rolling restart khi pod nhận SIGTERM; grace period ngắn khiến consumer không hoàn tất commit offsets và nhiều bản ghi cũ được replay ở pod mới.
Nhóm có listener cần close connection trong onPartitionsRevoked; callback kết thúc trước khi task async của partition cũ dừng và task viết vào database sau khi consumer mới nhận partition.
Ứng dụng dùng manual partition assignment thay vì subscription theo group; một lần thay topology topic khiến các partition mới không được consumer nào đọc.
Đội cho phép consumer group cân bằng tải trên nhiều AZ; một AZ mất mạng tạm thời làm partition di chuyển qua lại và số lần xử lý lại tăng đột biến.
Nhóm áp cooperative assignor mới cho một phần pod trước khi rollout xong; consumer group đang dùng mixed assignment protocol và khó thống nhất chiến lược cân bằng.
Ứng dụng chạy consumer theo pattern subscribe nhiều topic; một topic mới khớp pattern làm rebalance và một listener nhận payload không tương thích.
Đội vận hành tăng số partition topic lên gấp đôi; key partitioner không còn giữ cùng key trên partition cũ và thứ tự toàn lịch sử event theo khóa bị ảnh hưởng.
Nhóm chạy @KafkaListener có group id thay đổi theo tên pod; mỗi pod trở thành consumer group riêng và cùng record được xử lý nhiều lần thay vì cân bằng tải.
Ứng dụng dùng consumer group cho nhiều nguồn cùng task; một nguồn có record rất lớn làm worker chiếm lâu và gây rebalance ở các partition nguồn khác.
Đội gặp CommitFailedException ngay sau một lần rebalance; logic xử lý đánh dấu record đã hoàn tất nhưng không biết offset có được commit bởi generation hợp lệ hay không.
Nhóm pause partition vì lỗi downstream nhưng không resume sau khi hệ thống hồi phục; backlog tăng dù consumer vẫn ở trạng thái RUNNING.
Ứng dụng dùng container.pause để giảm tải; nhóm vận hành không phân biệt trạng thái pause với consumer không còn được assign partition và khó xác định lý do không tiến.
Đội bật pauseImmediate để dừng nhanh khi quá tải; một số record đã poll trước lúc pause vẫn được xử lý hoặc giữ lại và số lượng task đang chạy không giảm ngay.
Nhóm giảm max.poll.records để giảm thời gian xử lý mỗi batch; độ trễ broker-fetch tăng và throughput không đạt mục tiêu dù database còn đủ tài nguyên.
Ứng dụng có producer gửi dữ liệu nhanh hơn nhiều so với consumer; lag tăng liên tục nhưng không có ngưỡng kiểm soát tốc độ upstream và thời hạn xử lý bị phá.
Đội áp ThreadPoolTaskExecutor cho mỗi record Kafka; queue không giới hạn làm heap tăng trong outage downstream và offset committed dừng tiến.
Nhóm áp policy từ chối khi worker pool đầy; @KafkaListener coi task rejected như lỗi chung và record bị retry nóng làm CPU tăng thêm.
Ứng dụng giảm tốc độ listener bằng Thread.sleep sau mỗi record; max.poll.interval.ms và heartbeat timing bị ảnh hưởng khi số message lớn.
Đội dùng Semaphore giới hạn lời gọi đối tác từ consumer; permit không được trả ở nhánh exception và toàn bộ luồng dừng dù CPU thấp.
Nhóm đặt HTTP connect timeout nhưng thiếu read timeout trong handler; các worker chờ response vô hạn và việc pause consumer không giải quyết được task đang kẹt.
Ứng dụng xử lý ảnh đính kèm trong Kafka value rất lớn; consumer fetch.max.bytes và max.partition.fetch.bytes chưa tương thích message size nên listener gặp vòng lỗi fetch.
Đội tăng max.poll.records khi theo dõi backlog; mỗi record mất vài giây do API đối tác và consumer bị rebalance trước khi hết batch.
Nhóm chia các bước xử lý record thành nhiều CompletableFuture; một bước cuối lỗi sau khi acknowledge và hệ thống không thể tự phát lại message.
Ứng dụng dùng batch listener với chuỗi xử lý ưu tiên; một record poison ở đầu batch khiến message phía sau từ cùng partition không được xử lý đúng hạn.
Đội áp rate limit theo tenant ở handler; một tenant có nhiều message lấp queue và khiến những tenant khác chậm dù partition của họ vẫn còn record tốt.
Nhóm cần fairness giữa các partition; một partition chứa sự kiện xử lý lâu làm lịch xử lý của worker chung chậm cho nhiều partition khác.
Ứng dụng poll liên tục nhiều record rồi xử lý thành từng sub-batch; chỉ sub-batch đầu thất bại nhưng offset commit được tính theo batch tổng và khó đối soát.
Đội tăng số consumer để giảm lag nhưng chỉ có vài partition; các instance mới không nhận việc và database vẫn bão hòa bởi những instance cũ.
Nhóm nhận sự kiện từ Kafka vào một buffer nội bộ có dung lượng cố định; khi buffer đạt ngưỡng, consumer chưa dừng poll và record bị bỏ ngoài chính sách retry.
Ứng dụng dùng retry blocking cho lỗi 429; cùng một partition bị giữ lâu khiến các customer khác chung partition không được cập nhật.
Đội chuyển sang non-blocking retry topics để giảm chặn partition; sự kiện mới của cùng order có thể hoàn tất trước retry cũ và trạng thái bị đảo.
Nhóm bật circuit breaker khi đối tác lỗi; handler vẫn consume và publish sang retry topic với tốc độ cao tạo backlog ngoài tầm quan sát ban đầu.
Ứng dụng hạ timeout KafkaTemplate để giảm request latency; producer report timeout nhưng broker có thể đã nhận sự kiện và thao tác replay gây duplicate.
Đội đặt memory buffer của producer lớn để chịu tải; khi broker mất kết nối, số message pending giữ trong memory tăng và pod bị OOM.
Nhóm cấu hình max.block.ms nhỏ cho producer trong giờ tải cao; một số lời gọi KafkaTemplate.send thất bại trước khi có metadata topic vì broker phản hồi chậm.
Ứng dụng tăng linger.ms và batch.size để tăng throughput; thời gian chờ tích lũy batch không phù hợp SLA thông báo OTP gần realtime.
Đội dùng compression cho payload Kafka rất lớn; CPU producer bị bão hòa khi traffic tăng trong khi broker bandwidth chưa hết.
Nhóm làm chậm consumer có chủ đích để giảm database writes; Kafka retention sắp hết và message chưa xử lý có nguy cơ biến mất trước lúc backlog được tiêu thụ.
Ứng dụng bị giới hạn quota fetch từ broker; tăng concurrency consumer không giảm lag mà làm các partition thường xuyên bị throttled.
Đội xử lý sự kiện ở ba vùng địa lý; network RTT cao giữa consumer và broker làm poll latency và commit latency tăng theo thời điểm.
Nhóm ghi vào PostgreSQL từng record từ listener; connection pool chỉ có một số slot và tăng concurrency tạo hàng nghìn task chờ thay vì xử lý nhanh hơn.
Ứng dụng triển khai backpressure qua pause/resume dựa trên queue depth; một metric stale làm listener tiếp tục pause sau khi downstream đã phục hồi.
Đội xử lý dữ liệu cá nhân trong DLT; retention, quyền đọc và cơ chế xóa dữ liệu của topic lỗi không tuân theo yêu cầu bảo vệ thông tin khách hàng.
Nhóm có producer và consumer dùng TLS tới Kafka; chứng chỉ client hết hạn một phần pod khiến rebalance liên tục mà log chỉ ghi lỗi xác thực lẻ tẻ.
Ứng dụng dùng SASL credential lấy từ secret; secret được xoay vòng nhưng consumer pod cũ giữ cấu hình hết hạn và không còn join group.
Đội thay ACL của topic DLT sau rollout; consumer vẫn đọc main topic bình thường nhưng DeadLetterPublishingRecoverer không có quyền WRITE khi xử lý record lỗi.
Nhóm cấu hình ACL READ cho group id không chính xác; listener kết nối broker được nhưng không thể join group hoặc commit offset.
Ứng dụng thu thập lag qua Micrometer; biểu đồ chỉ thấy tổng lag mà không phân biệt partition đang đứng hoàn toàn với partition có throughput bình thường.
Đội giám sát consumer lag bằng số offset chênh lệch; topic có nhiều record rất lớn khiến 1.000 offset tương ứng thời gian xử lý khác hẳn 1.000 record nhỏ.
Nhóm đặt cảnh báo khi lag vượt một ngưỡng cố định; giờ thấp điểm consumer ngừng hoàn toàn nhưng số record ít nên không có cảnh báo nào được kích hoạt.
Ứng dụng hiển thị commit offset tiến đều trên dashboard; listener đang xử lý dữ liệu ngoài Kafka bằng worker async sau acknowledge nên metric không thể xác nhận nghiệp vụ đã hoàn tất.
Đội dùng Micrometer Observation cho KafkaListener; một nhánh gọi API ngoài không truyền trace context và không thể nối sự cố timeout với message gốc.
Nhóm gắn correlation ID từ producer vào Kafka headers; một bước transformer xóa header trước khi gửi DLT khiến điều tra không nối được nguồn và record lỗi.
Ứng dụng gắn record key vào log nhưng không gắn topic-partition-offset; khi nhiều bản cùng key được phát lại, đội support không xác định được bản nào gây lỗi.
Đội log toàn bộ payload để chẩn đoán sự cố retry; nội dung có số tài khoản và thông tin cá nhân bị ghi vào nền tảng log có quyền đọc rộng.
Nhóm xuất metric theo eventId hoặc orderId riêng từng bản ghi; số lượng time series tăng rất nhanh và dịch vụ giám sát tiêu tốn tài nguyên quá mức.
Ứng dụng chỉ đếm record vào DLT; đội không biết bao nhiêu record đã được xử lý lại thành công hay còn đang chờ kiểm tra thủ công.
Đội muốn quan sát thời gian ở mỗi retry topic; dashboard chỉ nhìn lag main topic nên thời gian thực từ sự kiện gốc đến xử lý cuối bị đánh giá thấp.
Nhóm theo dõi các rebalances chỉ bằng tổng số lần; không tách nguyên nhân max.poll.interval.ms, mất heartbeat và scale nên mỗi sự cố được xử lý bằng cùng một thao tác.
Ứng dụng cảnh báo khi commit failure tăng; callback exception không được nối với consumer generation làm team không biết lỗi do rebalance hay broker coordinator.
Đội cần đo độ tuổi bản ghi lâu nhất chưa xử lý; biểu đồ chỉ hiển thị khoảng cách offset và không cho biết một đơn đang trễ quá SLA bao lâu.
Nhóm muốn phát hiện partition bị kẹt bởi poison message; topic tổng vẫn có record được xử lý ở partition khác nên metric throughput chung trông bình thường.
Ứng dụng áp retry và DLT nhưng không có tài liệu chuyển trạng thái record; khách hàng nhận thông báo thất bại trong khi hệ thống vẫn tiếp tục retry nền.
Đội sử dụng log message headers cho trace; Kafka header là byte array nhưng một ứng dụng tự decode bằng charset khác và correlation ID trong log không khớp.
Nhóm xây dashboard producer delivery thành công dựa vào số lần gọi send; broker ném exception trong future và chỉ số thành công vẫn được tính như đã ghi nhận.
Ứng dụng có nhiều @KafkaListener cho hai nhóm business; chung metric name nhưng không phân biệt listener.id nên không xác định được nhóm nào đang tụt.
Đội triển khai rolling upgrade cả broker và Spring Kafka; một nhóm consumer sử dụng assignor khác phiên bản còn lại và số lần rebalance tăng mạnh trong lúc canary.
Nhóm chạy integration test bằng EmbeddedKafkaBroker với một broker; kịch bản mất leader và min.insync.replicas không thể kiểm như cluster production nhiều replica.
Ứng dụng dùng Testcontainers Kafka cho thử nghiệm retry; testcase chỉ mô phỏng exception đầu tiên và không xác minh record đi qua retry topics rồi DLT.
Đội test manual acknowledgment bằng cách gọi listener method trực tiếp; cách container thực commit offset khi callback hoàn tất không được thực thi trong bài test.
Nhóm viết test DefaultErrorHandler với một lỗi transient; thời gian backoff và số lần retry khi broker có rebalance không được đo ở môi trường thật.
Ứng dụng kiểm xử lý deserialization trên một payload JSON hợp lệ; record có bytes không tương thích và ErrorHandlingDeserializer không được thử nên consumer chết khi nhận dữ liệu lỗi.
Đội có testcase replay DLT bằng key mới; thứ tự bản ghi sau phát lại không giống production sử dụng key gốc nên không phát hiện ghi đè trạng thái.
Nhóm kiểm EOS consume-transform-produce chỉ bằng output topic; phần truy vấn database ngoài transaction không được kiểm nên claim exactly-once vượt phạm vi bảo đảm.
Ứng dụng test Kafka transaction bằng một producer đơn; production có nhiều pod cùng transactional.id prefix và lỗi fencing không xuất hiện trong test.
Đội dựng test consumer group với một instance duy nhất; khi production scale nhiều pod, partition revoke trong lúc xử lý batch gây lỗi commit chưa được thử.
Nhóm muốn kiểm rebalance lúc listener đang chờ API ngoài; test giả chỉ cho handler trả thành công tức thì và không tạo được tình huống max.poll.interval.ms.
Ứng dụng giả lập crash ngay sau offset commit; kịch bản ghi nghiệp vụ thất bại sau commit chưa được thử và nguy cơ mất xử lý chưa được đánh giá.
Đội dùng test consumer đọc từ earliest; test suite chạy lại với group ID đã dùng nên offset committed cũ làm assertion nhận không đủ số record.
Nhóm kiểm idempotency bằng cách gửi cùng record hai lần liên tiếp; production có hai pod xử lý đồng thời nên race trên bảng dedup chưa được phát hiện.
Ứng dụng dùng @EmbeddedKafka trong bài test Spring; topic từ testcase trước còn record làm một test đọc message thừa và thất bại tùy thứ tự chạy.
Đội test DLT consumer bằng event lỗi với nội dung ngắn; production có stack trace headers lớn vượt giới hạn record size và publish lỗi tiếp khi gặp exception thật.
Nhóm chạy SpringBootTest với Kafka container nhưng đóng broker trước khi listener container dừng; testcase tiếp theo gặp lỗi kết nối ngẫu nhiên khi context cache được dùng lại.
Ứng dụng viết performance test cho consumer với 100 record; production cần vài triệu record và quá tải chỉ phát sinh khi backpressure queue đạt ngưỡng cao.
Đội đo tải producer với acks=1 trong test; production yêu cầu acks=all và min.insync.replicas nên throughput dự tính không phù hợp sau triển khai.
Nhóm mô phỏng retry topic bằng lịch thời gian ảo; consumer thực phải chờ broker polling và rebalances nên độ trễ từng attempt khác kết quả đơn vị.
Ứng dụng kiểm hoạt động pause/resume bằng thao tác tắt listener; state pause, backlog fetch và các record in-flight không được bao phủ như production.
Đội rollback Spring Kafka sau khi thay đổi tên retry topics; message còn ở retry topic phiên bản mới không có consumer phiên bản cũ và nằm chờ tới hết retention.
Nhóm nâng cấp DLT handler để đọc schema mới; các record lỗi lịch sử thuộc schema cũ không thể được replay bằng bản triển khai hiện tại.
Ứng dụng chạy blue-green deployment với hai group ID; trong giai đoạn chuyển đổi, cả hai nhóm đọc một topic và side effect nghiệp vụ có thể diễn ra hai lần.
Đội dùng cùng group ID cho canary và stable để chia partition; bản canary chỉ hiểu schema mới nhưng có thể nhận record cũ chưa tương thích.
Nhóm thay replication factor và min.insync.replicas trong đợt nâng cấp broker; producer gặp lỗi ghi ngẫu nhiên khi một replica đang catch up nhưng thông báo API không rõ trạng thái cuối.
Ứng dụng di chuyển topic sang cluster mới bằng công cụ mirror; offset của consumer group không được ánh xạ hoàn chỉnh và một dải sự kiện bị phát lại hoặc bỏ qua.
Đội xử lý record Kafka sau disaster recovery bằng seek theo timestamp; các record có timestamp không tương ứng lúc nghiệp vụ phát sinh nên phạm vi replay sai.
Nhóm muốn khôi phục dữ liệu từ DLT sau outage nhiều ngày; retention đã xóa một phần record cần điều tra và công cụ replay không cảnh báo khoảng trống dữ liệu.
Ứng dụng dừng consumer để bảo trì database vài giờ; Kafka topic retention và tốc độ producer làm lag vượt khả năng catch up trước hạn nghiệp vụ.
Đội đặt chiến lược cân bằng lại consumer group trong giờ cao điểm; tần suất rebalance quá lớn khiến thời gian xử lý hữu ích chỉ chiếm phần nhỏ chu kỳ.
Nhóm áp SLA exactly-once cho quá trình gửi notification; Kafka đạt atomic commit nội bộ nhưng nhà cung cấp push notification trả timeout sau khi đã chấp nhận.
Ứng dụng xử lý duyệt khoản vay dựa trên các record cùng applicationId; record đến muộn sau DLT replay làm chuyển trạng thái từ APPROVED về PENDING ngoài ý muốn.
Đội dùng event nguồn có thể được gửi lại từ upstream với eventId không ổn định; Kafka producer idempotence không loại được các bản ghi nghiệp vụ trùng nguồn.
Nhóm xây luồng xử lý tiền với Kafka transaction và outbox; một lỗi rollback chéo giữa DB và Kafka chỉ phát hiện khi đối soát số dư cuối ngày.
Ứng dụng tạo sự kiện thay đổi quyền khách hàng qua Kafka; consumer bị lag nhiều giờ và vẫn áp quyền cũ cho những hành động đã được thực hiện trong thời gian chờ.
Đội vận hành muốn đối soát end-to-end từ offset đầu vào qua xử lý DB đến output topic; hệ thống chưa lưu correlation ID và trạng thái riêng của từng bước nên không thể chứng minh sự kiện nào bị mất hoặc lặp.
