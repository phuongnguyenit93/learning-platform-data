# Race condition

## 1. Khi yêu cầu hợp lệ riêng lẻ tạo ra kết quả sai khi chạy cùng nhau

Trong chương **Business logic security**, race condition là tình huống kết quả phụ thuộc vào thứ tự xen kẽ hoặc thời điểm thực hiện của các thao tác đồng thời. Trong bảo mật logic nghiệp vụ, điều đáng quan tâm là việc xen kẽ đó làm vi phạm quy tắc mà từng request riêng lẻ dường như vẫn tuân thủ.

Ví dụ, một sản phẩm còn một đơn vị. Hai request đều đọc thấy còn hàng, đều vượt qua kiểm tra và đều tạo đơn thành công. Người dùng có thể đã đăng nhập đúng, có quyền mua hàng và gửi dữ liệu hợp lệ; lỗi nằm ở cách hệ thống phối hợp các thao tác trên cùng tài nguyên.

Mục tiêu của bài là chuyển câu “cần chống race condition” thành yêu cầu có thể kiểm chứng:

**Tài nguyên dùng chung → bất biến nghiệp vụ → thao tác cạnh tranh → ranh giới nguyên tử → kết quả cho phép → bằng chứng kiểm thử.**

Sau bài học, người học cần có khả năng:

- Nhận diện khoảng cách giữa kiểm tra điều kiện và thay đổi trạng thái.
- Viết bất biến và quy tắc chuyển trạng thái khi có request đồng thời.
- Chọn yêu cầu về giao dịch, cập nhật có điều kiện, khóa, version và idempotency phù hợp.
- Kiểm chứng kết quả nghiệp vụ, kể cả khi có nhiều replica, retry hoặc tiến trình bị dừng.

Các ngưỡng và luồng trong bài là ví dụ thiết kế. Cơ chế cụ thể phải được xác nhận theo mô hình dữ liệu, công nghệ lưu trữ và hợp đồng nghiệp vụ thực tế.

## 2. Mô hình đơn giản của lỗi kiểm tra rồi sử dụng

Giả sử mã xử lý có logic:

```text
if read_available_stock(sku) >= quantity:
    create_order()
    write_available_stock(sku, previously_read_stock - quantity)
    return success
```

Với tồn kho ban đầu bằng 1 và hai request mỗi request mua 1:

| Bước | Request A | Request B | Trạng thái hoặc quan sát |
|---|---|---|---|
| 1 | Đọc tồn kho = 1 | | A cho rằng có thể mua |
| 2 | | Đọc tồn kho = 1 | B cũng cho rằng có thể mua |
| 3 | Tạo đơn A | | Một đơn đã được chấp nhận |
| 4 | | Tạo đơn B | Hai đơn đã được chấp nhận |
| 5 | Ghi tồn kho = 0 | | |
| 6 | | Ghi tồn kho = 0 | Tồn cuối vẫn là 0 nhưng đã bán 2 đơn vị |

Đây vừa có lỗi kiểm tra và sử dụng không cùng một quyết định, vừa có hiện tượng ghi đè dựa trên giá trị cũ. Chỉ kiểm tra tồn cuối không âm sẽ bỏ sót việc hệ thống đã bán vượt.

Nếu thay bước ghi bằng phép trừ nhưng không có điều kiện và ranh giới nguyên tử phù hợp, hai lần trừ có thể đưa tồn kho xuống âm. Cần bảo vệ cả quyết định nhận đơn và các thay đổi liên quan.

### 2.1. TOCTOU

TOCTOU là viết tắt của **time of check to time of use**: trạng thái được kiểm tra ở một thời điểm nhưng đến lúc sử dụng đã thay đổi.

Ví dụ:

- Kiểm tra mã giảm giá chưa dùng rồi mới đánh dấu đã dùng.
- Kiểm tra tổng số chỗ còn trống rồi mới tạo lượt đăng ký.
- Kiểm tra đơn đang chờ rồi mới hủy hoặc xác nhận.
- Kiểm tra quyền trên đối tượng rồi thay đổi đối tượng sau khi quyền hoặc chủ sở hữu đã đổi.

Giảm thời gian giữa hai bước có thể làm lỗi khó xuất hiện hơn, nhưng không biến hai bước thành một quyết định nguyên tử.

### 2.2. Race condition khác data race

Data race thường nói tới các truy cập bộ nhớ đồng thời không được đồng bộ theo mô hình của ngôn ngữ hoặc nền tảng. Race condition nghiệp vụ có thể tồn tại ngay cả khi mọi truy cập bộ nhớ trong từng process đều an toàn.

Hai service khác nhau cùng đọc và ghi database, hoặc một job hết hạn chạy cùng request xác nhận, có thể tạo lỗi nghiệp vụ mà không có data race trong bộ nhớ ứng dụng.

## 3. Bắt đầu từ bất biến thay vì tên công cụ

Bất biến là điều kiện phải luôn được bảo toàn ở các trạng thái nghiệp vụ có thể quan sát theo hợp đồng. Không nên chỉ yêu cầu “dùng lock” mà không nói lock bảo vệ điều gì.

| Luồng | Bất biến cần đặc tả | Thao tác có thể cạnh tranh |
|---|---|---|
| Giữ hàng | Tổng lượng đã cấp quyền sở hữu không vượt lượng có thể bán | Tạo nhiều lượt giữ, xác nhận, hết hạn |
| Dùng mã giảm giá một lần | Một chủ thể đủ điều kiện có nhiều nhất một lần sử dụng đã được chấp nhận | Nhiều request dùng cùng mã |
| Đăng ký sự kiện | Số chỗ được xác nhận không vượt sức chứa | Đăng ký, hủy, danh sách chờ |
| Hoàn tác một thao tác | Một kết quả nghiệp vụ không bị đảo ngược nhiều lần | Retry, webhook trùng, tác vụ định kỳ |
| Thay đổi trạng thái | Chỉ chuyển từ trạng thái nguồn hợp lệ tới đích được cho phép | Hủy và xác nhận cùng lúc |
| Chỉnh sửa đối tượng | Không âm thầm ghi đè một thay đổi chưa được caller chấp nhận | Hai người cập nhật cùng phiên bản |

Một bất biến cần có phạm vi: theo tenant, tài khoản, đối tượng, sản phẩm hay toàn bộ hệ thống. Cũng cần định nghĩa “đã chấp nhận” là gì: ghi commit, đã phát hành quyền sử dụng hay mới nhận request để xử lý.

Ví dụ yêu cầu rõ hơn:

> Với cùng một sản phẩm trong một tenant, tổng số lượng thuộc các lượt giữ còn hiệu lực và các lượt bán đã xác nhận không được vượt lượng hàng thuộc phạm vi kiểm soát. Mọi đường cấp hàng phải bảo toàn điều kiện này, kể cả khi request đến đồng thời qua nhiều replica.

### 3.1. Trạng thái trung gian và điểm quyết định

Một transaction có thể có trạng thái trung gian chưa được công bố. Bất biến phải được giữ ở ranh giới commit và các điểm mà tác dụng phụ hoặc quyền nghiệp vụ trở nên quan sát được.

Nếu email xác nhận, sự kiện xuất hàng hoặc response thành công được phát trước khi transaction hoàn tất, bên ngoài có thể quan sát một quyền lợi mà database sau đó rollback. Vì vậy phải xác định thứ tự giữa commit và tác dụng phụ.

Điểm quyết định, đôi khi gọi là điểm tuyến tính hóa trong một thiết kế yêu cầu tính chất này, là thời điểm thao tác được xem như có hiệu lực trong thứ tự các thao tác cạnh tranh. Không phải mọi quy trình phân tán đều có một điểm duy nhất cho toàn bộ hệ thống; đặc tả phải chỉ rõ phạm vi mà mình cam kết.

## 4. Mô hình đe dọa và các đường vào cần kiểm soát

Tác nhân có thể là người dùng hợp lệ gửi nhiều request song song, client tự retry sau timeout, webhook bị phát lại hoặc hai tác vụ nội bộ chạy trùng lịch. Không cần có một kỹ thuật vượt xác thực để khai thác lỗi này.

Hãy liệt kê:

1. Tài nguyên dùng chung và giới hạn nghiệp vụ của nó.
2. Mọi đường thay đổi tài nguyên: API, phiên bản cũ, giao diện quản trị, consumer, job hết hạn và công cụ vận hành.
3. Những thao tác phải loại trừ nhau hoặc chỉ được có một kết quả.
4. Khả năng caller lặp request, đổi idempotency key hoặc dùng nhiều tài khoản.
5. Thời điểm thất bại: trước commit, sau commit nhưng trước response, trong lúc lease hết hạn hoặc khi message được gửi lại.
6. Ranh giới tin cậy của tenant, chủ sở hữu, số lượng, trạng thái và phiên bản dữ liệu.

Giới hạn tốc độ có thể giảm tải hoặc giảm số lần thử khai thác, nhưng không chứng minh tính đúng dưới đồng thời. Chỉ hai request cũng đủ vi phạm bất biến.

Một khóa chỉ dùng ở endpoint công khai cũng chưa đủ nếu job nền hoặc đường quản trị cập nhật cùng dữ liệu theo cách khác. Mọi thành phần có quyền ghi phải tuân theo cơ chế bảo toàn bất biến tương ứng.

## 5. Các cơ chế bảo toàn bất biến và giới hạn của chúng

### 5.1. Cập nhật có điều kiện

Với tồn kho lưu ở một bản ghi, một quyết định trừ hàng có thể được biểu diễn bằng cập nhật có điều kiện:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE tenant_id = :tenant_id
  AND sku = :sku
  AND available >= :quantity;
```

Điều kiện tiên quyết là server đã kiểm tra `quantity` là số nguyên dương trong giới hạn cho phép, kiểu số không bị tràn và caller có quyền trên tenant, sản phẩm tương ứng. Không tin trực tiếp tenant hoặc số lượng do client khai.

Yêu cầu quan trọng là phép kiểm tra và phép trừ được thực hiện như một thao tác nguyên tử theo ngữ nghĩa của kho dữ liệu. Kết quả:

- Đúng một bản ghi được cập nhật: thao tác trừ đã thành công trong transaction đang xét.
- Không có bản ghi được cập nhật: không được tạo kết quả cấp hàng thành công dựa trên lần đọc trước đó.
- Kết quả không xác định do lỗi: cần đối soát transaction hoặc thao tác, không tự suy là chưa trừ.

Câu lệnh trên chỉ bảo vệ phần cập nhật tồn kho. Nếu còn phải tạo reservation, lưu idempotency và ghi sự kiện, các phần đó cần ranh giới giao dịch hoặc giao thức phối hợp phù hợp.

Có thể bổ sung ràng buộc `available >= 0` ở kho dữ liệu nếu nền tảng hỗ trợ. Ràng buộc này là lớp bảo vệ bổ sung, không thay thế kiểm tra số lượng dương, tính đúng của tổng phân bổ hoặc quy tắc tạo đơn.

### 5.2. Ràng buộc duy nhất

Một ràng buộc duy nhất phù hợp với yêu cầu “nhiều nhất một bản ghi cho cùng một khóa nghiệp vụ”, chẳng hạn:

```text
một lần dùng mã:
    (tenant_id, promotion_id, eligible_subject_id)

một thao tác idempotent:
    (tenant_id, caller_scope, operation_type, idempotency_key)
```

Khóa phải phản ánh đúng phạm vi nghiệp vụ và cách chuẩn hóa danh tính. Cần xác định bản ghi bị hủy hoặc xóa có làm được phép sử dụng lại hay không.

Kiểm tra “chưa có bản ghi” rồi insert ở tầng ứng dụng không thay thế ràng buộc duy nhất khi có nhiều writer. Hai transaction có thể cùng nhìn thấy trạng thái chưa tồn tại.

Ràng buộc duy nhất không tự bảo vệ một giới hạn tổng như “tối đa 100 người”. Mỗi người có thể là duy nhất nhưng tổng vẫn vượt 100 nếu việc cấp chỗ không được điều phối.

### 5.3. Kiểm soát lạc quan bằng phiên bản

Một cập nhật có thể yêu cầu phiên bản hiện tại vẫn bằng phiên bản mà caller đã đọc:

```sql
UPDATE business_object
SET state = :next_state,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :object_id
  AND version = :expected_version
  AND state = :allowed_source_state;
```

Nếu không cập nhật được, caller phải xử lý xung đột theo hợp đồng: đọc lại, yêu cầu người dùng xác nhận lại hoặc thử lại có giới hạn khi an toàn.

Không được âm thầm bỏ điều kiện version rồi ghi đè. Mọi writer liên quan phải cập nhật version theo cùng quy tắc; một job nền bỏ qua version có thể làm mất hiệu lực cơ chế này.

Phiên bản giúp tránh ghi đè và bảo vệ chuyển trạng thái ở phạm vi bản ghi, nhưng không tự duy trì mọi bất biến liên quan nhiều đối tượng.

### 5.4. Giao dịch và khóa

Nếu nhiều thay đổi phải cùng thành công hoặc cùng thất bại, có thể cần transaction trong cùng miền dữ liệu. Với khóa bi quan, các thao tác cạnh tranh phải khóa cùng tài nguyên và giữ khóa tới khi quyết định được hoàn tất.

Các yêu cầu cần nêu:

- Khóa bảo vệ hàng, đối tượng hay tập dữ liệu nào.
- Thứ tự lấy nhiều khóa để hạn chế deadlock.
- Thời hạn chờ và kết quả khi không lấy được khóa.
- Phạm vi rollback và điều kiện retry sau xung đột.
- Giới hạn thời gian transaction giữ tài nguyên.

Không gọi một dependency chậm hoặc chờ thao tác của người dùng khi đang giữ khóa dài nếu thiết kế không có lý do và cận rõ ràng.

Chỉ viết “dùng transaction” chưa đủ. Ở một số mức cô lập, hai transaction vẫn có thể cùng đọc một điều kiện tổng rồi tạo dữ liệu khiến điều kiện đó sai. Cần chọn cơ chế phù hợp với bất biến, ví dụ một bộ đếm được cập nhật có điều kiện, khóa phạm vi phù hợp hoặc mức cô lập có tính chất cần thiết.

Nếu dùng serializable, phải xử lý transaction bị hủy do xung đột và bảo đảm retry không lặp tác dụng phụ đã phát ra ngoài. Tính chất đó chỉ áp dụng trong phạm vi mà kho dữ liệu và giao dịch thực sự kiểm soát, không mở rộng tự động sang dịch vụ bên ngoài.

### 5.5. Khóa trong process, distributed lock và single writer

`synchronized`, mutex hoặc khóa trong bộ nhớ có thể bảo vệ các thread dùng chung khóa trong một process. Chúng không tự bảo vệ một bản ghi được cập nhật từ nhiều replica hoặc job khác.

Distributed lock có thêm các tình huống:

- Lease hết hạn trong lúc writer cũ vẫn chạy.
- Writer tạm dừng rồi tiếp tục với giả định mình còn quyền.
- Kết nối mất làm kết quả lấy hoặc gia hạn khóa không xác định.
- Thành phần ghi dữ liệu không kiểm tra quyền sở hữu khóa hiện tại.

Fencing token có thể giúp nếu tài nguyên đích kiểm tra thứ tự hoặc thế hệ quyền ghi và từ chối writer cũ **cùng với thao tác cập nhật**. Chỉ ghi token vào log hoặc kiểm tra riêng trước khi ghi vẫn có khoảng TOCTOU.

Một mô hình single writer hoặc queue theo khóa tài nguyên cũng có thể điều phối. Tuy nhiên, phải kiểm soát mọi đường ghi, xử lý message lặp, writer cũ sau failover và ranh giới commit. Queue có thứ tự không tự biến tác dụng phụ bên ngoài thành thực hiện đúng một lần.

## 6. Idempotency và chuyển trạng thái: hai loại yêu cầu khác nhau

### 6.1. Idempotency giải quyết lặp lại cùng thao tác

Với cùng một khóa idempotency hợp lệ và cùng nội dung trong thời hạn bảo vệ, hệ thống cần trả kết quả theo cùng một thao tác logic, không tạo thêm tài nguyên hoặc tác dụng phụ trái hợp đồng.

Cần đặc tả:

- Phạm vi khóa theo tenant, caller và loại thao tác.
- Cách so sánh nội dung yêu cầu bằng biểu diễn chuẩn hóa phía server.
- Kết quả khi cùng khóa nhưng khác nội dung.
- Hành vi khi thao tác đầu còn đang thực hiện.
- Thời hạn lưu kết quả và quy tắc sau thời hạn đó.
- Cách xử lý commit thành công nhưng caller không nhận response.

Không trả dữ liệu kết quả chỉ vì client biết một key; caller vẫn phải có quyền với thao tác và tài nguyên tương ứng.

Idempotency không tự ngăn hai thao tác khác nhau tranh cùng một đơn vị hàng. Người dùng có thể dùng hai key mới hoặc hai người khác nhau có thể mua cùng lúc. Bất biến tài nguyên vẫn phải được bảo vệ riêng.

### 6.2. Chuyển trạng thái phải kiểm tra và cập nhật cùng nhau

Ví dụ một lượt giữ hàng có các trạng thái:

```text
HELD -> CONFIRMED
HELD -> RELEASED
HELD -> EXPIRED

CONFIRMED, RELEASED, EXPIRED:
    không có chuyển tiếp trong phạm vi luồng minh họa này
```

Yêu cầu cần bảo đảm chỉ một nhánh rời `HELD` được chấp nhận. Nếu xác nhận và hết hạn chạy đồng thời, không được vừa bán hàng vừa hoàn lại cùng lượng hàng.

Đối với nhánh trả hàng về kho:

1. Chỉ thao tác thắng quyền chuyển từ `HELD` sang trạng thái trả hàng mới được cộng lại tồn.
2. Chuyển trạng thái và cộng tồn phải cùng transaction hoặc cùng giao thức có khả năng phục hồi.
3. Retry hay job chạy lặp không được cộng lại lần nữa.

Thời hạn phải được quyết định bằng nguồn thời gian và quy tắc phía server đã định nghĩa. Không lấy timestamp client làm bằng chứng còn hiệu lực.

Nếu quy tắc yêu cầu kiểm tra hết hạn tại lúc ra quyết định, không dùng một mốc được chụp quá sớm trước khi chờ khóa rồi mặc nhiên xem nó còn đúng. Cần nêu rõ điểm đo thời gian và cách xử lý tại đúng biên hết hạn.

## 7. Ví dụ đặc tả yêu cầu: giữ và xác nhận hàng

### 7.1. Phạm vi và bất biến

Hệ thống giả định có một mặt hàng với 10 đơn vị trong phạm vi một tenant. Mỗi request giữ từ 1 tới 5 đơn vị. Lượt giữ có thời hạn 10 phút; các con số chỉ phục vụ ví dụ.

Trong luồng này chưa xét nhập thêm, hoàn hàng sau bán hoặc chuyển kho. Đặt:

- `A`: số lượng còn có thể cấp.
- `H`: tổng số lượng của các lượt giữ ở trạng thái `HELD`.
- `C`: tổng số lượng đã `CONFIRMED`.

Các bất biến:

```text
A >= 0
H >= 0
C >= 0
A + H + C = 10

Mỗi reservation có nhiều nhất một kết quả rời trạng thái HELD.
Mỗi thao tác idempotent đã commit có một kết quả nhất quán.
```

Tạo lượt giữ chuyển lượng từ `A` sang `H`. Xác nhận chuyển từ `H` sang `C`. Hủy hoặc hết hạn chuyển từ `H` về `A`.

Việc quá thời hạn không tự làm dữ liệu trong database đổi trạng thái. Thiết kế phải định nghĩa ai thực hiện chuyển `EXPIRED`, khi nào xác nhận bị từ chối và cách xử lý lượng vẫn đang ở `HELD` trước khi tác vụ giải phóng hoàn tất. Chậm giải phóng có thể làm giảm lượng khả dụng tạm thời; không được vì muốn tăng khả dụng mà cấp trùng.

Rủi ro `R-BL-RACE-01` là nhiều thao tác cạnh tranh làm cấp vượt hàng, trả hàng nhiều lần hoặc tạo hai kết quả cho một lượt giữ.

### 7.2. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-RACE-01 | Mọi thao tác tạo, xác nhận, hủy và hết hạn phải bảo toàn các bất biến trong phạm vi tenant và mặt hàng đã định nghĩa. |
| SEC-RACE-02 | Server chỉ chấp nhận số lượng nguyên từ 1 tới 5, gắn tài nguyên với tenant đã kiểm tra quyền và không tin trạng thái hoặc tồn kho do client gửi. |
| SEC-RACE-03 | Kiểm tra đủ hàng và cấp lượng giữ phải là một quyết định nguyên tử. Tạo reservation, cập nhật tồn, lưu kết quả idempotency và ghi outbox phải cùng commit trong thiết kế một kho giao dịch của ví dụ. |
| SEC-RACE-04 | Với tồn đầu 10, không có giải phóng hoặc nhập thêm, tổng số lượng được cấp qua mọi replica không vượt 10. Đổi idempotency key không tạo thêm quyền vượt giới hạn này. |
| SEC-RACE-05 | Cùng khóa idempotency trong phạm vi tenant, caller và thao tác, cùng nội dung chuẩn hóa, trong 24 giờ kể từ kết quả commit phải ánh xạ tới cùng thao tác. Khác nội dung bị từ chối theo mã xung đột ổn định. |
| SEC-RACE-06 | Khi một thao tác cùng key chưa hoàn tất, request cạnh tranh phải chờ có cận hoặc nhận trạng thái chưa xác định theo hợp đồng; không tự tạo reservation thứ hai. |
| SEC-RACE-07 | Chỉ một chuyển tiếp từ `HELD` được chấp nhận. Xác nhận chỉ được thực hiện nếu chưa hết hạn tại điểm quyết định phía server; các nhánh hủy hoặc hết hạn chỉ hoàn lượng về kho một lần. |
| SEC-RACE-08 | Cập nhật không tác động bản ghi do điều kiện không còn đúng không được báo như một thay đổi mới thành công. Retry của kết quả đã commit phải được phân biệt với việc thắng một chuyển trạng thái mới. |
| SEC-RACE-09 | Không trả thành công hoặc phát tác dụng phụ xác nhận ra ngoài trước commit. Message phát lại sau commit không được làm lặp tác dụng phụ trái hợp đồng. |
| SEC-RACE-10 | Mọi writer gồm API, consumer, job hết hạn và công cụ quản trị phải tuân theo cơ chế bảo toàn bất biến. Khóa chỉ trong một process không được dùng làm bằng chứng cho cam kết nhiều replica. |
| SEC-RACE-11 | Khi timeout hoặc process dừng quanh thời điểm commit, hệ thống phải có cách tra cứu kết quả theo định danh thao tác; không mặc định thất bại rồi tạo lại với key mới. |
| SEC-RACE-12 | Ghi nhận được xung đột, chuyển trạng thái thắng, replay idempotency và kết quả đối soát; không ghi secret hoặc payload nhạy cảm dư thừa vào log. |

Thời hạn 24 giờ là phạm vi bảo vệ idempotency của ví dụ, không có nghĩa reservation còn hiệu lực 24 giờ. Trả lại kết quả tạo lượt giữ cũ không được gia hạn hoặc hồi sinh lượt giữ đã hết hạn. Trạng thái hiện tại phải có cách truy vấn riêng hoặc được trình bày theo hợp đồng rõ ràng.

Sau thời hạn bảo vệ, client không được mặc định key cũ còn ngăn thao tác mới. Hệ thống phải nêu quy tắc lưu giữ, tái sử dụng key và đối soát các request đến muộn.

### 7.3. Mã giả của thao tác tạo lượt giữ

```text
reserve(authenticated_context, request):
    validate_quantity_and_bind_authorized_tenant(request)
    operation_key = trusted_scope + operation_type + request.idempotency_key
    fingerprint = canonicalize_and_fingerprint_relevant_payload(request)

    begin transaction:
        claim operation_key using database-enforced uniqueness

        if a committed operation already owns the key:
            verify caller authorization and matching fingerprint
            return its committed result without allocating again

        if key ownership is pending or uncertain:
            stop this branch with the bounded pending/conflict behavior

        atomically subtract quantity only when enough inventory exists

        if allocation did not succeed:
            rollback
            return business rejection

        create reservation(state=HELD, quantity, server_defined_expiry)
        persist committed-result data for operation_key
        append outbox event with a unique event identity

    commit transaction
    return the committed reservation result
```

Đây là mã giả mô tả ngữ nghĩa, không phải cú pháp giao dịch chạy nguyên trạng. Việc tranh key cần tuân theo ngữ nghĩa chờ, rollback và quan sát dữ liệu đã commit của kho được chọn. Không đọc kết quả dở dang rồi xem đó là thành công.

Trong nhánh không đủ hàng của ví dụ, transaction được rollback và không lưu kết quả từ chối bền vững cho key. Nếu sản phẩm muốn replay cả kết quả thất bại, phải bổ sung chính sách lưu và định nghĩa liệu thao tác sau này còn được thử lại khi có hàng hay không.

Giao dịch một kho trong ví dụ không bao gồm việc gửi email hoặc gọi dịch vụ bên ngoài. Outbox chỉ tạo bản ghi cần phát cùng commit; việc xử lý tác dụng phụ nằm ở bước sau.

## 8. Ranh giới giao dịch, phân quyền và xử lý lỗi

### 8.1. Không có một transaction mặc định bao phủ mọi dịch vụ

Nếu trừ hàng ở database A rồi tạo đơn ở service B, lỗi giữa hai bước có thể để lại trạng thái treo. Một local transaction ở A không rollback được một kết quả đã được B chấp nhận.

Thiết kế có thể dùng suất giữ với vòng đời rõ ràng, outbox, xử lý idempotent, bù trừ và đối soát. Khi đó cần nêu:

- Trạng thái trung gian được phép tồn tại.
- Ai sở hữu việc tiếp tục, hủy hoặc giải phóng.
- Khi nào có thể báo thành công cho caller.
- Bất biến an toàn nào vẫn phải giữ ngay cả khi chưa hoàn tất.
- Cận thời gian tồn đọng và cách xử lý khi không tự phục hồi.

Bù trừ không đồng nghĩa với chưa từng có tác dụng phụ. Một thông báo đã gửi hoặc quyền đã được sử dụng không thể mặc nhiên bị xóa khỏi thực tế bằng rollback.

Với outbox phát ít nhất một lần, consumer phải nhận diện sự kiện trùng và thực hiện tác dụng phụ phù hợp. Nếu cập nhật dữ liệu consumer và ghi nhận đã xử lý ở cùng một database, cần bảo vệ chúng bằng cùng ranh giới nguyên tử. Nếu tác dụng phụ ở hệ thống ngoài, phải dựa vào hợp đồng idempotency hoặc đối soát tương ứng, không chỉ một cờ trong bộ nhớ.

### 8.2. Quyền có thể thay đổi giữa kiểm tra và cập nhật

Một request có thể kiểm tra người dùng là chủ sở hữu, rồi đối tượng được chuyển sang chủ khác trước khi request ghi. Cần xác định quyền phải đúng ở thời điểm nào và trên phiên bản nào.

Nếu yêu cầu quyền phải còn đúng tại quyết định cập nhật, điều kiện quyền hoặc phiên bản liên quan cần được kiểm tra trong cùng ranh giới có hiệu lực với thay đổi. Tương tự, tenant và đối tượng phải được ràng buộc trong truy vấn cập nhật, không chỉ lấy một `object_id` rồi bỏ ngữ cảnh.

Nếu quyền nằm ở dịch vụ khác hoặc có cache, cam kết “thu hồi có hiệu lực ngay lập tức ở mọi nơi” cần cơ chế nhất quán và bằng chứng riêng. Có thể có một khoảng hiệu lực theo hợp đồng, nhưng phải nêu rõ; không suy tính nguyên tử xuyên hệ thống từ một lần kiểm tra token.

### 8.3. Timeout không chứng minh rollback

Ba tình huống cần phân biệt:

| Điểm xảy ra lỗi | Điều có thể biết | Cách xử lý cần đặc tả |
|---|---|---|
| Trước khi bắt đầu transaction | Chưa có quyết định thay đổi từ transaction đó | Có thể thử theo hợp đồng, vẫn kiểm tra idempotency |
| Sau khi transaction rollback xác định | Thay đổi trong transaction không commit | Retry có giới hạn nếu điều kiện lỗi cho phép |
| Sau commit nhưng trước response, hoặc kết quả commit chưa rõ | Có thể đã có reservation và sự kiện | Tra cứu theo thao tác, không cấp lại mù quáng |

Retry sau deadlock hoặc xung đột phải khởi động lại phần đọc và quyết định phù hợp trên dữ liệu hiện tại. Không tái dùng kết quả “còn hàng” đã đọc trước transaction bị hủy.

## 9. Kiểm thử đồng thời và tiêu chí chấp nhận

### 9.1. Điều khiển lịch xen kẽ thay vì chỉ tăng số request

Một bài kiểm thử hữu ích cần chủ động tạo các điểm tranh chấp:

1. Chuẩn bị trạng thái dữ liệu và đồng hồ kiểm thử.
2. Dùng barrier hoặc điểm đồng bộ trong môi trường thử để các thao tác cùng đến trước quyết định cạnh tranh.
3. Cho chúng tiếp tục theo các thứ tự cần kiểm chứng.
4. Đợi mọi transaction và tác vụ liên quan hoàn tất hoặc hết hạn thử.
5. Đối chiếu kết quả với bất biến ở database và các điểm phát tác dụng phụ.

Chỉ thêm một khoảng sleep hoặc chạy tải lớn rồi hy vọng lỗi xuất hiện sẽ làm kiểm thử khó tái lập. Điểm đồng bộ và cơ chế gây lỗi chỉ thuộc môi trường kiểm thử, không được tạo đường điều khiển tùy ý trong sản phẩm.

Cần chạy qua nhiều replica khi yêu cầu có phạm vi nhiều replica. Một bài kiểm thử chỉ gọi hàm trong một process không chứng minh cơ chế khóa hoặc transaction hoạt động trên toàn bộ đường ghi.

### 9.2. Ma trận kiểm chứng cho ví dụ

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Tranh lượng hàng | Tồn đầu 10; 100 request hợp lệ, key khác nhau, mỗi request giữ 1; không hết hạn, không lỗi hạ tầng và không có giới hạn khác chặn trước | Đúng 10 reservation mới được chấp nhận; tổng lượng giữ 10, khả dụng 0 |
| T02 — Cùng idempotency key | Nhiều request cùng tenant, caller, key và nội dung khi đủ hàng | Chỉ một reservation được tạo và chỉ trừ một lần; các response tuân theo quy tắc replay hoặc pending |
| T03 — Key khác nội dung | Hai request cùng phạm vi key nhưng khác số lượng | Có nhiều nhất một nội dung thắng quyền sở hữu; request xung đột không tạo thêm reservation |
| T04 — Xác nhận và hủy | Hai thao tác hợp lệ cạnh tranh trên một reservation `HELD` chưa hết hạn | Chỉ một nhánh rời `HELD` thắng; không vừa cộng tồn vừa xác nhận bán |
| T05 — Xác nhận và hết hạn | Điều khiển đồng hồ quanh hạn, cho job và request cùng tranh trạng thái | Không xác nhận sau điểm hết hạn theo quy tắc; job chỉ hết hạn khi đã đến hạn; không có hai kết quả |
| T06 — Giải phóng lặp | Job hoặc request hủy được gửi lại nhiều lần | Tồn chỉ được cộng lại một lần cho lượng giữ đó |
| T07 — Lỗi trước commit | Dừng xử lý sau khi trừ hàng nhưng trước khi transaction commit | Transaction không để lại reservation hoặc trừ tồn riêng lẻ sau rollback |
| T08 — Mất response | Commit thành công rồi làm mất phản hồi; client gửi lại cùng key | Trả hoặc tra được kết quả cũ; không tạo reservation mới |
| T09 — Nhiều writer | API, consumer và job trên các replica cùng tác động tài nguyên | Các bất biến vẫn đúng; không có đường ghi bỏ qua cơ chế chung |
| T10 — Version cũ | Hai cập nhật cùng dựa vào một phiên bản | Không âm thầm ghi đè; nhánh thua xử lý xung đột theo hợp đồng |
| T11 — Message trùng | Phát lại cùng sự kiện sau commit | Không tạo tác dụng phụ trùng trái hợp đồng; có bằng chứng nhận diện sự kiện |
| T12 — Lease cũ | Với thiết kế dùng lease, cho writer cũ tiếp tục sau khi quyền đã chuyển | Writer cũ không được làm thay đổi dữ liệu dựa trên quyền đã hết hiệu lực |
| T13 — Ranh giới tenant và quyền | Đổi tenant tự khai hoặc làm quyền/chủ sở hữu thay đổi trước quyết định | Không thay đổi tài nguyên ngoài quyền theo ngữ nghĩa đã cam kết |
| T14 — Số lượng bất hợp lệ | Gửi 0, số âm, vượt mức hoặc giá trị ngoài miền biểu diễn | Bị từ chối trước thay đổi; không làm tăng tồn bằng phép trừ số âm |

T01 phải đếm **reservation mới và lượng được cấp**, không chỉ số response thành công. T02 có thể có nhiều response replay thành công nhưng vẫn chỉ một reservation; đây là hành vi đúng.

Sau mỗi ca, kiểm tra cả dữ liệu tồn, tập reservation, trạng thái idempotency và outbox. Nếu thông báo đã phát hoặc consumer đã tạo kết quả, phải đối chiếu các tác dụng phụ đó.

### 9.3. Bằng chứng và giới hạn của kiểm thử

Báo cáo nên ghi số replica, mức cô lập, trạng thái đầu, số request, lịch xen kẽ, điểm gây lỗi, clock và kết quả cuối. Với lỗi timing, cần lưu trace đủ để tái hiện thứ tự quyết định mà không ghi secret.

Một lần chạy không phát hiện vi phạm chưa chứng minh mọi lịch xen kẽ đều an toàn. Bằng chứng cần kết hợp thiết kế bất biến, ràng buộc thực thi và các ca cạnh tranh có chủ đích.

Khi có xung đột hợp lệ, cũng cần đo thời gian chờ, deadlock, số retry và tỷ lệ hoàn thành. Thiết kế đúng về an toàn nhưng giữ khóa vô hạn có thể làm hệ thống mất khả năng phục vụ. Cận chờ và hành vi lỗi phải có trong hợp đồng vận hành.

## 10. Liên kết yêu cầu với rủi ro và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu | Quyết định kiến trúc | Bằng chứng |
|---|---|---|---|
| R-BL-RACE-01: Cấp vượt hàng | SEC-RACE-01, 03, 04 | Cấp hàng có điều kiện trong transaction | T01, T09 và phương trình bảo toàn lượng |
| Tạo hai reservation do retry | SEC-RACE-05, 06, 11 | Khóa nghiệp vụ duy nhất, lưu kết quả và đối soát | T02, T03, T08 |
| Xác nhận và hoàn hàng cùng thắng | SEC-RACE-07, 08 | Chuyển trạng thái có điều kiện cùng cập nhật lượng | T04, T05, T06 |
| Phát xác nhận cho transaction rollback | SEC-RACE-03, 09 | Outbox cùng commit, consumer có xử lý trùng | T07, T11 |
| Khóa cục bộ bỏ sót writer khác | SEC-RACE-10 | Cơ chế dùng chung và kiểm soát mọi đường ghi | T09, T12 |
| Dùng dữ liệu client để vượt phạm vi | SEC-RACE-02 | Ràng buộc tenant, quyền, số lượng ở server | T13, T14 |

Trong vòng đời phát triển, thay đổi schema, thêm job hoặc thêm một endpoint cũng có thể mở đường ghi mới. Cần xem lại ranh giới nguyên tử và các ca kiểm thử tương ứng, không chỉ kiểm tra request mới có xác thực hay không.

## 11. Logging và xử lý vận hành

Thông tin hữu ích để điều tra gồm:

```text
request_id, operation_reference
resource_reference trong phạm vi được phép ghi log
operation_type
expected_version, observed_version nếu phù hợp
transition_from, transition_to
decision = committed | replayed | rejected | pending | uncertain
reason = insufficient_stock | state_conflict | version_conflict | ...
transaction_or_event_reference
lock_wait_duration, retry_count
```

Không cần đưa raw idempotency key, credential hoặc toàn bộ payload vào log. Nếu cần định danh để tương quan, dùng biểu diễn nội bộ được bảo vệ và chính sách lưu giữ phù hợp.

Các chỉ số nên theo dõi:

- Số xung đột version, trạng thái và idempotency.
- Thời gian chờ khóa, transaction timeout, deadlock và retry.
- Số thao tác chưa xác định kết quả hoặc chờ đối soát.
- Số reservation hết hạn chưa được giải phóng và tuổi tồn đọng.
- Sai lệch giữa tồn kho, lượng giữ, lượng bán và các sự kiện liên quan.
- Tác dụng phụ trùng hoặc sự kiện bị phát hiện lặp.

Không gắn mọi request ID hay user ID thành nhãn metric không giới hạn. Tỷ lệ xung đột tăng có thể do tải hợp lệ, lỗi client hoặc lạm dụng; cần kết hợp dữ liệu nghiệp vụ và tình trạng hệ thống.

Công cụ sửa dữ liệu cũng phải giữ bất biến và có audit. Một lệnh quản trị cộng tồn để “sửa nhanh” có thể che sai lệch hoặc làm lượng được cấp vượt nguồn hàng. Khi phát hiện vi phạm, cần cô lập đường gây lỗi, đối soát thao tác và sửa theo quy trình có thể kiểm chứng.

## 12. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Dùng lock để chống race” | Chưa có phạm vi, writer và bất biến | Nêu tài nguyên được bảo vệ, điểm quyết định và mọi đường ghi |
| “Có transaction là đủ” | Chưa xét mức cô lập và dữ liệu ngoài transaction | Chỉ ra cơ chế bảo vệ điều kiện cạnh tranh và giới hạn ranh giới |
| “Có idempotency nên không bán vượt” | Hai thao tác khác nhau vẫn tranh cùng lượng hàng | Giữ riêng yêu cầu chống lặp và bất biến tài nguyên |
| “Tồn cuối không âm là đạt” | Có thể mất cập nhật nhưng đã cấp vượt | Đối chiếu tổng lượng cấp và phương trình bảo toàn |
| “Timeout thì làm lại từ đầu” | Có thể đã commit | Đối soát theo thao tác và giữ nguyên danh tính retry |
| “Job chỉ chạy một lần theo lịch” | Có thể trùng lịch, restart hoặc redelivery | Thiết kế chuyển trạng thái và tác dụng phụ chịu được lặp |
| “Lease còn hạn lúc bắt đầu là an toàn” | Writer cũ có thể tiếp tục sau khi mất quyền | Kiểm soát quyền ghi tại tài nguyên đích và ngăn writer cũ |
| “Giảm tốc độ request sẽ hết lỗi” | Hai request vẫn có thể đụng nhau | Bảo vệ tính nguyên tử; dùng rate limit để kiểm soát tải |
| “Cập nhật 0 bản ghi vẫn trả thành công” | Nhầm không thắng điều kiện với đã thực hiện thay đổi | Phân biệt replay, trạng thái hiện tại và chuyển trạng thái mới |

## 13. Bài tập áp dụng

Bạn thiết kế hệ thống đăng ký sự kiện có 100 chỗ, hỗ trợ giữ chỗ 5 phút, xác nhận và hủy. Hãy viết một tập yêu cầu gồm:

1. Các bất biến về lượng chỗ và chuyển trạng thái.
2. Phạm vi tenant, người đăng ký, idempotency key và thời hạn bảo vệ.
3. Ranh giới nguyên tử cho giữ chỗ, xác nhận, hủy và hết hạn.
4. Cách xử lý hai request khác key nhưng cùng tranh chỗ cuối.
5. Hành vi khi commit thành công nhưng mất response, job chạy lặp hoặc writer cũ quay lại.
6. Ca kiểm thử có barrier, một ca chuyển trạng thái cạnh tranh và một ca tác dụng phụ trùng.
7. Chuỗi truy vết từ rủi ro tới yêu cầu, quyết định kiến trúc và bằng chứng.

Tự kiểm tra: **Nếu đảo thứ tự hai thao tác hợp lệ, hệ thống có thể cho kết quả nào, và trong mọi kết quả được phép thì bất biến nào vẫn phải đúng?** Nếu tài liệu chỉ mô tả từng request độc lập, cần bổ sung hành vi khi chúng cùng tranh một tài nguyên.
