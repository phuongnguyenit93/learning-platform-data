# Xác lập mục tiêu dịch vụ (SLO) và ngân sách độ trễ cho cơ sở dữ liệu

## Vì sao cơ sở dữ liệu cần SLO riêng?

Một cơ sở dữ liệu có thể vẫn hoạt động, vẫn chấp nhận kết nối và không phát sinh lỗi nghiêm trọng nhưng ứng dụng sử dụng nó đã chậm đến mức người dùng không thể tiếp tục công việc. Ngược lại, một truy vấn riêng lẻ có thể mất vài giây mà không ảnh hưởng đáng kể nếu đó là tác vụ báo cáo chạy ban đêm. Vì vậy, chỉ theo dõi CPU, dung lượng đĩa hoặc trạng thái tiến trình chưa đủ để đánh giá chất lượng dịch vụ.

Service Level Objective (SLO, mục tiêu mức dịch vụ) chuyển kỳ vọng về chất lượng thành một mục tiêu có thể đo lường trong một khoảng thời gian xác định. Với cơ sở dữ liệu, SLO thường mô tả tỷ lệ thao tác hoàn thành thành công, độ trễ của thao tác đọc hoặc ghi, và đôi khi cả mức độ sẵn sàng hay độ mới của dữ liệu. SLO giúp nhóm vận hành trả lời ba câu hỏi: thao tác nào quan trọng với người dùng, mức chậm nào có thể chấp nhận, và khi nào cần ưu tiên xử lý hiệu năng.

Ngân sách độ trễ (latency budget) là phần thời gian tối đa được phân bổ cho một thành phần trong tổng thời gian xử lý. Cơ sở dữ liệu thường chỉ là một chặng trong đường đi của yêu cầu: ứng dụng lấy kết nối, gửi lệnh, chờ khóa, thực thi kế hoạch truy vấn, nhận dữ liệu rồi tiếp tục xử lý. Nếu không dành ngân sách cụ thể cho chặng này, một truy vấn có thể tiêu thụ gần hết thời gian mà toàn bộ yêu cầu được phép sử dụng.

SLO và ngân sách độ trễ thuộc về quản lý hiệu năng dịch vụ. Chúng định hướng việc đo đạc, lựa chọn chỉ số, đọc kế hoạch thực thi, phân tích thống kê, cải thiện SQL và chỉ mục, nhận diện tranh chấp giao dịch, nút thắt I/O hoặc bộ nhớ, rồi kiểm chứng kết quả sau điều chỉnh.

## Phân biệt SLA, SLO và SLI

Ba thuật ngữ này có liên quan nhưng phục vụ các mục đích khác nhau:

| Thuật ngữ | Ý nghĩa | Ví dụ với cơ sở dữ liệu |
|---|---|---|
| SLI (Service Level Indicator) | Chỉ số phản ánh chất lượng thực tế | Tỷ lệ truy vấn đọc hoàn tất trong không quá 80 ms |
| SLO (Service Level Objective) | Mục tiêu cần đạt cho SLI trong một cửa sổ thời gian | Ít nhất 99% thao tác đọc đủ điều kiện hoàn tất trong 80 ms trong 28 ngày |
| SLA (Service Level Agreement) | Cam kết dịch vụ với khách hàng hoặc bên liên quan, thường kèm hệ quả khi vi phạm | Cam kết khả dụng theo hợp đồng và cơ chế bồi hoàn nếu không đạt |

SLO là mục tiêu vận hành nội bộ hoặc mục tiêu thống nhất giữa các nhóm. SLA là cam kết có tính ràng buộc với bên nhận dịch vụ. Không nên tự động coi mọi SLO là SLA.

Một SLI tốt phải có định nghĩa rõ ràng về sự kiện được đo, đơn vị, nguồn dữ liệu, phạm vi và cửa sổ thời gian. Chẳng hạn, “cơ sở dữ liệu phải nhanh” không phải SLI; “tỷ lệ yêu cầu đọc trực tuyến hoàn tất trong tối đa 80 ms, tính từ lúc tầng truy cập dữ liệu gửi lệnh đến khi nhận đủ kết quả” là một định nghĩa có thể triển khai.

## Chọn SLI phản ánh trải nghiệm thực tế

### Độ trễ

Độ trễ là thời gian một thao tác cần để hoàn tất. Không nên chỉ dùng thời gian trung bình (mean). Nếu 99 truy vấn mất 10 ms và một truy vấn mất 2 giây, trung bình có thể vẫn trông khá tốt trong khi một người dùng thực tế phải chờ rất lâu. Hãy quan sát phân phối độ trễ, đặc biệt là các phân vị:

- p50 là độ trễ mà một nửa số thao tác hoàn tất trong khoảng thời gian đó.
- p95 là ngưỡng mà 95% thao tác hoàn tất không vượt quá.
- p99 giúp phát hiện phần đuôi chậm, thường liên quan đến tranh chấp, truy vấn lệch dữ liệu, I/O hoặc hàng đợi.

Phân vị phải được tính từ histogram hoặc dữ liệu quan sát đủ chi tiết. Không lấy trung bình các giá trị p95 của từng máy chủ để suy ra p95 toàn cụm; cách tổng hợp đó không phản ánh đúng phân phối. Với histogram, có thể gộp các bucket rồi tính phân vị trên dữ liệu đã gộp.

Để kiểm tra một SLO dạng “99% thao tác không quá 80 ms”, hãy đo trực tiếp tỷ lệ sự kiện nằm trong ngưỡng. p95 hữu ích cho bảng điều khiển và chẩn đoán, nhưng p95 một mình không chứng minh được mục tiêu 99%.

### Tỷ lệ thành công và khả dụng

Một thao tác trả về kết quả đúng trong thời gian cho phép được xem là tốt. Lỗi kết nối, lỗi thực thi, bị hủy do timeout hoặc không thể lấy kết nối từ pool thường phải được tính là sự kiện không tốt nếu chúng ảnh hưởng đến yêu cầu của người dùng. Không loại các timeout ra khỏi mẫu số chỉ vì chúng không có thời gian hoàn tất; làm vậy sẽ khiến chỉ số trông tốt giả tạo.

Có thể định nghĩa riêng hai SLI:

1. **Tỷ lệ thành công:** số thao tác hoàn tất thành công chia cho tổng số thao tác đủ điều kiện.
2. **Tỷ lệ đáp ứng độ trễ:** số thao tác hoàn tất trong ngưỡng đã chọn chia cho tổng số thao tác đủ điều kiện.

Hoặc định nghĩa một sự kiện “tốt” kết hợp cả hai điều kiện: thao tác phải thành công và hoàn tất dưới ngưỡng. Dù chọn cách nào, cần ghi rõ timeout, hủy chủ động, retry và lỗi từ ứng dụng được tính như thế nào để các nhóm không diễn giải khác nhau.

### Chỉ số bổ trợ để giải thích nguyên nhân

Các chỉ số sau thường không nên thay thế SLI trải nghiệm người dùng, nhưng giúp giải thích vì sao SLO bị vi phạm:

- Thời gian chờ lấy kết nối từ connection pool và số kết nối đang chờ.
- Thời gian chờ khóa, deadlock, số giao dịch đang mở và thời lượng giao dịch.
- Thời gian thực thi SQL, số hàng đọc/trả về, số lần quét bảng và số lần đọc trang từ đĩa.
- IOPS, throughput, độ trễ đọc/ghi của thiết bị lưu trữ và hàng đợi I/O.
- Bộ nhớ làm việc, tỷ lệ cache hit, áp lực bộ nhớ và hoạt động spill ra đĩa.
- CPU, số phiên hoạt động, hàng đợi, số lần retry và tỷ lệ timeout.

CPU thấp không có nghĩa cơ sở dữ liệu không nghẽn: phiên làm việc có thể đang chờ khóa hoặc chờ I/O. Cache hit cao cũng không chứng minh mọi truy vấn đều nhanh. Luôn kết hợp các chỉ số với loại thao tác và dấu thời gian của yêu cầu.

## Xác định phạm vi SLO

Không nên gộp mọi truy vấn vào một SLO duy nhất. Truy vấn đọc phục vụ màn hình giao dịch, ghi đơn hàng, báo cáo tổng hợp và tác vụ bảo trì có yêu cầu khác nhau. Nếu gộp chúng, lượng truy vấn nhanh có thể che khuất một nhóm truy vấn quan trọng đang chậm.

Hãy phân nhóm theo đặc tính và mức độ quan trọng, ví dụ:

| Nhóm tải | Ví dụ | SLI phù hợp |
|---|---|---|
| Đọc tương tác | Tra cứu hồ sơ, xem danh sách, kiểm tra trạng thái | Tỷ lệ đọc hoàn tất dưới ngưỡng; p95/p99 |
| Ghi giao dịch | Tạo đơn, cập nhật số dư, xác nhận thanh toán | Tỷ lệ ghi thành công và độ trễ commit |
| Truy vấn nền | Đồng bộ, xử lý hàng đợi, tổng hợp dữ liệu | Thời gian hoàn thành, throughput, độ trễ hàng đợi |
| Báo cáo phân tích | Báo cáo theo ngày hoặc truy vấn nhiều bảng | Thời gian hoàn thành theo lớp ưu tiên, tác động lên tải trực tuyến |

Phạm vi SLO cần nêu rõ cụm hoặc dịch vụ, loại thao tác, tenant hoặc phân vùng nếu có, điểm bắt đầu và kết thúc phép đo, cửa sổ đánh giá, cùng các trường hợp được loại trừ. Chỉ loại những sự kiện thực sự nằm ngoài trách nhiệm của dịch vụ và đã được thống nhất trước; không thay đổi quy tắc loại trừ sau khi xảy ra sự cố.

Đặc biệt, phân biệt **độ trễ phía máy chủ cơ sở dữ liệu** với **độ trễ mà ứng dụng quan sát**. Thời gian phía ứng dụng có thể bao gồm chờ pool, mạng, driver, gửi câu lệnh, chờ khóa, thực thi, truyền kết quả và giải mã dữ liệu. SLO của cơ sở dữ liệu có thể theo dõi thời gian thực thi tại máy chủ, nhưng ngân sách cho lời gọi dữ liệu trong ứng dụng phải tính cả các khoảng chờ thuộc đường đi đó.

## Thiết lập mục tiêu có căn cứ

Một mục tiêu có ích phải đủ tham vọng để thúc đẩy cải thiện nhưng cũng phải dựa trên nhu cầu thực tế và khả năng vận hành. Có thể xây dựng mục tiêu theo quy trình sau:

1. **Xác định trải nghiệm cần bảo vệ.** Tìm các thao tác mà độ trễ ảnh hưởng trực tiếp đến thời gian phản hồi của màn hình, giao dịch hoặc API.
2. **Đo hiện trạng.** Thu thập dữ liệu đại diện cho giờ cao điểm, cuối ngày, chu kỳ chốt sổ và các đợt tăng tải. Theo dõi ít nhất một chu kỳ tải có ý nghĩa; nếu hệ thống có tính mùa vụ, cần quan sát đủ để không bỏ sót.
3. **Chọn ngưỡng có ý nghĩa.** Dựa vào thời gian phản hồi toàn hệ thống, kỳ vọng người dùng, giới hạn timeout và yêu cầu nghiệp vụ. Không chọn ngưỡng chỉ vì đó là con số hiện tại dễ đạt.
4. **Chọn tỷ lệ mục tiêu và cửa sổ.** Ví dụ 99% trong 28 ngày hoặc 99,9% trong 30 ngày. Cửa sổ dài giúp đánh giá ổn định; cửa sổ ngắn hỗ trợ phát hiện thay đổi gần đây.
5. **Kiểm tra khả năng đạt được.** Đối chiếu với phân phối hiện tại, tải dự kiến, mức dự phòng, giới hạn phần cứng và chi phí cải thiện.
6. **Thống nhất cách đo và chủ sở hữu.** Ghi rõ nguồn telemetry, truy vấn tính SLI, người chịu trách nhiệm và cách xử lý khi ngân sách bị tiêu thụ nhanh.

Ví dụ mục tiêu khởi đầu cho một hệ thống giao dịch có thể là:

- Đọc tương tác: ít nhất 99% thao tác đọc thành công trong tối đa 80 ms trong cửa sổ 28 ngày.
- Ghi giao dịch: ít nhất 99% thao tác ghi commit thành công trong tối đa 150 ms trong cửa sổ 28 ngày.
- Khả dụng: ít nhất 99,95% yêu cầu đủ điều kiện nhận được phản hồi thành công trong timeout đã quy định.

Đây chỉ là ví dụ để minh họa cách diễn đạt. Ngưỡng 80 ms, 150 ms và tỷ lệ mục tiêu không phải chuẩn chung cho mọi hệ quản trị hoặc mọi ứng dụng. Cần hiệu chỉnh theo workload, vị trí triển khai, độ lớn dữ liệu và kỳ vọng dịch vụ.

## Phân bổ ngân sách độ trễ

### Từ mục tiêu API đến phần dành cho cơ sở dữ liệu

Giả sử một API cần phản hồi trong 400 ms ở phân vị p95. Nhóm có thể lập ngân sách kỹ thuật cho đường đi xử lý như sau:

| Thành phần trên đường đi | Ngân sách minh họa |
|---|---:|
| Xử lý trong ứng dụng | 90 ms |
| Lời gọi cơ sở dữ liệu | 180 ms |
| Dịch vụ phụ thuộc khác | 70 ms |
| Dự phòng cho biến động và phần chưa phân loại | 60 ms |
| **Tổng** | **400 ms** |

Trong 180 ms dành cho lời gọi cơ sở dữ liệu, nhóm có thể phân tích tiếp:

| Thành phần của lời gọi dữ liệu | Ngân sách minh họa |
|---|---:|
| Chờ connection pool | 20 ms |
| Mạng và driver | 15 ms |
| Chờ khóa hoặc chờ giao dịch | 25 ms |
| Thực thi câu lệnh | 100 ms |
| Truyền và đọc kết quả | 20 ms |
| **Tổng** | **180 ms** |

Các con số trên là ngân sách thiết kế để điều phối công việc, không phải phép chứng minh thống kê rằng p95 của từng chặng cộng lại chính xác bằng p95 toàn API. Phân vị của tổng thời gian phụ thuộc vào phân phối và tương quan giữa các chặng; p95 của từng thành phần không thể cộng cơ học để suy ra p95 của toàn bộ yêu cầu. Hãy đo cả thời gian end-to-end và từng span thành phần, sau đó kiểm tra bằng tải thực tế.

Ngân sách cần có phần dự phòng. Nếu mọi thành phần đều được phép sử dụng hết phần phân bổ trong mọi tình huống, một đợt tăng tải nhỏ có thể làm toàn hệ thống vượt mục tiêu. Dự phòng cũng giúp hấp thụ biến động mạng, lịch chạy tác vụ nền và thay đổi phân bố dữ liệu.

### Đặt ngưỡng theo loại thao tác

Một truy vấn tra cứu khóa chính trả về một hàng có thể có ngân sách rất thấp. Một truy vấn tìm kiếm nhiều điều kiện, phân trang hoặc tổng hợp có thể cần ngưỡng khác. Không nên đặt một timeout chung quá rộng rồi xem đó là SLO.

Có thể quản lý một bảng ngân sách theo fingerprint truy vấn hoặc nhóm nghiệp vụ:

| Nhóm thao tác | Ngưỡng cần theo dõi | Câu hỏi chẩn đoán |
|---|---|---|
| Đọc theo khóa chính | Ngưỡng thấp, ổn định | Có dùng đúng chỉ mục và lấy đúng số hàng không? |
| Đọc danh sách có phân trang | Ngưỡng theo kích thước trang | Có quét hoặc sắp xếp quá nhiều hàng không? |
| Ghi một bản ghi | Ngưỡng commit | Có chờ khóa, constraint hoặc I/O đồng bộ không? |
| Cập nhật nhiều bản ghi | Ngưỡng theo kích thước lô | Giao dịch có giữ khóa quá lâu hoặc tạo tải ghi đột biến không? |
| Báo cáo tổng hợp | Mục tiêu hoàn thành theo lịch | Có cạnh tranh tài nguyên với tải tương tác không? |

Nếu một API gọi cơ sở dữ liệu nhiều lần tuần tự, tổng ngân sách DB của API phải bao quát tất cả các lời gọi trên đường đi. Nếu các lời gọi chạy song song, thời gian trên đường găng thường quyết định thời gian chờ, nhưng vẫn phải tính tải tổng hợp mà chúng tạo ra cho cơ sở dữ liệu.

### Timeout, retry và ngân sách

Timeout là giới hạn chờ của một thao tác; SLO là mục tiêu chất lượng trên một tập thao tác trong một khoảng thời gian. Timeout quá dài có thể giữ kết nối và tài nguyên trong lúc hệ thống đã quá tải. Timeout quá ngắn có thể hủy các thao tác hợp lệ khi tải tăng nhẹ.

Đặt timeout phù hợp với ngân sách của lời gọi và thời gian còn lại của yêu cầu cấp trên. Truyền deadline từ tầng API xuống tầng truy cập dữ liệu giúp tránh việc một truy vấn tiếp tục chạy sau khi người dùng đã hết thời gian chờ. Khi có retry, cần giới hạn số lần, dùng backoff có jitter khi thích hợp và bảo đảm thao tác có tính lặp an toàn. Retry không được làm tăng tải đến mức tạo vòng lặp quá tải; một lần thử lại cũng tiêu thụ ngân sách độ trễ của yêu cầu ban đầu.

## Đo lường và triển khai SLI

### Ghi nhận histogram và phân nhóm có kiểm soát

Nên ghi histogram độ trễ theo loại thao tác hoặc nhóm truy vấn đã chuẩn hóa. Tránh gắn nhãn bằng câu SQL nguyên văn, giá trị tham số, mã người dùng hoặc ID giao dịch: các nhãn có cardinality cao làm tăng chi phí giám sát và có thể làm lộ dữ liệu nhạy cảm. Có thể dùng query fingerprint, operation name hoặc nhóm nghiệp vụ đã được kiểm soát.

Ví dụ dưới đây minh họa cách tính tỷ lệ thao tác đọc hoàn tất trong tối đa 80 ms từ histogram Prometheus. Tên metric và nhãn cần được điều chỉnh theo hệ thống thực tế:

```promql
sum(rate(db_operation_duration_seconds_bucket{
  workload="interactive_read",
  le="0.08"
}[5m]))
/
sum(rate(db_operation_duration_seconds_count{
  workload="interactive_read"
}[5m]))
```

Giá trị kết quả là tỷ lệ thao tác nằm trong bucket không quá 0,08 giây trong khoảng lấy mẫu. Để đánh giá SLO 28 ngày, cần tính tỷ lệ trên tổng số sự kiện của cửa sổ tương ứng hoặc dùng hệ thống lưu trữ và truy vấn hỗ trợ cửa sổ dài; không lấy trung bình đơn giản của các tỷ lệ 5 phút nếu lưu lượng giữa các khoảng khác nhau đáng kể.

Để quan sát p95, có thể dùng:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(db_operation_duration_seconds_bucket{
      workload="interactive_read"
    }[5m])
  )
)
```

Metric `_count` phải đếm cùng tập thao tác đủ điều kiện với histogram. Nếu timeout hoặc lỗi không được ghi vào histogram thời lượng, hãy ghi nhận chúng riêng và bảo đảm phép tính SLI đưa chúng vào mẫu số theo quy tắc đã công bố. Với một SLI kết hợp thành công và độ trễ, tử số chỉ gồm thao tác vừa thành công vừa nằm trong ngưỡng.

### Kết hợp số liệu ứng dụng và cơ sở dữ liệu

Telemetry ở ứng dụng cho biết người dùng đã chờ bao lâu. Trace phân tán có thể tách thời gian chờ pool, lời gọi SQL và các dịch vụ phụ thuộc. Số liệu ở máy chủ cơ sở dữ liệu giúp xác định thời gian thực thi, chờ khóa, I/O, cache và mức sử dụng tài nguyên. Kết hợp các nguồn này giúp xác định phần ngân sách bị tiêu thụ ở đâu.

Với mỗi nhóm thao tác quan trọng, nên có tối thiểu:

- Tổng số thao tác và số thao tác thành công, timeout, lỗi.
- Histogram độ trễ, tỷ lệ trong ngưỡng, p50, p95 và p99.
- Thời gian chờ pool, thời gian chờ khóa và thời gian thực thi nếu có thể đo riêng.
- Lưu lượng, số hàng đọc/trả về và fingerprint của các truy vấn tiêu thụ nhiều thời gian.
- Mốc triển khai, thay đổi cấu hình, thay đổi schema và các đợt chạy tác vụ nền.

Không cần lưu toàn bộ câu SQL có tham số cho mọi truy vấn. Ưu tiên số liệu tổng hợp, fingerprint và trace được lấy mẫu có kiểm soát; bảo vệ thông tin xác thực và dữ liệu nghiệp vụ trong log.

## Ngân sách lỗi và cảnh báo

Nếu SLO yêu cầu 99% sự kiện tốt trong 28 ngày, phần còn lại 1% là ngân sách lỗi. Với 1.000.000 thao tác đủ điều kiện trong cửa sổ đó, ngân sách tương ứng là 10.000 thao tác không đạt tiêu chí. Nếu SLO là 99,9%, ngân sách chỉ còn 1.000 thao tác. Ngân sách lỗi giúp nhóm định lượng mức độ rủi ro và quyết định có nên tiếp tục phát hành thay đổi hay dành thời gian cho độ tin cậy.

Tỷ lệ tiêu thụ ngân sách quan trọng hơn một cảnh báo đơn lẻ. Một vài phút chậm bất thường có thể chưa làm SLO tháng bị vi phạm, nhưng nếu tốc độ tiêu thụ ngân sách cao hơn nhiều so với tốc độ cho phép, nhóm cần điều tra sớm. Có thể cảnh báo theo burn rate trên nhiều cửa sổ: cửa sổ ngắn phát hiện sự cố nghiêm trọng đang diễn ra, cửa sổ dài tránh phản ứng quá mức với dao động ngắn.

Ví dụ, nếu SLO 99% cho phép 1% sự kiện xấu, burn rate 5 nghĩa là tốc độ phát sinh sự kiện xấu đang gấp 5 lần tốc độ trung bình tương ứng với ngân sách. Cần chọn ngưỡng và thời lượng cảnh báo theo lưu lượng, mức độ quan trọng và khả năng phản ứng của đội vận hành. Với lưu lượng thấp, một vài lỗi có thể làm tỷ lệ dao động mạnh; hãy xem cả số lượng tuyệt đối và tỷ lệ.

Khi ngân sách lỗi gần cạn, nhóm có thể hoãn thay đổi rủi ro cao, giảm tải tác vụ nền, giới hạn truy vấn tốn tài nguyên hoặc ưu tiên xử lý nguyên nhân gốc. Khi ngân sách còn dồi dào, nhóm có thể dành một phần cho thay đổi có kiểm soát nhằm cải thiện chức năng hoặc hiệu năng. Quyết định cần dựa trên mức ảnh hưởng thực tế, không chỉ một màu trên dashboard.

## Dùng SLO để điều tra và cải thiện hiệu năng

Khi một SLI vượt ngưỡng, hãy xác định nhóm thao tác, khoảng thời gian và thành phần ngân sách bị tiêu thụ trước khi thay đổi cấu hình.

1. **Kiểm tra phạm vi ảnh hưởng.** Xác định thao tác đọc hay ghi, toàn cụm hay một node, tất cả tenant hay một nhóm dữ liệu, giờ cao điểm hay liên tục.
2. **Tách thời gian chờ.** So sánh thời gian chờ pool, mạng, khóa, thực thi và truyền kết quả. Nếu chờ pool cao, tăng số kết nối một cách mù quáng có thể làm cơ sở dữ liệu quá tải hơn.
3. **Tìm truy vấn đóng góp lớn.** Dùng thống kê theo fingerprint để tìm truy vấn có tổng thời gian tiêu thụ cao, tần suất lớn hoặc độ trễ bất thường. Tổng thời gian cao có thể do truy vấn chạy nhiều lần; độ trễ cao trên mỗi lần có thể do kế hoạch hoặc dữ liệu.
4. **Đọc kế hoạch thực thi.** Kiểm tra kiểu scan, thứ tự join, ước lượng số hàng, sort, spill và việc sử dụng chỉ mục. Dùng thống kê phù hợp để phát hiện ước lượng sai. Khi chạy `EXPLAIN ANALYZE`, nhớ rằng truy vấn thực sự được thực thi; đặc biệt cẩn trọng với câu lệnh ghi hoặc truy vấn có tác dụng phụ.
5. **Kiểm tra tranh chấp và tài nguyên.** Đối chiếu lock wait, deadlock, thời lượng giao dịch, I/O latency, cache miss, áp lực bộ nhớ và CPU. Một truy vấn có kế hoạch tốt vẫn có thể chậm khi phải chờ giao dịch khác hoặc thiết bị lưu trữ.
6. **Thay đổi có giả thuyết.** Chỉ rõ dự kiến thay đổi nào sẽ giảm phần thời gian nào, chẳng hạn thêm chỉ mục phù hợp để giảm số hàng đọc, sửa điều kiện SQL để tránh quét rộng, rút ngắn thời gian giữ khóa hoặc tách tác vụ báo cáo khỏi tải tương tác.
7. **Đo lại trong điều kiện tương đương.** So sánh cùng nhóm thao tác, cùng ngưỡng, lưu lượng và khoảng thời gian đại diện. Theo dõi cả p95/p99, tỷ lệ trong ngưỡng, lỗi, CPU, I/O, bộ nhớ và tác động đến ghi. Một chỉ số cải thiện không được đánh đổi bằng sự suy giảm lớn ở chỉ số khác.

SLO cho biết dịch vụ có đạt kỳ vọng hay không; nó không tự chỉ ra nguyên nhân. Muốn sửa đúng, cần nối kết mục tiêu với thống kê truy vấn, kế hoạch thực thi, cơ chế truy cập dữ liệu và trạng thái tài nguyên tại đúng thời điểm xảy ra vấn đề.

## Ví dụ xuyên suốt: API tra cứu đơn hàng

Một API tra cứu đơn hàng có mục tiêu phản hồi p95 không quá 400 ms. Qua trace, nhóm nhận thấy p95 lời gọi cơ sở dữ liệu đã tăng từ 90 ms lên 230 ms, trong khi thời gian ứng dụng và dịch vụ khác gần như ổn định. SLO đọc tương tác yêu cầu 99% thao tác hoàn tất trong 80 ms ở tầng dữ liệu, nên nhóm bắt đầu tiêu thụ ngân sách.

Nhóm kiểm tra histogram theo fingerprint và phát hiện một truy vấn danh sách đơn hàng có độ trễ p99 tăng mạnh. Kế hoạch thực thi cho thấy truy vấn quét nhiều hàng rồi sắp xếp trước khi trả về một trang nhỏ. Thống kê số hàng ước lượng khác xa số hàng thực tế. Nhóm kiểm tra điều kiện lọc và thứ tự sắp xếp, điều chỉnh chỉ mục ghép theo mẫu truy vấn, sau đó cập nhật thống kê nếu hệ quản trị cần.

Sau thay đổi, nhóm chạy lại tải đại diện và quan sát:

| Chỉ số | Trước điều chỉnh | Sau điều chỉnh |
|---|---:|---:|
| p50 lời gọi dữ liệu | 35 ms | 22 ms |
| p95 lời gọi dữ liệu | 230 ms | 68 ms |
| p99 lời gọi dữ liệu | 620 ms | 145 ms |
| Tỷ lệ thao tác trong 80 ms | 94,2% | 99,3% |
| CPU trung bình | 48% | 51% |

Các số liệu trên chỉ minh họa cách đánh giá. Nhóm cần tiếp tục kiểm tra thời gian ghi, chi phí duy trì chỉ mục, dung lượng lưu trữ, độ trễ trên giờ cao điểm và ảnh hưởng đến các truy vấn khác. Chỉ khi SLI được đo trên cửa sổ đủ đại diện và các tác động phụ vẫn trong giới hạn, thay đổi mới được xem là đã cải thiện dịch vụ một cách đáng tin cậy.

## Những sai lầm thường gặp

- **Chỉ nhìn thời gian trung bình:** che khuất phần đuôi chậm và các thao tác quan trọng bị ảnh hưởng.
- **Dùng một mục tiêu cho mọi workload:** làm truy vấn nhanh che khuất truy vấn chậm hoặc khiến tác vụ nền bị đánh giá thiếu công bằng.
- **Đo riêng máy chủ mà bỏ qua ứng dụng:** bỏ sót thời gian chờ pool, mạng, driver và truyền dữ liệu.
- **Loại timeout khỏi mẫu số:** tạo ra SLI tốt giả tạo đúng lúc dịch vụ gặp vấn đề.
- **Cộng các p95 của từng chặng:** tạo ra một kết quả thống kê không có cơ sở; hãy đo end-to-end và dùng ngân sách thành phần như công cụ thiết kế.
- **Đặt timeout bằng SLO:** nhầm giới hạn của một lần gọi với mục tiêu tỷ lệ trên toàn bộ tập sự kiện.
- **Tối ưu một truy vấn mà không kiểm tra tải tổng thể:** chỉ mục mới, retry hoặc tăng pool có thể cải thiện một nhóm nhưng làm tăng chi phí ghi, I/O hoặc tranh chấp ở nhóm khác.
- **Không đo lại sau thay đổi:** khiến nhóm không biết cải thiện có thật, có bền vững và có làm phát sinh hồi quy hay không.

## Checklist thiết lập SLO cho cơ sở dữ liệu

- [ ] Xác định thao tác và nhóm tải quan trọng với người dùng.
- [ ] Định nghĩa SLI, điểm bắt đầu/kết thúc, mẫu số và cách tính timeout/lỗi.
- [ ] Thu thập histogram và lưu lượng trong điều kiện đại diện.
- [ ] Chọn ngưỡng độ trễ, tỷ lệ mục tiêu và cửa sổ đánh giá có căn cứ.
- [ ] Phân bổ ngân sách cho pool, mạng, chờ khóa, thực thi và truyền kết quả.
- [ ] Thiết lập timeout/deadline và chính sách retry phù hợp với ngân sách.
- [ ] Theo dõi ngân sách lỗi, burn rate và các chỉ số giải thích nguyên nhân.
- [ ] Gắn SLI với thống kê truy vấn, kế hoạch thực thi, I/O, bộ nhớ và tranh chấp giao dịch.
- [ ] Đo lại sau mỗi thay đổi và kiểm tra tác động lên các nhóm tải khác.

Một SLO tốt tạo ra ngôn ngữ chung giữa phát triển, quản trị cơ sở dữ liệu và vận hành. Khi mục tiêu, cách đo và ngân sách độ trễ được thống nhất, nhóm có thể ưu tiên tối ưu dựa trên tác động đến dịch vụ, kiểm chứng kết quả bằng số liệu và phát hiện sớm khi hiệu năng bắt đầu lệch khỏi kỳ vọng.