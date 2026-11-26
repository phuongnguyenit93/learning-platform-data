Câu 1. Trong Project Reactor, kiểu nào biểu diễn luồng có tối đa một giá trị?
A. Mono có thể phát tối đa một onNext trong mỗi subscription
B. Flux chỉ phát đúng một giá trị trước khi hoàn thành
C. ParallelFlux chỉ phát một giá trị trên mỗi rail
D. Sinks.Many chỉ phát một giá trị cho từng subscriber
Đáp án đúng: A

Câu 2. Điều gì khiến chuỗi cold Flux thực sự bắt đầu phát dữ liệu?
A. Lệnh map được khai báo trong lúc xây dựng pipeline
B. Một subscriber đăng ký và có nhu cầu nhận dữ liệu
C. Đối tượng Flux được gán cho một biến Java mới
D. Một scheduler được khai báo nhưng chưa subscribe
Đáp án đúng: B

Câu 3. Sự khác nhau cơ bản giữa Mono.just và Mono.defer là gì?
A. just chạy bất đồng bộ, defer chạy đồng bộ mặc định
B. just lấy giá trị lúc tạo, defer khi subscribe nguồn
C. just luôn tạo mới, defer lưu kết quả dùng chung
D. just chỉ nhận null, defer từ chối giá trị null
Đáp án đúng: B

Câu 4. Mono.justOrEmpty(null) phát tín hiệu nào khi được subscribe?
A. Phát một onNext mang null trước khi onComplete
B. Phát một onError do tham số không có giá trị
C. Phát onComplete, không có phần tử onNext nào
D. Không phát tín hiệu nào cho đến khi bị cancel
Đáp án đúng: C

Câu 5. Flux.range(3, 4) tạo ra chuỗi số nguyên nào?
A. Các giá trị 3, 4, 5, 6, 7 theo thứ tự tăng
B. Phát lần lượt các số 3, 4, 5 và 6 trong Flux
C. Các giá trị 0, 1, 2, 3 theo thứ tự tăng dần
D. Các giá trị 4, 5, 6, 7 theo thứ tự tăng dần
Đáp án đúng: B

Câu 6. Mono.empty() gửi những tín hiệu nào khi được subscribe?
A. Trả một onNext rỗng rồi tiếp tục chờ dữ liệu
B. Phát onError vì không có phần tử được cung cấp
C. Không hoàn thành cho đến khi subscriber hủy
D. Hoàn thành qua onComplete mà không có onNext
Đáp án đúng: D

Câu 7. Flux.error(exception) thường làm điều gì khi được subscribe?
A. Phát onNext chứa Throwable như một phần tử
B. Bỏ qua Throwable rồi hoàn thành không có lỗi
C. Tự chuyển sang Publisher dự phòng nếu có lỗi
D. Phát onError với lỗi đã cung cấp rồi dừng
Đáp án đúng: D

Câu 8. Theo Reactive Streams, onError có ý nghĩa nào với một subscription?
A. Là cảnh báo rồi vẫn được phát tiếp các onNext
B. Là yêu cầu downstream phải gọi request vô hạn
C. Là tín hiệu kết thúc, không có onNext phía sau
D. Là tín hiệu chỉ xuất hiện sau một onComplete
Đáp án đúng: C

Câu 9. Subscription.request(n) thể hiện hành động nào của subscriber?
A. Ra lệnh Publisher phát chính xác n phần tử ngay
B. Yêu cầu phát lại n phần tử đã được gửi trước
C. Yêu cầu hủy n subscription không còn sử dụng
D. Báo nhu cầu nhận tối đa n phần tử tiếp theo
Đáp án đúng: D

Câu 10. Khi subscriber gọi Subscription.cancel(), điều gì được yêu cầu?
A. Yêu cầu ngừng phát trên subscription hiện tại
B. Yêu cầu upstream phát hết phần tử còn tồn đọng
C. Yêu cầu upstream chạy lại toàn bộ chuỗi từ đầu
D. Chuyển subscription sang một scheduler khác
Đáp án đúng: A

Câu 11. Mục tiêu của backpressure trong pipeline reactive là gì?
A. Ép upstream phát nhanh hơn bất kể nơi nhận xử lý
B. Bắt mọi operator lưu vô hạn tất cả phần tử
C. Điều tiết tốc độ phát theo nhu cầu của bên nhận
D. Ngăn mọi Publisher phát tín hiệu onComplete
Đáp án đúng: C

Câu 12. Operator map trong Flux chủ yếu thực hiện thao tác nào?
A. Hủy mọi Publisher chưa hoàn thành ở lần phát trước
B. Trộn kết quả bất đồng bộ theo thời gian hoàn tất
C. Biến đổi đồng bộ từng phần tử thành một phần tử khác
D. Phân phối từng phần tử vào một luồng con không giới hạn
Đáp án đúng: C

Câu 13. Khi flatMap ánh xạ phần tử sang Mono bất đồng bộ, điều nào có thể xảy ra?
A. Mọi kết quả luôn giữ thứ tự như nguồn ban đầu
B. Kết quả được xen kẽ theo thời điểm inner hoàn tất
C. Mỗi inner chỉ được subscribe sau khi inner trước xong
D. Operator luôn chạy tất cả inner trên đúng một thread
Đáp án đúng: B

Câu 14. Khi cần giữ thứ tự của các Mono tạo từ từng phần tử, nên dùng operator nào?
A. flatMap để mặc định giữ nguyên thứ tự mọi inner
B. concatMap xử lý các inner theo thứ tự nguồn
C. merge để chờ từng inner hoàn tất theo thứ tự
D. switchMap để lưu toàn bộ inner đã nhận trước đó
Đáp án đúng: B

Câu 15. Trong xử lý tìm kiếm theo ký tự nhập liên tục, switchMap giúp gì?
A. Giữ tất cả inner cũ để kết quả được phát theo thứ tự
B. Tự nhân bản mỗi inner cho toàn bộ subscriber khác
C. Hủy subscription của inner cũ để dùng inner mới
D. Đệm mọi inner mới đến khi inner đầu tiên hoàn tất
Đáp án đúng: C

Câu 16. Operator filter trong Flux xử lý các phần tử ra sao?
A. Biến đổi từng phần tử thành Boolean trước khi phát
B. Phát cả phần tử không đạt kèm thông tin lỗi
C. Chỉ phát các phần tử thỏa điều kiện predicate
D. Chia luồng thành hai Publisher theo đúng sai
Đáp án đúng: C

Câu 17. Flux.take(5) trên nguồn có nhiều phần tử thường làm gì?
A. Phát tối đa 5 phần tử rồi cancel nguồn upstream
B. Bỏ năm phần tử đầu trước khi bắt đầu chuyển tiếp
C. Đợi đủ năm phần tử rồi phát lại tất cả phần tử
D. Chuyển năm phần tử thành một List duy nhất
Đáp án đúng: A

Câu 18. Operator buffer(5) có tác dụng gì với Flux dữ liệu?
A. Chỉ phát phần tử thứ năm ở từng nhóm dữ liệu
B. Bỏ mọi phần tử nằm ngoài bộ đệm kích thước năm
C. Gom phần tử vào List có tối đa năm phần tử
D. Chạy năm subscriber riêng biệt cho cùng một Flux
Đáp án đúng: C

Câu 19. Flux.zip(left, right) ghép phần tử theo nguyên tắc nào?
A. Ghép mỗi phần tử trái với mọi phần tử bên phải
B. Phát từng phần tử theo thứ tự đến từ hai nguồn
C. Chỉ chọn phần tử mới nhất trong toàn bộ hai nguồn
D. Ghép theo cặp phần tử tương ứng từ mỗi Publisher
Đáp án đúng: D

Câu 20. combineLatest(left, right) khác zip chủ yếu ở điểm nào?
A. Ghép giá trị mới nhất sau khi cả hai nguồn đã phát
B. Chỉ phát khi mỗi nguồn có thêm đúng một phần tử mới
C. Chỉ chuyển tiếp phần tử từ nguồn vừa hoàn thành trước
D. Tạo một Publisher mới chỉ sau khi cả hai nguồn kết thúc
Đáp án đúng: A

Câu 21. Flux.merge trên nhiều nguồn bất đồng bộ thường có hành vi nào?
A. Chờ nguồn trước hoàn tất rồi mới subscribe nguồn sau
B. Ghép phần tử theo chỉ số tương ứng từ từng nguồn
C. Xen kẽ phần tử theo lúc đến, không giữ thứ tự giữa nguồn
D. Giữ mọi phần tử cho đến khi cả hai nguồn kết thúc
Đáp án đúng: C

Câu 22. Flux.concat(sourceA, sourceB) đảm bảo điều nào?
A. Subscribe hai nguồn cùng lúc rồi sắp xếp lại dữ liệu
B. Chỉ chọn nguồn phát nhanh hơn trong hai nguồn
C. Chỉ subscribe nguồn B sau khi nguồn A hoàn thành
D. Ghép phần tử của hai nguồn theo từng cặp chỉ số
Đáp án đúng: C

Câu 23. Khi dùng delayElements, hành vi kỳ vọng của Flux là gì?
A. Chặn thread gọi bằng Thread.sleep cho từng phần tử
B. Trì hoãn tín hiệu từng phần tử bằng timer không chặn
C. Trì hoãn việc tạo biến Flux nhưng không trì hoãn phát
D. Tự biến luồng cold thành luồng hot chia sẻ dữ liệu
Đáp án đúng: B

Câu 24. onErrorResume khác gì so với onErrorReturn trong Reactor?
A. Tự retry nguồn cũ thay vì phát một giá trị mặc định
B. Biến lỗi thành lỗi khác thay vì một giá trị cố định
C. Dùng Publisher dự phòng để thay thế luồng đang báo lỗi
D. Hủy subscription ngay thay vì phát tín hiệu hoàn tất
Đáp án đúng: C

Câu 25. Operator onErrorReturn thường xử lý lỗi thế nào?
A. Subscribe lại nguồn đầu vào từ vị trí đã lỗi
B. Chuyển lỗi hiện tại thành một exception mới
C. Tiếp tục nhận các onNext sau tín hiệu onError
D. Phát giá trị dự phòng rồi hoàn thành bình thường
Đáp án đúng: D

Câu 26. Operator onErrorMap thường dùng vào việc gì?
A. Chuyển onNext của luồng thành giá trị mặc định
B. Đăng ký lại nguồn từ đầu sau một lỗi tạm thời
C. Đệm phần tử bị lỗi để xử lý khi upstream hoàn tất
D. Biến đổi Throwable trước khi phát tín hiệu lỗi
Đáp án đúng: D

Câu 27. Khi áp dụng retry trên Publisher có side effect, rủi ro nào cần kiểm soát?
A. retry luôn tiếp tục chính xác tại phần tử vừa lỗi
B. retry sẽ tự rollback transaction ngoài pipeline
C. Subscribe lại có thể lặp các tác dụng phụ nghiệp vụ
D. retry luôn chuyển nguồn cold thành nguồn hot chia sẻ
Đáp án đúng: C

Câu 28. Operator timeout trên nguồn phản hồi quá chậm thường làm gì?
A. Tự bỏ giới hạn chờ sau khi nhận một request(n)
B. Phát lỗi timeout khi quá thời gian chờ tín hiệu
C. Tự tăng số thread mà không phát bất kỳ lỗi nào
D. Phát lại phần tử cũ cho đến khi nguồn mới hoàn tất
Đáp án đúng: B

Câu 29. doOnNext phù hợp khi cần thực hiện mục đích nào?
A. Ánh xạ từng phần tử thành một giá trị nghiệp vụ mới
B. Quan sát, ghi log phần tử mà không biến đổi giá trị
C. Thay thế bất kỳ onError nào bằng một Publisher mới
D. Hủy mọi phần tử chưa được xử lý khi onComplete
Đáp án đúng: B

Câu 30. doFinally có điểm hữu ích gì khi giải phóng tài nguyên?
A. Chạy callback khi complete, error hoặc cancel
B. Callback chỉ được gọi nếu nguồn phát onComplete
C. Callback luôn chạy trước khi upstream được subscribe
D. Callback tự ghi rollback cho mọi DB transaction
Đáp án đúng: A

Câu 31. Flux.using hữu ích cho trường hợp quản lý tài nguyên nào?
A. Giữ tài nguyên dùng chung cho mọi subscriber vĩnh viễn
B. Tự chuyển mọi lời gọi JDBC sang luồng không chặn
C. Bỏ qua lỗi giải phóng nếu subscriber đã gọi cancel
D. Tạo và dọn tài nguyên cho mỗi subscription riêng biệt
Đáp án đúng: D

Câu 32. usingWhen khác using chủ yếu ở điểm nào?
A. Chỉ dọn tài nguyên khi onNext đầu tiên được gửi
B. Lấy và giải phóng tài nguyên theo cơ chế bất đồng bộ
C. Bắt buộc dùng cùng một tài nguyên cho mọi subscriber
D. Bỏ qua xử lý lỗi khi việc giải phóng tài nguyên thất bại
Đáp án đúng: B

Câu 33. Schedulers.boundedElastic() thường phù hợp cho công việc nào?
A. Chạy tác vụ blocking trên nhóm thread có giới hạn
B. Chạy CPU-bound song song trên một thread duy nhất
C. Đưa mọi tác vụ lên event-loop không có blocking
D. Đảm bảo một thread mới vô hạn cho mỗi phần tử
Đáp án đúng: A

Câu 34. Khi xử lý CPU-bound độc lập qua parallel(), cách cấu hình nào phù hợp?
A. Dùng publishOn immediate để tạo thêm CPU core
B. Dùng block() bên trong map để chia đều CPU
C. Dùng subscribeOn single cho từng phần tử CPU
D. Dùng parallel() rồi runOn với scheduler thích hợp
Đáp án đúng: D

Câu 35. subscribeOn thường tác động đến phần nào của chuỗi Reactor?
A. Scheduler chỉ dành cho mọi operator sau vị trí gọi
B. Chọn scheduler cho lúc subscribe nguồn và gửi request
C. Scheduler dành riêng cho callback doFinally cuối chuỗi
D. Scheduler dành cho chuyển đổi kết quả mỗi lần flatMap
Đáp án đúng: B

Câu 36. publishOn thường có hiệu lực như thế nào trong pipeline?
A. Chuyển các operator downstream sang scheduler đã chọn
B. Chỉ thay scheduler của upstream trước điểm đặt operator
C. Chỉ thay scheduler dùng để đăng ký nguồn lần đầu
D. Tự tách mỗi phần tử thành một thread mới riêng
Đáp án đúng: A

Câu 37. Trong Reactor, Context được thiết kế để mang dữ liệu theo hướng nào?
A. Gắn với subscription, không phụ thuộc thread
B. Theo ThreadLocal cố định của thread dựng Publisher
C. Theo biến static dùng chung giữa các subscriber
D. Theo tham số bắt buộc của mọi phương thức map
Đáp án đúng: A

Câu 38. Operator deferContextual được dùng để làm gì?
A. Ghi đè Context của toàn bộ JVM trong một lệnh
B. Sao chép ThreadLocal của mọi thread trong scheduler
C. Lưu phần tử onNext vào một cache tĩnh toàn cục
D. Đọc ContextView khi subscription được thiết lập
Đáp án đúng: D

Câu 39. Tại sao không thể mặc định dựa vào ThreadLocal để truyền metadata reactive?
A. Mọi pipeline reactive luôn thực thi trên một thread
B. Tín hiệu có thể đổi thread sau khi chuyển scheduler
C. Context của Reactor luôn tự xóa mọi ThreadLocal
D. Không thể dùng thread trong ứng dụng Reactor Core
Đáp án đúng: B

Câu 40. Một cold Publisher có đặc tính quan trọng nào?
A. Mọi subscription luôn nhận phần dữ liệu phát còn lại
B. Publisher tự phát dữ liệu ngay khi được khởi tạo
C. Publisher chỉ giữ một subscriber trong toàn bộ vòng đời
D. Mỗi subscription có thể thực thi độc lập nguồn dữ liệu
Đáp án đúng: D

Câu 41. Hot Publisher thường khác cold Publisher ở điểm nào?
A. Nguồn đã có thể phát trước lúc subscriber mới tham gia
B. Mỗi subscriber luôn khiến nguồn thực thi lại từ đầu
C. Mọi subscriber đều nhận lại lịch sử dù không replay
D. Nguồn chỉ bắt đầu phát sau khi downstream request
Đáp án đúng: A

Câu 42. Operator cache() đặt trên Flux cold thường dẫn đến điều gì?
A. Bỏ qua mọi dữ liệu cũ khi subscriber mới đăng ký
B. Lưu tín hiệu để subscriber đến sau được nhận lại
C. Giữ nguồn cold và luôn gọi lại mỗi lần subscribe
D. Chỉ cache các lỗi còn giá trị được phát trực tiếp
Đáp án đúng: B

Câu 43. Sinks.Many trong Reactor thường cung cấp khả năng nào?
A. Đảm bảo mọi event đều được ghi bền vững vào ổ đĩa
B. Tự tạo transaction giữa DB và subscriber nhận dữ liệu
C. Chuyển mọi Publisher cold sang singleton hot vô điều kiện
D. Cho phép phát tín hiệu qua API của sink vào Publisher
Đáp án đúng: D

Câu 44. Với Sinks.Many, tryEmitNext(value) trả về gì khi gọi phát?
A. EmitResult cho biết thành công hoặc lý do thất bại
B. Một Mono chờ mọi subscriber xác nhận đã nhận
C. Một Subscription cho phép yêu cầu phần tử tiếp
D. Một Throwable luôn được ném nếu không có subscriber
Đáp án đúng: A

Câu 45. Sinks.many().replay().limit(1) có tính chất nào?
A. Phát lại phần tử mới nhất cho subscriber đến sau
B. Giữ toàn bộ lịch sử message trong ổ đĩa bền vững
C. Chỉ cho phép một subscriber được nhận phần tử
D. Luôn từ chối subscribe nếu nguồn đã từng phát
Đáp án đúng: A

Câu 46. StepVerifier trong reactor-test thường dùng để kiểm tra điều gì?
A. Số thread vật lý tối đa của mọi scheduler trong JVM
B. Cấu trúc bytecode của operator khi tối ưu compiler
C. Kiểm tra thứ tự dữ liệu và tín hiệu của Publisher
D. Mức sử dụng RAM của tất cả application context
Đáp án đúng: C

Câu 47. StepVerifier.withVirtualTime có lợi thế nào khi test delay dài?
A. Dùng đồng hồ ảo để tiến thời gian khi kiểm thử delay
B. Buộc pipeline dùng Thread.sleep để tăng tốc kiểm thử
C. Tự bỏ mọi tín hiệu onError trước khi chạy kiểm thử
D. Cho phép phát nhiều giá trị null vào một luồng Mono
Đáp án đúng: A

Câu 48. Operator onBackpressureBuffer giúp giải quyết nhu cầu nào?
A. Bỏ phần tử cũ và chỉ giữ phần tử mới nhất
B. Tự chuyển onError thành một giá trị dự phòng
C. Tăng số subscriber khi upstream phát quá nhanh
D. Đệm phần tử khi downstream chưa thể xử lý kịp
Đáp án đúng: D
