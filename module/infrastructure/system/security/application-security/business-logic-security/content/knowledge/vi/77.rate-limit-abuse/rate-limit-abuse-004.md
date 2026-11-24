# Payment retry velocity — Tốc độ thử lại thanh toán

## Mục tiêu bài học

Trong chương **Rate Limit Abuse**, payment retry velocity là tốc độ và mức độ tập trung của các lần thử lại thanh toán theo thời gian. Kiểm soát này bảo vệ luồng thanh toán khỏi thử dồn dập, dò phương tiện thanh toán, tiêu hao tài nguyên nhà cung cấp và những lần thu tiền trùng do xử lý sai retry.

Một yêu cầu thanh toán có thể hợp lệ về cú pháp và quyền truy cập nhưng vẫn không được phép thực hiện ngay: đơn hàng đã thanh toán, một lần thử cũ chưa rõ kết quả, người dùng chưa hoàn tất xác thực bổ sung hoặc tốc độ thử đã vượt chính sách. Vì vậy, rate limit phải phối hợp với business invariants, state machine, quyền theo đối tượng, transaction và idempotency.

Sau bài học, bạn có thể:

- Phân biệt retry của request, lần truyền lại đến nhà cung cấp và một lần thử thanh toán mới.
- Chọn đúng sự kiện, phạm vi và thời điểm tiêu thụ hạn mức.
- Ngăn retry sau timeout tạo thêm nghĩa vụ thanh toán chưa được kiểm soát.
- Thiết kế backoff, giới hạn đồng thời và điểm tiếp nhận nguyên tử.
- Kiểm thử yêu cầu trùng, webhook đến muộn, worker chạy lại và các đường lách giới hạn.

## 1. Vì sao thanh toán cần một chính sách retry riêng?

Một người dùng bấm nút “Thanh toán” nhiều lần có thể là do mạng chậm, giao diện không phản hồi hoặc hệ thống xác thực bổ sung chưa hoàn tất. Cùng biểu hiện đó cũng có thể đến từ một chương trình tự động đang thử hàng loạt phương tiện thanh toán.

Hệ thống không thể giải quyết cả hai bằng cách chỉ tắt nút trên giao diện. Client khác, nhiều tab, SDK, proxy và công việc nền đều có thể gửi tiếp yêu cầu. Mặt khác, từ chối mọi retry cũng làm người dùng hợp lệ không thể khôi phục một giao dịch bị gián đoạn.

Ví dụ một lỗi nghiêm trọng:

```text
Backend gửi yêu cầu thanh toán A.
Nhà cung cấp xử lý nhưng phản hồi bị mất.
Backend coi timeout là thất bại và tạo yêu cầu B với khóa mới.
Cả A và B đều tạo tác động thu tiền.
```

Giới hạn “tối đa 5 lần mỗi phút” vẫn cho phép lỗi này xảy ra. Tốc độ thấp không chứng minh thao tác mới an toàn. Trước khi xét còn bao nhiêu lượt, phải trả lời: **lần thử trước có thể vẫn tạo tác động hay không?**

## 2. Phân biệt các đơn vị xử lý

| Khái niệm | Ý nghĩa trong bài | Ví dụ |
|---|---|---|
| Đơn hàng | Nhu cầu nghiệp vụ cần thanh toán | Một đơn có tổng tiền và loại tiền đã được server xác định. |
| Payment intent nội bộ | Mục tiêu thu một khoản tiền xác định cho đơn | Theo dõi trạng thái thanh toán, không phụ thuộc số lần client gửi request. |
| Payment attempt | Một lần thử nghiệp vụ mới được hệ thống tiếp nhận | Thử thanh toán bằng một phương tiện được phép sau khi lần trước đã có kết quả đủ rõ. |
| Provider operation | Một thao tác cụ thể tại nhà cung cấp | Tạo thanh toán, xác thực hoặc thu tiền theo mô hình tích hợp. |
| Transport retry | Truyền lại cùng một provider operation | Dùng lại khóa idempotency của thao tác đó nếu hợp đồng nhà cung cấp cho phép. |
| Client retry | Client gửi lại lệnh sau khi không nhận được phản hồi | Backend trả operation đã có nếu cùng khóa và cùng nội dung. |
| Truy vấn hoặc webhook trạng thái | Xác nhận kết quả của thao tác đã có | Cập nhật trạng thái, không tự tạo payment attempt mới. |

Một payment attempt có thể phát sinh nhiều lần truyền tải của cùng provider operation. Ngược lại, đổi phương tiện thanh toán hoặc thay đổi nội dung nghiệp vụ có thể cần một attempt mới, sau khi các điều kiện trạng thái được thỏa mãn.

Bài học dùng mô hình đơn hàng được thanh toán một lần với một khoản tiền xác định. Trả góp, thanh toán nhiều phần và kết hợp nhiều phương tiện cần mô hình invariant riêng. Với luồng tách authorization và capture, hai bước có định danh và trạng thái riêng; được authorization không mặc nhiên có nghĩa đã hoàn tất thu tiền.

Không dùng cùng một khóa idempotency cho các thao tác khác nghĩa chỉ vì chúng thuộc một đơn hàng. Khóa của thao tác tạo thanh toán không tự thay thế khóa của capture hoặc hoàn tiền.

## 3. Đếm điều gì để không hiểu sai velocity?

### 3.1. Ít nhất ba bộ đếm khác nhau

| Bộ đếm | Khi tăng | Mục đích |
|---|---|---|
| Request đến hệ thống | Mỗi request thuộc loại được đo, kể cả client retry | Bảo vệ tài nguyên API và phát hiện spam. |
| Attempt nghiệp vụ mới | Khi một attempt mới được tiếp nhận bền vững | Kiểm soát số lần thử thanh toán thực sự được cấp quyền. |
| Lần gọi ra nhà cung cấp | Mỗi lần thực hiện lời gọi thuộc loại được đo | Bảo vệ hạn mức tích hợp, chi phí và khả năng phục vụ. |

Gửi lại cùng client idempotency key có thể tăng bộ đếm request nhưng không tăng bộ đếm attempt. Truyền lại cùng provider operation có thể không tạo tác động thu tiền mới, nhưng vẫn tiêu thụ một lần gọi ra ngoài.

Truy vấn trạng thái cũng tạo tải cho nhà cung cấp. Nếu chỉ giới hạn lệnh thanh toán nhưng cho phép polling không giới hạn, hệ thống vẫn có thể bị quá tải. Nên phân loại ngân sách cho lệnh tạo tác động và ngân sách cho truy vấn khôi phục trạng thái, đồng thời tuân thủ giới hạn tổng áp dụng cho tích hợp.

### 3.2. Không chờ thành công mới đếm

Nếu chỉ tăng bộ đếm khi thanh toán thành công, một chương trình có thể tạo vô số lần thử bị từ chối mà không dùng hết hạn mức. Khi tất cả attempt đang xử lý đều chưa được tính, nhiều request đồng thời cũng có thể cùng vượt cổng.

Với ngưỡng số attempt được tiếp nhận, phải tính cả attempt đang chờ, đang xử lý và chưa rõ kết quả. Nếu thiết kế có giữ chỗ trước khi tạo attempt, phần giữ chỗ đó cũng phải được tính, nhưng không cộng hai lần sau khi chuyển sang đã tiêu thụ.

Kết quả decline hoặc timeout không mặc nhiên hoàn lại lượt. Nếu bộ đếm đo số attempt được tiếp nhận, lượt đó đã được sử dụng. Một ngoại lệ hoàn lượt do chứng minh chưa có khả năng dispatch cần chính sách riêng và thao tác hoàn idempotent; không dùng mọi lỗi làm điều kiện reset bộ đếm.

## 4. Chọn phạm vi và ngưỡng

### 4.1. Phạm vi cần phản ánh cả danh tính lẫn mục tiêu

Các lớp thường cần phối hợp:

- **Đơn hàng hoặc payment intent:** ngăn nhiều attempt chưa giải quyết cùng nhắm tới một khoản phải thu.
- **Khách hàng:** phát hiện một chủ thể thử qua nhiều đơn hàng.
- **Phương tiện thanh toán:** phát hiện hoạt động tập trung vào cùng phương tiện qua nhiều tài khoản, nếu có định danh đáng tin cậy trong phạm vi tích hợp.
- **Tổ chức hoặc merchant:** bảo vệ tài nguyên dùng chung và hạn mức tích hợp.
- **IP hoặc thiết bị:** tín hiệu bổ sung, không phải danh tính duy nhất.

Backend xác định người gọi từ ngữ cảnh xác thực và kiểm tra quyền trên đơn hàng. `customerId`, `tenantId`, số tiền và loại tiền do client gửi không được tự trở thành nguồn sự thật.

Nếu dùng token hoặc fingerprint của nhà cung cấp để liên kết phương tiện, cần hiểu phạm vi ổn định của định danh đó. Không giả định token của hai nhà cung cấp khác nhau biểu diễn cùng một phương tiện. Không tự thu thập số thẻ hoặc dữ liệu xác thực nhạy cảm chỉ để tạo khóa rate limit.

Định danh phương tiện có thể vẫn nhạy cảm. Cần giới hạn quyền sử dụng và tránh đưa nó thành nhãn metrics có số lượng giá trị không kiểm soát.

### 4.2. Chính sách minh họa

Các số sau phục vụ phân tích và kiểm thử, không phải cấu hình khuyến nghị cho mọi nhà cung cấp hoặc sản phẩm:

| Phạm vi | Điều kiện minh họa | Mục tiêu |
|---|---|---|
| Một payment intent | Tối đa 3 attempt mới trong 10 phút trượt | Chặn thử lại quá nhiều cho cùng khoản phải thu. |
| Một khách hàng | Tối đa 6 attempt mới trong 15 phút trượt | Hạn chế phân tán qua nhiều đơn hàng. |
| Một định danh phương tiện đáng tin cậy | Tối đa 4 attempt mới trong 10 phút trượt | Hạn chế tập trung qua nhiều tài khoản. |
| Một payment intent | Chỉ một attempt có khả năng tiếp tục tạo tác động tại một thời điểm | Bảo vệ trạng thái; đây không chỉ là giới hạn tốc độ. |
| Sau một kết quả đủ điều kiện retry | Không tiếp nhận attempt mới trước `nextAllowedAt` | Tránh thử dồn và thực thi cooldown. |
| Một merchant hoặc tích hợp | Ngân sách gọi ra cấu hình theo hợp đồng và năng lực thực tế | Bảo vệ nhà cung cấp và tài nguyên dùng chung. |

Các điều kiện phải đồng thời thỏa. Còn lượt theo khách hàng không cho phép mở attempt mới khi attempt cũ đang `UNKNOWN`. Một lần xác minh bổ sung thành công cũng không làm mất điều kiện ngân sách hoặc quyền theo đối tượng.

### 4.3. Biểu diễn điều kiện theo thời gian

Với cửa sổ dài `W`, có thể quy ước:

```text
U(s, t, W) = số attempt đã được tiếp nhận trong khoảng (t - W, t]
             + phần giữ chỗ liên quan chưa được chuyển thành attempt

Một attempt mới được tiếp nhận nếu:
  mọi U(s, t, W) + 1 <= limit(s, W)
  và t >= nextAllowedAt
  và không có attempt chưa giải quyết cấm việc thử mới
  và quyền, trạng thái đơn hàng, số tiền cùng các invariant đều hợp lệ
```

Phần attempt và phần giữ chỗ phải rời nhau. Thời điểm xét do server xác định nhất quán, không lấy đồng hồ hoặc countdown của trình duyệt làm căn cứ.

Cửa sổ cố định có thể tạo burst sát mốc reset. Nếu tác động không cho phép burst đó, cần cửa sổ trượt hoặc cơ chế phối hợp phù hợp. Token bucket hữu ích để điều tiết lưu lượng, nhưng không tự có nghĩa “không quá N attempt trong mọi cửa sổ W”.

## 5. State machine quyết định có được thử mới không

Một mô hình attempt đơn giản có thể gồm:

```text
READY -> IN_FLIGHT -> SUCCEEDED
                  -> DECLINED_RETRYABLE
                  -> DECLINED_FINAL_FOR_ATTEMPT
                  -> REQUIRES_ACTION
                  -> UNKNOWN

UNKNOWN -> đối soát -> kết quả đã xác nhận
REQUIRES_ACTION -> tiếp tục cùng luồng -> kết quả hoặc UNKNOWN
```

Tên trạng thái là mô hình nội bộ minh họa. Việc ánh xạ trạng thái hoặc mã lỗi cụ thể phải theo hợp đồng của nhà cung cấp đang tích hợp, không dựa vào tên gọi có vẻ tương đương.

| Kết quả hiện tại | Hướng xử lý |
|---|---|
| `SUCCEEDED` | Trả kết quả đã có; không tạo attempt mới cho khoản đã thanh toán. |
| `IN_FLIGHT` hoặc đang chờ kết quả | Trả trạng thái hiện có; không tạo một attempt cạnh tranh. |
| `UNKNOWN` | Truy vấn, chờ thông báo hoặc đối soát cùng thao tác; chưa đủ căn cứ để thử mới. |
| `REQUIRES_ACTION` | Tiếp tục xác thực hoặc tương tác cần thiết của luồng hiện tại; không coi mỗi lần mở trang xác thực là attempt mới. |
| `DECLINED_RETRYABLE` đã xác nhận | Có thể xét retry theo chính sách nhà cung cấp, quyền, cooldown và các ngưỡng. |
| `DECLINED_FINAL_FOR_ATTEMPT` | Không tự gửi lại cùng yêu cầu một cách máy móc; có thể cần phương tiện khác, hành động người dùng hoặc xem xét theo chính sách. |

“Final cho attempt” không nhất thiết có nghĩa đơn hàng vĩnh viễn không thể thanh toán. Ngược lại, “retryable” không có nghĩa được thử ngay, vô hạn hoặc bất chấp điều kiện của phương tiện thanh toán.

HTTP timeout hoặc lỗi máy chủ không tự chứng minh yêu cầu chưa được xử lý. Kết nối bị ngắt sau khi gửi có thể để lại một tác động thành công ở nhà cung cấp. Một kết quả truy vấn “chưa tìm thấy” cũng cần được hiểu theo bảo đảm nhất quán và thời gian hiển thị của nhà cung cấp; không tự coi mọi lần chưa thấy là bằng chứng chưa từng có tác động.

Người dùng bấm hủy trên giao diện cũng không chứng minh nhà cung cấp đã hủy thao tác. Trạng thái hủy cần được xác nhận theo mô hình xử lý thực tế.

## 6. Idempotency ở hai ranh giới

### 6.1. Từ client đến backend

Một khóa idempotency nội bộ cần được ràng buộc với đúng phạm vi, chẳng hạn tenant, chủ thể và loại lệnh. Server lưu dấu vân tay nội dung nghiệp vụ đã chuẩn hóa để phân biệt retry với thay đổi yêu cầu.

- Cùng khóa, cùng nội dung: trả operation hoặc trạng thái đã có, sau khi kiểm tra quyền xem hiện tại.
- Cùng khóa, khác đơn hàng, phương tiện hoặc nội dung ảnh hưởng thanh toán: từ chối xung đột.
- Khóa mới: không tự được cấp quyền; vẫn phải đi qua state machine và mọi giới hạn.

Idempotency không chống được lạm dụng tạo hàng loạt lệnh mới. Ngược lại, giới hạn velocity không thay thế idempotency cho một lệnh bị gửi trùng.

Với yêu cầu bị từ chối trước khi tiếp nhận, hợp đồng API cần nêu có lưu kết quả từ chối theo khóa hay không. Nếu có lưu, client phải biết cách bắt đầu lần thử được phép tiếp theo; nếu không lưu lâu dài, backend vẫn cần phân xử các yêu cầu đồng thời trước khi tạo attempt.

### 6.2. Từ backend đến nhà cung cấp

Mỗi provider operation cần một định danh nội bộ ổn định và khóa phía nhà cung cấp theo hợp đồng tích hợp. Khi truyền lại cùng thao tác được phép, dùng lại khóa đó và giữ nguyên các tham số liên quan. Không sinh khóa mới chỉ vì worker chạy lại hoặc HTTP timeout.

Khóa provider nên được tạo và lưu trước khi có khả năng dispatch, để worker khác phục hồi được đúng thao tác. Không phụ thuộc vào biến tạm trong bộ nhớ hoặc việc client còn giữ một trang web.

Khi nghiệp vụ thật sự cho phép một attempt mới, nó có định danh và quan hệ với attempt trước rõ ràng; các provider operation mới có khóa riêng phù hợp. Việc này chỉ diễn ra sau khi trạng thái cho phép, không phải một cách bỏ qua kết quả chưa rõ.

Cần biết thời gian lưu và phạm vi idempotency của nhà cung cấp. Bản ghi nội bộ còn tồn tại không có nghĩa khóa provider luôn được ghi nhớ. Khi khóa bên ngoài có thể đã hết hiệu lực mà kết quả cũ chưa rõ, không tự gửi lại như thể vẫn được bảo vệ; phải dùng quy trình đối soát thích hợp.

Chuyển sang nhà cung cấp khác không giữ được bảo đảm chống trùng của nhà cung cấp cũ. Failover khi thao tác cũ chưa rõ kết quả có thể tạo hai khoản thu độc lập, dù mỗi bên đều xử lý khóa idempotency của mình đúng.

## 7. Một nơi điều phối retry

Nhiều tầng cùng retry có thể khuếch đại lưu lượng. Giả sử trình duyệt, backend và thư viện tích hợp mỗi tầng thực hiện tối đa 3 lần, và mỗi lần ở tầng trên lại kích hoạt đầy đủ các lần của tầng dưới. Một hành động có thể dẫn tới 3 × 3 × 3 = 27 lần thực thi ở tầng thấp nhất.

Cần xác định rõ:

- Tầng nào sở hữu quyết định tạo attempt mới.
- Tầng nào chỉ được truyền lại cùng provider operation.
- Loại lỗi nào đủ điều kiện retry và phải giữ nguyên định danh nào.
- Tổng số lần truyền tải, deadline và ngân sách gọi ra.
- Cách client lấy trạng thái thay vì tạo thêm công việc.

Một thiết kế dễ kiểm soát là backend giữ trạng thái retry bền vững. Frontend gửi lệnh có idempotency key, nhận operation ID và theo dõi kết quả. Tác vụ nền dùng lại operation ID, provider key và lịch đã lưu; worker khởi động lại không đưa bộ đếm về 0.

Giới hạn ingress cần đặt trước những công việc đắt đỏ phù hợp, nhưng backend vẫn phải nhận diện retry cùng thao tác trước khi tiêu thụ thêm hạn mức attempt. Hai lớp này giải quyết hai loại tài nguyên khác nhau.

## 8. Backoff, cooldown và deadline

Backoff làm giãn những lần thử tiếp theo; cooldown xác định thời điểm sớm nhất được phép; velocity giới hạn số lượng trong một khoảng; giới hạn đồng thời ngăn nhiều thao tác cùng chưa giải quyết. Không cơ chế nào thay thế hoàn toàn các cơ chế còn lại.

Một lịch truyền lại cùng thao tác có thể dùng công thức khái niệm:

```text
delay(k) = min(cap, base × 2^k)

scheduledAt = max(
    now + delay(k),
    providerNotBefore,
    localCooldownUntil
) + jitterKhôngÂm
```

`k` là chỉ số lần retry theo quy ước đã xác định. Các tham số phải phù hợp với nhà cung cấp và tác động nghiệp vụ. Khi triển khai cần chặn tràn số, giới hạn số lần và dùng jitter có biên để tránh nhiều worker cùng thức dậy tại một mốc.

Nếu nhận được thời điểm không được thử trước đó từ nhà cung cấp, jitter không được làm lịch chạy sớm hơn mốc này. Retry vẫn cần kiểm tra lại điều kiện lúc thực thi; một lịch đã được tạo không cấp quyền vượt hạn mức hoặc tiếp tục khi đơn đã thanh toán.

Deadline của luồng tương tác không phải bằng chứng rằng thanh toán thất bại. Khi vượt deadline, có thể ngừng tự động thử mới và chuyển sang thông báo đang đối soát. Không được reset intent rồi bắt đầu lại chỉ vì người dùng đã chờ quá lâu.

Truy vấn khôi phục trạng thái cũng cần backoff và ngân sách riêng. Chuyển từ retry thanh toán sang polling liên tục vài mili giây không giải quyết bài toán tải.

## 9. Tiếp nhận attempt mới bằng giao dịch nhất quán

### 9.1. Luồng tham chiếu

Giả mã sau mô tả thiết kế trong đó trạng thái thanh toán và hạn mức tiếp nhận nằm trong cùng ranh giới giao dịch:

```text
Nhận lệnh và áp dụng kiểm soát request cơ bản.
Xác thực người gọi.

BEGIN TRANSACTION
  Khóa aggregate thanh toán ổn định của đơn hàng.
  Kiểm tra tenant, quyền theo đối tượng và nội dung chuẩn hóa.

  Phân xử client idempotency key.
  Nếu đã có operation cùng nội dung: trả trạng thái được phép xem.
  Nếu cùng khóa nhưng khác nội dung: từ chối xung đột.

  Đọc số tiền, loại tiền và trạng thái từ dữ liệu tin cậy.
  Nếu đã thanh toán: trả kết quả hiện có, không tạo attempt.
  Nếu đang có attempt chưa giải quyết hoặc cần tiếp tục xác thực:
    trả trạng thái/chỉ dẫn của luồng đó, không tạo attempt mới.

  Kiểm tra kết quả trước đó có cho phép thử mới không.
  Kiểm tra cooldown, thời hạn và chính sách liên quan.
  Khóa các phạm vi hạn mức theo thứ tự nhất quán.
  Kiểm tra và tiêu thụ hạn mức tiếp nhận của mọi phạm vi.

  Tạo attempt và provider operation với định danh ổn định.
  Lưu snapshot số tiền, loại tiền và khóa provider.
  Ghi nextAllowedAt theo chính sách.
  Ghi operation result và outbox để dispatch.
COMMIT
```

Nếu một ngưỡng không đạt, không được để lại hạn mức attempt đã tiêu thụ ở các phạm vi khác. Bộ đếm request hoặc lần thử bị từ chối có thể vẫn tăng theo chính sách riêng, nhưng không được nhầm với attempt đã được tiếp nhận.

Điểm khóa phải bao phủ mục tiêu thu tiền ổn định. Nếu mỗi request có thể tạo một intent mới cho cùng đơn rồi chỉ khóa intent đó, các intent khác nhau vẫn có thể cùng được thanh toán. Cần ràng buộc và phân xử tại cấp đơn hoặc mục tiêu thanh toán tương ứng.

Việc tạo dòng idempotency hoặc bucket chưa tồn tại cũng phải an toàn khi cạnh tranh. Một truy vấn đọc không thấy dòng không tự ngăn giao dịch khác cùng tạo nó. Cần ràng buộc duy nhất, cơ chế khóa phù hợp và xử lý xung đột hoặc retry giao dịch.

### 9.2. Giả mã Java ở tầng dịch vụ

Đoạn sau thể hiện trách nhiệm của các thành phần, không phải chương trình có thể chạy độc lập:

```java
RetryResult requestPaymentRetry(Actor actor, RetryCommand command) {
    return transaction.required(() -> {
        Payment payment = payments.lockForOrder(command.orderId());
        authorization.requireCanPay(actor, payment);

        ExistingCommand existing = commands.findMatching(command);
        if (existing != null) {
            return existing.visibleResultFor(actor);
        }

        payment.requireNewAttemptAllowed();
        retryPolicy.requireEligible(payment, clock.now());

        // Tất cả phạm vi cùng đạt hoặc không tiêu thụ hạn mức attempt.
        velocity.consumeAtomically(payment, actor);

        // Giá trị từ payment, không lấy totalAmount của client làm chuẩn.
        Attempt attempt = attempts.createWithStableProviderKey(payment);
        commands.bind(command, attempt);
        outbox.enqueueDispatch(attempt.id());
        return RetryResult.accepted(attempt.id());
    });
}
```

Trong mô hình này, `commands.findMatching` phải có phạm vi đúng và kiểm tra dấu vân tay nội dung; nó không được tìm bằng một khóa tùy ý trên toàn hệ thống rồi trả dữ liệu của người khác. Cơ chế chống trùng phải được củng cố bằng ràng buộc lưu trữ, không chỉ bằng câu `if`.

`velocity.consumeAtomically` là một hợp đồng cần triển khai thật sự. Một thao tác nguyên tử trên một bộ đếm từ xa không tự tạo giao dịch chung với dữ liệu thanh toán. Nếu hai hệ thống tách biệt, cần thiết kế giữ chỗ, phục hồi và giới hạn độ vượt ngưỡng có chủ đích; không mặc định rằng các lệnh độc lập là nguyên tử toàn cục.

### 9.3. Không giữ giao dịch mở qua lời gọi mạng

Worker dispatch nhận công việc, chuyển trạng thái có điều kiện và gọi nhà cung cấp ngoài giao dịch dữ liệu ngắn. Mọi lần gửi của cùng provider operation dùng cùng khóa theo hợp đồng. Kết quả được ghi lại bằng chuyển trạng thái hợp lệ và cơ chế khử trùng lặp.

Nếu worker chết sau khi gửi nhưng trước khi ghi kết quả, worker mới không biết chắc yêu cầu chưa xảy ra. Nó phải phục hồi cùng thao tác bằng idempotency hoặc đối soát, không tạo attempt và khóa mới.

Lease hoặc khóa worker giúp tránh xử lý đồng thời trong hệ thống nội bộ, nhưng không tự thu hồi được một yêu cầu đã ra ngoài. Worker cũ còn chạy sau khi mất lease vẫn có thể tạo tác động nếu không có bảo vệ tương ứng tại ranh giới thực thi. Không coi thời gian lease hết là bằng chứng an toàn để thanh toán lần nữa.

## 10. Webhook, truy vấn trạng thái và chống trả tiền trùng

Webhook cần được xác minh theo cơ chế của nhà cung cấp và ánh xạ đến đúng merchant, provider operation và payment. Kiểm tra số tiền, loại tiền và quan hệ với đơn trước khi đánh dấu thanh toán hoàn tất. Client quay lại trang thành công không phải nguồn xác nhận duy nhất đáng tin cậy.

Xử lý webhook cũng cần idempotency và transaction:

1. Nhận diện sự kiện và ngăn tác động trùng.
2. Khóa trạng thái thanh toán liên quan.
3. Kiểm tra quan hệ, giá trị và chuyển trạng thái hợp lệ.
4. Cập nhật attempt và kết quả payment theo mô hình.
5. Ghi công việc hậu thanh toán một cách bền vững và chống trùng.

Không áp dụng trạng thái chỉ theo thứ tự webhook đến. Một thông báo cũ “đang xử lý” không được ghi đè trạng thái đã thành công. Khi nhận các kết quả mâu thuẫn hoặc một thay đổi không phù hợp với giả định hiện tại, cần đối soát theo nguồn có thẩm quyền của tích hợp thay vì tùy tiện bỏ qua hoặc mở attempt mới.

Nếu phát hiện hai provider operation đều thu tiền cho một khoản đáng lẽ chỉ thanh toán một lần, ràng buộc “một bản ghi paid” ở cơ sở dữ liệu chỉ giúp phát hiện xung đột nội bộ. Nó không làm khoản thu thứ hai biến mất. Cần ghi nhận sự cố, đối soát và thực hiện quy trình xử lý bù trừ có quyền theo nghiệp vụ.

Phòng ngừa quan trọng là không mở attempt cạnh tranh khi một thao tác trước vẫn có khả năng tạo tác động. Velocity là lớp hạn chế mức độ lạm dụng, không phải bằng chứng chống thu trùng.

## 11. Diễn tiến ví dụ

Giả sử đơn hàng được thanh toán một lần, cooldown đã được cấu hình và lần thử mới chỉ được phép sau kết quả đủ rõ:

| Thời điểm | Sự kiện | Quyết định đúng |
|---|---|---|
| 09:00:00 | Attempt A được tiếp nhận | Tiêu thụ 1 lượt attempt, lưu khóa provider, ghi công việc dispatch. |
| 09:00:03 | Lời gọi bị timeout sau khi gửi | A chuyển sang chưa rõ kết quả; không hoàn lượt và không tạo B. |
| 09:00:04 | Client retry cùng khóa | Trả operation A và trạng thái hiện tại; không tiêu thụ thêm lượt attempt. |
| 09:00:35 | Client dùng khóa mới khi A vẫn chưa rõ | Không tạo attempt mới, dù cooldown thời gian có thể đã hết. |
| 09:00:40 | Đối soát xác nhận A bị từ chối và thuộc nhóm được phép thử lại | Cập nhật trạng thái; tiếp tục áp dụng cooldown và các ngưỡng. |
| 09:01:00 | Các điều kiện thử mới đều đạt | Tiếp nhận B với định danh mới, tiêu thụ lượt attempt thứ 2. |
| 09:01:02 | B được xác nhận thành công | Đánh dấu khoản thanh toán hoàn tất và kích hoạt hậu xử lý chống trùng. |
| 09:01:03 | Thông báo cũ cho biết A từng đang xử lý | Không đưa đơn hàng quay lại trạng thái chưa thanh toán. |

Nếu tại 09:00:40 kết quả là A đã thành công, luồng phải kết thúc với A, không được tiếp nhận B. Nếu kết quả vẫn chưa đủ rõ, tiếp tục đối soát; không dùng việc chờ lâu làm điều kiện tự cấp một lượt thu tiền mới.

## 12. Chọn phản hồi và xử lý sự cố

### 12.1. Phản hồi phải thể hiện đúng nguyên nhân

| Nguyên nhân | Nội dung phản hồi cần có |
|---|---|
| Vượt giới hạn tần suất hoặc số lượng theo thời gian | Thông báo tạm hạn chế và hướng dẫn retry phù hợp; HTTP 429 có thể áp dụng theo hợp đồng API. |
| Attempt đang xử lý hoặc chưa rõ kết quả | Operation ID và trạng thái để theo dõi; không hướng client tạo khóa mới để vượt qua. |
| Cần xác thực bổ sung | Chỉ dẫn tiếp tục luồng hiện tại và thời hạn liên quan. |
| Đã thanh toán | Kết quả đã có, không tạo lại tác động. |
| Nội dung khác với idempotency key cũ | Xung đột rõ ràng, không tái sử dụng lệnh cũ cho khoản khác. |
| Thiếu quyền trên đơn hàng | Từ chối theo hợp đồng phân quyền, không tiết lộ dữ liệu thanh toán của chủ thể khác. |

Nếu cung cấp `Retry-After`, nó không phải lời hứa rằng một attempt mới sẽ được tiếp nhận đúng lúc đó: trạng thái cũ, hạn mức khác hoặc điều kiện nhà cung cấp vẫn có thể cấm thử mới. Không dùng 429 cho mọi trường hợp đang đối soát vì điều đó dễ khiến client hiểu rằng chỉ cần đợi rồi tạo thanh toán khác.

### 12.2. Khi nhà cung cấp hoặc dịch vụ rate limit gặp lỗi

Nhà cung cấp chậm có thể gây một làn sóng retry hợp lệ. Hệ thống nên làm giãn lịch, giới hạn gọi ra và cung cấp trạng thái có ích thay vì tăng retry đồng loạt. Không tự kết luận tất cả khách hàng tăng tốc thử lại đều là kẻ tấn công.

Không đọc được bộ đếm không có nghĩa đã dùng bằng 0. Với thao tác có thể tạo khoản thu, chính sách có thể tạm dừng tiếp nhận mới hoặc chuyển sang chờ. Luồng khôi phục kết quả cũ cần ngân sách được bảo vệ để không bị toàn bộ attempt mới chiếm hết tài nguyên.

Giới hạn cục bộ trên mỗi máy không bằng giới hạn toàn hệ thống. Nếu mỗi máy cho phép N lần gọi mà có nhiều máy cùng dispatch, tổng có thể lớn hơn dự kiến. Thiết kế ngân sách gọi ra cần xét phạm vi chia sẻ thật sự và cơ chế dự phòng khi đồng bộ lỗi.

## 13. Các cách lạm dụng và lỗi thiết kế cần kiểm soát

| Tình huống | Vì sao cơ chế đơn giản thất bại | Kiểm soát liên quan |
|---|---|---|
| Đổi idempotency key liên tục | Mỗi request bị coi là thao tác mới | State machine và ngưỡng theo đơn, khách hàng, phương tiện. |
| Tạo nhiều intent cho cùng đơn | Mỗi intent có khóa riêng nên không xung đột | Phân xử trên mục tiêu thanh toán ổn định và invariant cấp đơn. |
| Chia hoạt động qua nhiều tài khoản | Bộ đếm theo tài khoản riêng lẻ không đủ | Phạm vi phương tiện, merchant và tín hiệu rủi ro phù hợp. |
| Thay IP hoặc dùng mạng dùng chung | IP không phản ánh chắc chắn một chủ thể | Dùng danh tính nghiệp vụ; tránh chặn nhầm chỉ vì chung mạng. |
| Gửi nhiều request đồng thời | Tất cả cùng đọc lượng còn lại trước khi cập nhật | Kiểm tra và tiêu thụ nguyên tử, giới hạn một attempt chưa giải quyết. |
| Dò phương tiện bằng các attempt bị từ chối | Chỉ tính thanh toán thành công | Tính attempt được tiếp nhận và số lần gọi ra; theo dõi kết quả thất bại. |
| Cố tình tạo lỗi để nhận lại lượt | Mọi timeout đều hoàn hạn mức | Chỉ hoàn theo bằng chứng và định nghĩa bộ đếm; giữ trạng thái chưa rõ. |
| Gọi endpoint, SDK hoặc tác vụ nền khác | Rate limit chỉ đặt ở một controller | Điểm tiếp nhận chung trong dịch vụ nghiệp vụ. |
| Retry ở nhiều tầng | Tổng lần gọi bị nhân lên | Một nơi điều phối, giới hạn tổng và định danh ổn định. |
| Chuyển provider khi timeout | Hai bên không chia sẻ idempotency | Đối soát thao tác cũ trước khi mở khả năng thu tiền khác. |
| Polling quá nhanh để chờ kết quả | Truy vấn không được tính vào tải tích hợp | Backoff và ngân sách khôi phục trạng thái. |

Ngưỡng cần được điều chỉnh từ dữ liệu sử dụng hợp lệ, tác động có thể chịu và điều kiện tích hợp. Không dùng một con số duy nhất cho mọi sản phẩm rồi tự động khóa tài khoản khi chạm ngưỡng.

## 14. Quan sát và đánh giá hiệu quả

Một bản ghi phục vụ điều tra nên liên kết được request, command, payment, attempt, provider operation và sự kiện trạng thái. Ghi phiên bản chính sách, mã lý do, thời điểm xét, phạm vi giới hạn và lịch retry, nhưng không ghi bí mật hoặc dữ liệu thanh toán nhạy cảm.

Không đưa số thẻ đầy đủ, dữ liệu xác thực nhạy cảm, thông tin bí mật tích hợp hoặc token có thể dùng để thanh toán vào log. Với các tham chiếu cần thiết, giới hạn truy cập và dùng định danh nội bộ thích hợp. Băm một giá trị không tự làm nó hết nhạy cảm.

Các chỉ số hữu ích gồm:

- Số request, số attempt mới và số lần gọi provider, được phân biệt rõ.
- Số lần retry cùng operation và số attempt mới của cùng mục tiêu thanh toán.
- Tỷ lệ bị giới hạn theo phạm vi, phiên bản chính sách và nhóm sử dụng hợp lệ.
- Số payment đang `UNKNOWN`, tuổi của chúng và thời gian đối soát.
- Tỷ lệ thành công sau retry đủ điều kiện và số trường hợp thu trùng đã xác minh.
- Chênh lệch giữa số công việc outbox và tác động nghiệp vụ được ghi nhận.
- Mức tiêu thụ ngân sách truy vấn trạng thái so với lệnh tạo tác động.

Các tỷ lệ cần mẫu số và cửa sổ rõ ràng. Lấy attempt trong một giờ chia cho đơn thanh toán thành công trong cùng giờ có thể gây sai lệch nếu hai nhóm không thuộc cùng vòng đời đơn hàng. Nên phân tích cohort phù hợp khi đánh giá hiệu quả retry.

Tỷ lệ bị chặn tăng có thể do tấn công, do nhà cung cấp gặp sự cố hoặc do chính sách quá chặt. Đối chiếu kết quả đối soát, phản hồi hỗ trợ và hành vi hợp lệ trước khi kết luận. Không thể suy ra mọi trường hợp lạm dụng lọt qua chỉ từ dữ liệu bị chặn.

## 15. Kiểm thử các invariant quan trọng

### 15.1. Biên, thời gian và trạng thái

| Tình huống | Kết quả cần xác minh |
|---|---|
| Đã dùng 2/3 lượt, trạng thái cho phép và cooldown hết | Attempt mới được tiếp nhận, lượng dùng thành 3. |
| Đã dùng 3/3 lượt | Không có attempt thứ 4 và không có provider operation mới. |
| Còn lượt nhưng chưa đến `nextAllowedAt` | Không tiếp nhận sớm; đồng hồ client không thay đổi được quyết định. |
| Đúng tại mốc được phép | Áp dụng đúng quy ước biên, sau khi các điều kiện khác đều đạt. |
| Cooldown đã hết nhưng attempt cũ vẫn `UNKNOWN` | Không tạo attempt mới. |
| Đang `REQUIRES_ACTION` | Tiếp tục luồng hiện tại theo hợp đồng, không đếm mỗi lần mở xác thực là attempt mới. |
| Đơn đã thanh toán | Trả kết quả hiện có, không tạo thêm khoản thu. |
| Sửa số tiền hoặc loại tiền từ client | Không thay đổi snapshot thanh toán tin cậy trái quy tắc. |
| Attempt bị decline hoặc timeout | Không tự hoàn hạn mức attempt đã tiêu thụ. |

### 15.2. Đồng thời và nhiều phạm vi

Thực hiện kiểm thử trên cơ chế lưu trữ cần bảo vệ, không chỉ mock bộ đếm:

1. Hai mươi request cùng khóa và nội dung: một operation nội bộ, một attempt và một lần tiêu thụ hạn mức nghiệp vụ. Nếu không có lỗi hoặc truyền lại, chỉ một lần dispatch; khi có truyền lại được phép, mọi lần vẫn giữ định danh và không tạo thêm tác động.
2. Hai mươi khóa khác nhau cho cùng đơn, trong lúc attempt đầu vẫn chưa giải quyết: không mở các attempt cạnh tranh dù hạn mức theo thời gian còn lượt.
3. Nhiều đơn khác nhau của cùng khách hàng cùng tranh hạn mức 3: trong điều kiện mọi kiểm tra khác đều đạt và không có lỗi, chỉ 3 attempt được tiếp nhận.
4. Phạm vi khách hàng còn lượt nhưng phạm vi phương tiện đã đầy: từ chối, không để lại lượng đã tiêu thụ ở các phạm vi nghiệp vụ khác.
5. Nhiều worker trên nhiều máy tranh ngân sách gọi ra: tổng tuân thủ phạm vi đã thiết kế, không chỉ đúng trên từng máy.

Dùng điểm đồng bộ để các request thực sự cạnh tranh tại thời điểm đọc và cập nhật. Kiểm tra attempt, operation, lượng sử dụng, outbox và tác động phía nhà cung cấp mô phỏng; mã HTTP riêng lẻ không đủ chứng minh đúng.

### 15.3. Phục hồi, webhook và idempotency

- Mất phản hồi backend sau commit rồi retry: trả operation cũ, không tiêu thụ thêm lượt attempt.
- Cùng khóa nhưng đổi đơn hoặc phương tiện: xung đột, không tạo thao tác khác dưới khóa cũ.
- Worker chết sau khi provider xử lý: phục hồi bằng cùng operation hoặc đối soát, không sinh khóa thu tiền mới.
- Webhook gửi lặp: không ghi nhận thanh toán hoặc thực hiện hậu xử lý hai lần.
- Webhook đến sai thứ tự: không đưa trạng thái thành công quay lại đang xử lý.
- Webhook sai merchant, sai amount hoặc currency: không tự đánh dấu đơn đã thanh toán; tạo đường điều tra phù hợp.
- Provider key có thể đã hết thời gian ghi nhớ trong khi kết quả còn chưa rõ: không tự truyền lại như một thao tác mới được bảo vệ.
- Worker khởi động lại: không reset số lần retry, deadline hoặc lịch không được chạy trước đó.
- Jitter và backoff: không chạy sớm hơn mốc nhà cung cấp hoặc cooldown; không vượt giới hạn lần gọi đã định nghĩa.
- Chuyển provider trong tình trạng chưa rõ: bị ngăn hoặc đưa vào quy trình kiểm soát đã xác định, không failover tùy tiện.
- Dịch vụ giới hạn gặp lỗi: hành vi dự phòng đúng chính sách và vẫn giữ invariant thanh toán.

## 16. Bài tập thiết kế

Một đơn hàng có attempt A đã được tiếp nhận. Nhà cung cấp có thể đã xử lý A nhưng backend đang timeout. Người dùng mở tab khác, đổi phương tiện và gửi lệnh mới với idempotency key khác. Đồng thời, worker cũ nhận lại công việc do hàng đợi giao lặp.

Hãy thiết kế cách xử lý và trả lời:

1. Trạng thái nào ngăn việc tạo attempt mới dù ngưỡng velocity vẫn còn lượt?
2. Những bộ đếm nào tăng khi client gửi lại, worker truyền lại hoặc hệ thống truy vấn trạng thái?
3. Định danh và khóa nào phải giữ nguyên để phục hồi A?
4. Điều kiện nào đủ để cho phép một attempt B thật sự mới?
5. Nếu A được xác nhận thành công sau khi giao diện đã báo chờ, backend cập nhật và thông báo thế nào?
6. Nếu nguồn trạng thái hoặc rate limit không hoạt động, hành vi nào giữ được invariant mà vẫn cho phép khôi phục kết quả cũ?
7. Bằng chứng bền vững nào chứng minh không có hai tác động thu tiền cho cùng mục tiêu thanh toán?
