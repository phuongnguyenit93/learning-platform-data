# Thử nhiều mô hình cho cùng một tập tình huống nghiệp vụ

Trong Domain-Driven Design (DDD), mô hình miền là cách đội ngũ diễn đạt và giải quyết một phần thực tế nghiệp vụ bằng các khái niệm, quan hệ, hành vi và quy tắc. Mô hình đầu tiên thường chỉ phản ánh những gì nhóm hiểu ở thời điểm bắt đầu. Khi xem xét thêm trường hợp biên, ngoại lệ, thay đổi theo thời gian hoặc nhiều thao tác đồng thời, mô hình đó có thể bộc lộ những điểm yếu.

**Thử nhiều mô hình cho cùng một tập tình huống nghiệp vụ** là cách khám phá mô hình sâu hơn: giữ nguyên các tình huống cần giải quyết, tạo ra một vài cách biểu diễn nghiệp vụ khác nhau, rồi kiểm tra từng cách bằng cùng một bộ tình huống. Việc so sánh cho thấy mô hình nào diễn đạt quy tắc tự nhiên hơn, đặt bất biến ở đúng nơi, xử lý thay đổi rõ ràng và có độ phức tạp phù hợp.

Mục tiêu không phải tạo nhiều class hay tìm một mô hình trừu tượng nhất. Mục tiêu là chọn mô hình giải thích được nghiệp vụ, giúp đội phát triển suy luận đúng và thay đổi có kiểm soát.

## 1. Mô hình miền là một giả thuyết có thể kiểm chứng

Một mô hình miền không phải bản sao của thế giới thực. Nó là một cách chọn lọc khái niệm và quy tắc để giải quyết những vấn đề cụ thể trong một Bounded Context.

Một mô hình thường bao gồm:

- **Khái niệm:** những điều nghiệp vụ quan tâm, như lịch hẹn, khung giờ, lượt giữ chỗ, khách hàng hoặc hạn mức.
- **Định danh và quan hệ:** đối tượng nào có identity, đối tượng nào là Value Object, đối tượng nào tham chiếu đối tượng khác bằng ID.
- **Hành vi:** những hành động hợp lệ mà đối tượng có thể thực hiện.
- **Bất biến:** điều kiện phải luôn đúng sau mỗi thay đổi được chấp nhận.
- **Vòng đời:** các trạng thái và chuyển đổi có ý nghĩa nghiệp vụ.
- **Ranh giới nhất quán:** phần dữ liệu nào cần được thay đổi như một đơn vị để bảo vệ bất biến.

Khi nhóm nói “một lịch hẹn có thể được giữ tạm trước khi xác nhận”, đó là một giả thuyết về cách nghiệp vụ vận hành. Có thể biểu diễn nó bằng trạng thái của lịch hẹn, bằng một đối tượng giữ chỗ riêng hoặc bằng một mô hình năng lực theo khung giờ. Mỗi cách có hệ quả khác nhau đối với hết hạn, hủy, đặt trùng và điều phối.

Một mô hình tốt cần được thử bằng tình huống cụ thể. Nếu nhóm chỉ thảo luận tên class mà không mô phỏng hành vi, mô hình rất dễ phản ánh cách nghĩ của lập trình viên hơn là cách nghiệp vụ thực sự hoạt động.

## 2. Vì sao nên thử nhiều mô hình?

Mô hình đầu tiên thường được hình thành từ ví dụ dễ nhất. Nó có thể giải quyết luồng bình thường nhưng chưa bộc lộ được quy tắc ẩn.

Thử các mô hình thay thế giúp:

- Nhận ra một khái niệm quan trọng đang bị gộp vào một trường trạng thái hoặc một boolean.
- Phát hiện bất biến chưa có đối tượng nào chịu trách nhiệm bảo vệ.
- Nhìn thấy các quan hệ đang buộc nhiều đối tượng thay đổi cùng lúc.
- Phân biệt trạng thái nghiệp vụ với trạng thái kỹ thuật hoặc trạng thái của quy trình.
- Kiểm tra mô hình có diễn đạt được thời gian hiệu lực, giữ tạm, hết hạn và bù trừ không.
- Tránh chọn Aggregate Boundary chỉ vì cấu trúc bảng hoặc quan hệ ORM hiện có.
- So sánh lợi ích của mô hình sâu với chi phí vận hành và độ phức tạp mà nó tạo ra.

Hai mô hình có thể cùng giải quyết được tình huống thông thường, nhưng khác nhau rõ khi có hai người cùng đặt chỗ cuối cùng hoặc một yêu cầu đổi lịch thất bại giữa chừng. Những tình huống này giúp làm lộ ra sự khác biệt trong cách mỗi mô hình bảo vệ quy tắc.

## 3. Giữ nguyên một bộ tình huống khi so sánh

Để so sánh công bằng, cần giữ nguyên tập tình huống nghiệp vụ. Nếu mỗi mô hình được thử bằng một tập ví dụ khác nhau, nhóm có thể vô tình chọn mô hình mình thích bằng cách chỉ đưa ra những trường hợp mô hình đó xử lý tốt.

Một bộ tình huống nên có nhiều loại:

| Loại tình huống | Câu hỏi cần làm rõ |
| --- | --- |
| Luồng bình thường | Người dùng thực hiện hành động phổ biến thì điều gì xảy ra? |
| Ranh giới | Điều gì xảy ra ngay tại ngưỡng số lượng, thời gian hoặc hạn mức? |
| Ngoại lệ nghiệp vụ | Khi không đủ điều kiện, mô hình biểu diễn kết quả ra sao? |
| Cạnh tranh | Hai người cùng yêu cầu tài nguyên cuối cùng thì ai được chấp nhận? |
| Thời gian | Giữ chỗ hết hạn, chính sách đổi hoặc hủy có hiệu lực khi nào? |
| Thay đổi | Nghiệp vụ thêm quy tắc hoặc loại dịch vụ mới thì mô hình biến đổi thế nào? |
| Tích hợp | Khi context khác hoặc hệ thống bên ngoài phản hồi chậm thì chuyện gì xảy ra? |
| Phục hồi | Nếu một bước thành công và bước tiếp theo thất bại thì xử lý thế nào? |

Hãy viết tình huống bằng ngôn ngữ của chuyên gia nghiệp vụ. Tránh bắt đầu bằng cách nói về bảng, endpoint hoặc class. Ví dụ: “Hai bệnh nhân cùng yêu cầu khung giờ chỉ còn một chỗ” diễn đạt vấn đề nghiệp vụ rõ hơn “cần khóa row khi update”.

## 4. Ví dụ xuyên suốt: đặt lịch khám theo khung giờ

Giả sử một phòng khám cho phép bệnh nhân đặt lịch với bác sĩ theo khung giờ. Mỗi khung giờ có sức chứa nhất định. Người dùng có thể giữ chỗ trong thời gian ngắn để hoàn tất thông tin, xác nhận lịch, hủy hoặc đổi lịch.

Sau khi trao đổi với chuyên gia, nhóm ghi nhận cùng một bộ tình huống:

1. Bệnh nhân đặt một khung giờ còn chỗ và lịch được xác nhận.
2. Hai bệnh nhân đồng thời yêu cầu chỗ cuối cùng trong cùng khung giờ.
3. Một bệnh nhân giữ chỗ nhưng không xác nhận trước khi thời hạn giữ kết thúc.
4. Bệnh nhân hủy trước hạn cho phép; chỗ được giải phóng và có thể mời người trong danh sách chờ.
5. Bệnh nhân đổi sang khung giờ khác; nếu khung giờ mới không còn chỗ thì lịch cũ vẫn được giữ.
6. Phòng khám giảm sức chứa hoặc bác sĩ chặn một khung giờ đã có lịch.
7. Bệnh nhân không đến; hệ thống cần ghi nhận no-show và áp dụng quy tắc tương ứng.
8. Một command hoặc message được gửi lặp; hệ thống không được tạo hai lịch cho cùng một ý định.

Các quy tắc cần xác minh thêm với nghiệp vụ:

- Sức chứa được tính theo số bệnh nhân, số phút khám hay một đơn vị năng lực khác?
- Một bệnh nhân có được đặt hai lịch trùng thời gian ở hai chuyên khoa không?
- Giữ chỗ có chiếm sức chứa không, và giữ chỗ hết hạn chính xác lúc nào?
- Hủy trước và sau thời hạn có kết quả khác nhau không?
- Lịch hẹn được xem là xác nhận khi nào?
- Khi bác sĩ chặn lịch đã có người đặt, phòng khám chuyển lịch, hủy lịch hay yêu cầu nhân viên xử lý?

Những câu hỏi chưa được xác nhận phải được ghi là giả định cần làm rõ, không nên tự biến chúng thành quy tắc của mô hình.

## 5. Mô hình ứng viên A: khung giờ có trạng thái đặt chỗ

Mô hình đơn giản đầu tiên coi mỗi khung giờ là một đối tượng có trạng thái AVAILABLE hoặc BOOKED. Khi đặt, hệ thống chuyển trạng thái và lưu bệnh nhân đã đặt.

~~~text
AppointmentSlot
-------------------------
slotId
providerId
startAt
endAt
status: AVAILABLE | BOOKED
patientId
~~~

Hành vi có thể là:

- book(patientId): nếu khung giờ còn trống thì chuyển thành BOOKED.
- cancel(): chuyển về AVAILABLE.
- reschedule(targetSlot): chuyển lịch sang khung giờ khác.

Mô hình này dễ hiểu và có thể rất phù hợp nếu nghiệp vụ thực sự chỉ có một chỗ cho mỗi khung giờ, không có giữ tạm, không có nhiều trạng thái và quy tắc hủy/đổi đơn giản.

Tuy nhiên, khi thử cùng bộ tình huống:

- Tình huống 1 được xử lý tự nhiên.
- Tình huống 2 cần khóa hoặc version để ngăn hai request cùng đặt một chỗ.
- Tình huống 3 buộc phải thêm trạng thái HOLD và thời điểm hết hạn.
- Tình huống 4 cần biết ai đang chờ và điều kiện nào giải phóng chỗ.
- Tình huống 5 cần phối hợp cập nhật hai khung giờ; nếu cập nhật khung giờ mới thất bại, lịch cũ không được mất.
- Tình huống 6 khó xử lý nếu khung giờ đã BOOKED mà phòng khám cần giảm sức chứa hoặc chặn lịch.
- Tình huống 7 cần thêm trạng thái NO_SHOW hoặc một bản ghi kết quả riêng.

Mô hình vẫn có thể mở rộng, nhưng các trạng thái và trường dữ liệu bắt đầu tích tụ. Nếu một slot có sức chứa nhiều hơn một bệnh nhân, status đơn giản không còn biểu diễn đủ thông tin.

**Điều mô hình A làm tốt:** đơn giản, dễ hiểu với bài toán một chỗ cho mỗi khung giờ.

**Điểm cần xem xét:** khi có giữ tạm, nhiều chỗ, danh sách chờ và vòng đời đặt lịch phức tạp, khái niệm “slot đã đặt hay chưa” không còn đủ sâu.

## 6. Mô hình ứng viên B: lịch hẹn có vòng đời riêng

Mô hình thứ hai coi Appointment là đối tượng trung tâm. Một lịch hẹn có định danh, bệnh nhân, bác sĩ, khoảng thời gian và trạng thái riêng.

~~~text
Appointment
-------------------------
appointmentId
patientId
providerId
timeRange
status:
  REQUESTED
  HELD
  CONFIRMED
  CANCELLED
  COMPLETED
  NO_SHOW
~~~

Các hành vi có thể gồm:

- request()
- hold(until)
- confirm()
- cancel(reason)
- reschedule(newTimeRange)
- markNoShow()
- complete()

Mô hình này diễn đạt vòng đời của một cuộc hẹn rõ hơn. Có thể lưu lịch sử, lý do hủy, kết quả khám và các quy tắc riêng của một lịch hẹn. Nó phù hợp khi lịch hẹn là khái niệm nghiệp vụ có identity và vòng đời độc lập.

Nhưng khi thử tình huống 2, ta phải hỏi: Aggregate Appointment nào chịu trách nhiệm ngăn hai lịch cùng chiếm chỗ cuối cùng? Hai request có thể tạo hai Appointment khác nhau; mỗi Aggregate riêng lẻ đều hợp lệ. Việc truy vấn “còn chỗ không?” trước khi lưu không tự bảo vệ được trước race condition.

Có thể bổ sung một Schedule hoặc Capacity service để kiểm tra sức chứa. Tuy nhiên, nếu chỉ truy vấn số lịch hiện có rồi tạo Appointment, hai request vẫn có thể cùng vượt qua kiểm tra. Cần một cơ chế nhất quán như conditional update, unique/exclusion constraint phù hợp hoặc một Aggregate sở hữu sức chứa.

Mô hình B làm rõ vòng đời lịch hẹn nhưng chưa tự trả lời câu hỏi quyền sở hữu bất biến sức chứa. Nếu đặt mọi lịch hẹn và mọi khung giờ vào một Aggregate lớn để giải quyết, phạm vi khóa và mức độ tranh chấp có thể tăng quá mức.

**Điều mô hình B làm tốt:** thể hiện lịch hẹn như một khái niệm có identity, trạng thái và hành vi riêng.

**Điểm cần xem xét:** bất biến “không vượt sức chứa” nằm ở đâu và được bảo vệ nguyên tử như thế nào?

## 7. Mô hình ứng viên C: sức chứa và lượt giữ chỗ là khái niệm hạng nhất

Mô hình thứ ba bắt đầu từ câu hỏi nghiệp vụ: “Một khung thời gian có thể phục vụ bao nhiêu lượt đặt, và những lượt nào đang chiếm năng lực đó?”

Thay vì chỉ lưu BOOKED, mô hình có:

- CapacitySlot: khung thời gian với sức chứa và các lượt chiếm chỗ.
- Reservation: một lượt giữ chỗ hoặc đặt chỗ, có identity và vòng đời.
- PatientId: định danh bệnh nhân, không giữ toàn bộ Patient object.
- WaitlistEntry: mục trong danh sách chờ, nếu nghiệp vụ cần.

~~~text
CapacitySlot (Aggregate Root)
--------------------------------
slotId
providerId
timeRange
capacity
reservations

Reservation (Entity bên trong Aggregate)
--------------------------------
reservationId
patientId
status: HELD | CONFIRMED | RELEASED | EXPIRED
expiresAt
~~~

Aggregate Root chịu trách nhiệm bảo vệ bất biến:

~~~text
Số reservation đang chiếm chỗ <= capacity
~~~

Trong ví dụ đơn giản, một lượt HOLD chưa hết hạn và một lượt CONFIRMED đều chiếm một đơn vị sức chứa. RELEASED và EXPIRED không chiếm chỗ. Nếu nghiệp vụ có loại lịch cần nhiều đơn vị năng lực hoặc thời lượng khác nhau, mô hình có thể thay số lượng reservation bằng đơn vị năng lực tương ứng.

Các hành vi có thể là:

- hold(patientId, now, duration): tạo lượt giữ tạm nếu còn sức chứa.
- confirm(reservationId, now): xác nhận một lượt giữ còn hiệu lực.
- release(reservationId, reason): giải phóng sức chứa.
- expireHolds(now): chuyển các lượt giữ đã hết hạn sang EXPIRED.
- changeCapacity(newCapacity): chỉ chấp nhận thay đổi nếu không vi phạm quy tắc sức chứa.

Ở mô hình này, “giữ chỗ” không còn là một cờ phụ trên lịch hẹn. Nó là khái niệm có định danh, thời hạn và vòng đời. Điều đó giúp mô hình diễn đạt rõ hơn các tình huống chờ thanh toán, hết hạn và giải phóng chỗ.

## 8. Thử cùng bộ tình huống trên mô hình C

**Tình huống 1 — đặt lịch bình thường**

Aggregate nhận yêu cầu hold, tạo Reservation và sau khi các điều kiện cần thiết hoàn tất thì xác nhận. Nếu nghiệp vụ không cần bước giữ tạm, có thể có hành vi đặt trực tiếp. Mô hình không bắt buộc mọi quy trình phải dùng HOLD; nó chỉ cung cấp khái niệm khi nghiệp vụ cần.

**Tình huống 2 — hai bệnh nhân tranh chỗ cuối**

Hai request có thể cùng đọc sức chứa còn một. Khi append thay đổi, optimistic locking trên CapacitySlot hoặc conditional update bảo vệ việc tiêu thụ sức chứa. Chỉ một request được chấp nhận; request còn lại phải đọc lại và nhận kết quả hết chỗ nếu không còn năng lực.

**Tình huống 3 — lượt giữ chỗ hết hạn**

Reservation có expiresAt và trạng thái. Khi xác nhận, Aggregate kiểm tra thời điểm hiện tại so với thời hạn. Nếu đã hết hạn, lượt giữ chuyển thành EXPIRED và không được xác nhận. Một tiến trình nền có thể phát lệnh hết hạn để cập nhật trạng thái và phát event tương ứng.

**Tình huống 4 — hủy và danh sách chờ**

Hủy chuyển Reservation sang RELEASED, giải phóng năng lực. Hệ thống có thể phát ReservationReleased; một process manager hoặc thành phần điều phối danh sách chờ chọn người tiếp theo và gửi lời mời giữ chỗ. Lời mời không đồng nghĩa lịch đã xác nhận.

**Tình huống 5 — đổi lịch**

Đổi lịch liên quan hai CapacitySlot. Nếu khung giờ mới không còn chỗ, lịch cũ cần được giữ nguyên. Có thể giữ chỗ ở slot mới trước, sau đó giải phóng slot cũ. Nếu bước giải phóng thất bại, quy trình phải retry hoặc bù trừ lượt giữ mới theo quy tắc đã định. Đây là quy trình qua nhiều Aggregate, không nên giả định một lần gọi phương thức có thể cập nhật nguyên tử cả hai slot.

**Tình huống 6 — thay đổi sức chứa**

changeCapacity() kiểm tra số chỗ đang bị chiếm. Nếu sức chứa mới thấp hơn số lượt HOLD còn hiệu lực cộng số lượt CONFIRMED, Aggregate từ chối thay đổi hoặc tạo một quy trình điều chỉnh lịch riêng. Không được âm thầm xóa Reservation để phù hợp con số mới.

**Tình huống 7 — bệnh nhân không đến**

Lịch hẹn có thể được ghi nhận NO_SHOW. Tùy nghiệp vụ, sức chứa đã qua thời điểm khám không được coi là chỗ có thể bán lại. Reservation/Appointment lưu kết quả để báo cáo và áp dụng chính sách liên quan.

**Tình huống 8 — command gửi lặp**

Command có commandId hoặc idempotency key. Aggregate hoặc application layer nhận biết yêu cầu đã xử lý để không tạo hai Reservation. Consumer cũng cần deduplicate event nếu message được gửi lặp.

Mô hình C diễn đạt nhiều tình huống trực tiếp hơn, nhưng đi kèm chi phí: quản lý reservation lifecycle, concurrency, hết hạn, process manager và các projection. Nếu nghiệp vụ thực tế chỉ có một slot một booking, mô hình này có thể là quá mức cần thiết.

## 9. So sánh ba mô hình trên cùng tình huống

| Tình huống | A — Slot có trạng thái | B — Appointment có vòng đời | C — Capacity và Reservation |
| --- | --- | --- | --- |
| Đặt một chỗ còn trống | Tự nhiên | Tự nhiên | Tự nhiên |
| Hai người tranh chỗ cuối | Cần lock/version | Cần cơ chế sức chứa bên ngoài Appointment | Bất biến nằm ở CapacitySlot |
| Giữ tạm và hết hạn | Phải mở rộng trạng thái | Có thể mô hình trong Appointment | Reservation có lifecycle riêng |
| Hủy và mời danh sách chờ | Cần thêm cơ chế | Appointment phát event hủy | Release capacity rồi điều phối waitlist |
| Đổi lịch an toàn | Khó phối hợp hai slot | Hành vi rõ nhưng vẫn cần bảo vệ sức chứa | Giữ slot mới, sau đó giải phóng slot cũ |
| Giảm sức chứa | Khó nếu slot đã booked | Cần kiểm tra các Appointment liên quan | CapacitySlot bảo vệ số lượng đang chiếm |
| No-show | Cần thêm trạng thái | Rất tự nhiên | Kết hợp Reservation với kết quả Appointment |
| Chống gửi lặp | Cần idempotency | Cần idempotency | Có thể gắn command ID vào Reservation |

Không có một cột “thắng” cho mọi bài toán. Mô hình A có thể là lựa chọn tốt nhất cho sản phẩm nhỏ với sức chứa một. Mô hình B phù hợp khi vòng đời lịch hẹn là trung tâm và sức chứa được bảo vệ bằng một cơ chế riêng. Mô hình C hữu ích khi giữ chỗ, sức chứa, hết hạn và tranh chấp tài nguyên là phần cốt lõi của nghiệp vụ.

## 10. Đánh giá mô hình theo tiêu chí, không theo số lượng class

Sau khi mô phỏng, hãy so sánh các mô hình theo cùng một bộ tiêu chí:

| Tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| Ngôn ngữ nghiệp vụ | Chuyên gia có nhận ra và dùng được các khái niệm này không? |
| Khả năng diễn đạt | Quy tắc có thể viết thành hành vi rõ ràng hay phải giải thích bằng nhiều điều kiện rời rạc? |
| Quyền sở hữu bất biến | Có thể chỉ ra đối tượng/ranh giới nào bảo vệ từng bất biến không? |
| Vòng đời | Trạng thái và chuyển đổi có phản ánh đúng nghiệp vụ không? |
| Cạnh tranh | Hai request đồng thời có thể phá vỡ quy tắc không? |
| Thay đổi | Thêm quy tắc mới có làm nhiều phần không liên quan phải sửa không? |
| Tính nhất quán | Phần nào cần nhất quán ngay, phần nào có thể cập nhật trễ? |
| Độ phức tạp | Mô hình có thêm khái niệm thực sự cần thiết hay chỉ thêm abstraction? |
| Khả năng kiểm thử | Tình huống có thể được kiểm tra trực tiếp bằng hành vi và kết quả không? |

Có thể dùng bảng điểm định tính như Tốt, Chấp nhận được, Yếu, kèm lý do. Nếu dùng điểm số, hãy thống nhất trọng số với nghiệp vụ; không nên giả vờ rằng tổng điểm là kết quả khoa học chính xác.

## 11. Tìm bất biến trước khi chọn Aggregate Boundary

Một cách hữu ích để so sánh mô hình là liệt kê bất biến rồi hỏi mỗi mô hình bảo vệ chúng ở đâu.

Trong ví dụ đặt lịch:

1. Số lượt đang chiếm sức chứa không được vượt quá capacity.
2. Một Reservation chỉ được xác nhận nếu còn hiệu lực.
3. Một Reservation đã RELEASED hoặc EXPIRED không thể xác nhận lại.
4. Đổi lịch thất bại không được làm mất lịch cũ.
5. Một command lặp không tạo thêm lượt giữ chỗ.

Với mỗi bất biến, hỏi:

- Dữ liệu nào cần được đọc để kiểm tra?
- Dữ liệu nào cần được thay đổi cùng nhau?
- Có thể đặt quy tắc trong một Aggregate không?
- Nếu cần nhiều Aggregate, quy trình phối hợp và bù trừ là gì?
- Cơ chế persistence/concurrency nào bảo vệ thao tác ghi?

Aggregate Boundary nên được xác định theo bất biến và nhu cầu nhất quán nghiệp vụ, không chỉ theo quan hệ “có chứa” hoặc theo số bảng. Nếu một quy tắc cần nhiều Aggregate, hãy cân nhắc một mô hình sở hữu quy tắc phù hợp, thao tác nguyên tử ở persistence hoặc quy trình điều phối eventual consistency.

## 12. Mô hình sâu làm rõ các khái niệm ẩn

Một mô hình có thể ban đầu chỉ có Appointment với status. Khi trao đổi thêm, nhóm phát hiện:

- HOLD khác CONFIRMED vì HOLD có thời hạn.
- Reservation khác Appointment vì reservation chiếm năng lực, còn appointment có thông tin cuộc hẹn và kết quả khám.
- Capacity khác số lượng lịch đã tạo vì cần tính cả các lượt giữ tạm chưa hết hạn.
- Waitlist Entry khác Reservation vì người trong danh sách chờ chưa sở hữu chỗ.
- No-show là kết quả của lịch hẹn, không phải trạng thái giải phóng chỗ trong quá khứ.

Đây là dấu hiệu mô hình đang trở nên sâu hơn: nó tạo ra các khái niệm giúp giải thích quy tắc mà trước đó bị ẩn trong boolean, truy vấn hoặc điều kiện if.

Tuy nhiên, không phải mọi danh từ đều cần thành class. Một khái niệm chỉ nên được mô hình hóa riêng khi nó có ý nghĩa, identity, vòng đời, quy tắc hoặc vai trò riêng trong ngôn ngữ nghiệp vụ.

## 13. Mô phỏng bằng ví dụ và event timeline

Ngoài bảng trạng thái, có thể dùng timeline để kiểm tra một mô hình.

Ví dụ hai bệnh nhân tranh chỗ cuối:

~~~text
09:00:00  CapacitySlot còn 1 đơn vị
09:00:01  Request A yêu cầu HOLD
09:00:01  Request B yêu cầu HOLD
09:00:02  A append reservation với version 12 -> thành công
09:00:02  B append với expected version 12 -> conflict
09:00:03  B tải lại trạng thái: capacity đã hết
09:00:03  B nhận kết quả SLOT_FULL
~~~

Timeline giúp nhóm kiểm tra:

- Có thời điểm nào hai request cùng được coi là thành công không?
- Version được kiểm tra ở đâu?
- Request thất bại nhận kết quả gì?
- Có event nào được phát trước khi ghi thành công không?
- Khi retry, hệ thống có nạp lại trạng thái không?

Với mô hình khác, hãy viết timeline tương tự. Nếu nhóm không thể mô tả rõ một bước vì không biết đối tượng nào chịu trách nhiệm, đó là dấu hiệu mô hình chưa đủ rõ.

## 14. Dùng ngôn ngữ chung để đánh giá mô hình

Một mô hình sâu không chỉ giúp lập trình viên. Chuyên gia nghiệp vụ cần có thể dùng các thuật ngữ của mô hình để mô tả trường hợp thật.

Hãy thử hỏi:

- Chuyên gia có phân biệt được giữ chỗ với xác nhận lịch không?
- Họ có nói “giải phóng reservation” hay chỉ nói “đổi status về available”?
- Họ có phân biệt người trong danh sách chờ với người đã được giữ chỗ không?
- Họ có dùng cùng một nghĩa cho “hủy”, “hết hạn” và “không đến” không?
- Có thuật ngữ nào trong code khiến chuyên gia hiểu sai quy trình không?

Nếu mô hình yêu cầu chuyên gia liên tục dịch từ ngôn ngữ của họ sang tên kỹ thuật, mô hình có thể chưa phản ánh đúng cách họ suy nghĩ về nghiệp vụ. Có thể cần EventStorming, Example Mapping hoặc một buổi model storming để khám phá thêm.

## 15. Khi nào cần thử hai, ba hoặc nhiều mô hình?

Thường chỉ cần một số ít mô hình có khác biệt về cách tổ chức khái niệm hoặc quyền sở hữu quy tắc. Ba mô hình có chủ đích thường đủ để làm rõ lựa chọn.

Nên tạo mô hình thay thế khi:

- Có nhiều cách hợp lý để đặt Aggregate Boundary.
- Một quy tắc quan trọng chưa rõ ai sở hữu.
- Khái niệm trung tâm có vòng đời phức tạp.
- Mô hình hiện tại cần nhiều cờ và điều kiện để xử lý tình huống mới.
- Có xung đột giữa yêu cầu nghiệp vụ và cách lưu trữ hiện tại.
- Một thay đổi nhỏ buộc nhiều đối tượng hoặc context cùng cập nhật.

Không cần tạo hàng chục mô hình chỉ để chứng minh đã khám phá đủ. Khi các mô hình mới chỉ đổi tên class mà không thay đổi cách diễn đạt quy tắc, quan hệ hoặc ranh giới nhất quán, chúng không đem lại thêm hiểu biết.

## 16. Quy trình thử nhiều mô hình

Có thể thực hiện theo các bước sau:

1. **Chọn một phạm vi nghiệp vụ:** giữ câu hỏi đủ hẹp để nhóm có thể mô phỏng chi tiết, ví dụ đặt lịch theo khung giờ.
2. **Thu thập tình huống:** ghi luồng bình thường, ngoại lệ, ranh giới, cạnh tranh, thời gian và thay đổi.
3. **Rút ra quy tắc và bất biến:** viết rõ điều gì phải đúng và điều gì được phép xảy ra.
4. **Tạo mô hình ứng viên đầu tiên:** biểu diễn khái niệm, quan hệ, hành vi và ranh giới.
5. **Tạo một hoặc hai mô hình thay thế:** thay đổi cách tổ chức khái niệm hoặc quyền sở hữu bất biến, không chỉ đổi tên.
6. **Mô phỏng cùng bộ tình huống:** ghi lại từng bước, trạng thái, kết quả và event trong từng mô hình.
7. **Tìm điểm gãy:** xem tình huống nào buộc mô hình phải thêm cờ, truy vấn vòng, sửa nhiều Aggregate hoặc dựa vào giả định ẩn.
8. **So sánh theo tiêu chí:** ngôn ngữ, hành vi, bất biến, concurrency, thay đổi, consistency và chi phí.
9. **Xác nhận với chuyên gia:** kiểm tra thuật ngữ và quy tắc bằng ví dụ thực tế.
10. **Chọn và ghi lại quyết định:** nêu mô hình được chọn, trade-off và lý do loại các lựa chọn khác.
11. **Kiểm chứng trong code:** viết test theo tình huống; chỉ prototype phần có rủi ro kỹ thuật hoặc nghiệp vụ chưa rõ.
12. **Tiếp tục học:** khi có tình huống mới làm lộ giả định sai, quay lại khám phá và điều chỉnh mô hình.

## 17. Dùng test tình huống như ví dụ thực thi

Sau khi chọn mô hình, các tình huống có thể trở thành acceptance test hoặc domain test. Điều này giúp mô hình không chỉ tồn tại trong sơ đồ.

Ví dụ bảng test:

| Given | When | Then |
| --- | --- | --- |
| Khung giờ còn một chỗ | Hai request giữ chỗ đồng thời | Chỉ một reservation được chấp nhận |
| Reservation còn hiệu lực | Bệnh nhân xác nhận | Reservation chuyển sang CONFIRMED |
| Reservation đã hết hạn | Bệnh nhân xác nhận | Không được xác nhận, chỗ có thể được cấp cho người khác |
| Lịch cũ đã xác nhận | Đổi sang khung giờ mới đã đầy | Lịch cũ vẫn còn hiệu lực |
| Reservation đã giải phóng | Consumer nhận lại event hủy | Không giải phóng thêm lần nữa |
| Capacity đang có 5 lượt chiếm chỗ | Giảm capacity xuống 4 | Thay đổi bị từ chối hoặc chuyển sang quy trình điều chỉnh |

Test không thay thế việc trao đổi với chuyên gia. Chúng là cách lưu lại ví dụ đã được xác nhận để kiểm tra mô hình và code theo thời gian.

## 18. Những lỗi thường gặp khi thử mô hình

**Chỉ thử luồng thành công.** Các mô hình thường giống nhau ở trường hợp đơn giản. Hãy thêm tranh chấp, hết hạn, hủy, thay đổi và phục hồi.

**Thay tên class nhưng giữ nguyên tư duy.** Đổi Slot thành BookingSlot không tạo ra mô hình mới nếu quyền sở hữu quy tắc và hành vi vẫn như cũ. Mô hình thay thế cần khác ở cách giải thích nghiệp vụ.

**Chọn mô hình dựa trên database hiện tại.** Schema có thể là kết quả của thiết kế cũ hoặc giới hạn kỹ thuật. Bắt đầu từ quy tắc nghiệp vụ rồi mới chọn cách lưu.

**Đưa mọi thứ vào một Aggregate lớn.** Điều đó có thể làm một bất biến dễ bảo vệ nhưng tạo tranh chấp và giới hạn khả năng mở rộng. Hãy xem dữ liệu nào thực sự cần nhất quán cùng nhau.

**Chia Aggregate quá nhỏ mà không có cơ chế phối hợp.** Một quy tắc cần nhiều dữ liệu có thể bị phá vỡ nếu mỗi phần thay đổi độc lập. Phải xác định transaction, conditional update hoặc process manager.

**Dùng truy vấn để thay thế bất biến.** Kiểm tra “còn chỗ không?” trước khi insert không bảo vệ được hai request đồng thời. Cần cơ chế nguyên tử ở ranh giới ghi.

**Thêm abstraction trước khi hiểu nghiệp vụ.** Một interface hoặc generic rule engine không làm mô hình sâu hơn nếu không diễn đạt khái niệm thật.

**Bỏ qua chi phí vận hành.** Event, reservation, process manager và projection giúp diễn đạt quy trình nhưng cần retry, idempotency, giám sát và phục hồi.

**Không ghi lại giả định.** Khi giả định bị coi là sự thật, mô hình có thể được xây trên quy tắc chưa được chuyên gia xác nhận.

## 19. Ghi lại quyết định mô hình

Sau khi so sánh, nên ghi ngắn gọn:

- Tập tình huống đã dùng để đánh giá.
- Các mô hình ứng viên và khác biệt chính.
- Bất biến quan trọng và nơi mỗi mô hình bảo vệ.
- Mô hình được chọn và lý do.
- Trade-off được chấp nhận.
- Giả định còn chờ xác nhận.
- Tình huống nào sẽ khiến nhóm xem xét lại quyết định.

Ví dụ:

~~~text
Decision: Dùng CapacitySlot làm Aggregate Root cho sức chứa của một khung giờ.

Reason:
- Quy tắc không vượt capacity được bảo vệ tại một ranh giới.
- Reservation có vòng đời HOLD/CONFIRMED/RELEASED/EXPIRED.
- Đổi lịch có thể được điều phối qua hai reservation.

Trade-offs:
- Cần quản lý concurrency và expiry.
- Slot phổ biến có thể trở thành điểm nóng.
- Thông tin lâm sàng vẫn thuộc mô hình Appointment riêng.

Revisit when:
- Nghiệp vụ chuyển từ capacity cố định sang tài nguyên theo thời lượng/loại dịch vụ.
~~~

Đây không phải tài liệu kiến trúc dài. Nó giúp người đọc sau này hiểu vì sao mô hình có hình dạng hiện tại và điều gì có thể khiến quyết định thay đổi.

## 20. Checklist đánh giá mô hình ứng viên

- Cùng một bộ tình huống đã được dùng để thử mọi mô hình chưa?
- Bộ tình huống có luồng bình thường, ngoại lệ, cạnh tranh và thời gian không?
- Mỗi mô hình có khái niệm, hành vi và quan hệ rõ ràng không?
- Các bất biến có được chỉ định cho một chủ sở hữu cụ thể không?
- Có tình huống nào buộc phải sửa nhiều đối tượng mà không có ranh giới nhất quán không?
- Mô hình có diễn đạt được hết hạn, hủy, retry và bù trừ khi nghiệp vụ cần không?
- Chuyên gia nghiệp vụ có hiểu và sử dụng được thuật ngữ không?
- Mô hình có đang phản chiếu schema hoặc ORM thay vì nghiệp vụ không?
- Độ phức tạp bổ sung có mang lại khả năng diễn đạt hoặc bảo vệ quy tắc thực sự không?
- Các giả định và trade-off đã được ghi lại chưa?
- Có test tình huống để giữ lại ví dụ đã xác nhận không?

## 21. Nguyên tắc cần ghi nhớ

Thử nhiều mô hình là một kỹ thuật khám phá, không phải cuộc thi tìm thiết kế nhiều class nhất. Hãy giữ nguyên một tập tình huống nghiệp vụ, tạo một số mô hình có khác biệt thực sự về khái niệm, hành vi hoặc ranh giới, rồi mô phỏng từng tình huống trên từng mô hình.

Mô hình đáng chọn là mô hình dùng ngôn ngữ nghiệp vụ rõ, đặt bất biến ở nơi có thể bảo vệ, xử lý được các tình huống đã xác nhận và có độ phức tạp tương xứng với giá trị nó mang lại. Khi chuyên gia và đội phát triển cùng dùng được mô hình để giải thích trường hợp thật, mô hình đã trở thành công cụ suy nghĩ chung thay vì chỉ là cấu trúc code.
