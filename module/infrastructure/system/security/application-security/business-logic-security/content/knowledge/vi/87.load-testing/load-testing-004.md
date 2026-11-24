# Quota reset load — Kiểm thử tải tại thời điểm đặt lại hạn mức

## 1. Mục tiêu và phạm vi

Một hệ thống có thể kiểm soát quota đúng trong phần lớn thời gian nhưng gặp lỗi ngay lúc chuyển kỳ. Nhiều người dùng cùng chờ hạn mức mới, request cũ chưa kết thúc, cache hết hạn hàng loạt và các instance cùng khởi tạo bộ đếm có thể tạo ra một đợt tải đặc biệt nguy hiểm.

Trong bảo mật logic nghiệp vụ, hậu quả không chỉ là phản hồi chậm. Hệ thống có thể cấp vượt hạn mức, trừ một thao tác vào hai kỳ, làm mất lượt đã sử dụng hoặc cho phép người dùng tự làm mới quota bằng cách phát lại yêu cầu và thay định danh.

**Quota reset load** là kiểm thử tải tập trung vào ranh giới đặt lại hoặc làm mới hạn mức. Bài kiểm thử cần quan sát đồng thời hiệu năng, tính nhất quán và khả năng chống lạm dụng tại ranh giới đó.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, kết nối business invariants với quyền theo đối tượng, state machine, transaction, idempotency và các tình huống tấn công logic. Các cấu hình và luồng tải dưới đây là ví dụ cho môi trường kiểm thử được kiểm soát, không phải yêu cầu chạy tải lên một hệ thống bên ngoài.

Sau bài học, bạn có thể:

- Định nghĩa chính xác quota, kỳ tính hạn mức và thời điểm ghi nhận sử dụng.
- Thiết kế tải trước, trong và sau ranh giới chuyển kỳ.
- Kiểm chứng hạn mức theo tổ chức và kỳ, kể cả khi có retry hoặc request chạy qua ranh giới.
- Phát hiện lỗi reset bộ đếm, mất cập nhật, cache không nhất quán và đường đi bỏ qua kiểm tra.
- Đánh giá kết quả bằng dữ liệu đã commit, trạng thái thao tác và số đo tải thực tế.

## 2. Không phải quota nào cũng có một lần reset

Trước khi thiết kế tải, cần xác định cơ chế hạn mức đang được kiểm tra.

| Cơ chế | Đặc điểm | Điểm tải cần chú ý |
| --- | --- | --- |
| Cửa sổ cố định | Mỗi kỳ có một mức cấp riêng, chẳng hạn theo ngày hoặc phút | Ranh giới chuyển kỳ và khởi tạo dữ liệu kỳ mới |
| Cửa sổ trượt | Tính tổng trong một khoảng thời gian lùi từ hiện tại | Nhiều phần sử dụng cũ đồng thời hết hiệu lực |
| Token bucket | Dung lượng được bổ sung theo tốc độ và giới hạn sức chứa | Tải đồng loạt khi có thêm token hoặc sau thời gian ít sử dụng |
| Hạn mức theo chu kỳ dịch vụ | Gắn với gói, chu kỳ hợp đồng hoặc cấu hình riêng | Nhiều khách hàng cùng chuyển kỳ, cập nhật gói và công việc nền |

Không áp kỳ vọng “bộ đếm phải về không lúc nửa đêm” lên mọi cơ chế. Bài học dùng cửa sổ cố định làm ví dụ chính, sau đó chỉ ra các biến thể cần điều chỉnh.

Với quota mềm, hệ thống có thể cho phép một sai lệch được định nghĩa trước. Khi đó phải xác định rõ giới hạn sai lệch, phạm vi và cách đối soát. Không tự đổi quota nghiêm ngặt thành quota mềm sau khi test phát hiện cấp vượt.

## 3. Viết hợp đồng quota trước khi sinh tải

### 3.1. Các quyết định cần chốt

Một hợp đồng đủ để kiểm thử cần trả lời:

- Quota áp dụng theo người dùng, tổ chức, tài nguyên, loại thao tác hay tổ hợp nào?
- Một lượt tính theo số request, số thao tác logic, số đơn vị dữ liệu hay giá trị nghiệp vụ?
- Kỳ được xác định theo múi giờ nào và khoảng thời gian nào?
- Thời điểm nào quyết định kỳ của thao tác: tiếp nhận hợp lệ, giữ chỗ hay hoàn tất?
- Thao tác thất bại, bị hủy hoặc bị từ chối có tiêu thụ quota không?
- Phát lại cùng thao tác có bị tính thêm không?
- Có giữ chỗ, chuyển phần dư hoặc thay đổi mức cấp giữa kỳ không?
- Khi kho dữ liệu quota không sẵn sàng, hành vi được phép là gì?

Không lấy thời điểm client gửi theo lời khai của client làm nguồn sự thật nếu chính sách không cho phép. Người gọi có thể đổi timestamp hoặc gửi lại một yêu cầu cũ để cố chọn kỳ có lợi.

### 3.2. Hợp đồng minh họa trong bài

Giả sử mỗi tổ chức được thực hiện tối đa `1000` đơn vị thao tác trong mỗi cửa sổ cố định 60 giây. Múi giờ của ví dụ là UTC. Mỗi thao tác hợp lệ tốn một đơn vị, không chuyển phần dư giữa các kỳ.

Kỳ P có khoảng thời gian:

```text
P = [12:00:00, 12:01:00)
P+1 = [12:01:00, 12:02:00)
```

Biên phải không thuộc kỳ trước. Thời điểm tiếp nhận hợp lệ để giữ quota trên server quyết định kỳ; kỳ đó được lưu cùng danh tính thao tác và không thay đổi khi worker hoàn tất sau ranh giới.

Khoảng 60 giây giúp mô tả test ngắn. Nếu hệ thống thực tế có quota theo ngày, việc rút ngắn kỳ hoặc điều khiển thời gian trong test phải giữ đúng những cơ chế cần kiểm chứng; không mặc định test một phút đại diện đầy đủ cho công việc nền chạy theo ngày.

## 4. Bất biến tại ranh giới chuyển kỳ

Với một tổ chức `T`, kỳ `P`, hạn mức cấp `Q(T,P)` và mô hình có giữ chỗ:

```text
reserved(T,P) + consumed(T,P) <= Q(T,P)
available(T,P) = Q(T,P) - reserved(T,P) - consumed(T,P)
```

Ở đây `reserved` là phần giữ còn hiệu lực; khi hoàn tất, phần tương ứng chuyển sang `consumed`, không được cộng vào cả hai. Các công thức giả định mức cấp cố định trong kỳ và chính sách không có chuyển dư hay khoản điều chỉnh khác.

Các bất biến bổ sung:

1. Mỗi thao tác logic chỉ được ghi nhận sử dụng quota theo số lần mà hợp đồng cho phép.
2. Thao tác đã gắn với kỳ P không tự bị chuyển sang P+1 chỉ vì phản hồi hoặc xử lý hoàn tất trễ.
3. Giải phóng phần giữ của P không làm tăng quota của P+1.
4. Một tổ chức không đọc, tiêu thụ hoặc đặt lại quota của tổ chức khác ngoài quyền được cấp.
5. Retry, khởi động lại instance và cache hết hạn không xóa lịch sử cần để bảo vệ các điều kiện trên.
6. Công việc reset không tạo ra khoảng thời gian mà kiểm tra hạn mức bị bỏ qua.

Nếu giảm mức cấp giữa kỳ xuống dưới phần đã dùng, bất biến cần được diễn đạt theo chính sách thay đổi gói, chẳng hạn ngừng cấp mới và ghi nhận phần vượt do thay đổi cấu hình. Không dùng công thức với mức cấp mới để kết luận mọi phần sử dụng hợp lệ trước đó đều là lỗi.

## 5. Vì sao tải lúc reset khác tải thông thường?

### 5.1. Nhiều người dùng cùng quay lại

Khi quota mới mở, các thao tác bị chặn trước đó có thể được gửi đồng loạt. Client tự retry, tác vụ định kỳ và người dùng bấm lại đều làm tăng tải trong một khoảng ngắn. Tải trung bình cả giờ có thể thấp nhưng tải tại ranh giới rất cao.

### 5.2. Hết hạn cache và khởi tạo cùng lúc

Nhiều khóa cache hết hạn có thể khiến các instance cùng truy vấn nguồn dữ liệu, cùng tạo bộ đếm kỳ mới hoặc cùng lấy cấu hình hạn mức. Nếu mỗi instance tạm coi cache trống là “chưa dùng lượt nào”, hệ thống có thể cấp vượt trước khi dữ liệu được đồng bộ.

### 5.3. Công việc nền cạnh tranh với request thật

Một job cập nhật hàng loạt bộ đếm có thể giữ khóa, tạo tải ghi hoặc làm tăng hàng đợi đúng lúc lượng request tăng. Nếu có nhiều bản sao job chạy, reset có thể diễn ra lặp lại hoặc xóa cả phần sử dụng vừa ghi của kỳ mới.

### 5.4. Request chạy qua ranh giới

Request được tiếp nhận cuối kỳ có thể hoàn tất ở kỳ sau. Callback, thông điệp hoặc thao tác hủy đến muộn có thể tác động sai bộ đếm nếu hệ thống chỉ tìm “kỳ hiện tại” khi cập nhật.

### 5.5. Nhiều đồng hồ và dữ liệu cũ

Các instance có thể nhìn ranh giới khác nhau vì lệch đồng hồ, cấu hình múi giờ hoặc cache chính sách. Test cần biết nguồn thời gian nào quyết định quota và các sai lệch nào thuộc hợp đồng, thay vì chỉ dựa vào đồng hồ của máy phát tải.

## 6. Mô hình dữ liệu và reset cần được kiểm chứng

### 6.1. Bộ đếm bị ghi về không

Một triển khai dễ lỗi có thể hoạt động như sau:

```text
00:00:00  Job bắt đầu reset bộ đếm
00:00:01  Request mới tiêu thụ 1 lượt
00:00:02  Job ghi bộ đếm về 0 dựa trên dữ liệu cũ
00:00:03  Lượt vừa dùng không còn được phản ánh
```

Nếu job được chạy lại, phần sử dụng mới có thể tiếp tục bị xóa. Cần sinh tải trong khi job chậm, bị gián đoạn hoặc được thực hiện lại để kiểm tra việc đặt lại không phá dữ liệu đang dùng.

### 6.2. Bộ đếm gắn với kỳ

Một cách mô hình hóa khác là đặt định danh kỳ vào phạm vi dữ liệu:

```text
quotaKey = (tenantId, quotaType, periodId)
operation = (operationId, tenantId, periodId, reservedUnits, outcome)
```

Khi chuyển kỳ, request hợp lệ được ánh xạ vào `periodId` mới; không cần xóa ngay dữ liệu kỳ cũ. Dữ liệu cũ vẫn phục vụ hoàn tất thao tác, giải phóng giữ chỗ và đối soát.

Cách mô hình hóa này không tự bảo đảm an toàn. Test vẫn cần kiểm tra khởi tạo đồng thời, cập nhật có điều kiện, ràng buộc duy nhất và việc tất cả instance dùng cùng quy tắc xác định kỳ.

### 6.3. Cache và nguồn dữ liệu có thẩm quyền

Xác định nơi quyết định cấp lượt: database, kho đếm dùng chung hay một cơ chế khác. Một cache chỉ phục vụ hiển thị có thể tạm cũ mà không gây cấp vượt; một cache tham gia cấp quyền sử dụng cần có bảo đảm mạnh hơn tương ứng.

Không chỉ kiểm tra số `remaining` trên giao diện. Giá trị đó có thể là snapshot đã cũ. Bằng chứng về cấp vượt cần dựa trên các thao tác được chấp nhận, phần giữ và phần tiêu thụ đã ghi nhận ở nguồn phù hợp.

## 7. Thiết kế tải trước, trong và sau ranh giới

Một kịch bản nên có các pha rõ ràng:

| Pha | Mục tiêu | Dạng tải minh họa |
| --- | --- | --- |
| Làm nóng | Ổn định kết nối và hiểu đường xử lý thông thường | Tải vừa phải, dữ liệu hợp lệ |
| Cuối kỳ P | Đưa một số tổ chức gần hoặc tới mức hết quota | Nhiều thao tác riêng biệt, ghi nhận phần còn lại |
| Sát ranh giới | Tạo request đang xử lý và retry có kiểm soát | Tăng tốc độ đến, trì hoãn một số worker test |
| Đầu kỳ P+1 | Kiểm tra cấp quota mới dưới tải đồng loạt | Burst trên nhiều tổ chức và nhiều instance |
| Sau burst | Kiểm tra phục hồi và ảnh hưởng kéo dài | Giảm tải, tiếp tục các thao tác đối chứng |
| Kết thúc quan sát | Xác định kết quả cuối của các thao tác | Ngừng tạo mới, chờ xử lý và đối soát có thời hạn |

Không phải tất cả tổ chức đều cần có cùng mức sử dụng ban đầu. Nên có nhóm đã hết quota, nhóm còn ít lượt và nhóm còn nhiều để nhận diện việc reset sai phạm vi hoặc cấp mới không công bằng.

Với hệ thống nhiều tổ chức, thử cả ranh giới đồng loạt và ranh giới phân tán theo cấu hình khách hàng nếu có. Hai dạng này tạo đặc tính tải khác nhau; không tự áp phân tán nếu nghiệp vụ thực sự yêu cầu cùng một ranh giới.

Một cấu hình mô tả có thể là:

```yaml
scenario: fixed-window-quota-boundary
tenants: 10
unitsPerOperation: 1
quotaPerTenantPerPeriod: 1000
periodSeconds: 60
timeZone: UTC
phases:
  - warmup
  - consume-near-limit
  - overlap-boundary
  - burst-after-boundary
  - drain-and-reconcile
variants:
  - exact-retries
  - concurrent-initialization
  - delayed-old-period-completion
  - cache-expiration
```

Các con số chỉ là fixture minh họa, không phải khuyến nghị năng lực cho một hệ thống thật. Không cần tạo thêm tệp cấu hình để học hoặc diễn giải kịch bản này.

## 8. Phân biệt tải đến, số client và tải thực sự được xử lý

### 8.1. Mô hình client chờ kết quả

Nếu mỗi client gửi một request rồi chờ xong mới gửi tiếp, server chậm sẽ làm tốc độ gửi giảm. Mô hình này hữu ích khi đại diện đúng hành vi người dùng, nhưng có thể che việc hệ thống không chịu được lượng đến cố định tại ranh giới.

### 8.2. Mô hình tốc độ đến độc lập

Với một lịch phát yêu cầu dự kiến độc lập với thời gian trả lời, có thể quan sát rõ hơn hàng đợi và mức quá tải khi nhiều người cùng quay lại. Bộ phát tải vẫn phải giới hạn số tác vụ đang chờ và ghi nhận khi không thể phát đúng lịch.

Nếu máy phát tải bỏ lỡ lịch, đó là tải chưa được phát, không phải request bị server từ chối. Phân biệt ít nhất:

- Số yêu cầu dự kiến phát.
- Số lần gọi thực tế đã phát.
- Số request tới được điểm quan sát phía server.
- Số thao tác logic riêng biệt.
- Số lượt được cấp, bị từ chối và còn chưa xác định kết quả.

Retry làm số lần gọi lớn hơn số thao tác logic. Nếu không tách hai đại lượng, một đợt retry có thể bị hiểu nhầm là tăng sử dụng quota hợp lệ hoặc tăng tỷ lệ lỗi nghiệp vụ.

### 8.3. Kiểm tra năng lực bộ phát tải

Quan sát tài nguyên và độ trễ lập lịch của bộ phát tải. Một generator bị nghẽn kết nối hoặc CPU có thể làm mất chính burst cần kiểm tra.

Không chỉ dùng timestamp gửi ở generator để phân loại kỳ. Theo hợp đồng minh họa, thời điểm tiếp nhận hợp lệ trên server mới quyết định kỳ; hàng đợi và độ trễ mạng có thể khiến request tới sau ranh giới dự định.

## 9. Kịch bản cốt lõi: không cấp vượt ở cả hai kỳ

Giả sử một tổ chức có quota `1000` mỗi kỳ, mỗi thao tác mới hợp lệ tốn một lượt. Nếu đủ `1200` thao tác riêng biệt thật sự được đánh giá trong cùng kỳ, không có lỗi khác và tất cả kết quả đã kết thúc, kỳ vọng là `1000` lượt được cấp và `200` thao tác bị từ chối vì hết quota.

```text
given:
  quota của T trong P là 1000
  chưa có lượt giữ hoặc tiêu thụ
  các thao tác có quyền, dữ liệu hợp lệ và operationId riêng

when:
  gửi đủ thao tác để cạnh tranh trên cùng quota của P
  đồng thời đi qua ranh giới sang P+1
  tiếp tục gửi các thao tác mới ở P+1
  ngừng tạo mới và chờ kết quả cuối

then, for each persisted period:
  reserved + consumed <= 1000
  dữ liệu thao tác và bộ đếm khớp nhau
  không có lượt được cấp ngoài quyền
  thao tác cũ không bị ghi lại thành thao tác mới của kỳ sau
```

Để khẳng định đúng `1000` thành công trong một kỳ, phải chứng minh có đủ thao tác có thể được chấp nhận được đánh giá trong kỳ đó và hệ thống có khả năng hoàn tất theo hợp đồng. Nếu một phần request tới sau ranh giới, không gán chúng về kỳ cũ chỉ vì generator dự định gửi trước ranh giới.

Với cửa sổ cố định, sử dụng hết quota ngay cuối P rồi dùng hết quota đầu P+1 có thể là hành vi hợp lệ. Tổng gần `2Q` trong một khoảng ngắn đi qua ranh giới không tự chứng minh cấp vượt. Nếu nghiệp vụ muốn giới hạn mọi khoảng 60 giây liên tục, cần cơ chế và oracle khác với cửa sổ cố định.

## 10. Retry, idempotency và thao tác chạy qua ranh giới

### 10.1. Mất phản hồi sau khi đã cấp lượt

Cho một thao tác được tiếp nhận hợp lệ ở cuối P, lưu việc giữ quota nhưng làm mất phản hồi. Sang P+1, client gửi lại cùng thao tác theo hợp đồng idempotency.

Kỳ vọng:

- Nhận diện được thao tác đã tồn tại.
- Không cấp thêm một lượt cho bản phát lại.
- Không trừ quota của P+1 chỉ vì lần phát lại tới ở kỳ mới.
- Trả kết quả hoặc trạng thái theo dõi phù hợp quyền hiện tại.

Việc đặt `periodId` hiện tại vào không gian khóa idempotency một cách máy móc có thể khiến cùng khóa ở hai phía ranh giới bị coi là hai thao tác. Thiết kế danh tính cần phù hợp ý định nghiệp vụ; test phải tìm được tình huống này.

### 10.2. Hoàn tất và hủy giữ chỗ đến muộn

Với mô hình giữ chỗ, thao tác đã giữ ở P hoàn tất trong P+1 phải chuyển phần giữ sang tiêu thụ theo kỳ đã gắn, nếu đó là hợp đồng. Không cộng thêm tiêu thụ ở P+1 mà vẫn để phần giữ ở P tồn tại.

Nếu thao tác được hủy, chỉ giải phóng phần giữ tương ứng theo chính sách. Một callback hủy cũ không được tăng quota kỳ mới bằng cách cập nhật bộ đếm “hiện tại”.

Phát lại callback hoàn tất hoặc hủy để kiểm tra việc chuyển phần giữ chỉ xảy ra đúng số lần cho phép. Tổng hợp dữ liệu sau cùng phải không có phần giữ âm, lượt trả lại dư hoặc tiêu thụ cộng lặp.

### 10.3. Yêu cầu từng bị từ chối

Một người đã hết quota ở P có thể được phép tạo thao tác mới trong P+1. Nhưng phát lại một khóa có kết quả từ chối cuối cùng đã được lưu có thể vẫn trả kết quả cũ, tùy hợp đồng.

Test cần tách “hỏi lại kết quả thao tác cũ” với “gửi ý định mới trong kỳ mới”. Không tự ép mọi retry phải được đánh giá lại, cũng không giữ kết quả từ chối cũ cho mọi thao tác mới của người dùng.

## 11. Ma trận lỗi và biến thể lạm dụng tại reset

| Biến thể | Rủi ro cần tìm | Bằng chứng quyết định |
| --- | --- | --- |
| Nhiều request đầu tiên của kỳ mới | Khởi tạo nhiều bộ đếm hoặc ghi đè phần đã dùng | Một phạm vi quota nhất quán, tổng cấp không vượt |
| Hai bản sao job reset | Reset lặp xóa phần sử dụng mới | Lượt đã cấp vẫn được phản ánh đầy đủ |
| Job reset chậm hoặc chạy lại | Cửa sổ bỏ qua kiểm tra hoặc khóa kéo dài | Không cấp vượt; độ trễ phục hồi theo mục tiêu |
| Cache hết hạn hàng loạt | Tăng truy vấn nguồn, nhiều instance cùng cấp từ số liệu cũ | Không cấp quota độc lập trái hợp đồng |
| Kho quota tạm lỗi | Đường dự phòng cho phép không giới hạn | Hành vi lỗi giữ đúng chính sách đã định |
| Đồng hồ hoặc múi giờ khác nhau | Một thao tác được gắn hai kỳ hoặc chọn sai kỳ | Period ID theo nguồn thời gian và quy tắc đã chốt |
| Đổi tenant hoặc quota type từ client | Dùng hạn mức của phạm vi khác | Quyền theo đối tượng và phạm vi từ ngữ cảnh đáng tin cậy |
| Đổi operation ID sau khi đã dùng quyền nghiệp vụ | Bỏ qua giới hạn chỉ bảo vệ bằng idempotency | Bất biến trên đơn hàng, yêu cầu duyệt hoặc tài nguyên vẫn đúng |
| Giải phóng giữ chỗ cũ sau reset | Tăng quota kỳ mới hoặc làm âm phần giữ | Bút toán gắn đúng kỳ và đúng thao tác |
| Cập nhật gói cùng lúc chuyển kỳ | Dùng nhiều phiên bản mức cấp không nhất quán | Áp dụng đúng chính sách cấu hình và điểm hiệu lực |

Không mặc định mọi lỗi phải dẫn tới một kiểu phản hồi duy nhất. Với hệ thống quota nghiêm ngặt, không được âm thầm cho phép vượt khi mất kho đếm. Nếu có chế độ dự phòng với mức cấp giới hạn, test phải kiểm tra đúng giới hạn và phạm vi dự phòng được đặc tả.

Với thay đổi gói, ghi lại phiên bản chính sách áp dụng cho quyết định cấp lượt khi cần. Không so mọi thao tác với một con số quota cuối cùng nếu giữa kỳ đã có thay đổi hợp lệ.

## 12. Đo hiệu năng mà không che lỗi bảo mật

### 12.1. Chia số đo theo loại kết quả

Theo dõi độ trễ và thông lượng riêng cho thao tác được cấp, từ chối vì quota, lỗi kỹ thuật và tra cứu kết quả. Nếu gộp tất cả, nhiều phản hồi từ chối rất nhanh có thể làm số đo chung trông tốt dù thao tác hợp lệ bị treo.

Một số số đo hữu ích:

- Tốc độ đến thực tế và số request đang chờ.
- Độ trễ p95, p99 theo nhóm thao tác và theo pha tải.
- Số lượt cấp mới mỗi tổ chức, mỗi kỳ.
- Lỗi kỹ thuật, timeout và số thao tác chưa xác định kết quả.
- Thời gian chờ khóa, xung đột cập nhật và retry nội bộ.
- Mức sử dụng kết nối, tài nguyên lưu trữ và độ dài hàng đợi.
- Cache miss, khởi tạo bộ đếm và tải vào nguồn dữ liệu.
- Thời gian từ ranh giới tới khi tổ chức đủ điều kiện dùng được quota mới.

Mục tiêu độ trễ và thông lượng phải do yêu cầu hệ thống xác định. Các ngưỡng đạt hiệu năng không được cho phép bỏ qua bất biến nghiêm ngặt về cấp vượt hoặc truy cập sai phạm vi.

### 12.2. Kiểm tra ảnh hưởng giữa các tổ chức

Cho một nhóm tổ chức phát tải cao, nhóm khác có tải hợp lệ vừa phải. Quan sát tổ chức ít tải có bị chặn lâu hoặc không thể nhận quota mới chỉ vì một nhóm khác chiếm tài nguyên dùng chung hay không.

Phân tích cần tính đến lượng yêu cầu hợp lệ và mức cấp của từng nhóm. Chênh lệch số thành công tuyệt đối không tự chứng minh thiếu công bằng nếu workload đầu vào khác nhau.

### 12.3. Giữ khả năng truy vết mà không gây tải quan sát quá mức

Gắn thao tác với mã lần chạy để đối soát. Các chi tiết có độ phân biệt cao như operation ID phù hợp với log hoặc dữ liệu kiểm thử được kiểm soát; không nhất thiết đưa tất cả làm nhãn metric.

Không ghi token, dữ liệu riêng tư hoặc toàn bộ payload nhạy cảm vào báo cáo. Thu thập đủ mốc để xác định kỳ và hiệu lực mà không để chính việc ghi log làm thay đổi nghiêm trọng tải cần đo.

## 13. Đối soát kết quả sau khi ngừng tạo tải

### 13.1. Tách lần thử khỏi thao tác

Một thao tác có thể có nhiều request vì retry. Đếm theo định danh thao tác logic, sau đó phân loại các trạng thái cuối thành các nhóm loại trừ nhau.

```text
N thao tác riêng biệt đã được gửi
  = thành công cuối cùng
  + từ chối nghiệp vụ cuối cùng
  + thất bại kỹ thuật cuối cùng đã xác định không có hiệu lực
  + chưa xác định được kết quả
```

Nếu hợp đồng có trạng thái cuối khác, bổ sung nhóm tương ứng mà không đếm hai lần. Timeout giao tiếp không tự thuộc nhóm thất bại không có hiệu lực; cần tra cứu hoặc đối soát trước.

Những yêu cầu generator chưa phát được phải được báo riêng, không thêm vào số từ chối của server. Những thao tác không có định danh ổn định cần có cách đối soát tương đương đủ tin cậy; nếu không, khó chứng minh retry không tạo trùng.

### 13.2. Đối soát theo tổ chức và kỳ đã lưu

Với mỗi phạm vi, tính lại tổng giữ còn hiệu lực và tiêu thụ từ nguồn dữ liệu đáng tin cậy, rồi so với bộ đếm và mức cấp tương ứng. Nếu có outbox, worker hoặc dịch vụ ngoài, kiểm tra phần hiệu lực mà chúng chịu trách nhiệm.

Không chỉ lấy tổng thành công toàn hệ thống. Một tổ chức vượt `100` lượt và tổ chức khác thiếu `100` lượt vẫn có thể làm tổng chung trông đúng.

Không loại bỏ các request kết thúc sau khoảng đo hiệu năng. Chúng có thể đã được tiếp nhận trước đó và là nơi lỗi cấp trùng hoặc hạch toán sai kỳ xuất hiện.

### 13.3. Tiêu chí kết thúc quan sát

Dừng tạo thao tác mới, tiếp tục xử lý kết quả và chờ các công việc liên quan kết thúc trong thời hạn đã định. Nếu còn thao tác chưa rõ, báo số lượng cùng trạng thái hiện tại; không coi việc chưa thấy vi phạm là bằng chứng hoàn thành kiểm thử.

Khi một test lỗi hoặc hết thời hạn, xác định các request, worker và job còn chạy trước khi dọn dữ liệu. Xóa fixture trong lúc tác vụ cũ vẫn ghi có thể làm dữ liệu xuất hiện lại hoặc ảnh hưởng lần chạy tiếp theo.

## 14. Quy trình thực hiện và điều kiện đạt

Một quy trình thực tế có thể gồm:

1. Chốt hợp đồng quota và các bất biến cùng người phụ trách nghiệp vụ.
2. Dựng fixture có tổ chức, quyền và số lượt ban đầu xác định.
3. Kiểm tra từng luồng ở tải thấp, gồm hết quota, kỳ mới, retry và callback muộn.
4. Xác nhận nguồn thời gian, cấu hình kỳ và ranh giới transaction của môi trường.
5. Chạy các pha tải với mã lần chạy riêng, ghi số request thực sự được phát.
6. Thêm từng biến thể lỗi quan trọng để biết nguyên nhân tác động.
7. Ngừng tạo mới, chờ kết quả và đối soát theo thao tác, tổ chức, kỳ.
8. Đánh giá cả bất biến, khả năng hoàn thành và mục tiêu hiệu năng.

Điều kiện đạt minh họa cho quota nghiêm ngặt:

- Không có phạm vi nào được cấp vượt mức theo chính sách có hiệu lực.
- Không có thao tác bị tính hai lần do phát lại hoặc chuyển kỳ.
- Không có truy cập hoặc reset quota ngoài quyền.
- Không mất lượt đã cấp hoặc trả lại quota sai kỳ.
- Thao tác hợp lệ có thể sử dụng quota mới theo mục tiêu phục hồi.
- Độ trễ, lỗi kỹ thuật và thông lượng đáp ứng ngưỡng đã xác định cho kịch bản.
- Các thao tác của lần chạy được đối soát, hoặc kết quả được đánh dấu chưa kết luận nếu còn thiếu bằng chứng.

Không đặt ngưỡng “cho phép một ít giao dịch cấp vượt” chỉ để bù cho độ khó tái hiện. Nếu thiết kế có sai lệch được chấp thuận, phải mô tả như một chính sách rõ ràng từ trước và kiểm thử giới hạn đó.

## 15. Chẩn đoán lỗi và tạo ca hồi quy

Khi phát hiện vấn đề, phân biệt các nhóm nguyên nhân:

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| Bộ đếm thấp hơn tổng thao tác đã cấp | Mất cập nhật, reset ghi đè, cập nhật không nguyên tử |
| Một thao tác xuất hiện ở hai kỳ | Danh tính idempotency hoặc quyết định kỳ thay đổi khi retry |
| Quota kỳ mới tăng sau callback cũ | Giải phóng giữ chỗ dùng kỳ hiện tại thay vì kỳ đã lưu |
| Tất cả tổ chức cùng chậm ở ranh giới | Hết hạn cache đồng loạt, job reset, tranh chấp nguồn chung |
| Chỉ nhiều instance mới cấp vượt | Trạng thái cục bộ, đồng hồ hoặc cấu hình không nhất quán |
| Báo hết quota dù còn khả dụng | Lượt giữ mắc kẹt, cache cũ hoặc hoàn tất thiếu cập nhật |
| Báo cáo generator đẹp nhưng ít request tới server | Giới hạn phát tải, lỗi mạng hoặc bỏ lỡ lịch phát |

Thu nhỏ một lỗi đã tìm thấy về kịch bản dễ hiểu: một tổ chức, hai kỳ, một thao tác chạy qua biên hoặc hai request cùng khởi tạo kỳ mới. Dùng nguồn thời gian có thể điều khiển và điểm điều khiển test khi phù hợp để tái hiện ranh giới.

Giữ ca hồi quy chức năng hoặc tích hợp cho lỗi logic tối thiểu, rồi chạy lại kịch bản tải để xác nhận ảnh hưởng ở quy mô cần thiết. Không dùng một lần chạy tải lớn làm bằng chứng duy nhất cho mọi thay đổi về transaction hoặc idempotency.

Nếu lỗi chỉ là hiệu năng, không khắc phục bằng cách bỏ kiểm tra quota, tin số dư do client gửi hoặc cho phép đường dự phòng không giới hạn. Mọi thay đổi để giảm tranh chấp vẫn cần giữ các bất biến đã chốt.

## 16. Danh sách kiểm tra cho quota reset load

- Đã xác định cơ chế quota và thời điểm nào thật sự có ranh giới làm mới.
- Đã chốt phạm vi, đơn vị, múi giờ và quy tắc bao gồm biên của kỳ.
- Đã xác định thời điểm gắn kỳ và lưu kỳ cùng thao tác khi cần.
- Đã có bất biến cho phần giữ, tiêu thụ, giải phóng và retry.
- Đã chuẩn bị tải trước biên, tại biên, sau biên và pha đối soát.
- Đã phân biệt request dự kiến, request thực tế và thao tác logic riêng biệt.
- Đã kiểm tra nhiều tổ chức, nhiều instance và các phạm vi quyền liên quan.
- Đã thử cache hết hạn, job chậm hoặc lặp, lỗi kho quota và callback cũ theo rủi ro.
- Đã đo hiệu năng riêng cho thành công, từ chối quota và lỗi kỹ thuật.
- Đã đối soát dữ liệu đã commit theo tổ chức và kỳ, không chỉ tổng toàn hệ thống.
- Đã xác định cách xử lý thao tác chưa rõ kết quả và tác vụ còn chạy.
- Đã giữ ca hồi quy nhỏ cho lỗi logic được phát hiện trong tải lớn.

Quota reset load đạt mục tiêu khi hệ thống vừa phục vụ được nhu cầu hợp lệ sau ranh giới, vừa giữ đúng giới hạn trong toàn bộ quá trình chuyển kỳ. Bằng chứng cần bao gồm lượng tải thực sự đã đến, danh tính và kỳ của từng thao tác, cùng các hiệu lực đã được ghi nhận nhất quán.
