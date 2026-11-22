# Đồng hồ UTC, sai lệch thời gian và khoảng dung sai khi xác minh JWT

## 1. Vì sao xác minh JWT phụ thuộc vào đồng hồ?

JWT thường mang các claim thời gian như `iat` (thời điểm phát hành), `nbf` (thời điểm bắt đầu có hiệu lực) và `exp` (thời điểm hết hạn). Bên nhận so sánh những mốc này với thời gian hiện tại để quyết định token đã có hiệu lực, còn mới hay đã hết hạn.

Phép kiểm tra chỉ đáng tin khi **đồng hồ của bên phát hành và các bên xác minh có thời gian đủ gần nhau**. Nếu đồng hồ lệch, một token hợp lệ có thể bị từ chối quá sớm; ngược lại, token đã đến hạn có thể tiếp tục được chấp nhận.

Ví dụ, authorization server phát hành token với `exp` lúc 12:00 UTC. Nếu đồng hồ của một API chạy nhanh hơn 90 giây, API có thể cho rằng đã đến 12:00 trước thời điểm thực tế 90 giây. Nếu đồng hồ chạy chậm 90 giây, API có thể tiếp tục chấp nhận token sau thời điểm hết hạn thực tế.

Vì vậy, xử lý thời gian là một phần của chính sách bảo mật JWT. Nó bao gồm định nghĩa thời gian thống nhất, đồng bộ đồng hồ, kiểm tra sai lệch, lựa chọn leeway và giám sát trong vận hành.

## 2. UTC, Unix time và múi giờ

### UTC là mốc tham chiếu chung

UTC (Coordinated Universal Time) là chuẩn thời gian dùng để biểu diễn cùng một thời điểm trên toàn hệ thống. Các máy chủ có thể đặt ở những quốc gia và múi giờ khác nhau nhưng vẫn so sánh được cùng một mốc UTC.

JWT không nên phụ thuộc vào giờ địa phương của máy phát hành hoặc máy xác minh. Với các claim thời gian chuẩn, JWT sử dụng **NumericDate**, tức số giây tính từ Unix Epoch `1970-01-01T00:00:00Z` theo quy ước UTC/POSIX, bỏ qua leap seconds.

Ví dụ, cùng một thời điểm có thể được hiển thị là:

```text
2023-11-14T22:13:20Z       (UTC)
2023-11-15T05:13:20+07:00  (UTC+07:00)
```

Hai cách hiển thị trên biểu diễn cùng một thời điểm và phải tạo ra cùng một NumericDate. Offset `+07:00` là thông tin hiển thị theo múi giờ, không phải một phần cần cộng thêm vào timestamp sau khi đã chuyển về Unix time.

### Múi giờ khác nhau không đồng nghĩa đồng hồ bị lệch

Múi giờ chỉ là quy tắc hiển thị giờ địa phương so với UTC. Hai máy ở hai múi giờ khác nhau vẫn có thể đồng bộ chính xác đến cùng một thời điểm UTC.

Ngược lại, hai máy cùng hiển thị giờ địa phương giống nhau vẫn có thể có đồng hồ sai nếu chúng không đồng bộ. Thay đổi giờ mùa hè (*daylight saving time*) cũng không nên ảnh hưởng đến phép so sánh NumericDate vì phép so sánh dựa trên Unix time, không dựa trên chuỗi giờ địa phương.

Khi tạo hoặc kiểm tra JWT:

- Lấy thời gian tuyệt đối từ đồng hồ hệ thống đã được đồng bộ.
- Dùng Unix time theo giây cho NumericDate.
- Không phân tích `exp`, `nbf` hoặc `iat` như một chuỗi giờ địa phương không có timezone.
- Không tự cộng/trừ offset múi giờ vào NumericDate.

## 3. Wall clock và monotonic clock

Hệ điều hành thường cung cấp hai khái niệm thời gian có mục đích khác nhau.

| Loại đồng hồ | Đặc điểm | Dùng trong JWT như thế nào? |
| --- | --- | --- |
| Wall clock / system clock | Biểu diễn ngày giờ tuyệt đối, có thể quy đổi sang UTC hoặc Unix time; có thể được điều chỉnh khi đồng bộ | Dùng để so sánh `iat`, `nbf`, `exp` với thời điểm hiện tại |
| Monotonic clock | Đo thời gian trôi qua; không được thiết kế để biểu diễn ngày giờ lịch hoặc Unix Epoch | Dùng cho timeout và đo duration trong một tiến trình; không so sánh trực tiếp với NumericDate |

Ví dụ, `exp = 1700003600` là một mốc Unix time. Một giá trị monotonic như “đã trôi qua 73.2 giây kể từ khi tiến trình khởi động” không thể so sánh trực tiếp với `1700003600`.

Monotonic clock hữu ích để đo một khoảng chờ sau khi một sự kiện xảy ra vì nó không bị nhảy lùi hoặc nhảy tiến theo cách của wall clock. Tuy nhiên, giá trị monotonic thường không có ý nghĩa chung giữa các máy hoặc qua lần khởi động lại. Do đó, nó không thay thế đồng hồ UTC khi xác minh các claim thời gian tuyệt đối trong JWT.

## 4. Clock offset, clock drift và clock skew

Các khái niệm này thường được dùng gần nghĩa nhau, nhưng nên phân biệt khi phân tích sự cố.

- **Clock offset:** chênh lệch giữa thời gian của một máy và mốc tham chiếu tại cùng thời điểm.
- **Clock drift:** tốc độ đồng hồ chạy nhanh hoặc chậm so với mốc tham chiếu; sai lệch có thể tăng dần theo thời gian nếu không được hiệu chỉnh.
- **Clock skew:** độ lệch thời gian giữa hai đồng hồ, ví dụ đồng hồ của issuer và resource server.

Quy ước trong bài này:

\[
\Delta = T_{local} - T_{reference}
\]

- Nếu `Δ > 0`, đồng hồ local chạy trước mốc tham chiếu.
- Nếu `Δ < 0`, đồng hồ local chạy sau mốc tham chiếu.
- Nếu `Δ = 0`, hai đồng hồ trùng thời điểm tại phép đo đó.

Ví dụ, đồng hồ API chỉ `12:00:45 UTC` trong khi thời gian tham chiếu là `12:00:00 UTC`. Khi đó API chạy nhanh 45 giây (`Δ = +45s`).

Offset có thể thay đổi theo thời gian do drift của bộ dao động phần cứng, môi trường máy ảo, lỗi mạng hoặc nguồn thời gian, hay thay đổi cấu hình. Một lần kiểm tra đồng hồ thành công không bảo đảm máy sẽ luôn đồng bộ; cần giám sát liên tục.

## 5. Clock skew ảnh hưởng đến từng claim như thế nào?

Độ lệch có thể xuất hiện ở issuer, resource server hoặc giữa các resource server với nhau. Bảng sau giả định thời gian thực là mốc tham chiếu và xét từng trường hợp riêng.

| Tình huống | Ảnh hưởng thường gặp | Rủi ro |
| --- | --- | --- |
| Đồng hồ issuer chạy nhanh | `iat`, `nbf` và `exp` được ghi ở các mốc tương lai hơn thời gian tham chiếu | `nbf` có thể khiến token bị từ chối lâu hơn; `exp` có thể làm token được chấp nhận lâu hơn dự kiến |
| Đồng hồ issuer chạy chậm | Các mốc thời gian được ghi sớm hơn thời gian tham chiếu | `nbf` có thể làm token bắt đầu được chấp nhận sớm; `exp` có thể khiến token hết hạn sớm; `iat` có thể làm token trông cũ hơn |
| Đồng hồ verifier chạy nhanh | `now` lớn hơn thời gian thực | `nbf` dễ đạt sớm; `exp` có thể bị xem là hết hạn sớm; tuổi tính từ `iat` có thể lớn hơn thực tế |
| Đồng hồ verifier chạy chậm | `now` nhỏ hơn thời gian thực | `nbf` có thể chưa đạt; `exp` có thể được chấp nhận muộn; tuổi tính từ `iat` có thể nhỏ hơn thực tế |
| Các verifier lệch nhau | Cùng một token có thể cho kết quả khác nhau ở từng API/node | Request thành công ở node này nhưng thất bại ở node khác |

Ví dụ: issuer và verifier đều chạy nhanh 30 giây so với UTC nhưng cùng lệch như nhau trong suốt vòng đời token. Phần chênh lệch tương đối giữa chúng gần bằng 0 nên kiểm tra thời gian có thể nhất quán. Tuy nhiên, nếu một thành phần khác dùng thời gian chính xác hoặc lệch theo hướng khác, kết quả có thể thay đổi.

Vì thế, mục tiêu vận hành là đồng bộ tất cả thành phần với nguồn thời gian đáng tin cậy, không chỉ làm cho hai máy tình cờ có cùng độ lệch.

## 6. Leeway: khoảng dung sai khi kiểm tra thời gian JWT

RFC 7519 cho phép bên xử lý JWT áp dụng một khoảng dung sai nhỏ để xử lý clock skew. Khoảng này thường được gọi là **leeway** hoặc clock-skew tolerance; RFC nêu rằng khoảng dung sai thường không quá vài phút.

Leeway là cấu hình của bên xác minh. Nó không được ghi trong JWT và không làm thay đổi giá trị `exp`, `nbf` hoặc `iat` do issuer tạo ra.

Gọi `L` là leeway không âm, tính bằng giây. Các quy tắc minh họa thường dùng là:

**Not Before (`nbf`):**

\[
\text{now} + L \geq \text{nbf}
\]

**Expiration (`exp`):**

\[
\text{now} < \text{exp} + L
\]

**Future Issued At (`iat`), nếu chính sách kiểm tra timestamp tương lai:**

\[
\text{iat} \leq \text{now} + L
\]

Đây là cách biểu diễn một chính sách dung sai đối xứng thường gặp. RFC 7519 cho phép leeway nhỏ cho kiểm tra thời gian, nhưng không bắt buộc mọi thư viện hoặc profile phải áp dụng cùng một công thức cho mọi claim. Cần kiểm tra đúng hành vi của thư viện và profile đang sử dụng.

### Leeway mở rộng ranh giới ở cả hai phía

Với cùng một `L`:

- `nbf` có thể được chấp nhận sớm hơn tối đa `L` giây theo đồng hồ verifier.
- `exp` có thể tiếp tục được chấp nhận muộn hơn tối đa `L` giây theo đồng hồ verifier.
- `iat` có thể được xem là hợp lệ dù nằm trước `now` tối đa `L` giây theo kiểm tra future timestamp.

Ví dụ `nbf = 1700000060`, `exp = 1700003600`, `L = 30` giây:

| Thời gian verifier | Kiểm tra `nbf` | Kiểm tra `exp` |
| --- | --- | --- |
| `1700000030` | Đạt đúng ranh giới dung sai | Chưa hết hạn |
| `1700000060` | Đạt, đúng `nbf` | Chưa hết hạn |
| `1700003599` | Đạt | Chưa hết hạn |
| `1700003600` | Đạt | Được chấp nhận trong leeway |
| `1700003629` | Đạt | Được chấp nhận trong leeway |
| `1700003630` | Đạt | Từ chối tại ranh giới `exp + L` |

Leeway giúp tránh lỗi do sai lệch nhỏ nhưng đồng thời nới rộng cửa sổ chấp nhận token. Nếu cần chính sách bất đối xứng, ví dụ chỉ cho phép dung sai ở `exp` mà không muốn chấp nhận token trước `nbf`, cần cấu hình riêng nếu thư viện hỗ trợ hoặc thực hiện chính sách bổ sung một cách rõ ràng sau khi xác minh token.

## 7. Vì sao không nên đặt leeway quá lớn?

Giả sử access token có thời hạn 5 phút nhưng verifier cấu hình leeway 5 phút cho `exp`. Theo công thức trên, token có thể được chấp nhận thêm tối đa 5 phút sau `exp`. Cửa sổ chấp nhận thực tế vì vậy dài hơn đáng kể so với thời hạn do issuer dự kiến.

Leeway quá lớn có thể:

- Kéo dài thời gian sử dụng token bị đánh cắp.
- Làm chậm hiệu lực của thay đổi quyền hoặc thu hồi dựa trên thời điểm hết hạn.
- Tạo khác biệt khó hiểu giữa các hệ thống nếu chúng cấu hình leeway không giống nhau.
- Che giấu lỗi đồng bộ đồng hồ kéo dài thay vì khắc phục nguyên nhân.

Nguyên tắc lựa chọn:

1. Đồng bộ đồng hồ trước, chỉ dùng leeway để bù phần sai lệch nhỏ còn lại.
2. Chọn giá trị nhỏ dựa trên số liệu offset thực tế giữa các máy.
3. Dùng cấu hình thống nhất cho các verifier có cùng chính sách.
4. Xem xét riêng độ nhạy của token, thời hạn token và mức chấp nhận rủi ro.
5. Đo lường và cảnh báo khi offset vượt quá ngưỡng leeway đã chọn.
6. Đánh giá lại leeway khi thay đổi hạ tầng, nguồn thời gian hoặc phân bố địa lý của dịch vụ.

Không coi “vài phút” là giá trị mặc định cần bật. Đó là giới hạn hướng dẫn về một khoảng dung sai nhỏ; giá trị thực tế nên thấp nhất có thể mà vẫn xử lý được độ lệch đã đo.

## 8. Đồng bộ thời gian trong hệ thống phân tán

Các máy chủ cần một hoặc nhiều nguồn thời gian tham chiếu ổn định. Việc lựa chọn phụ thuộc vào độ chính xác cần thiết, quy mô mạng, môi trường triển khai và yêu cầu an toàn.

### NTP

**Network Time Protocol (NTP)** đồng bộ đồng hồ qua mạng và là lựa chọn phổ biến cho máy chủ, máy ảo và hạ tầng dịch vụ. NTP ước lượng độ lệch và độ trễ giữa client với server thời gian, sau đó hệ điều hành hoặc dịch vụ đồng bộ điều chỉnh clock.

Thực hành vận hành:

- Dùng các nguồn NTP đáng tin cậy và có dự phòng.
- Cấu hình đồng nhất cho các node cùng hệ thống.
- Theo dõi offset, jitter, reachability và trạng thái đồng bộ.
- Không chỉ kiểm tra tiến trình NTP đang chạy; cần kiểm tra clock thực sự đã đồng bộ và sai lệch còn trong ngưỡng.
- Bảo vệ cấu hình và đường truyền đến nguồn thời gian.

### NTS và xác thực nguồn thời gian

NTP thông thường không tự bảo đảm mọi phản hồi thời gian đến từ nguồn hợp lệ. Kẻ tấn công có khả năng giả mạo hoặc can thiệp lưu lượng thời gian có thể cố làm đồng hồ chạy nhanh hoặc chậm.

**Network Time Security (NTS)**, được mô tả trong [RFC 8915](https://www.rfc-editor.org/rfc/rfc8915), bổ sung cơ chế bảo vệ mật mã cho trao đổi NTP. NTS giúp xác thực và bảo vệ các thông điệp thời gian trong phạm vi giao thức; nó không bảo đảm máy chủ thời gian không bị xâm nhập hoặc thời gian mà nguồn cung cấp luôn chính xác tuyệt đối.

### PTP

**Precision Time Protocol (PTP, IEEE 1588)** được dùng trong môi trường cần độ chính xác cao, thường trong mạng nội bộ được kiểm soát và có hỗ trợ phần cứng phù hợp. PTP có thể đạt độ chính xác tốt hơn NTP trong một số môi trường, nhưng yêu cầu thiết kế, thiết bị và vận hành tương ứng.

Không phải mọi hệ thống JWT đều cần PTP. Với nhiều ứng dụng web/API thông thường, NTP được cấu hình và giám sát tốt đã đáp ứng yêu cầu. Điều quan trọng là chọn nguồn thời gian theo yêu cầu thực tế và kiểm tra độ lệch mà hệ thống có thể gặp.

## 9. Điều chỉnh đồng hồ: step, slew và nhảy thời gian

Khi phát hiện đồng hồ lệch, dịch vụ đồng bộ có thể điều chỉnh thời gian theo các cách khác nhau:

- **Step:** thay đổi wall clock một bước để đưa thời gian về gần mốc tham chiếu. Điều này có thể tạo ra một bước nhảy tiến hoặc lùi.
- **Slew:** điều chỉnh tốc độ chạy của đồng hồ trong một khoảng thời gian để giảm sai lệch dần dần, hạn chế bước nhảy đột ngột.

Việc điều chỉnh có thể ảnh hưởng đến kiểm tra JWT:

| Thay đổi wall clock | Ảnh hưởng có thể xảy ra |
| --- | --- |
| Nhảy tiến | Token có thể bị xem là hết hạn sớm; `iat` có thể bị xem là quá cũ; `nbf` có thể đạt sớm |
| Nhảy lùi | Token hết hạn có thể bị xem là còn hiệu lực; `nbf` có thể chưa đạt; tuổi tính từ `iat` có thể giảm đột ngột |
| Slew | Thời gian vẫn trôi nhưng tốc độ có thể khác nhẹ trong giai đoạn hiệu chỉnh |

Nhảy lùi đặc biệt cần chú ý vì một token đã bị từ chối do hết hạn có thể lại vượt qua phép so sánh thời gian nếu wall clock quay về trước `exp`. Ứng dụng không nên tự giả định wall clock luôn tăng đơn điệu.

Khi vận hành:

- Đồng bộ thời gian trước khi đưa node vào phục vụ.
- Theo dõi sự kiện step lớn hoặc thay đổi thời gian bất thường.
- Cảnh báo khi đồng hồ lùi hoặc nhảy vượt ngưỡng chính sách.
- Đánh giá việc tạm ngừng xác minh hoặc loại node khỏi tải khi clock không đáng tin cậy, theo mức độ rủi ro của hệ thống.
- Không dùng monotonic clock để thay thế Unix time; sử dụng nó cho các phép đo duration cục bộ phù hợp.

## 10. Leap seconds và leap smear

NumericDate theo RFC 7519 bỏ qua leap seconds và theo quy ước POSIX mỗi ngày có 86.400 giây. Tuy nhiên, các hệ điều hành và nhà cung cấp hạ tầng có thể xử lý thời điểm leap second theo cách khác nhau.

Một số nhà cung cấp dùng **leap smear**: thay vì điều chỉnh đồng hồ bằng một bước tại thời điểm leap second, họ phân bố thay đổi đó trong một khoảng thời gian để đồng hồ tiến dần. Trong thời gian smear, thời gian hiển thị có thể lệch nhẹ so với nguồn không dùng smear.

Nếu issuer dùng một nguồn smear còn verifier dùng nguồn không smear, chúng có thể xuất hiện clock skew tạm thời. Cách xử lý:

- Biết rõ chính sách leap-second/smear của nguồn thời gian đang dùng.
- Ưu tiên dùng cùng một chính sách thời gian trong các thành phần cần phối hợp chặt chẽ.
- Đo độ lệch thực tế và đặt leeway phù hợp, nhỏ và có kiểm soát.
- Không tự cộng hoặc trừ leap second vào NumericDate.

Đây thường không phải vấn đề hằng ngày của API thông thường, nhưng có thể quan trọng với hệ thống phân tán yêu cầu độ chính xác thời gian cao.

## 11. Đồng nhất chính sách thời gian giữa nhiều verifier

Trong kiến trúc có nhiều API hoặc nhiều node chạy cùng một dịch vụ, mọi verifier nên áp dụng chính sách thời gian tương thích.

Ví dụ một load balancer phân phối request đến ba node:

| Node | Offset so với UTC | Leeway `exp` | Kết quả gần ranh giới hết hạn |
| --- | ---: | ---: | --- |
| API-A | `+2s` | `30s` | Deadline theo UTC xấp xỉ `exp + 28s` |
| API-B | `-25s` | `30s` | Deadline theo UTC xấp xỉ `exp + 55s` |
| API-C | `+70s` | `30s` | Deadline theo UTC xấp xỉ `exp - 40s`; offset vượt leeway |

Một request có thể thành công trên API-B nhưng thất bại trên API-C. Nếu lỗi chỉ xuất hiện ngẫu nhiên theo node, cần xem xét trạng thái đồng bộ đồng hồ bên cạnh việc kiểm tra token và chữ ký.

Để giảm khác biệt:

- Dùng cùng cấu hình nguồn thời gian và chính sách leeway cho các node cùng vai trò.
- Theo dõi offset theo từng node, không chỉ theo cụm.
- Không để một node có clock unhealthy tiếp tục xử lý request nhạy cảm.
- Kiểm thử token gần ranh giới thời gian trên tất cả loại verifier.
- Ghi log thời gian hiện tại, claim thời gian và lý do từ chối ở mức đủ để chẩn đoán, nhưng không ghi toàn bộ JWT hoặc dữ liệu bí mật.

## 12. Hành vi khi nguồn thời gian không đáng tin cậy

Nếu máy không thể đồng bộ thời gian hoặc không biết đồng hồ hiện tại sai lệch bao nhiêu, các phép kiểm tra `exp`, `nbf` và max-age dựa trên `iat` không còn đáng tin.

Một số tình huống:

- Node mới khởi động nhưng chưa đồng bộ thời gian.
- Nguồn NTP mất kết nối trong thời gian dài.
- Offset vượt ngưỡng cho phép.
- Đồng hồ hệ thống bị điều chỉnh thủ công.
- Phản hồi thời gian có dấu hiệu bị giả mạo hoặc bất thường.

Chính sách cần được xác định trước:

1. Đánh dấu node chưa sẵn sàng cho đến khi đồng hồ đạt trạng thái đồng bộ cần thiết.
2. Nếu độ lệch vượt ngưỡng, cảnh báo và cân nhắc loại node khỏi tải.
3. Với hoạt động bảo mật nhạy cảm, không mặc định chấp nhận token khi không thể xác định thời gian đáng tin cậy.
4. Khôi phục đồng bộ, xác nhận offset ổn định rồi mới đưa node trở lại phục vụ.
5. Có phương án dự phòng nguồn thời gian nhưng phải bảo đảm nguồn dự phòng cũng được tin cậy.

Hành vi cụ thể phụ thuộc yêu cầu sẵn sàng và rủi ro. Điều quan trọng là lỗi nguồn thời gian phải được phát hiện và xử lý như một tình trạng vận hành có ảnh hưởng đến bảo mật.

## 13. Quy trình xác minh thời gian trong JWT

Một quy trình tổng quát cho resource server:

1. Xác minh cấu trúc và bảo vệ mật mã của JWT trước khi tin claims.
2. Lấy wall clock hiện tại theo Unix time từ hệ thống đã đồng bộ.
3. Kiểm tra trạng thái đồng bộ và độ lệch đồng hồ có nằm trong ngưỡng vận hành không.
4. Kiểm tra `nbf` nếu claim có mặt hoặc được profile yêu cầu.
5. Kiểm tra `exp` nếu claim có mặt hoặc được profile yêu cầu.
6. Nếu áp dụng max-age, kiểm tra `iat` và tính tuổi token.
7. Áp dụng leeway nhỏ, nhất quán theo chính sách cho từng ranh giới.
8. Tiếp tục kiểm tra issuer, audience, token type, quyền và trạng thái thu hồi.
9. Từ chối nếu bất kỳ điều kiện bắt buộc nào không đạt hoặc thời gian hiện tại không đáng tin cậy.

Giả mã minh họa:

```text
MAX_ALLOWED_CLOCK_OFFSET_SECONDS = 5
CLOCK_SKEW_LEEWAY_SECONDS = 30

function validateTimeClaims(claims, trustedNowEpochSeconds, clockHealth):
    if not clockHealth.isSynchronized:
        return false

    if abs(clockHealth.offsetSeconds) > MAX_ALLOWED_CLOCK_OFFSET_SECONDS:
        return false

    if claims.nbf exists:
        if not isValidNumericDate(claims.nbf):
            return false
        if trustedNowEpochSeconds + CLOCK_SKEW_LEEWAY_SECONDS < claims.nbf:
            return false

    if claims.exp exists:
        if not isValidNumericDate(claims.exp):
            return false
        if trustedNowEpochSeconds >= claims.exp + CLOCK_SKEW_LEEWAY_SECONDS:
            return false

    return true
```

Đây là giả mã mô tả chính sách, không phải API của thư viện cụ thể. Các giới hạn 5 giây và 30 giây chỉ là ví dụ để minh họa; hệ thống phải chọn ngưỡng theo yêu cầu, số liệu đo và profile. Ví dụ chưa bao gồm `iat`, issuer, audience, chữ ký, token type hoặc quyền; các bước đó vẫn cần được thực hiện nếu chính sách yêu cầu.

## 14. Giám sát và chẩn đoán clock skew

Để phân biệt lỗi token với lỗi đồng hồ, hệ thống nên quan sát trạng thái thời gian như một phần của telemetry.

Các chỉ số hữu ích:

- Offset giữa đồng hồ node và nguồn tham chiếu.
- Drift hoặc xu hướng offset theo thời gian.
- Trạng thái đồng bộ và thời gian kể từ lần đồng bộ thành công gần nhất.
- Nguồn thời gian hiện đang được sử dụng.
- Số lần clock step hoặc thay đổi thời gian bất thường.
- Số lượng JWT bị từ chối do `exp`, `nbf` hoặc `iat`.
- Phân bố thời gian còn lại hoặc độ lệch giữa `now` và claim tại thời điểm từ chối.

Log phục vụ chẩn đoán nên ghi lý do cụ thể như `token expired`, `token not active yet`, `iat too far in future` hoặc `clock unhealthy`. Không ghi nguyên token bearer, chữ ký, refresh token hoặc dữ liệu xác thực nhạy cảm.

Nếu nhiều token hợp lệ cùng bị từ chối tại một node, trong khi các node khác vẫn chấp nhận, hãy so sánh offset và cấu hình leeway trước khi kết luận issuer phát hành token sai.

## 15. Kịch bản kiểm thử đồng hồ và leeway

Giả sử hệ thống dùng `L = 30` giây cho kiểm tra `nbf` và `exp`, đồng thời yêu cầu clock offset của verifier không vượt 5 giây.

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Đồng hồ issuer và verifier cùng UTC | Kết quả theo claim và leeway | Trường hợp chuẩn |
| Verifier chậm 20 giây, `nbf` sắp đến | Xử lý theo leeway đã cấu hình | Clock skew âm |
| Verifier nhanh 20 giây, `exp` sắp đến | Xử lý theo leeway đã cấu hình | Clock skew dương |
| Offset vượt 5 giây | Đánh dấu clock unhealthy theo ví dụ chính sách | Ngưỡng vận hành |
| `now + L` đúng bằng `nbf` | Đạt bước `nbf` | Ranh giới bao gồm |
| `now` đúng bằng `exp + L` | Từ chối | Ranh giới hết hạn với leeway |
| Wall clock nhảy tiến | Phát hiện thay đổi và kiểm tra hành vi từ chối sớm | Clock step forward |
| Wall clock nhảy lùi | Phát hiện rollback và không chấp nhận token ngoài chính sách | Clock step backward |
| Nguồn NTP không khả dụng | Cảnh báo và xử lý theo clock-health policy | Mất nguồn thời gian |
| Node vừa khởi động, chưa đồng bộ | Chưa sẵn sàng xác minh token nhạy cảm | Startup readiness |
| Các node có offset khác nhau | Phát hiện kết quả xác minh không nhất quán | Cluster consistency |
| Nguồn thời gian dùng leap smear khác nhau | Đo và xử lý offset theo chính sách | Leap smear interoperability |
| Múi giờ hệ điều hành thay đổi nhưng Unix time không đổi | Kết quả JWT không đổi | Timezone independence |
| Đồng hồ địa phương có DST chuyển đổi | Không làm thay đổi NumericDate của cùng thời điểm | Daylight saving independence |

Kiểm thử nên được thực hiện trên môi trường có thể mô phỏng thời gian hoặc clock offset an toàn. Không thay đổi đồng hồ của hệ thống production chỉ để kiểm thử một trường hợp JWT.

## 16. Nguyên tắc cần ghi nhớ

1. Dùng UTC/Unix time làm mốc chung cho các claim thời gian JWT; không dùng giờ địa phương để so sánh trực tiếp.
2. Phân biệt wall clock dùng cho thời điểm tuyệt đối với monotonic clock dùng để đo thời lượng.
3. Clock offset là chênh lệch hiện tại; drift là sai lệch tốc độ; skew là độ lệch giữa các đồng hồ.
4. Đồng hồ issuer và verifier lệch có thể làm `iat`, `nbf`, `exp` bị đánh giá sai theo các hướng khác nhau.
5. Đồng bộ thời gian bằng nguồn đáng tin cậy và giám sát offset liên tục.
6. Leeway là dung sai của verifier, không thay đổi NumericDate trong token và có thể mở rộng chấp nhận ở cả hai ranh giới.
7. Chọn leeway nhỏ theo số liệu thực tế; không dùng leeway lớn để che giấu lỗi đồng bộ.
8. Phát hiện clock step, rollback và trạng thái nguồn thời gian không đáng tin cậy.
9. Các verifier trong cùng hệ thống cần chính sách thời gian tương thích.
10. Chỉ chấp nhận JWT khi cả token và nguồn thời gian phục vụ quyết định xác minh đều đáp ứng chính sách tin cậy.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 2 và 4.1.4–4.1.6](https://www.rfc-editor.org/rfc/rfc7519): NumericDate và các claim thời gian `exp`, `nbf`, `iat`.
- [RFC 5905 — Network Time Protocol Version 4](https://www.rfc-editor.org/rfc/rfc5905): giao thức đồng bộ thời gian NTP.
- [RFC 8633 — Network Time Protocol Best Current Practices](https://www.rfc-editor.org/rfc/rfc8633): thực hành triển khai và vận hành NTP.
- [RFC 8915 — Network Time Security for the Network Time Protocol](https://www.rfc-editor.org/rfc/rfc8915): bảo vệ mật mã cho trao đổi NTP.
- [RFC 3339 — Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339): định dạng ngày giờ có timezone.
- [IEEE 1588 — Precision Time Protocol](https://standards.ieee.org/ieee/1588/6825/): chuẩn đồng bộ thời gian chính xác cao trong mạng.

**Kết luận:** JWT cần một nguồn thời gian UTC đáng tin cậy để đánh giá `iat`, `nbf` và `exp`. Đồng bộ clock giữa issuer và verifier, đo sai lệch, cấu hình leeway nhỏ và nhất quán, đồng thời xử lý clock jump hoặc nguồn thời gian lỗi là những điều kiện quan trọng để token được chấp nhận đúng thời điểm.
