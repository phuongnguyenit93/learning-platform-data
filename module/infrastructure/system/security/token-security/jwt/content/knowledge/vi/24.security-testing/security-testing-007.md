# exp, nbf, iat tại ranh giới thời gian và khi đồng hồ lệch

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Kiểm thử bảo mật  
> **Phạm vi:** Kiểm thử các mốc thời gian của JWT và hành vi khi đồng hồ issuer/verifier lệch nhau; tập trung vào semantics của NumericDate, boundary conditions, clock skew và kiểm thử hệ thống phân tán, không phụ thuộc Java, Spring hay framework cụ thể.

Các claim thời gian quyết định khi nào JWT có thể được chấp nhận. Một lỗi nhỏ ở phép so sánh tại ranh giới có thể khiến token hết hạn vẫn được dùng, token chưa đến thời điểm hiệu lực được chấp nhận sớm hoặc token mới phát hành bị từ chối do đồng hồ lệch.

Ba claim cần phân biệt:

- **exp (Expiration Time):** thời điểm token không còn được chấp nhận.
- **nbf (Not Before):** thời điểm sớm nhất token được chấp nhận.
- **iat (Issued At):** thời điểm token được phát hành; có thể dùng để đánh giá tuổi token và phát hiện timestamp bất hợp lý.

Theo RFC 7519, các giá trị này dùng **NumericDate**: số giây kể từ Unix epoch tại 1970-01-01T00:00:00Z, không tính leap seconds. Chúng không phải chuỗi ngày giờ ISO 8601 và không mặc định dùng millisecond.

Kiểm thử đúng phải bao phủ cả thời điểm ngay trước, đúng tại và ngay sau từng mốc; đồng thời mô phỏng verifier nhanh/chậm hơn issuer. Không nên chỉ kiểm tra một token hết hạn rõ ràng hoặc một token còn hạn nhiều giờ.

## 1. Semantics chính xác của exp, nbf và iat

### 1.1. exp — thời điểm hết hạn

RFC 7519 quy định thời điểm hiện tại phải **trước** giá trị exp. Vì vậy, nếu không áp dụng leeway:

\[
accept_{exp} \iff now < exp
\]

Hệ quả:

- Khi now nhỏ hơn exp, kiểm tra exp đạt.
- Khi now bằng exp, token đã tới thời điểm hết hạn và phải bị từ chối.
- Khi now lớn hơn exp, token phải bị từ chối.

Phép so sánh phải là nghiêm ngặt. Lỗi dùng now <= exp sẽ chấp nhận token thêm đúng tại thời điểm exp.

### 1.2. nbf — thời điểm bắt đầu hiệu lực

RFC 7519 quy định thời điểm hiện tại phải **bằng hoặc sau** giá trị nbf. Không có leeway:

\[
accept_{nbf} \iff now \ge nbf
\]

Hệ quả:

- Khi now nhỏ hơn nbf, token chưa có hiệu lực và phải bị từ chối.
- Khi now bằng nbf, token có thể được chấp nhận.
- Khi now lớn hơn nbf, kiểm tra nbf đạt.

Phép so sánh khác với exp: tại đúng nbf được phép, tại đúng exp không được phép.

### 1.3. iat — thời điểm phát hành

iat xác định thời điểm JWT được phát hành. RFC 7519 không định nghĩa iat như một điều kiện hết hạn tự động giống exp và không quy định một ngưỡng tuổi tối đa chung cho mọi JWT.

Ứng dụng có thể dùng iat để:

- Từ chối token có thời điểm phát hành ở tương lai vượt quá clock tolerance.
- Giới hạn tuổi tối đa của token theo profile.
- Điều tra token được phát hành trước/sau một sự kiện.
- Đánh giá token có quá cũ so với chính sách hiện tại không.

Vì vậy, cần phân biệt:

1. **Syntax/claim validation:** iat tồn tại, có kiểu NumericDate hợp lệ.
2. **Future-time policy:** iat không vượt quá mức lệch đồng hồ được cho phép.
3. **Maximum-age policy:** token không cũ hơn giới hạn do profile quy định.

Không nên mặc định mọi JWT đều phải có cùng max age. Access token, ID token, token nghiệp vụ và token lưu trữ dài hạn có vòng đời khác nhau.

### 1.4. Bảng semantics tại ranh giới

| Claim | Điều kiện không có leeway | Ngay trước mốc | Đúng tại mốc | Ngay sau mốc |
|---|---|---|---|---|
| exp = T | now < T | Chấp nhận exp | Từ chối | Từ chối |
| nbf = T | now >= T | Từ chối | Chấp nhận nbf | Chấp nhận |
| iat = T | Không có phép so sánh hết hạn mặc định | Phụ thuộc future/max-age policy | Phụ thuộc policy | Phụ thuộc policy |

Việc exp và nbf có semantics khác nhau là lý do cần test boundary riêng, không dùng một helper so sánh thời gian chung mà không kiểm tra chiều điều kiện.

## 2. NumericDate và lỗi đơn vị thời gian

### 2.1. NumericDate tính bằng giây

NumericDate là số giây kể từ Unix epoch UTC. Ví dụ một timestamp dạng số nguyên:

~~~json
{
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794803600
}
~~~

Payload trên minh họa token có thời điểm bắt đầu hiệu lực tại iat/nbf và hết hạn sau đó một giờ. Các giá trị chỉ dùng minh họa, không phải thời gian hiện tại hay token thực.

Không chuyển NumericDate thành millisecond khi ghi JWT. Một giá trị millisecond bị hiểu nhầm là giây có thể đẩy thời điểm lên xa hàng nghìn năm; giá trị giây bị hiểu nhầm là millisecond có thể khiến token bị coi là đã hết hạn từ rất lâu.

### 2.2. Seconds và milliseconds

| Dữ liệu | Ví dụ | Cách diễn giải |
|---|---:|---|
| Unix seconds | 1794800000 | NumericDate hợp lệ về đơn vị |
| Unix milliseconds | 1794800000000 | Không phải đơn vị NumericDate |
| Chuỗi ISO 8601 | "2026-11-16T12:00:00Z" | Không phải NumericDate |
| Chuỗi số | "1794800000" | Sai kiểu nếu profile yêu cầu JSON number |

Một số runtime biểu diễn thời gian bằng millisecond trong khi JWT dùng giây. Lớp chuyển đổi phải được kiểm tra rõ ràng tại ranh giới giữa API thời gian và serializer.

### 2.3. Kiểm tra kiểu dữ liệu

Nếu profile yêu cầu NumericDate, kiểm tra:

- Giá trị là JSON number, không phải string.
- Giá trị hữu hạn và nằm trong miền thời gian hệ thống hỗ trợ.
- Không chấp nhận null, boolean, array hoặc object.
- Không chấp nhận số quá lớn gây overflow hoặc wraparound.
- Không âm thầm chuyển đổi kiểu bằng cách parse chuỗi.
- Có semantics rõ với số thập phân nếu hệ thống hỗ trợ fractional NumericDate.

RFC 7519 định nghĩa NumericDate là JSON number và không bắt buộc phải là số nguyên. Nếu implementation chỉ hỗ trợ số nguyên giây, giới hạn đó cần được ghi rõ trong profile và áp dụng nhất quán giữa issuer/verifier.

### 2.4. Độ chính xác và làm tròn

Nếu timestamp có phần thập phân, không nên làm tròn sớm trước khi so sánh. Ví dụ exp là T + 0.5 giây:

- Tại T, token vẫn còn trước exp.
- Tại T + 0.5 giây, token đã tới exp và phải bị từ chối nếu không có leeway.

Nếu parser chuyển mọi giá trị về integer bằng cách cắt phần thập phân, ranh giới thực tế có thể bị thay đổi. Cần xác định độ chính xác được hỗ trợ và kiểm thử hành vi ở phần lẻ.

### 2.5. Duplicate claim và parser consistency

JWT payload có hai claim cùng tên như exp hoặc nbf có thể được các parser xử lý khác nhau. RFC 7519 yêu cầu parser hoặc từ chối JWT có duplicate claim names, hoặc dùng giá trị xuất hiện cuối cùng theo quy tắc được mô tả trong chuẩn.

Để tránh parser differential giữa gateway và resource server:

- Chọn một semantics rõ và thống nhất.
- Ưu tiên từ chối duplicate claim nhạy cảm nếu profile cho phép.
- Đảm bảo lớp parse và lớp validate dùng cùng một biểu diễn claims.
- Có test với exp/nbf/iat bị lặp và thứ tự member đảo ngược.

## 3. Leeway và clock skew

### 3.1. Vì sao đồng hồ có thể lệch?

Issuer và verifier có thể chạy trên các máy, container, region hoặc nhà cung cấp khác nhau. Đồng hồ có thể lệch vì:

- NTP chưa đồng bộ hoặc mất kết nối time source.
- Máy ảo/container vừa khởi động và chưa ổn định clock.
- NTP step/slew hoặc điều chỉnh thủ công.
- Cấu hình timezone sai ở tầng hiển thị/chuyển đổi.
- Host bị suspend/resume.
- Đồng hồ phần cứng hoặc hypervisor có vấn đề.
- Một thành phần dùng wall clock, thành phần khác dùng monotonic clock không đúng mục đích.

JWT timestamps là thời điểm tuyệt đối theo Unix time/UTC. Timezone của người dùng không được tham gia phép so sánh.

### 3.2. Leeway là gì?

RFC 7519 cho phép verifier có một khoảng leeway nhỏ để bù clock skew. Leeway thường không nên lớn hơn vài phút; trong hệ thống có kiểm soát thời gian tốt, nên chọn mức nhỏ dựa trên dữ liệu đo được.

Với leeway L:

\[
accept_{exp} \iff now < exp + L
\]

\[
accept_{nbf} \iff now + L \ge nbf
\]

Leeway mở rộng cửa sổ chấp nhận ở cả hai phía:

- exp: token có thể được chấp nhận thêm tối đa L sau exp.
- nbf: token có thể được chấp nhận sớm tối đa L trước nbf.

Do đó, leeway không chỉ là tiện ích tránh lỗi người dùng. Nó làm tăng cửa sổ mà token có thể được chấp nhận. Cần ghi nhận đây là một quyết định bảo mật.

### 3.3. Ví dụ với leeway

Giả sử exp = 1000 và L = 30 giây:

| now | Kết quả exp | Lý do |
|---:|---|---|
| 999 | Chấp nhận | Trước exp |
| 1000 | Chấp nhận | Trong leeway |
| 1029.999 | Chấp nhận | Nhỏ hơn exp + L |
| 1030 | Từ chối | Đã tới exp + L |
| 1031 | Từ chối | Vượt exp + L |

Giả sử nbf = 1000 và L = 30 giây:

| now | Kết quả nbf | Lý do |
|---:|---|---|
| 969.999 | Từ chối | Trước nbf - L |
| 970 | Chấp nhận | Đúng ranh giới leeway |
| 999 | Chấp nhận | Trong leeway trước nbf |
| 1000 | Chấp nhận | Đúng nbf |
| 1001 | Chấp nhận | Sau nbf |

Ví dụ dùng cùng một L để minh họa. Hệ thống có thể định nghĩa tolerance khác nhau theo claim/profile, nhưng phải ghi rõ và kiểm thử.

### 3.4. Không cộng leeway nhiều lần

Một lỗi cấu hình phổ biến là mỗi lớp tự cộng một khoảng tolerance:

- JWT library có leeway 60 giây.
- API gateway thêm 60 giây.
- Resource server thêm 60 giây.
- Cache status giữ active thêm 60 giây.

Tổng cửa sổ chấp nhận có thể vượt xa dự định. Cần xác định một ngân sách tổng thể và biết mỗi lớp áp dụng tolerance nào. Không cộng thêm leeway lần nữa nếu thư viện đã áp dụng.

### 3.5. Phân biệt clock skew và network latency

Leeway chủ yếu bù sai khác đồng hồ. Request mất thời gian trên mạng không làm thay đổi exp; verifier kiểm tra thời gian khi nhận request.

Nếu token có exp rất gần, request gửi trước exp nhưng đến sau exp có thể bị từ chối. Đây là hành vi bình thường của phép xác minh tại thời điểm nhận. Không tăng leeway quá lớn chỉ để che độ trễ mạng; hãy cân nhắc lifetime, timeout, retry và semantics của thao tác.

## 4. Đồng hồ nhanh/chậm ảnh hưởng từng claim thế nào?

Đặt:

- T là thời gian thực tham chiếu.
- Issuer clock = T + I.
- Verifier clock = T + V.
- Clock offset tương đối giữa verifier và issuer là V - I.

Nếu verifier chạy nhanh hơn issuer, V - I dương. Nếu verifier chạy chậm hơn issuer, V - I âm.

### 4.1. Verifier chạy nhanh hơn issuer

Verifier nghĩ thời gian đã muộn hơn thực tế:

- exp: token có thể bị từ chối sớm hơn thời điểm issuer dự định.
- nbf: token có thể được chấp nhận sớm hơn thời điểm issuer dự định.
- iat: token vừa phát hành thường không bị xem là có iat ở tương lai do offset này, vì verifier đang thấy thời gian muộn hơn thời điểm issuer ghi. Ngược lại, verifier chậm hơn issuer có thể thấy iat ở tương lai.

### 4.2. Verifier chạy chậm hơn issuer

Verifier nghĩ thời gian còn sớm hơn thực tế:

- exp: token có thể tiếp tục được chấp nhận lâu hơn thời điểm thực tế exp.
- nbf: token có thể bị từ chối muộn, tức chấp nhận trễ hơn.
- iat: token vừa phát hành có thể bị xem là có iat trong tương lai.

Leeway có thể giảm false reject, nhưng cũng kéo dài khả năng chấp nhận token sau exp và cho phép token trước nbf. Do đó, cần kiểm thử cả hai hướng lệch.

### 4.3. Ma trận hướng lệch

| Clock verifier so với issuer | exp | nbf | iat future check |
|---|---|---|---|
| Nhanh hơn | Có thể hết hạn sớm | Có thể có hiệu lực sớm | Ít gặp false future do lệch này |
| Chậm hơn | Có thể chấp nhận quá lâu | Có thể có hiệu lực muộn | Có thể bị xem là ở tương lai |
| Đồng bộ | Theo boundary đã định | Theo boundary đã định | Theo policy iat |

Đây là tác động tương đối giữa hai clock. Một hệ thống có thể có cả issuer và verifier cùng lệch so với UTC thực; cần đo offset của từng bên với time source đáng tin cậy.

## 5. Chính sách kiểm tra iat

### 5.1. Không dùng iat như exp thứ hai

iat không tự làm token hết hạn. Nếu muốn giới hạn tuổi token, phải có một policy rõ, ví dụ:

\[
now - iat \le maxAge + tolerance
\]

Đồng thời cần xử lý iat trong tương lai:

\[
iat \le now + futureTolerance
\]

Hai điều kiện này là policy ứng dụng, không phải phép kiểm tra mặc định bắt buộc giống exp/nbf cho mọi JWT.

### 5.2. Future iat

Một token có iat ở tương lai có thể cho thấy:

- Issuer clock chạy nhanh hơn verifier.
- Token được tạo bởi một issuer khác với clock không đồng bộ.
- Timestamp bị lỗi đơn vị giây/millisecond.
- Token giả hoặc dữ liệu test không đúng.
- Claim iat bị xử lý sai kiểu/precision.

Verifier có thể cho phép một future tolerance nhỏ, nhưng phải ghi rõ. Nếu iat vượt ngưỡng, từ chối hoặc đưa vào quy trình xử lý theo profile.

### 5.3. Maximum token age

Nếu profile yêu cầu token không quá cũ:

- Xác định max age theo loại token.
- Tính từ iat đã được xác minh, không lấy iat từ token chưa xác minh để cấp quyền.
- Xác định tolerance cho clock skew.
- Kiểm tra iat không quá xa trong tương lai.
- Kiểm tra quan hệ giữa iat và exp.

Ví dụ một access token có exp trong tương lai nhưng iat quá cũ vẫn có thể bị từ chối nếu profile đặt max age. Đây là policy bổ sung để giới hạn token lifetime thực tế.

### 5.4. Quan hệ giữa iat, nbf và exp

Các quan hệ thường cần kiểm tra:

- iat không được ở tương lai vượt quá tolerance.
- exp phải sau iat theo profile token có lifetime dương.
- nbf không được sau exp nếu điều đó tạo khoảng hiệu lực rỗng hoặc vô nghĩa.
- Lifetime exp - iat không vượt giới hạn profile.
- Nếu nbf có mặt, khoảng hiệu lực exp - nbf phải đáp ứng policy.

Không phải mọi profile đều bắt buộc nbf. Không tự thêm điều kiện bắt buộc claim nếu contract không yêu cầu, nhưng khi claim xuất hiện thì phải xác minh kiểu và semantics.

## 6. Ranh giới thời gian cần kiểm thử

### 6.1. Boundary matrix cho exp

Với exp = T, không leeway:

| Thời điểm kiểm tra | Kết quả mong đợi |
|---|---|
| T - 1 giây | Chấp nhận exp |
| T - 1 đơn vị precision | Chấp nhận exp |
| T | Từ chối |
| T + 1 đơn vị precision | Từ chối |
| T + 1 giây | Từ chối |

Với leeway L, thay ranh giới hết hạn bằng T + L và kiểm tra ngay trước, đúng tại, ngay sau ranh giới đó.

### 6.2. Boundary matrix cho nbf

Với nbf = T, không leeway:

| Thời điểm kiểm tra | Kết quả mong đợi |
|---|---|
| T - 1 giây | Từ chối |
| T - 1 đơn vị precision | Từ chối |
| T | Chấp nhận nbf |
| T + 1 đơn vị precision | Chấp nhận |
| T + 1 giây | Chấp nhận |

Với leeway L, ranh giới bắt đầu chấp nhận là T - L. Kiểm tra ngay trước, đúng tại và ngay sau mốc đó.

### 6.3. Boundary matrix cho iat

iat không có boundary accept/reject chung nếu không có policy. Hãy kiểm thử từng policy đã chọn:

| Policy | Ngay dưới ranh giới | Đúng ranh giới | Ngay trên ranh giới |
|---|---|---|---|
| Future tolerance F: iat <= now + F | Đạt | Đạt | Vượt F thì từ chối |
| Max age A: now - iat <= A | Trong tuổi thì đạt | Đạt tại A | Quá A thì từ chối |

Phải xác định phép so sánh tại equality cho từng policy và dùng nhất quán giữa các verifier.

### 6.4. Kiểm thử kết hợp nhiều claim

Không chỉ test từng claim độc lập. Cần test:

- exp hợp lệ nhưng nbf ở tương lai.
- nbf hợp lệ nhưng exp đã qua.
- iat ở tương lai trong khi exp/nbf hợp lệ.
- exp trước iat.
- nbf bằng exp.
- Lifetime vượt max lifetime.
- Token có exp/nbf thiếu hoặc sai kiểu theo contract.
- Clock skew khiến một claim đạt và claim khác không đạt.

Một token chỉ được chấp nhận khi tất cả điều kiện thời gian bắt buộc của profile đều đạt.

## 7. Đồng bộ thời gian và nguồn clock

### 7.1. Dùng UTC/Unix time cho JWT

JWT NumericDate không chứa timezone. Hệ thống phải:

- Chuyển thời điểm về Unix epoch seconds.
- Không dùng timezone local của máy hoặc người dùng.
- Không áp dụng daylight saving time vào phép so sánh.
- Chuẩn hóa đơn vị giây/millisecond tại boundary.
- Dùng cùng quy tắc precision ở issuer và verifier.

Timezone cấu hình sai có thể làm thời gian lệch nhiều giờ dù NTP đồng bộ đúng epoch time. Cần phân biệt lỗi timezone hiển thị với lỗi clock thực.

### 7.2. Wall clock và monotonic clock

JWT claims là timestamp tuyệt đối nên cần wall clock gắn với Unix epoch để so sánh exp/nbf/iat.

Monotonic clock phù hợp để đo duration, timeout và elapsed time vì không bị điều chỉnh lùi/tiến theo cùng cách wall clock. Không dùng monotonic clock trực tiếp để so sánh NumericDate nếu không có phép ánh xạ được thiết kế đúng.

Một hệ thống có thể đọc wall clock một lần khi bắt đầu xử lý request, sau đó dùng monotonic clock cho timeout nội bộ. Không trộn hai loại clock mà không hiểu semantics.

### 7.3. NTP và giám sát offset

Vận hành cần:

- Dùng time source đáng tin cậy và cấu hình đồng bộ nhất quán.
- Theo dõi offset, jitter, synchronization state và thời điểm lần đồng bộ gần nhất.
- Cảnh báo khi offset vượt ngân sách.
- Phát hiện clock jump hoặc thời gian đi lùi bất thường.
- Bảo đảm container/VM lấy thời gian từ host/hạ tầng đúng cách.
- Kiểm tra time sync ở mọi region, node và môi trường DR.

Không xem NTP daemon đang chạy là bằng chứng đồng hồ đã đồng bộ. Cần quan sát trạng thái và offset thực tế.

### 7.4. Clock jump trong khi service đang chạy

Đồng hồ có thể bị step hoặc điều chỉnh trong lúc process đang hoạt động. Kiểm thử:

- Wall clock nhảy tiến qua exp.
- Wall clock nhảy lùi khiến token cũ có vẻ còn hạn.
- Clock được đồng bộ lại sau thời gian mất NTP.
- Một node có offset khác các node còn lại.

Sau clock jump, verifier không được tạo trạng thái cache active kéo dài vượt policy. Nếu hệ thống có risk lớn, có thể yêu cầu đồng bộ lại hoặc fail-closed khi clock health không đạt.

## 8. Kiểm thử phân tán và nhiều verifier

### 8.1. Mỗi verifier có thể có clock khác nhau

Trong một hệ thống nhiều API, mỗi node có thể có offset riêng. Cùng một token có thể:

- Được node A chấp nhận.
- Bị node B từ chối.
- Được node C chấp nhận lâu hơn do clock chậm hoặc leeway lớn.

Điều này gây lỗi ngẫu nhiên theo load balancing và có thể tạo cửa sổ bảo mật không đồng nhất.

### 8.2. Ma trận kiểm thử clock offset

Giả sử issuer clock được xem là mốc tham chiếu. Chạy cùng một token qua verifier với offset:

| Verifier offset | Ý nghĩa |
|---:|---|
| -120 giây | Chậm hơn issuer 2 phút |
| -30 giây | Chậm hơn issuer 30 giây |
| 0 giây | Đồng bộ |
| +30 giây | Nhanh hơn issuer 30 giây |
| +120 giây | Nhanh hơn issuer 2 phút |

Các giá trị trên chỉ là ma trận test minh họa. Chọn offset theo SLO đồng bộ thời gian thực tế và leeway được phê duyệt.

### 8.3. Consistency giữa gateway và resource server

Nếu gateway và backend cùng kiểm tra JWT:

- Cả hai cần cùng hiểu exp/nbf/iat.
- Leeway phải được quản lý theo contract, không cấu hình tùy tiện ở từng nơi.
- Không để gateway chấp nhận token mà backend từ chối hoặc ngược lại ngoài thiết kế.
- Nếu gateway cache kết quả verify, cache không được vượt exp + leeway.
- Backend vẫn phải xác minh token/claims theo ranh giới tin cậy của nó; không mặc định tin header xác minh do client gửi.

### 8.4. Cache và thời điểm hết hạn

Nếu verifier cache kết quả token active:

- Cache TTL không được kéo dài qua thời điểm token bị từ chối theo exp + leeway.
- Khi token gần hết hạn, TTL cache phải bị giới hạn theo thời gian còn lại.
- Cache status không được làm sống lại token đã revoke.
- Khi clock offset thay đổi, cache được tạo theo clock cũ cần được đánh giá.

Không chỉ test hàm validate JWT; cần test cả cache layer và request routing.

## 9. Thiết kế test deterministic

### 9.1. Inject clock thay vì chờ thời gian thật

Test thời gian nên có thể đặt clock giả lập:

~~~text
clock = FixedClock(epochSeconds = T)
result = validator.validate(token, clock)
assert result == expected
~~~

Validator nhận clock abstraction hoặc nguồn thời gian có thể thay thế trong test. Không dùng sleep để chờ exp tới vì test chậm, không ổn định và phụ thuộc scheduler.

### 9.2. Test với precision rõ ràng

Chọn precision phù hợp với implementation:

- Số nguyên giây nếu chỉ hỗ trợ integer NumericDate.
- Millisecond hoặc fractional seconds nếu parser giữ được precision đó.
- Kiểm tra chuyển đổi qua serializer/parser không làm mất phần lẻ ngoài ý muốn.

Khi test “ngay trước” và “ngay sau”, dùng epsilon nhỏ hơn đơn vị precision được hỗ trợ. Nếu implementation chỉ hỗ trợ integer seconds, dùng T-1 và T+1 thay vì một phần lẻ mà hệ thống không thể biểu diễn.

### 9.3. Kiểm tra cả issuer và verifier

Test issuer:

- exp được tạo theo giây, không phải millisecond.
- iat/nbf/exp dùng cùng nguồn clock hoặc policy rõ.
- Lifetime không vượt profile.
- Không phát hành token với khoảng hiệu lực rỗng.

Test verifier:

- So sánh boundary đúng.
- Leeway được áp dụng đúng một lần.
- Future iat và max age theo policy.
- Kiểu dữ liệu/precision được kiểm tra.
- Clock health và skew được quan sát.

### 9.4. Test độc lập với thời gian máy thật

Không để kết quả test phụ thuộc giờ hệ điều hành đang chạy. Dùng fixed clock cho unit test và một bộ integration test có thể điều chỉnh clock của thành phần test. Không thay đổi đồng hồ máy production hoặc host dùng chung chỉ để chạy test.

## 10. Ma trận kiểm thử bảo mật thời gian

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | now = exp - 1 giây, không leeway | Chấp nhận exp |
| T02 | now = exp | Từ chối |
| T03 | now = exp + 1 giây | Từ chối |
| T04 | now = nbf - 1 giây, không leeway | Từ chối |
| T05 | now = nbf | Chấp nhận nbf |
| T06 | now = nbf + 1 giây | Chấp nhận nbf |
| T07 | exp với leeway, now ngay trước exp + L | Chấp nhận |
| T08 | exp với leeway, now đúng exp + L | Từ chối |
| T09 | nbf với leeway, now ngay trước nbf - L | Từ chối |
| T10 | nbf với leeway, now đúng nbf - L | Chấp nhận |
| T11 | iat ở tương lai trong future tolerance | Xử lý theo policy đã định |
| T12 | iat vượt future tolerance | Từ chối theo policy |
| T13 | Token vượt maximum age | Từ chối theo profile |
| T14 | exp/nbf/iat là chuỗi thay vì JSON number | Từ chối nếu profile yêu cầu NumericDate |
| T15 | NumericDate dùng milliseconds | Từ chối hoặc phát hiện sai đơn vị theo validation policy |
| T16 | NumericDate quá lớn gây overflow | Từ chối có kiểm soát |
| T17 | NumericDate fractional | So sánh theo precision được hỗ trợ |
| T18 | Duplicate exp/nbf/iat | Xử lý theo semantics parser đã định, không có parser differential |
| T19 | exp trước iat | Từ chối theo profile |
| T20 | nbf bằng exp | Từ chối nếu profile yêu cầu khoảng hiệu lực dương |
| T21 | nbf sau exp | Từ chối |
| T22 | Verifier chậm hơn issuer | Kết quả đúng theo leeway/skew policy |
| T23 | Verifier nhanh hơn issuer | Kết quả đúng theo leeway/skew policy |
| T24 | Clock nhảy lùi trong khi service chạy | Không làm token cũ được chấp nhận ngoài policy |
| T25 | Clock nhảy tiến qua exp | Token bị từ chối đúng |
| T26 | Hai verifier có offset khác nhau | Sai khác được phát hiện; policy thống nhất |
| T27 | Gateway cache active qua exp + leeway | Cache bị giới hạn và không chấp nhận quá hạn |
| T28 | Leeway bị cấu hình ở hai lớp | Tổng tolerance không vượt ngân sách |
| T29 | Time source mất đồng bộ | Health alert/failure policy được thực thi |
| T30 | Token hợp lệ về thời gian nhưng sai audience | Vẫn bị từ chối |

## 11. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng now <= exp | Chấp nhận tại đúng thời điểm hết hạn | Dùng now < exp khi không có leeway |
| Dùng now > nbf | Từ chối tại đúng nbf | Chấp nhận khi now >= nbf |
| Nhầm seconds với milliseconds | Token hết hạn quá sớm hoặc quá muộn | Chuẩn hóa NumericDate theo giây |
| Parse timestamp string tự động | Các verifier có thể diễn giải khác nhau | Yêu cầu JSON number theo profile |
| Làm tròn timestamp trước khi so sánh | Boundary bị dịch chuyển | Giữ precision được hỗ trợ |
| Leeway quá lớn | Mở rộng cửa sổ replay | Chọn leeway nhỏ dựa trên đo đạc |
| Cộng leeway ở nhiều lớp | Tổng tolerance ngoài dự kiến | Quản lý một ngân sách tổng thể |
| Dùng iat như exp mà không có policy | Từ chối token hợp lệ hoặc cho qua token cũ | Định nghĩa future tolerance/max age |
| Chỉ test token hết hạn từ lâu | Bỏ sót lỗi equality boundary | Test ngay trước, tại và sau mốc |
| Dùng sleep trong test | Flaky và chậm | Inject fixed clock |
| Dùng timezone local | Lệch giờ theo môi trường | Dùng Unix time/UTC |
| Bỏ qua clock offset từng node | Kết quả khác nhau giữa verifier | Giám sát và test distributed skew |
| Cache active quá thời hạn | Token hết hạn vẫn được chấp nhận | Giới hạn cache theo exp + leeway |
| Tin iat/exp chưa xác minh | Dữ liệu attacker kiểm soát ảnh hưởng quyết định | Xác minh chữ ký/profile trước khi tin claims |

## 12. Quy trình điều tra khi phát hiện lỗi thời gian

Khi token bị chấp nhận quá hạn hoặc bị từ chối bất thường:

1. Ghi request ID, issuer, token profile và verifier/node xử lý.
2. Không ghi raw JWT; dùng token ID hoặc fingerprint đã được thiết kế an toàn.
3. Ghi thời điểm wall clock tại issuer, gateway và verifier.
4. Thu thập offset/NTP health, leeway và cấu hình time policy thực tế.
5. Kiểm tra đơn vị timestamp và precision khi phát hành/parse.
6. Kiểm tra cache active, JWKS/status cache và TTL.
7. Tái hiện bằng fixed clock với cùng NumericDate.
8. So sánh kết quả tại exp, nbf và các ranh giới leeway.
9. Xác định phạm vi node/region bị ảnh hưởng.
10. Sửa policy hoặc clock synchronization, sau đó chạy regression matrix.

Nếu token hết hạn vẫn được chấp nhận, đánh giá các request đã được xử lý trong cửa sổ đó. Nếu token hợp lệ bị từ chối do clock skew, đánh giá ảnh hưởng availability và các lần retry có thể gây thao tác trùng lặp.

## 13. Checklist kiểm thử exp, nbf và iat

**Semantics và dữ liệu**

- [ ] exp dùng điều kiện now < exp khi không có leeway.
- [ ] nbf dùng điều kiện now >= nbf khi không có leeway.
- [ ] iat được xử lý theo policy riêng, không nhầm với exp.
- [ ] NumericDate dùng giây kể từ Unix epoch UTC.
- [ ] Kiểu JSON number, precision, range và duplicate claim được kiểm tra.
- [ ] Quan hệ iat/nbf/exp và max lifetime được kiểm tra theo profile.

**Clock skew và leeway**

- [ ] Có số liệu offset thực tế của issuer/verifier.
- [ ] Leeway nhỏ, có lý do và có ngân sách tổng.
- [ ] Boundary exp + L và nbf - L được test đúng equality.
- [ ] Future iat tolerance được định nghĩa riêng.
- [ ] Clock nhanh/chậm ở cả hai hướng đều có test.
- [ ] Time source mất đồng bộ hoặc clock jump có alert/failure policy.

**Hệ thống phân tán**

- [ ] Gateway, API và worker có time policy nhất quán.
- [ ] Cache active không vượt exp + leeway.
- [ ] Mọi region/node được giám sát clock offset.
- [ ] Không có lớp cộng leeway ngoài dự kiến.
- [ ] Timezone local không tham gia phép so sánh NumericDate.

**Chất lượng test**

- [ ] Dùng fixed/injected clock, không sleep.
- [ ] Test ngay trước, đúng tại và ngay sau mỗi boundary.
- [ ] Có test fractional precision nếu implementation hỗ trợ.
- [ ] Có test seconds/milliseconds, overflow và malformed claims.
- [ ] Có regression test cho mọi lỗi đã phát hiện.

**Điều cần nhớ:** exp là ranh giới loại trừ, nbf là ranh giới bao gồm, còn iat chỉ trở thành điều kiện từ chối khi profile đặt future-time hoặc maximum-age policy. NumericDate dùng giây UTC. Leeway giảm false reject do clock skew nhưng mở rộng cửa sổ chấp nhận token; cần đo clock offset, giới hạn tolerance và kiểm thử chính xác ngay trước, tại và sau ranh giới trên mọi verifier.

## Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT), Section 2 and Section 4.1](https://www.rfc-editor.org/rfc/rfc7519): NumericDate và semantics của exp, nbf, iat.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT và validation theo profile.
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): Profile access token và claims thời gian.
- [RFC 3339 — Date and Time on the Internet: Timestamps](https://www.rfc-editor.org/rfc/rfc3339): Định dạng timestamp dạng văn bản để phân biệt với NumericDate.
- [RFC 5905 — Network Time Protocol Version 4](https://www.rfc-editor.org/rfc/rfc5905): Đồng bộ thời gian qua NTP.
- [RFC 8915 — Network Time Security for the Network Time Protocol](https://www.rfc-editor.org/rfc/rfc8915): Bảo vệ xác thực cho trao đổi NTP.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): Ghi nhận và tương quan sự kiện phục vụ điều tra.
