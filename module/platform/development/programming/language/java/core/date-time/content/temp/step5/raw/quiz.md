Câu 1. Khi biểu diễn ngày sinh 15/04/2026 mà không kèm giờ hay múi giờ, kiểu `java.time` nào phù hợp?
A. `Instant` lưu ngày lịch nhưng không cần UTC timestamp.
B. `LocalTime` lưu ngày lịch nhưng bỏ thông tin giờ.
C. `LocalDate` lưu ngày lịch mà không kèm giờ hay zone.
D. `OffsetDateTime` lưu ngày lịch nhưng bỏ thông tin offset.
Đáp án đúng: C

Câu 2. `LocalTime.of(14, 30)` biểu diễn dữ liệu nào trong `java.time`?
A. Thời điểm 14:30 UTC với mốc epoch cố định.
B. Giờ 14:30 trong ngày, không kèm ngày hay zone.
C. Ngày hiện tại tại địa phương kèm giờ 14:30.
D. Giờ 14:30 gắn với offset mặc định của JVM.
Đáp án đúng: B

Câu 3. Muốn chuyển một `LocalDateTime` thành `Instant` xác định, thông tin nào cần bổ sung?
A. Ngày trong tuần vì LocalDateTime chưa có dữ liệu này.
B. Múi giờ hoặc UTC offset để quy đổi giờ địa phương.
C. Độ phân giải nanosecond của đồng hồ hệ điều hành.
D. Định dạng `DateTimeFormatter` dùng lúc tạo giá trị.
Đáp án đúng: B

Câu 4. Trong `java.time`, `Instant` chủ yếu dùng để đại diện thông tin nào?
A. Quy tắc chuyển giờ mùa hè của một múi giờ vùng.
B. Ngày theo lịch địa phương không kèm giờ phút.
C. Giờ đồng hồ của một thành phố không chứa ngày lịch.
D. Một thời điểm xác định trên dòng thời gian UTC.
Đáp án đúng: D

Câu 5. Khi cần xử lý thay đổi UTC offset theo lịch sử và DST của Paris, nên giữ thông tin nào?
A. `LocalDateTime.now()` để truy ra quy tắc vùng Paris.
B. `ZoneId.of("Europe/Paris")` để dùng các quy tắc vùng.
C. `ZoneOffset.of("+01:00")` để theo đổi mọi quy tắc mùa hè.
D. `Duration.ofHours(1)` để mô tả lịch sử offset của Paris.
Đáp án đúng: B

Câu 6. Điểm khác biệt hữu ích giữa `OffsetDateTime` và `ZonedDateTime` là gì?
A. `OffsetDateTime` chỉ có ngày lịch, không có giờ phút.
B. `ZonedDateTime` có zone vùng; `OffsetDateTime` có UTC offset.
C. `OffsetDateTime` có zone vùng; ZonedDateTime chỉ có offset.
D. `ZonedDateTime` không thể đổi thành Instant vì thiếu offset.
Đáp án đúng: B

Câu 7. Gọi `toInstant()` trên `ZonedDateTime` trả kết quả nào?
A. Instant của nửa đêm UTC theo ngày địa phương.
B. LocalDateTime giữ giờ phút và loại bỏ offset cũ.
C. ZoneOffset được đọc từ múi giờ mặc định của JVM.
D. Instant ứng với ngày giờ và offset của giá trị gốc.
Đáp án đúng: D

Câu 8. Trong chuỗi `2026-11-26T08:00:00Z` dùng với `Instant.parse`, hậu tố `Z` nói lên điều gì?
A. Giờ biểu diễn theo múi giờ của người dùng.
B. Giờ biểu diễn theo zone của máy đang chạy.
C. Giờ biểu diễn với UTC offset bằng không.
D. Giờ biểu diễn tại một region không có DST.
Đáp án đúng: C

Câu 9. Kết quả nào đúng với `LocalDate.of(2024, 2, 29)`?
A. Ném DateTimeException do tháng 2 chỉ có 28 ngày.
B. Tự chuyển giá trị sang ngày 01/03/2024.
C. Tạo được LocalDate vì năm 2024 là năm nhuận.
D. Tạo ngày 29/02/2025 vì điều chỉnh năm nhuận.
Đáp án đúng: C

Câu 10. Kết quả của `LocalDate.of(2025, 1, 31).plusMonths(1)` là ngày nào?
A. `2025-02-28`, ngày cuối tháng đích hợp lệ.
B. `2025-02-31`, vì API giữ nguyên ngày trong tháng.
C. `2025-03-01`, do tràn một ngày sau tháng 2.
D. `2025-03-03`, do cộng đủ 31 ngày vào tháng 1.
Đáp án đúng: A

Câu 11. Sau `LocalDate b = a.plusDays(1)`, trong đó `a` là LocalDate, nhận định nào đúng?
A. `a` được tăng một ngày và `b` dùng chung object.
B. `a` chỉ đổi khi JVM chạy garbage collection.
C. `a` không đổi; `b` tham chiếu giá trị ngày mới.
D. `b` chứa giờ hệ thống còn `a` giữ ngày cũ.
Đáp án đúng: C

Câu 12. Ở New York, ngày 08/03/2026 lúc 02:30 rơi vào DST gap; gọi `atZone` trên LocalDateTime đó thường cho gì?
A. 02:30 cùng ngày với offset `-05:00` dù DST gap.
B. 01:30 cùng ngày với offset `-05:00` khi lùi giờ.
C. 02:30 hôm sau với offset `-04:00` do DST gap.
D. 03:30 cùng ngày với offset `-04:00` vì DST gap.
Đáp án đúng: D

Câu 13. New York có giờ 01:30 lặp lại ngày 01/11/2026; `withLaterOffsetAtOverlap()` ưu tiên offset nào?
A. Offset `-05:00` ứng với lần xuất hiện 01:30 muộn hơn.
B. Offset `-06:00` do áp dụng hai lần chỉnh giờ mùa đông.
C. Offset `+00:00` do hai thời điểm cùng đổi về UTC.
D. Offset `-04:00` ứng với lần xuất hiện 01:30 sớm hơn.
Đáp án đúng: A

Câu 14. Khi đổi `ZonedDateTime` sang zone khác bằng `withZoneSameInstant`, yếu tố nào được giữ?
A. Giữ Instant, có thể đổi giờ địa phương.
B. Giữ giờ hiển thị và offset bất kể vùng mới.
C. Giữ LocalDateTime, có thể đổi Instant.
D. Giữ offset ban đầu và thay đổi zone vùng.
Đáp án đúng: A

Câu 15. Khi dùng `withZoneSameLocal` trên một `ZonedDateTime`, ý nghĩa chính là gì?
A. Giữ offset cũ dù vùng đích có quy tắc DST khác.
B. Giữ Instant và chuyển giờ địa phương theo zone mới.
C. Giữ ZoneId cũ và thay cách format thời gian.
D. Cố giữ giờ địa phương, resolve offset theo zone mới.
Đáp án đúng: D

Câu 16. Khi mô hình hóa khoảng 90 phút thực trôi qua, kiểu nào phù hợp hơn?
A. `LocalDate` vì lưu số phút giữa hai thời điểm tuyệt đối.
B. `Period` vì mô tả lượng thời gian theo năm/tháng/ngày.
C. `ZoneOffset` vì đo trực tiếp thời gian trôi giữa hai event.
D. `Duration` vì mô tả lượng thời gian dựa trên giây/nano.
Đáp án đúng: D

Câu 17. Giữa Instant `2026-01-01T00:00:00Z` và `2026-01-01T01:30:00Z`, `Duration.between` bằng gì?
A. `Duration.ofMinutes(30)` cho khoảng thời gian nửa giờ.
B. `Duration.ofMinutes(60)` cho khoảng thời gian một giờ.
C. `Duration.ofMinutes(90)` cho khoảng thời gian một giờ rưỡi.
D. `Duration.ofMinutes(150)` cho khoảng thời gian hai giờ rưỡi.
Đáp án đúng: C

Câu 18. `Period.between(2026-01-15, 2026-03-20)` theo ISO calendar cho giá trị nào?
A. `Period.of(0, 2, 5)` là hai tháng năm ngày.
B. `Period.of(0, 3, 5)` là ba tháng năm ngày.
C. `Period.of(0, 2, 4)` là hai tháng bốn ngày.
D. `Period.of(0, 1, 35)` là một tháng 35 ngày.
Đáp án đúng: A

Câu 19. Tại New York từ trưa 07/03/2026 qua DST bắt đầu, `plus(Period.ofDays(1))` khác `plus(Duration.ofDays(1))` thế nào?
A. Period cho 13:00; Duration cho 12:00 hôm sau.
B. Period và Duration đều cho 13:00 hôm sau.
C. Period và Duration đều cho 12:00 hôm sau.
D. Period cho 12:00; Duration cho 13:00 hôm sau.
Đáp án đúng: D

Câu 20. Giá trị của `ChronoUnit.DAYS.between(LocalDate.of(2026,3,1), LocalDate.of(2026,3,4))` là bao nhiêu?
A. Giá trị `2` vì chỉ tính ngày nằm ở giữa.
B. Giá trị `4` vì tính cả ngày đầu và ngày cuối.
C. Giá trị `72` vì phương thức trả về số giờ.
D. Giá trị `3` vì từ ngày 1 đến ngày 4 cách ba ngày.
Đáp án đúng: D

Câu 21. Trong `DateTimeFormatter` pattern, `MM` khác `mm` ở điểm nào?
A. `MM` là phút, còn `mm` là tháng.
B. `MM` là tháng, còn `mm` là phút.
C. `MM` là múi giờ, còn `mm` là tháng.
D. `MM` là ngày, còn `mm` là giây.
Đáp án đúng: B

Câu 22. Điều nào đúng khi dùng chung `DateTimeFormatter` bất biến giữa nhiều thread?
A. Dùng chung được vì formatter bất biến và thread-safe.
B. Cần clone trước mỗi lần parse để phòng race condition.
C. Cần synchronized mỗi lần dùng vì formatter thay đổi state.
D. Cần tạo formatter mới cho từng thread mỗi khi format.
Đáp án đúng: A

Câu 23. Muốn parse chuỗi `26/11/2026` thành LocalDate, đoạn nào phù hợp?
A. `Instant.parse(s, DateTimeFormatter.ofPattern("dd/MM/uuuu"))`.
B. `LocalDate.parse(s, DateTimeFormatter.ofPattern("dd/MM/uuuu"))`.
C. `ZoneId.of(s, DateTimeFormatter.ofPattern("dd/MM/uuuu"))`.
D. `LocalTime.parse(s, DateTimeFormatter.ofPattern("dd/MM/uuuu"))`.
Đáp án đúng: B

Câu 24. Chuỗi `2026-11-26T15:00:00+07:00` cần parse cả thời gian và UTC offset; dùng gì?
A. Dùng `LocalDate.parse(...)` để lưu cả giờ phút và offset.
B. Dùng `LocalDateTime.parse(...)` để lưu UTC offset của chuỗi.
C. Dùng `OffsetDateTime.parse(...)` để đọc ngày giờ và offset.
D. Dùng `Instant.ofEpochMilli(...)` để parse ISO offset string.
Đáp án đúng: C

Câu 25. Khi `LocalDate.parse("2025-02-29")` với ISO default, điều gì xảy ra?
A. Trả `2025-02-28` do tự điều chỉnh về cuối tháng.
B. Trả null do default parser bỏ qua ngày không hợp lệ.
C. Ném `DateTimeParseException` vì 2025 không nhuận.
D. Trả `2025-03-01` do tự chuyển sang tháng sau.
Đáp án đúng: C

Câu 26. Muốn kiểm thử mã gọi `LocalDate.now(clock)` không phụ thuộc thời gian thật, nên tạo Clock nào?
A. `Clock.fixed(instant, zone)` tạo đồng hồ ổn định cho test.
B. `Clock.systemDefaultZone()` cố định giờ khi test chạy.
C. `Clock.offset(clock, duration)` tạo đồng hồ ngừng chạy.
D. `Clock.tickSeconds(zone)` cố định giờ từ lần đọc đầu.
Đáp án đúng: A

Câu 27. Khi dùng `ZoneId.systemDefault()` để tạo lịch hẹn tại server, rủi ro gì cần chú ý?
A. Zone mặc định là zone của user HTTP hiện tại.
B. Zone mặc định tùy cấu hình từng máy và môi trường chạy.
C. Zone được suy ra từ request nên không thể thay đổi.
D. Zone mặc định luôn là UTC dù máy có zone riêng.
Đáp án đúng: B

Câu 28. Đâu là kết quả của `Instant.ofEpochMilli(1000)`?
A. `1970-01-02T00:00:00Z` vì 1000 ms là 1 ngày.
B. `1970-01-01T00:00:01Z` vì 1000 ms bằng một giây.
C. `1970-01-01T00:16:40Z` vì 1000 ms là 1000 giây.
D. `1970-01-01T00:00:00Z` vì milli bị loại khi parse.
Đáp án đúng: B

Câu 29. Hai bản ghi lưu cùng sự kiện theo hai zone khác nhau; cách nào so sánh thứ tự thời gian chính xác?
A. So sánh chuỗi giờ địa phương sau khi bỏ UTC offset.
B. So sánh LocalDateTime dù hai giá trị ở hai zone khác nhau.
C. So sánh Instant thay vì đồng hồ địa phương ở từng zone.
D. So sánh tên ZoneId vì thứ tự tên quyết định thời điểm.
Đáp án đúng: C

Câu 30. Khi lưu thời điểm giao dịch để hiển thị ở nhiều múi giờ, thiết kế nào hợp lý?
A. Lưu `LocalDateTime` theo zone của server rồi coi đó là UTC.
B. Lưu tên zone và bỏ mốc thời điểm tuyệt đối của giao dịch.
C. Lưu `LocalDate` rồi lấy giờ hệ thống khi người dùng xem.
D. Lưu `Instant`; giữ zone mong muốn riêng cho việc hiển thị.
Đáp án đúng: D

Câu 31. Khi chuyển từ `java.util.Date` cũ sang `java.time.Instant`, cách nào phù hợp?
A. Gọi `date.toInstant()` để giữ cùng mốc thời điểm.
B. Gọi `LocalDateTime.of(date)` để giữ cùng mốc thời điểm.
C. Gọi `Instant.ofEpochSecond(date.getTime())` để đổi mili-giây.
D. Gọi `date.toLocalDate()` để giữ cùng mốc thời điểm.
Đáp án đúng: A

Câu 32. Với `ZoneRules.getValidOffsets(localDateTime)` của một region, kết quả biểu thị điều gì?
A. Trả danh sách 0, 1 hoặc 2 offset cho gap, thường, overlap.
B. Trả một Instant cho mỗi offset hợp lệ trong ngày.
C. Trả các Duration để tính chênh lệch DST trong vùng.
D. Trả một offset dù local time rơi vào khoảng overlap.
Đáp án đúng: A
