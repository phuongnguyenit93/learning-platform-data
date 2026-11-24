# Clock skew tolerance — Dung sai lệch đồng hồ

## 1. Vì sao dung sai thời gian là một quy tắc bảo mật?

Trong chương **Time Based Rules**, nhiều quyết định nghiệp vụ phụ thuộc vào thời gian: báo giá còn hiệu lực hay không, lượt giữ chỗ đã hết hạn chưa, một phê duyệt có được dùng để thực hiện giao dịch hay không, hoặc một yêu cầu có đến trong cửa sổ cho phép không.

Các máy tham gia xử lý không nhất thiết hiển thị cùng một thời điểm. **Clock skew tolerance** là khoảng dung sai được chính sách cho phép khi so sánh mốc thời gian giữa những đồng hồ có thể lệch nhau. Dung sai giúp hạn chế việc từ chối sai ở gần ranh giới, nhưng đồng thời có thể cho phép hành động sớm hơn hoặc muộn hơn mốc ghi trên dữ liệu.

Trong bảo mật logic nghiệp vụ, câu hỏi không chỉ là “đồng hồ lệch bao nhiêu”, mà còn là “quyền lợi nào được mở rộng khi hệ thống chấp nhận độ lệch đó”. Một giây dung sai ở token đăng nhập và một giây dung sai ở thời hạn chốt giá có thể có tác động rất khác nhau.

### Ví dụ xuyên suốt

Người dùng giữ ba slot chạy tác vụ đến `10:05:00Z`. Họ đăng nhập bằng token do một service khác phát hành. Service xác thực token có dung sai thời gian riêng để xử lý chênh lệch đồng hồ.

Nếu đội phát triển dùng luôn dung sai token để xác nhận giữ chỗ, người dùng có thể tiếp tục dùng reservation sau `10:05:00Z`, trong khi hệ thống đã bắt đầu thu hồi hoặc cấp slot cho người khác. Tương tự, nếu token có thời gian phát hành hợp lệ, điều đó không chứng minh báo giá hay phê duyệt bên trong quy trình vẫn còn hiệu lực.

Bài này tập trung vào cách xác định nguồn giờ, ranh giới chấp nhận, phạm vi dung sai và điểm ra quyết định sao cho không mở đường bỏ qua thời hạn nghiệp vụ, trạng thái, quyền theo đối tượng hoặc cơ chế chống yêu cầu lặp.

## 2. Phân biệt các khái niệm dễ bị gộp nhầm

| Khái niệm | Ý nghĩa | Hệ quả khi thiết kế |
|---|---|---|
| Clock offset | Độ lệch của một đồng hồ so với mốc tham chiếu đã chọn | Cần biết nguồn tham chiếu và mức tin cậy của phép đo |
| Clock skew | Trong bài này, chênh lệch số đọc giữa các đồng hồ tại cùng một thời điểm | Quyết định liên service cần xét chênh lệch tương đối |
| Clock drift | Độ lệch thay đổi theo thời gian do tốc độ chạy đồng hồ khác nhau | Số đo cũ không chứng minh đồng hồ hiện tại vẫn nằm trong giới hạn |
| Network latency | Thời gian dữ liệu đi qua mạng | Không đồng nhất với chênh lệch đồng hồ |
| Queueing delay | Thời gian chờ trong hàng đợi hoặc chờ tài nguyên xử lý | Không được tự đổi thành quyền gia hạn |
| Timestamp precision | Độ chi tiết của cách biểu diễn thời gian | Giây, mili giây hoặc nano giây không tự bảo đảm độ chính xác thực tế |
| Time zone | Quy tắc biểu diễn giờ địa phương | Hai chuỗi giờ địa phương khác nhau có thể chỉ cùng một instant |
| Grace period | Khoảng gia hạn do nghiệp vụ chủ động cho phép | Phải là chính sách minh bạch, không ẩn dưới tên cấu hình kỹ thuật |

Tài liệu khác có thể dùng thuật ngữ skew và drift theo cách hơi khác. Điều quan trọng là xác định đại lượng đang đo: chênh lệch số đọc hay chênh lệch tốc độ đồng hồ.

Một request đến muộn do mạng vẫn đến muộn theo mốc tiếp nhận của server. Muốn chấp nhận theo một mốc sớm hơn, hệ thống phải có bằng chứng tiếp nhận đáng tin cậy và hợp đồng nghiệp vụ tương ứng. Trường `sentAt` do client tự khai báo không tạo ra bằng chứng đó.

### Thời điểm tuyệt đối và khoảng thời gian đã trôi qua

- Dùng thời điểm tuyệt đối có ngữ nghĩa rõ để kiểm tra hạn như `expires_at` hoặc `approval_valid_until`.
- Dùng nguồn đo khoảng thời gian phù hợp để đo timeout nội bộ hoặc ngân sách xử lý của một tiến trình.
- Không so sánh trực tiếp hai giá trị chỉ vì cả hai đều là số nguyên: chúng có thể khác đơn vị, khác mốc gốc hoặc khác loại đồng hồ.

Chuẩn hóa thời điểm tuyệt đối thành `Instant` hoặc kiểu dữ liệu tương đương giúp giảm nhầm lẫn biểu diễn. Việc dùng UTC không tự đồng bộ đồng hồ giữa các máy.

## 3. Viết rõ khoảng hợp lệ và hai phía dung sai

Giả sử một quyền có thời điểm bắt đầu `S` và thời điểm kết thúc `E`. Trong mô hình của bài này, khoảng hợp lệ gốc là nửa mở:

```text
S <= now < E
```

Nghĩa là đúng tại `S` thì được bắt đầu; đúng tại `E` thì đã hết hạn. Quy tắc này cần thống nhất ở API, worker, cơ sở dữ liệu và kiểm thử.

Nếu chính sách cho phép:

- `L_early`: lượng thời gian có thể chấp nhận trước mốc bắt đầu.
- `L_late`: lượng thời gian có thể chấp nhận sau mốc kết thúc.

thì điều kiện được mô hình hóa thành:

```text
S - L_early <= now < E + L_late
```

Hai dung sai không nhất thiết bằng nhau. Một chức năng có thể cho phép kết thúc muộn một ít nhưng tuyệt đối không được mở sớm. Đặt cùng một biến `clockSkew` cho mọi phép kiểm tra mà không xác định hai phía sẽ che giấu sự khác biệt này.

### Ví dụ ranh giới

Giả sử `S = 10:00:00Z`, `E = 10:05:00Z`, `L_early = 2 giây` và `L_late = 2 giây`. Các con số chỉ để minh họa công thức, không phải giá trị nên áp dụng chung cho hệ thống thực tế.

| Số đọc `now` tại bên kiểm tra | Kết quả theo mô hình |
|---|---|
| `09:59:57.999Z` | Từ chối vì sớm hơn cận dưới |
| `09:59:58.000Z` | Chấp nhận ở cận dưới đã nới |
| `10:00:00.000Z` | Chấp nhận |
| `10:05:00.000Z` | Chấp nhận nhờ dung sai phía kết thúc |
| `10:05:01.999Z` | Chấp nhận trong cửa sổ nới |
| `10:05:02.000Z` | Từ chối ở cận trên đã nới |

Chấp nhận ở `10:05:00Z` trong ví dụ là hệ quả có chủ đích của `L_late`, không phải thuộc tính mặc định của mọi thời hạn. Với một deadline nghiệp vụ không có gia hạn, điều kiện vẫn là `now < E`.

### Độ chính xác phải đi cùng quy tắc làm tròn

Nếu thời hạn được lưu theo giây nhưng một service so sánh theo mili giây, phải xác định cách chuyển đổi. Không tùy tiện làm tròn thời gian hiện tại xuống theo giây để “giảm lỗi”, vì việc đó có thể tạo thêm một cửa sổ chấp nhận.

Kiểm tra giây và mili giây ngay tại biên chuyển đổi. Timestamp sai đơn vị không được tự thử nhiều cách diễn giải đến khi tìm được một giá trị hợp lệ. Dữ liệu thời gian không phân tích được hoặc vượt miền hỗ trợ phải bị xử lý như dữ liệu không hợp lệ theo hợp đồng.

## 4. Tính phần mở rộng thực tế, không chỉ nhìn giá trị cấu hình

Để phân tích, gọi `t` là thời gian tham chiếu lý tưởng và số đọc của máy `i` là:

```text
C_i(t) = t + delta_i(t)
```

Trong một khoảng vận hành giả định, nếu:

```text
|delta_issuer| <= epsilon_issuer
|delta_validator| <= epsilon_validator
```

thì chênh lệch số đọc giữa hai máy có thể lên đến:

```text
|C_issuer(t) - C_validator(t)|
  <= epsilon_issuer + epsilon_validator
```

Hai máy đều “lệch không quá một giây” so với cùng tham chiếu không có nghĩa là chúng lệch nhau không quá một giây. Một máy nhanh một giây và máy kia chậm một giây có thể chênh nhau hai giây.

Các cận trên này là giả định để suy luận. Số đo trung bình hoặc percentile trong giám sát không tự biến thành bảo đảm tuyệt đối cho mọi thời điểm, đặc biệt khi mất đồng bộ hoặc sau một thay đổi lớn của đồng hồ.

### Trường hợp A: deadline là một instant đã được ấn định

Giả sử `E` là deadline tuyệt đối của nghiệp vụ, độc lập với đồng hồ bên phát hành. Bên kiểm tra chấp nhận khi:

```text
C_validator(t) < E + L_late
```

Nếu đồng hồ kiểm tra có thể chậm tối đa `epsilon_validator`, thời điểm thực được chấp nhận muộn có thể tiến gần:

```text
E + L_late + epsilon_validator
```

Vì vậy `L_late = 0` không chứng minh hệ thống có độ chính xác tuyệt đối theo thời gian tham chiếu. Nó chỉ nói rằng chính sách không chủ động cộng thêm gia hạn vào số đọc đã chọn.

### Trường hợp B: deadline được tạo từ đồng hồ bên phát hành

Giả sử bên phát hành tạo hạn bằng số đọc của nó tại lúc phát hành `t0`:

```text
E = C_issuer(t0) + TTL
```

Bên kiểm tra chấp nhận nếu `C_validator(t) < E + L_late`. Thay vào mô hình:

```text
t < t0 + TTL + L_late + delta_issuer(t0) - delta_validator(t)
```

Trong các giả định cận trên đã nêu, tuổi thực của quyền khi còn có thể được chấp nhận có thể tiến gần:

```text
TTL + L_late + epsilon_issuer + epsilon_validator
```

Ví dụ TTL ba mươi giây, dung sai phía kết thúc hai giây, bên phát hành nhanh một giây và bên kiểm tra chậm một giây: quyền có thể còn được chấp nhận gần tuổi thực ba mươi bốn giây. Đây là phép suy ra từ mô hình, không phải một bảo đảm về độ lệch của hạ tầng cụ thể.

Hai trường hợp có mốc gốc khác nhau nên không được cộng mọi thành phần một cách máy móc. Trước khi tính ngân sách bảo mật, cần biết deadline là instant cố định, được tạo bằng đồng hồ nào hay được suy ra từ một sự kiện nào.

Phía bắt đầu cũng cần phân tích tương tự: đồng hồ kiểm tra chạy nhanh và `L_early` cùng làm tăng khả năng chấp nhận trước mốc gốc. Nếu nghiệp vụ cấm thực hiện sớm, dung sai phía bắt đầu cần được xét riêng.

## 5. Chọn phạm vi và ngân sách dung sai

Không có một giá trị dung sai phù hợp cho mọi module, mọi endpoint và mọi loại quyền lợi. Quyết định cần dựa trên cả mức sai lệch có thể kiểm soát được và tác động của cửa sổ được nới.

Một quy trình thiết kế có thể gồm:

1. Xác định các máy và nguồn giờ tham gia tạo, kiểm tra, thực thi điều kiện.
2. Xác định cận sai lệch cần đáp ứng, cách đo, tuổi của số đo và hành vi khi không còn tin được cận đó.
3. Xác định mức chấp nhận sớm hoặc muộn tối đa mà nghiệp vụ cho phép.
4. Kiểm tra phần mở rộng thực tế theo mô hình mốc gốc và số lần chuyển quyền qua service.
5. Cấu hình riêng theo loại điều kiện, có giới hạn, phiên bản và dấu vết thay đổi.

Nếu mức lệch hạ tầng vượt điều nghiệp vụ chấp nhận, tăng dung sai không tự giải quyết được mâu thuẫn. Có thể cần đồng bộ giờ tốt hơn, tập trung điểm ra quyết định, thay đổi quy trình tiếp nhận hoặc từ chối tạm thời thao tác phụ thuộc mốc đó.

### Những loại chính sách cần tách

| Loại điều kiện | Cách xem xét dung sai |
|---|---|
| Cửa sổ hiệu lực của token xác thực | Có thể có dung sai theo chính sách xác thực và ngữ nghĩa loại token |
| Hạn xác nhận reservation | Dựa vào nguồn giờ và thời điểm quyết định của nghiệp vụ; không kế thừa cấu hình token |
| Hạn báo giá | Nếu cho gia hạn thì phải xác định cả giá và điều kiện được giữ trong khoảng đó |
| Thời gian bắt đầu chương trình | Nới phía bắt đầu có thể mở quyền lợi trước thời điểm công bố |
| Thời gian hiệu lực phê duyệt | Không để dung sai bỏ qua phiên bản, đối tượng hoặc điều kiện thu hồi |
| Cửa sổ chống replay của thông điệp | Phải kết hợp định danh dùng một lần hoặc cơ chế chống lặp; timestamp không đủ |
| Timeout nội bộ | Dựa trên ngân sách xử lý và nguồn đo thời gian đã trôi qua phù hợp |

Các invariant chính sách nên gồm:

- Dung sai không âm và không vượt giới hạn cấu hình đã được phê chuẩn.
- Client không được truyền một giá trị dung sai để server áp dụng trực tiếp.
- Nếu có cấu hình theo tenant, quyền thay đổi và giới hạn tối đa vẫn do hệ thống kiểm soát.
- Không tự tăng dung sai theo số lần retry hoặc theo độ trễ của request hiện tại.
- Không sửa deadline gốc mỗi lần kiểm tra.
- Cửa sổ thời gian hợp lệ không thay thế quyền theo đối tượng, trạng thái hoặc phê duyệt.

### Gia hạn nghiệp vụ phải có tên và điều kiện rõ

Nếu khách hàng được thêm ba mươi giây để hoàn tất thanh toán sau một mốc, hãy mô hình hóa đây là grace period với điều kiện áp dụng cụ thể. Có thể lưu `original_deadline`, `grace_until`, `grace_policy_version` và quyết định áp dụng.

Không nên giấu quyền gia hạn đó trong một cấu hình chung tên `clock_skew_seconds`. Người vận hành có thể tăng cấu hình để chữa lỗi đồng bộ mà vô tình thay đổi quyền lợi tài chính hoặc quyền giữ tài nguyên.

## 6. Nguồn thời gian, xác thực và ranh giới tin cậy

Server phải xác định nguồn giờ dùng để ra quyết định. Nguồn đó có thể là đồng hồ của service được giám sát, đồng hồ cơ sở dữ liệu hoặc một thành phần thời gian được thiết kế riêng. Không nguồn nào trở thành chính xác tuyệt đối chỉ vì được gọi từ phía server.

Client có thể gửi `clientTime`, múi giờ hoặc mốc đã hiển thị để hỗ trợ trải nghiệm và điều tra. Những trường đó không được quyết định việc một reservation còn hạn, một phê duyệt còn hiệu lực hoặc một giao dịch được chấp nhận trước deadline.

Tương tự, dữ liệu được ký chỉ chứng minh một nguồn giữ khóa đã tạo nội dung theo cơ chế xác minh tương ứng. Nó không tự chứng minh đồng hồ nguồn đúng, thời hạn phù hợp chính sách hoặc người gọi còn quyền trên đối tượng.

### Ví dụ với JWT

RFC 7519 quy định kiểm tra `exp` theo điều kiện thời gian hiện tại nằm trước hạn hết hiệu lực; `nbf` cho phép bắt đầu tại hoặc sau mốc chưa-được-dùng-trước. RFC cũng cho phép một khoảng dung sai nhỏ cho chênh lệch đồng hồ. Đây không phải yêu cầu mọi ứng dụng phải sử dụng một số giây cố định. [RFC 7519, mục 4.1.4–4.1.5](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.4).

Trong ứng dụng, xác thực token và quyết định nghiệp vụ là hai bước có chính sách riêng. Token vượt qua kiểm tra thời gian không cho phép bỏ qua hạn báo giá, trạng thái đã hủy hoặc kiểm tra chủ sở hữu reservation.

Nếu dùng `iat` để giới hạn tuổi tối đa của token hoặc thông điệp, phải định nghĩa thêm điều kiện chấp nhận thời điểm phát hành trong tương lai và tuổi tối đa. Chỉ kiểm tra `exp` có thể không đáp ứng chính sách tuổi tối đa mà ứng dụng mong muốn. Không được tin `iat` hoặc `exp` từ một payload chưa qua các bước xác minh token bắt buộc.

### Tránh cộng dồn qua các tầng

Giả sử gateway chấp nhận `E + 2 giây`. Nếu nó tạo quyền nội bộ mới bằng cách lấy hạn đã nới rồi cộng tiếp hai giây, service phía sau có thể lại tiếp tục cộng. Quyền truy cập bị kéo dài qua mỗi bước dù không ai chủ đích cho gia hạn dài như vậy.

Giữ deadline gốc và chính sách của từng điều kiện. Nếu cần cấp một quyền mới cho tác vụ nội bộ, đó phải là quyết định cấp quyền có thời hạn riêng, đúng mục đích, đúng đối tượng và có khả năng truy nguyên; không phải kết quả tự động của việc token cũ vừa được chấp nhận nhờ dung sai.

Các service độc lập kiểm tra cùng deadline gốc với cùng dung sai không tự tạo phép cộng dồn số học. Rủi ro cộng dồn xuất hiện khi một tầng sửa hạn, tái cấp quyền hoặc coi kết quả kiểm tra trước là quyền bỏ qua điều kiện ở bước sau.

## 7. Đặt phép kiểm tra thời gian tại điểm quyết định nghiệp vụ

Một điều kiện đúng lúc request đi vào API chưa chắc còn đúng khi tài nguyên được thay đổi. Request có thể chờ khóa, chờ hàng đợi hoặc chạy nhiều bước kiểm tra khác.

Luồng dễ sai:

```text
10:04:59.800  API đọc giờ và kết luận reservation còn hạn.
10:04:59.900  API bắt đầu chờ khóa allocation.
10:05:00.000  Reservation hết hạn theo chính sách.
10:05:01.000  API lấy được khóa và xác nhận bằng kết quả kiểm tra cũ.
```

Nếu hợp đồng yêu cầu reservation còn hạn tại lúc ra quyết định trên trạng thái đã khóa, kết quả cuối cùng phải bị từ chối. Dung sai đồng hồ không phải lý do để tái sử dụng vô thời hạn một lần kiểm tra trước đó.

### Xác định thời điểm nào là thời điểm có ý nghĩa

Nhóm phát triển phải chọn và công bố ngữ nghĩa, chẳng hạn:

- Request được **tiếp nhận bền vững trước hạn** thì được đưa vào xử lý, dù hoàn tất sau đó.
- Quyết định xác nhận trên **trạng thái hiện hành đã được bảo vệ** phải diễn ra trước hạn.
- Tài nguyên hoặc hành động bên ngoài phải **thực sự hoàn tất trước hạn**.

Ba hợp đồng này khác nhau. Một timestamp ở controller không chứng minh tiếp nhận bền vững; một phép kiểm tra trong transaction không tự chứng minh commit hoặc hành động bên ngoài hoàn tất trước một instant tuyệt đối.

Trong ví dụ reservation, chọn hợp đồng thứ hai: thời gian quyết định được lấy sau khi đã giành quyền xử lý trạng thái cần thiết, và reservation phải còn ở trạng thái được phép xác nhận.

### Ví dụ giao dịch với PostgreSQL

PostgreSQL phân biệt thời gian bắt đầu transaction, bắt đầu statement và thời gian tại lúc gọi hàm. `CURRENT_TIMESTAMP` cùng `now()` gắn với lúc bắt đầu transaction; `statement_timestamp()` gắn với lúc bắt đầu statement; `clock_timestamp()` lấy thời gian tại lần gọi. Một transaction đã chờ lâu cần chọn đúng ngữ nghĩa thay vì giả định mọi hàm đều trả thời gian sau lúc lấy khóa. [PostgreSQL, Current Date/Time](https://www.postgresql.org/docs/current/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Phác thảo dưới đây không áp dụng gia hạn nghiệp vụ:

```sql
BEGIN;

SELECT id, tenant_id, owner_id, state, expires_at, version
FROM reservation
WHERE tenant_id = :verified_tenant_id
  AND id = :reservation_id
FOR UPDATE;

-- Ứng dụng kiểm tra quyền theo đối tượng và các guard trên hàng đã khóa.
-- Sau khi có các khóa nghiệp vụ cần thiết, lấy mốc quyết định mới:
SELECT clock_timestamp() AS decision_at;

-- :decision_at được bind từ kết quả server vừa lấy,
-- tuyệt đối không lấy từ body hoặc header do client cung cấp.
UPDATE reservation
SET state = 'CONFIRMED',
    confirmed_at = :decision_at,
    version = version + 1
WHERE tenant_id = :verified_tenant_id
  AND id = :reservation_id
  AND state = 'RESERVED'
  AND version = :locked_version
  AND expires_at > :decision_at;

-- Bắt buộc kiểm tra affected_rows = 1 trước bước ghi hiệu ứng tiếp theo.
-- Ghi kết quả idempotency, audit và outbox trong cùng transaction nếu có.
COMMIT;
```

Đây là khung giao dịch có nhánh điều khiển ở ứng dụng. Không chạy tiếp như đã xác nhận nếu không có hàng hoặc số hàng cập nhật khác một. Mọi lỗi làm thất bại thay đổi phải rollback các ghi liên quan theo cấu hình transaction.

Việc lấy thời gian mới sau khóa giải quyết lỗi dùng mốc cũ trong ví dụ, nhưng không sửa được đồng hồ cơ sở dữ liệu đang lệch ngoài giới hạn tin cậy. Nếu thao tác còn cần lấy khóa khác sau khi đo giờ, cần đặt lại điểm đo hoặc thay đổi thiết kế để đáp ứng hợp đồng đã chọn.

Giới hạn thời gian transaction và số bước sau quyết định giúp giảm khoảng cách giữa quyết định với commit. Nếu yêu cầu thực sự là commit hoặc hoàn tất hành động bên ngoài trước hạn, cần thiết kế cơ chế đáp ứng yêu cầu đó; không đổi tên `decision_at` thành `completed_at` để giả lập bằng chứng.

## 8. Biểu diễn cửa sổ thời gian trong Java

Tách logic cửa sổ thành một thành phần có đầu vào và ranh giới rõ giúp tránh các phép cộng trừ rải rác khắp service. Dung sai phải đến từ policy phía server, không phải request.

Ví dụ sau mô hình hóa khoảng nửa mở đã nêu. Các kiểu `record` cần phiên bản Java hỗ trợ record:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

record TimeWindow(Instant startsAt, Instant expiresAt) {
    TimeWindow {
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(expiresAt);
        if (!startsAt.isBefore(expiresAt)) {
            throw new IllegalArgumentException("Invalid time window");
        }
    }
}

record SkewPolicy(Duration early, Duration late) {
    SkewPolicy {
        Objects.requireNonNull(early);
        Objects.requireNonNull(late);
        if (early.isNegative() || late.isNegative()) {
            throw new IllegalArgumentException("Negative tolerance");
        }
    }

    static SkewPolicy bounded(
            Duration early, Duration late, Duration configuredMaximum) {
        Objects.requireNonNull(configuredMaximum);
        if (configuredMaximum.isNegative()) {
            throw new IllegalArgumentException("Invalid maximum");
        }
        SkewPolicy policy = new SkewPolicy(early, late);
        if (early.compareTo(configuredMaximum) > 0
                || late.compareTo(configuredMaximum) > 0) {
            throw new IllegalArgumentException("Tolerance exceeds maximum");
        }
        return policy;
    }
}

final class TimeWindows {
    private TimeWindows() {}

    static boolean contains(
            Instant now, TimeWindow window, SkewPolicy policy) {
        Objects.requireNonNull(now);
        Objects.requireNonNull(window);
        Objects.requireNonNull(policy);
        try {
            Instant lower = window.startsAt().minus(policy.early());
            Instant upper = window.expiresAt().plus(policy.late());
            return !now.isBefore(lower) && now.isBefore(upper);
        } catch (DateTimeException | ArithmeticException ex) {
            throw new IllegalArgumentException("Time range overflow", ex);
        }
    }
}
```

Trong triển khai thực, đường nạp cấu hình phải sử dụng kiểm tra giới hạn như `bounded`, đồng thời giới hạn các mốc thời gian và TTL theo loại dữ liệu. Constructor chỉ kiểm tra không âm không đủ để biến mọi giá trị dung sai thành hợp lệ. Nếu cần giới hạn riêng phía sớm và muộn, thể hiện hai mức tối đa trong policy.

Hàm `contains` chỉ trả lời một câu hỏi về cửa sổ thời gian. Nó không xác minh chữ ký token, không kiểm tra tenant, không lấy khóa và không xác định một thao tác còn được phép trong state machine hay không.

### Sử dụng đồng hồ có thể thay thế trong kiểm thử

Inject `Clock` hoặc một giao diện thời gian tương đương thay vì gọi giờ hệ thống rải rác. Tại điểm quyết định, lấy một `Instant` và dùng nhất quán cho các điều kiện cần cùng một mốc.

Ví dụ phác thảo service chọn đồng hồ của ứng dụng làm nguồn thời gian có thẩm quyền theo hợp đồng:

```java
@Transactional
public Confirmation confirm(Actor actor, UUID reservationId) {
    Reservation reservation = reservations.lockInTenant(
        actor.tenantId(), reservationId
    ).orElseThrow(NotFoundException::new);

    policy.requireCanConfirm(actor, reservation);
    policy.requireCurrentApprovalIfNeeded(reservation);
    timeHealth.requireWithinAcceptedBounds();

    // Lấy sau các bước có thể chờ và sau khi đã có khóa cần thiết.
    Instant decisionAt = clock.instant();

    if (reservation.state() != RESERVED) {
        throw new InvalidTransitionException();
    }
    if (!decisionAt.isBefore(reservation.expiresAt())) {
        throw new ReservationExpiredException();
    }

    reservations.confirmOrThrow(reservation, decisionAt);
    audit.recordConfirmation(actor, reservation, decisionAt);
    return Confirmation.of(reservation.id(), decisionAt);
}
```

Các repository và policy là giao diện minh họa. Chúng phải bảo đảm kiểm tra phiên bản, rollback và tính nhất quán của phê duyệt cùng các guard cần thiết. `Clock` là một phụ thuộc phần mềm; việc inject nó không tự chứng minh nguồn giờ đang đồng bộ. `timeHealth` biểu diễn cơ chế kiểm soát sức khỏe nguồn giờ cần được thiết kế thực sự.

Nếu hợp đồng chọn đồng hồ cơ sở dữ liệu, `decisionAt` phải đến từ nguồn đó theo quy trình tương ứng, thay vì trộn một kiểm tra bằng giờ ứng dụng với một cập nhật bằng giờ cơ sở dữ liệu mà không phân tích sai lệch giữa chúng.

Ví dụ không cộng `L_late` vào reservation vì chính sách đã chọn không có gia hạn. Dung sai riêng của token xác thực không xuất hiện trong phép kiểm tra deadline này.

## 9. Đồng hồ đo thời lượng không thay thế deadline tuyệt đối

Đối với timeout nội bộ trong một JVM, có thể đo chênh lệch bằng `System.nanoTime()`. Theo Java API, giá trị này dùng để đo thời gian đã trôi qua, có mốc gốc tùy ý trong JVM và không phải timestamp lịch. [Java SE 21, System.nanoTime()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

```java
long started = System.nanoTime();
long timeoutNanos = Duration.ofSeconds(2).toNanos();

// ... xử lý một bước nội bộ ...

if (System.nanoTime() - started >= timeoutNanos) {
    throw new ProcessingTimeoutException();
}
```

Không lưu `nanoTime()` làm `expires_at`, không gửi nó sang JVM khác để so sánh và không dùng nó như giờ UTC. Giá trị thời lượng phải có giới hạn hợp lý và được kiểm tra trước khi chuyển đổi đơn vị.

Hai loại phép đo phục vụ hai yêu cầu khác nhau:

| Câu hỏi | Nguồn dữ liệu phù hợp |
|---|---|
| Bước xử lý cục bộ đã chạy quá hai giây chưa? | Chênh lệch từ nguồn đo thời lượng cục bộ |
| Reservation còn hạn tại mốc quyết định không? | Deadline tuyệt đối và nguồn giờ có thẩm quyền của nghiệp vụ |
| Request đã được tiếp nhận bền vững trước deadline chưa? | Bản ghi tiếp nhận đáng tin cậy cùng chính sách về mốc đó |
| Tác vụ bên ngoài đã dừng chưa? | Bằng chứng trạng thái runtime, không chỉ một timeout đã trôi qua |

Nếu chuyển một deadline tuyệt đối thành thời lượng chờ cục bộ để tối ưu lập lịch, vẫn phải giữ deadline gốc và kiểm tra theo hợp đồng lúc hành động. Phép chuyển đổi không được biến một quyền đã hết hạn hoặc bị thu hồi thành quyền vẫn còn dùng được.

Không giả định mọi môi trường xử lý việc tạm dừng máy hoặc JVM giống nhau. Những tình huống suspend, khôi phục máy ảo và mất nguồn giờ cần được đưa vào giả định vận hành cùng các kiểm thử liên quan của hệ thống thực tế.

## 10. Retry, hàng đợi và state machine ở gần thời hạn

### Timestamp hợp lệ không ngăn replay

Một thông điệp có timestamp nằm trong cửa sổ cho phép có thể bị gửi lại nhiều lần ngay trong cửa sổ đó. Cần thêm định danh thao tác, nonce dùng một lần, ràng buộc duy nhất hoặc cơ chế idempotency phù hợp.

Với idempotency, cần phân biệt:

- Nếu ý định đã commit thành công, retry có thể lấy lại kết quả theo chính sách truy cập hiện tại mà không thực hiện hiệu ứng mới.
- Nếu ý định chưa được chấp nhận hoặc chưa được thực hiện, việc xử lý sau hạn phụ thuộc hợp đồng tiếp nhận, không tự được miễn kiểm tra thời gian.
- Một idempotency key mới không làm reservation hết hạn trở lại hợp lệ.
- Cùng key nhưng khác đối tượng hoặc khác nội dung phải bị xử lý như xung đột ý định.

Không gia hạn `expires_at` mỗi lần nhận retry. Nếu cần gia hạn thật, đó phải là hành động riêng có quyền, điều kiện, giới hạn số lần và dấu vết kiểm toán.

### Hàng đợi có hai hợp đồng thường gặp

**Xử lý theo thời điểm thực thi:** worker lấy trạng thái hiện hành, quyền cần thiết và nguồn giờ có thẩm quyền rồi kiểm tra trước khi ra quyết định. Thông điệp nằm trong hàng đợi lâu có thể bị từ chối khi xử lý.

**Xử lý theo thời điểm tiếp nhận:** server ghi bền vững một quyết định tiếp nhận trước hạn, gắn đúng actor, nội dung và operation ID. Worker được phép hoàn tất sau đó trong phạm vi cam kết đã được chấp nhận.

Hợp đồng thứ hai còn cần xác định điều gì xảy ra nếu người dùng hủy, quyền bị thu hồi hoặc tài nguyên thay đổi sau khi tiếp nhận. Không phải mọi guard đều có thể “đóng băng” tại thời điểm tiếp nhận. Những quyền nào được cam kết và những điều kiện nào phải kiểm tra lại cần được quy định rõ.

Không dùng `submittedAt` do client gửi hoặc timestamp của message broker một cách mặc định để chứng minh ứng dụng đã chấp nhận nghiệp vụ trước hạn.

### Job hết hạn chỉ là bộ xử lý chuyển trạng thái

Một reservation có thể vẫn mang trạng thái `RESERVED` sau `expires_at` vì job dọn chưa chạy. Endpoint xác nhận phải tự kiểm tra thời hạn; trạng thái chưa được dọn không chứng minh quyền vẫn hợp lệ.

Ngược lại, khi reservation đã chuyển sang `EXPIRED`, một lần đồng hồ chạy lùi không được làm nó tự hồi sinh. Luôn kiểm tra cả trạng thái và thời hạn.

Khi job hết hạn cạnh tranh với xác nhận, chúng phải dùng cùng định nghĩa ranh giới và cơ chế bảo vệ chuyển trạng thái. Chỉ một kết quả được commit theo policy; không vừa xác nhận sử dụng vừa trả tài nguyên về pool.

### Lease hết hạn không chứng minh bên sử dụng đã ngừng

Với tài nguyên phân tán, tiến trình cũ có thể tiếp tục hoạt động sau khi hệ thống coi lease đã hết hạn. Dung sai đồng hồ càng không phải bằng chứng rằng có thể cấp lại an toàn.

Nếu cần chống bên sử dụng cũ, phải có cơ chế như thu hồi quyền truy cập có hiệu lực hoặc fencing/generation được thành phần thực sự kiểm soát tài nguyên kiểm tra. Việc tăng hoặc giảm dung sai chỉ thay đổi đánh giá thời gian, không tự ngăn một tiến trình cũ ghi tiếp vào tài nguyên.

## 11. Đồng hồ bất thường, quan sát và chính sách khi mất độ tin cậy

Nguồn giờ có thể bị điều chỉnh tiến, điều chỉnh lùi hoặc mất thông tin đồng bộ. Một số đo offset tốt ở thời điểm khởi động không đủ bảo đảm cho toàn bộ vòng đời service.

Các tín hiệu nên theo dõi gồm:

- Ước lượng độ lệch, sai số của phép đo và thời điểm đồng bộ gần nhất.
- Trạng thái nguồn tham chiếu và các sự kiện thay đổi đồng hồ đáng kể.
- Chênh lệch giữa các nguồn tham gia cùng một quyết định.
- Số quyết định được chấp nhận chỉ nhờ dung sai, tách phía bắt đầu và kết thúc.
- Tỷ lệ từ chối gần ranh giới, độ trễ hàng đợi và retry để phân biệt nguyên nhân.
- Phiên bản chính sách, giá trị dung sai và thay đổi cấu hình đang áp dụng trên từng nhóm instance.

Không suy ra offset đáng tin cậy bằng cách lấy `serverTime - clientTime` của request bất kỳ. Client có thể khai sai và thời gian mạng hai chiều không nhất thiết đối xứng. Số liệu đó chỉ nên là một tín hiệu phụ trong phạm vi đã xác định.

### Khi biết một khoảng bất định của thời gian

Nếu hệ thống thực sự có cơ sở bảo đảm thời gian tham chiếu nằm trong khoảng:

```text
[clock_reading - uncertainty, clock_reading + uncertainty]
```

và yêu cầu an toàn là không hành động sớm hơn `S` hay tại/sau `E`, điều kiện bảo thủ có thể là:

```text
clock_reading - uncertainty >= S
clock_reading + uncertainty < E
```

Cách này thu hẹp vùng chấp nhận để tránh vùng chưa chắc chắn. Nó phục vụ mục tiêu khác với leeway vốn nới vùng chấp nhận nhằm giảm từ chối sai. Cả hai đều cần một mô hình và nguồn dữ liệu có độ tin cậy phù hợp; gán một số nhỏ cho `uncertainty` không tạo ra bảo đảm thực tế.

Nếu hợp đồng nghiệp vụ quy định sử dụng số đọc của một nguồn cụ thể thay vì thời gian tham chiếu lý tưởng, phải nói rõ điều đó. Hệ thống không nên hứa hẹn độ chính xác tuyệt đối mà hạ tầng chưa chứng minh được.

### Hành vi khi mất độ tin cậy phải được định nghĩa trước

| Tình trạng | Cách xử lý cần cân nhắc theo chính sách |
|---|---|
| Sai lệch trong giới hạn được chấp nhận, số đo còn mới | Dùng nguồn giờ và dung sai đã cấu hình |
| Độ lệch vượt giới hạn hoặc không còn biết cận sai số | Chặn hoặc chuyển tuyến các quyết định phụ thuộc deadline quan trọng |
| Nguồn giờ của một instance bất thường | Loại instance khỏi luồng quyết định liên quan và điều tra |
| Hàng đợi chậm nhưng nguồn giờ vẫn tốt | Áp dụng hợp đồng tiếp nhận/thực thi; không tăng dung sai đồng hồ để che độ trễ |
| Nhiều phiên bản dung sai cùng hoạt động | Kiểm soát triển khai, xác định policy của quyết định và tránh cho client chọn node có cửa sổ rộng hơn |

Mức độ dừng hoặc tiếp tục cần phù hợp tác động nghiệp vụ. Đối với thao tác chỉ đọc có thể có hành vi khác thao tác xác nhận giá hoặc cấp phát tài nguyên. Không tự chuyển deadline sang dùng giờ client khi nguồn giờ server gặp lỗi.

### Dữ liệu audit cho quyết định thời gian

Ghi nhận operation ID, đối tượng và tenant, trạng thái/phiên bản liên quan, nguồn giờ, `decision_at`, deadline gốc, dung sai từng phía, phiên bản policy và mã quyết định. Nếu áp dụng gia hạn nghiệp vụ, ghi riêng lý do và thời hạn gia hạn.

Giữ dữ liệu đủ giải thích việc chấp nhận gần ranh giới mà không ghi token hoặc thông tin xác thực bí mật. Timestamp trong audit hỗ trợ truy nguyên; tự nó không chứng minh đồng hồ đã đúng ở thời điểm đó.

## 12. Kiểm thử các ranh giới và tình huống lạm dụng

Kiểm thử bằng thời gian điều khiển được, không chờ bằng `sleep` để cố rơi vào một mili giây cụ thể. Tách kiểm thử công thức cửa sổ khỏi kiểm thử transaction, quyền, state machine và phục hồi.

### Bảng ranh giới cho cửa sổ nửa mở

Gọi `lower = S - L_early`, `upper = E + L_late`. Chọn `tick` là độ phân giải kiểm thử phù hợp với dữ liệu được lưu.

| Thời điểm kiểm tra | Kết quả |
|---|---|
| `lower - tick` | Từ chối |
| `lower` | Chấp nhận |
| Một điểm nằm giữa hai cận | Chấp nhận |
| `upper - tick` | Chấp nhận nếu điểm đó vẫn nằm trong cửa sổ |
| `upper` | Từ chối |
| `upper + tick` | Từ chối |

Kiểm thử riêng trường hợp hai dung sai bằng không, chỉ nới một phía và cửa sổ ngắn hơn các khoảng bất định cần xét. Với Java có thể dùng `Clock.fixed` cho từng mốc hoặc một clock kiểm thử được điều khiển; việc thay đồng hồ của test không được làm thay đổi cấu hình thời gian của máy dùng chung.

### Ma trận lỗi logic và cạnh tranh

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Client gửi thời gian chậm hơn để giữ reservation còn hạn | Không ảnh hưởng nguồn giờ quyết định của server |
| Client gửi dung sai lớn, số âm hoặc khác đơn vị | Không được dùng làm policy; dữ liệu sai bị từ chối theo hợp đồng |
| Token còn được chấp nhận nhờ dung sai nhưng báo giá đã hết hạn | Không thực hiện giao dịch theo giá cũ ngoài chính sách |
| Thay đổi tenant hoặc allocation trong request có thời gian hợp lệ | Vẫn kiểm tra quyền theo đối tượng |
| Thiếu phê duyệt hoặc phê duyệt bị thu hồi trong cửa sổ thời gian | Không được bỏ qua guard nghiệp vụ |
| Request kiểm tra trước hạn nhưng chờ khóa đến sau hạn | Quyết định dùng mốc đúng theo hợp đồng, không dùng kết quả cũ |
| Transaction bắt đầu trước hạn nhưng lấy khóa sau hạn | Không nhầm giờ bắt đầu transaction với giờ quyết định mới |
| Job hết hạn chưa chạy | Endpoint vẫn chặn xác nhận quá hạn |
| Job hết hạn và xác nhận chạy đồng thời | Chỉ một chuyển trạng thái hợp lệ được commit; sức chứa không bị sử dụng trùng |
| Đồng hồ nhảy lùi sau khi trạng thái đã `EXPIRED` | Reservation không hồi sinh |
| Đồng hồ mất đồng bộ ngoài cận chấp nhận | Thực hiện đúng chính sách nguồn giờ không đáng tin, không tự mở rộng cửa sổ |
| Retry một ý định đã thành công sau deadline | Không tạo hiệu ứng mới; trả kết quả chỉ khi quyền truy cập hiện tại cho phép |
| Ý định chưa được chấp nhận được gửi lại sau deadline | Không được miễn kiểm tra chỉ vì dùng lại key |
| Cùng thông điệp hợp lệ được gửi nhiều lần trong cửa sổ | Cơ chế chống replay/idempotency ngăn lặp hiệu ứng |
| Gateway rồi worker lần lượt xử lý cùng deadline | Không tự cộng dung sai vào deadline qua từng tầng |
| Một instance có cấu hình dung sai lớn hơn | Phát hiện sai cấu hình; không để routing trở thành cách chọn chính sách yếu hơn |
| Timestamp cực lớn, sai đơn vị hoặc phép cộng bị tràn | Không biến lỗi thành kết quả cho phép |
| Hai chuỗi có offset múi giờ khác nhau biểu diễn cùng instant | Cho cùng kết quả sau chuẩn hóa |
| Worker xử lý chậm theo hợp đồng tiếp nhận trước hạn | Chỉ thực hiện quyền đã được tiếp nhận bền vững, vẫn tôn trọng các guard phải kiểm tra lại |
| Lease hết hạn nhưng tiến trình cũ còn hoạt động | Không coi kiểm tra thời gian là bằng chứng đủ để cấp lại tài nguyên |

### Kiểm thử mô hình hai đồng hồ

Tạo clock phát hành và clock kiểm tra với offset độc lập. Kiểm tra ít nhất các tổ hợp: cả hai đúng tham chiếu, bên phát hành nhanh/bên kiểm tra chậm, bên phát hành chậm/bên kiểm tra nhanh và cả hai cùng lệch một phía.

Đo kết quả theo mốc tham chiếu của test, không chỉ theo số đọc một máy. Với ví dụ TTL ba mươi giây, `L_late = 2 giây`, issuer nhanh một giây và validator chậm một giây, phải thấy cận chấp nhận muộn tương ứng mô hình gần ba mươi bốn giây, với cận trên loại trừ như đã định nghĩa.

Kiểm thử này chứng minh công thức và triển khai dưới các giả định đã tạo. Nó không chứng minh đồng hồ sản xuất luôn có offset trong cùng giới hạn; điều đó còn phụ thuộc giám sát và chính sách vận hành.

## 13. Câu hỏi tự kiểm tra thiết kế

Trước khi áp dụng clock skew tolerance, nhóm phát triển cần trả lời được:

1. Mốc bắt đầu và kết thúc đến từ đâu; nguồn nào có thẩm quyền và deadline có bị client tác động không?
2. Khoảng hợp lệ đóng hay mở ở từng phía; phép làm tròn và đơn vị có thống nhất không?
3. Vì sao cần dung sai phía bắt đầu, phía kết thúc hoặc cả hai, và quyền lợi nào được nới?
4. Cận sai lệch giữa các nguồn được biết bằng cách nào; khi mất độ tin cậy thì thao tác nào bị chặn?
5. Hạn token, hạn phê duyệt, hạn báo giá và hạn reservation có chính sách độc lập không?
6. Quyết định dựa vào lúc tiếp nhận bền vững, lúc xử lý trên trạng thái hiện hành hay lúc hoàn tất hành động?
7. Phép kiểm tra có diễn ra sau các bước chờ quan trọng và gắn với chuyển trạng thái nguyên tử không?
8. Retry, message giao lặp, job hết hạn chạy chậm và đồng hồ chạy lùi có thể làm quyền cũ sống lại không?
9. Dung sai có bị cộng dồn qua gateway, service, worker hoặc quá trình tái cấp quyền không?
10. Kiểm thử và audit có đủ để giải thích một quyết định sát ranh giới mà không dựa vào giờ do client khai báo không?

Clock skew tolerance được kiểm soát khi khoảng chấp nhận được định nghĩa rõ, nguồn giờ có giả định tin cậy cụ thể, phần mở rộng quyền lợi nằm trong ngân sách cho phép và mọi quyết định vẫn tuân thủ quyền theo đối tượng, state machine, transaction cùng cơ chế chống xử lý lặp.
