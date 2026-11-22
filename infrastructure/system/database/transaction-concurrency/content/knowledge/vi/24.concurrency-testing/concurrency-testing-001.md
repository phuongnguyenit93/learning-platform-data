# Chọn bất biến và tập tình huống cạnh tranh cần kiểm thử

Kiểm thử đồng thời có giá trị khi nó chứng minh được rằng nhiều giao dịch chạy xen kẽ vẫn giữ đúng quy tắc nghiệp vụ. Chỉ kiểm tra mỗi request trả HTTP 200, mỗi câu SQL không ném exception hoặc mỗi transaction có thể COMMIT là chưa đủ. Một hệ thống có thể trả thành công cho tất cả request nhưng vẫn bán vượt tồn kho, tạo hai bản ghi cho cùng một định danh, mất một lần cập nhật hoặc để trạng thái nghiệp vụ rơi vào tổ hợp không hợp lệ.

Cách thiết kế kiểm thử nên bắt đầu từ **bất biến**: điều gì phải luôn đúng trong mọi trạng thái đã commit? Từ mỗi bất biến, xác định những thao tác có thể thay đổi nó, những giao dịch có thể chạy đồng thời, thứ tự xen kẽ nguy hiểm và kết quả phải được kiểm tra. Khi làm theo hướng này, tập test phản ánh rủi ro nghiệp vụ thay vì chỉ phản ánh danh sách API hoặc câu SQL.

Bài học này trình bày cách chọn bất biến, chuyển chúng thành tình huống cạnh tranh, dựng lịch thực thi có kiểm soát, xác định oracle để kết luận đúng/sai và xây dựng bộ kiểm thử có thể chạy lặp lại trên database thật.

## 1. Bắt đầu từ quy tắc phải luôn đúng

### 1.1. Bất biến là điều kiện đúng với mọi trạng thái hợp lệ

Một bất biến (invariant) là điều kiện mà dữ liệu phải thỏa mãn trước và sau mỗi transaction đã commit. Nó mô tả trạng thái được phép tồn tại, không mô tả cách một hàm được viết.

Ví dụ:

- Số lượng tồn kho không bao giờ âm.
- Tổng tiền ghi nợ và ghi có của một bút toán cân bằng.
- Một mã hóa đơn chỉ thuộc về một hóa đơn trong phạm vi tổ chức.
- Một phòng không có hai lịch đặt đang hiệu lực bị chồng lấn.
- Một đơn hàng không thể vừa được giao vừa bị hủy.
- Mỗi message nghiệp vụ chỉ tạo ra tối đa một lần tác dụng phụ đã xác nhận.
- Một tài khoản không thể có hai bản ghi mặc định đang hoạt động cùng loại.
- Mọi hàng con phải tham chiếu đến hàng cha còn hợp lệ theo quy tắc nghiệp vụ.

Nếu không viết được điều kiện bằng ngôn ngữ rõ ràng, nhóm phát triển khó biết cần tạo lịch cạnh tranh nào và kiểm tra kết quả ra sao.

### 1.2. Phân biệt bất biến với quy trình thực hiện

Ví dụ nghiệp vụ bán một sản phẩm:

- Quy trình: đọc tồn kho, kiểm tra số lượng, tạo đơn, trừ tồn.
- Bất biến: tồn kho đã xác nhận không âm; mỗi đơn chỉ được trừ tồn một lần; đơn đã xác nhận phải có dòng hàng và số lượng hợp lệ.

Một test chỉ xác nhận hàm đặt hàng gọi đủ bốn bước có thể vẫn bỏ sót race condition giữa bước đọc và bước ghi. Bất biến mô tả kết quả cần giữ dù hai request chạy xen kẽ theo bất kỳ thứ tự nào.

### 1.3. Viết bất biến dưới dạng điều kiện kiểm tra được

Từ câu mô tả nghiệp vụ, chuyển thành biểu thức hoặc truy vấn có thể kiểm tra.

Ví dụ:

| Quy tắc | Dạng kiểm tra |
|---|---|
| Tồn kho không âm | Với mọi SKU, available_quantity >= 0 |
| Mỗi email chuẩn hóa chỉ thuộc một khách hàng trong tenant | Không có hai hàng cùng (tenant_id, normalized_email) |
| Tổng bút toán cân bằng | Với mỗi journal_entry, tổng debit = tổng credit |
| Một người chỉ có một đăng ký ACTIVE cho một sự kiện | Không có cặp (event_id, customer_id) trùng trong tập ACTIVE |
| Một message không tạo hai lần cấp thưởng | Mỗi message_id có tối đa một ledger entry tương ứng |
| Đơn đã giao không thể bị hủy trực tiếp | Không tồn tại trạng thái SHIPPED và CANCELLED cùng một đơn |
| Không có lịch phòng chồng lấn | Với cùng room_id, không có hai khoảng ACTIVE giao nhau |

Biểu thức cần phản ánh đúng phạm vi, trạng thái, cách chuẩn hóa và semantics của dữ liệu. Chẳng hạn, kiểm tra email thô có thể bỏ sót hai giá trị khác hoa/thường nhưng cùng định danh theo chính sách.

### 1.4. Bất biến có thể thuộc một hàng hoặc nhiều hàng

**Bất biến trong một hàng** thường dễ biểu diễn bằng CHECK hoặc kiểu dữ liệu:

- quantity >= 0.
- status thuộc tập giá trị cho phép.
- end_time > start_time.

**Bất biến giữa nhiều hàng** cần quan tâm đến concurrency:

- Một mã chỉ xuất hiện một lần.
- Một khách hàng chỉ có một hóa đơn chưa thanh toán.
- Không có hai lịch đặt chồng lấn.
- Tổng số ghế được phân bổ không vượt sức chứa.
- Tổng ghi nợ bằng tổng ghi có trên nhiều dòng.
- Ít nhất một nhân viên vẫn ở trạng thái trực.

Bất biến liên hàng thường là nơi các test tuần tự dễ vượt qua nhưng test đồng thời có thể phát hiện write skew, phantom hoặc check-then-act race.

## 2. Xác định phạm vi và thời điểm bất biến phải đúng

### 2.1. Trạng thái đã commit là điểm kiểm tra cơ bản

Nhiều bất biến áp dụng cho trạng thái đã commit. Trong transaction, dữ liệu trung gian có thể tạm thời chưa cân bằng hoặc chưa hoàn thiện, miễn là transaction chưa cho phép bên khác quan sát một trạng thái vi phạm theo isolation contract.

Ví dụ, một giao dịch chuyển tiền có thể cập nhật tài khoản nguồn trước tài khoản đích. Giữa hai câu UPDATE, tổng số dư tạm thời có thể giảm trong transaction. Sau COMMIT, tổng phải được bảo toàn. Nếu transaction rollback, cả hai thay đổi phải được hoàn tác.

Vì vậy, oracle thường cần đợi tất cả worker kết thúc, sau đó đọc trạng thái đã commit bằng một connection độc lập.

### 2.2. Một số quy tắc phải được bảo vệ ngay khi cấp quyền

Một số nghiệp vụ yêu cầu không có hai bên cùng được quyền thực hiện một tài nguyên tại cùng thời điểm:

- Chỉ một worker được claim một job chưa xử lý.
- Chỉ một người được giữ chỗ cuối cùng.
- Chỉ một tiến trình được sở hữu lease còn hiệu lực.
- Một mã coupon chỉ được redeem một lần.

Trong các trường hợp này, cần kiểm tra cả lịch sử thao tác và trạng thái cuối. Hai worker có thể cùng ghi kết quả cuối giống nhau nhưng đã cùng thực hiện một tác dụng phụ trước đó. Chỉ kiểm tra hàng cuối không phát hiện được việc gửi email hoặc gọi dịch vụ thanh toán hai lần.

### 2.3. Bất biến trạng thái và bất biến lịch sử

Có hai dạng oracle:

- **State invariant:** kiểm tra trạng thái hiện tại, ví dụ tồn kho không âm hoặc không có hai mã trùng.
- **History invariant:** kiểm tra chuỗi sự kiện, ví dụ một payment operation chỉ có một lần capture được xác nhận hoặc một job không có hai owner đồng thời.

Nếu nghiệp vụ phụ thuộc vào “chỉ xảy ra một lần”, “không bao giờ xảy ra trước”, “mỗi lần chỉ có một owner” hoặc “thứ tự A phải trước B”, hãy lưu đủ event/audit để test lịch sử.

### 2.4. Xác định ranh giới thời gian

Với quy tắc theo thời gian, phải thống nhất:

- Khoảng thời gian đóng hay mở ở đầu/cuối.
- Múi giờ và cách lưu UTC.
- Hai khoảng chạm biên có được coi là chồng lấn không.
- Trạng thái nào chiếm tài nguyên: PENDING, CONFIRMED hay ACTIVE.
- Lease hết hạn ở thời điểm bằng expiry hay chỉ sau expiry.
- Thời điểm nghiệp vụ dựa trên server time, database time hay thời gian do client gửi.

Nếu test không cố định các quy tắc này, hai người có thể đánh giá cùng một kết quả theo hai cách khác nhau.

## 3. Từ bất biến đến tình huống cạnh tranh

### 3.1. Tìm các thao tác cùng đọc hoặc ghi dữ liệu liên quan

Với mỗi bất biến, liệt kê các operation có thể làm nó đúng hoặc sai:

- Tạo mới.
- Cập nhật.
- Xóa cứng hoặc xóa mềm.
- Chuyển trạng thái.
- Claim/release.
- Retry.
- Xử lý message hoặc webhook.
- Batch import.
- Tác vụ nền và tác vụ bù trừ.

Sau đó xác định những operation nào có thể chạy đồng thời và chạm vào cùng hàng, cùng index key, cùng predicate hoặc cùng tài nguyên nghiệp vụ.

Ví dụ, bất biến “một người chỉ có một đăng ký ACTIVE cho một sự kiện” bị ảnh hưởng bởi:

- Hai request tạo đăng ký đồng thời.
- Một request tạo mới đồng thời với request hủy đăng ký cũ.
- Hai request cùng kích hoạt một đăng ký PENDING.
- Batch import chạy cùng API.
- Retry sau timeout khi lần đầu đã commit.

### 3.2. Tìm cửa sổ check-then-act

Một mẫu rủi ro:

~~~text
Đọc điều kiện
    |
    v
Tính quyết định ở ứng dụng
    |
    v
Ghi thay đổi
~~~

Nếu một transaction khác có thể thay đổi dữ liệu giữa đọc và ghi, hãy tạo tình huống để hai transaction cùng đọc một trạng thái ban đầu trước khi cả hai ghi.

Ví dụ:

~~~text
T1: đọc available = 1
T2: đọc available = 1
T1: quyết định đặt một sản phẩm
T2: quyết định đặt một sản phẩm
T1: ghi đơn và trừ tồn
T2: ghi đơn và trừ tồn
~~~

Oracle phải chứng minh chỉ một đơn được xác nhận hoặc số tồn không âm, tùy chính sách nghiệp vụ. Nếu cả hai request được báo thành công nhưng tồn kho thành -1, bất biến bị vi phạm.

### 3.3. Tìm các giao dịch đọc cùng snapshot nhưng ghi khác hàng

Đây là cách phát hiện write skew.

Ví dụ quy tắc “luôn có ít nhất một bác sĩ trực”:

~~~text
Ban đầu: bác sĩ A = ON, bác sĩ B = ON

T1 đọc: có 2 bác sĩ trực
T2 đọc: có 2 bác sĩ trực

T1 tắt A
T2 tắt B

T1 commit
T2 commit
~~~

Nếu hai transaction chỉ ghi hai hàng khác nhau và isolation level không phát hiện phụ thuộc liên hàng, kết quả có thể vi phạm quy tắc dù không có lost update trên cùng một hàng.

Test phải ép cả hai transaction đọc cùng trạng thái trước khi cho phép ghi. Chạy tuần tự sẽ không tái hiện lỗi.

### 3.4. Tìm thứ tự lấy tài nguyên khác nhau

Với hai tài nguyên A và B:

~~~text
T1: khóa A -> khóa B
T2: khóa B -> khóa A
~~~

Đây là ứng viên cho deadlock. Hãy kiểm tra cả thứ tự truy cập index, bảng phụ, trigger và foreign key, không chỉ thứ tự câu SQL nhìn thấy ở service.

### 3.5. Tìm thao tác lặp và giao hàng ít nhất một lần

Một request có thể được gửi lại do timeout hoặc message được giao lại sau khi worker crash.

Tạo các trường hợp:

- Hai request cùng idempotency key đến đồng thời.
- Một request retry sau khi lần đầu commit nhưng response bị mất.
- Consumer xử lý message rồi crash trước ACK.
- Webhook provider gửi lại cùng event ID.
- Hai request khác key nhưng cùng payload.
- Cùng key nhưng payload khác.

Mục tiêu là kiểm tra đúng semantics của key và bảo đảm tác dụng phụ không lặp.

## 4. Phân loại bất biến để không bỏ sót tình huống

### 4.1. Tính duy nhất và chống tạo trùng

Ví dụ:

- Một email chuẩn hóa duy nhất trong tenant.
- Một mã đơn duy nhất.
- Một coupon chỉ redeem một lần.
- Một webhook event chỉ được xử lý một lần.
- Một đăng ký ACTIVE duy nhất cho mỗi cặp sự kiện/khách hàng.

Tình huống cần thử: hai transaction cùng kiểm tra chưa tồn tại, hai INSERT cùng unique key, UPSERT đồng thời, soft delete và tạo lại, hoặc cùng key trong hai tenant khác nhau.

### 4.2. Giới hạn số lượng và tài nguyên

Ví dụ:

- Tồn kho không âm.
- Không bán quá sức chứa.
- Không có quá N reservation đang hoạt động.
- Số lượt sử dụng coupon không vượt quota.
- Một tài khoản không chi vượt hạn mức.

Tình huống cần thử: nhiều request cùng tranh phần tài nguyên cuối cùng, nhiều transaction đọc cùng quota, một giao dịch giải phóng tài nguyên trong lúc giao dịch khác đặt, hoặc batch và API cùng cập nhật.

### 4.3. Bảo toàn tổng và cân bằng

Ví dụ:

- Chuyển tiền không làm thay đổi tổng số dư.
- Tổng debit bằng tổng credit.
- Tổng số vé đã bán không vượt số vé phát hành.
- Tổng số lượng ở các kho bằng tổng số lượng theo sổ kiểm kê.

Tình huống cần thử: hai chuyển khoản giao nhau, cập nhật hai tài khoản theo thứ tự ngược, retry một transfer, rollback giữa các bước và chạy đối soát sau khi mọi transaction kết thúc.

### 4.4. Chuyển trạng thái hợp lệ

Ví dụ:

- DRAFT -> SUBMITTED -> APPROVED.
- PENDING -> PAID hoặc CANCELLED.
- Job READY -> CLAIMED -> DONE.
- Payment AUTHORIZED -> CAPTURED hoặc VOIDED.

Tình huống cần thử: hai lệnh chuyển trạng thái cạnh tranh, lệnh cũ đến muộn, retry cùng transition, hủy đồng thời với thanh toán và worker cũ cập nhật sau khi lease hết hạn.

### 4.5. Quan hệ và vòng đời dữ liệu

Ví dụ:

- Không tạo hàng con nếu hàng cha đã bị xóa.
- Không xóa khách hàng đang có hóa đơn cần lưu trữ.
- Không để tài liệu ACTIVE tham chiếu đến phiên bản đã thu hồi.
- Một user chỉ có một bản ghi mặc định.

Tình huống cần thử: INSERT child đồng thời DELETE parent, hai thao tác cascade, soft delete đồng thời với tạo tham chiếu và thay đổi trạng thái cha/con.

### 4.6. Khoảng và predicate

Ví dụ:

- Lịch đặt không chồng lấn.
- Không có hai nhân viên nhận cùng ca.
- Một người chỉ có một hợp đồng hiệu lực tại một thời điểm.
- Tổng phân bổ trong nhóm không vượt giới hạn.

Tình huống cần thử: hai transaction cùng truy vấn “không có hàng nào thỏa điều kiện” rồi cùng INSERT; hai khoảng gần nhau ở biên; chèn phantom giữa lần kiểm tra và ghi; thay đổi trạng thái khiến hàng đi vào hoặc ra khỏi tập predicate.

### 4.7. Thứ tự và tính nhất quán của lịch sử

Ví dụ:

- Không phát SHIPPED trước PAID.
- Một sequence number không bị cấp hai lần.
- Một sự kiện chỉ được áp dụng sau sự kiện predecessor.
- Một phiên bản cấu hình mới chỉ có hiệu lực sau khi được publish.

Tình huống cần thử: message đến sai thứ tự, worker xử lý song song, retry sự kiện cũ, hai writer cùng tăng sequence và event bị phát lại.

## 5. Tạo ma trận bất biến - thao tác - lịch cạnh tranh

Một bảng traceability giúp chuyển quy tắc thành test cụ thể.

| Bất biến | Thao tác ảnh hưởng | Tình huống cạnh tranh | Oracle |
|---|---|---|---|
| Tồn kho không âm | Đặt hàng, hủy, nhập kho | N request tranh một đơn vị cuối | available >= 0; số đơn xác nhận không vượt hàng |
| Email duy nhất theo tenant | Tạo/sửa khách hàng | Hai INSERT cùng normalized email | Chỉ một hàng cho mỗi (tenant, email) |
| Chỉ một đăng ký ACTIVE | Tạo, kích hoạt, hủy | Hai request kích hoạt cùng người/sự kiện | COUNT(ACTIVE) <= 1 |
| Chuyển tiền bảo toàn tổng | Debit/credit | Hai transfer giao nhau, một lần retry | Tổng tiền không đổi; mỗi transfer có một ledger pair |
| Lịch không chồng lấn | Tạo/đổi lịch | Hai khoảng giao nhau được đặt đồng thời | Không có cặp khoảng ACTIVE giao nhau |
| Job chỉ có một owner hợp lệ | Claim/renew/complete | Hai worker claim cùng job; lease hết hạn | Tối đa một owner hợp lệ tại một thời điểm |
| Event chỉ áp dụng một lần | Consumer xử lý message | Redelivery sau crash trước ACK | Một hiệu ứng nghiệp vụ cho mỗi message ID |
| Đơn có transition hợp lệ | Pay/cancel/ship | Thanh toán và hủy đến đồng thời | Trạng thái cuối thuộc tập hợp hợp lệ, ledger phù hợp |

Không phải bất biến nào cũng cần mọi loại test. Ma trận giúp chọn test có giá trị và chỉ ra những khoảng trống chưa có oracle.

## 6. Thiết kế oracle: biết chắc test đã phát hiện lỗi

### 6.1. Oracle phải kiểm tra điều kiện nghiệp vụ

Một test không nên chỉ assert:

~~~java
assertTrue(responseA.isSuccessful());
assertTrue(responseB.isSuccessful());
~~~

Hai response thành công không chứng minh dữ liệu đúng. Cần kiểm tra kết quả đã commit:

~~~sql
SELECT SUM(available_quantity)
FROM inventory
WHERE sku = 'BOOK-01';
~~~

Hoặc:

~~~sql
SELECT tenant_id, normalized_email, COUNT(*)
FROM customer
GROUP BY tenant_id, normalized_email
HAVING COUNT(*) > 1;
~~~

Oracle nên diễn đạt trực tiếp bất biến đã nêu ở đầu bài.

### 6.2. Kiểm tra cả kết quả và số tác dụng phụ

Với idempotency, trạng thái đơn hàng có thể chỉ có một hàng nhưng payment provider đã bị gọi hai lần. Cần ghi nhận số lần gọi bằng fake provider, event log hoặc bảng ledger.

Ví dụ oracle:

- Một idempotency key có tối đa một order ID.
- Số payment capture thành công bằng 1.
- Hai lần gửi cùng key trả cùng resource ID.
- Payload mismatch bị từ chối.
- Outbox có một event nghiệp vụ cho operation đó.

### 6.3. Kiểm tra các bất biến liên quan cùng lúc

Một giao dịch có thể giữ một bất biến nhưng phá bất biến khác. Ví dụ, hệ thống không bán vượt tồn kho nhưng lại tạo đơn không có payment record.

Với một luồng nghiệp vụ, liệt kê nhóm bất biến liên quan:

- Không bán vượt số lượng.
- Mỗi đơn có tổng dòng hàng đúng.
- Tổng tiền đơn khớp ledger.
- Payment chỉ capture một lần.
- Mỗi order operation có một event outbox.
- Trạng thái đơn và payment tương thích.

Oracle có thể gồm nhiều truy vấn và kiểm tra lịch sử.

### 6.4. Đọc bằng connection độc lập sau khi worker kết thúc

Không nên dùng connection của một transaction còn mở để xác minh kết quả của transaction khác. Sau khi tất cả worker kết thúc, mở connection mới ở isolation phù hợp và truy vấn dữ liệu đã commit.

Nếu test chạy song song nhiều case trên cùng database, dùng tenant/key/schema riêng để tránh oracle của case này nhìn thấy dữ liệu case khác.

### 6.5. Không suy luận từ số exception đơn thuần

Một exception có thể là kết quả được mong đợi, ví dụ unique violation, deadlock victim hoặc serialization failure. Điều cần kiểm tra là:

- Lỗi đúng loại có được trả về không?
- Transaction đã rollback đúng phạm vi chưa?
- Ứng dụng có retry theo chính sách không?
- Kết quả cuối có giữ bất biến không?
- Có tác dụng phụ bị lặp không?

Một test có thể pass dù một worker nhận lỗi, miễn là nghiệp vụ cho phép một request thất bại và dữ liệu vẫn hợp lệ.

## 7. Tạo lịch đồng thời có kiểm soát

### 7.1. Dùng nhiều connection và transaction thật

Mỗi actor trong test phải dùng connection độc lập. Nếu hai thread vô tình dùng cùng một connection hoặc cùng transaction context, test không còn mô phỏng hai giao dịch độc lập.

Mẫu khung:

~~~text
Actor A                         Actor B
-------                         -------
Lấy connection A                Lấy connection B
BEGIN                           BEGIN
Đọc trạng thái                   Đọc trạng thái
Báo đã sẵn sàng                  Báo đã sẵn sàng
Chờ barrier                      Chờ barrier
Ghi thay đổi                     Ghi thay đổi
COMMIT/ROLLBACK                  COMMIT/ROLLBACK
~~~

Barrier bảo đảm cả hai actor đạt cùng một điểm trước khi tiếp tục.

### 7.2. Barrier, latch và semaphore

Các công cụ đồng bộ hữu ích:

- **Barrier:** chờ một nhóm actor cùng đến một điểm rồi cho tất cả đi tiếp.
- **Latch:** một actor báo sự kiện; actor khác chờ sự kiện đó.
- **Semaphore:** giới hạn số actor được đi qua một đoạn.
- **Queue điều phối:** test controller gửi tín hiệu theo thứ tự định trước.
- **Hook trong test adapter:** đặt điểm chờ sau một thao tác cụ thể mà không thay đổi production behavior.

Trong Java, có thể dùng CyclicBarrier, CountDownLatch, Phaser hoặc Semaphore. Chọn công cụ theo lịch cần tạo.

### 7.3. Không dùng sleep để ép thứ tự

Mẫu sau không đáng tin cậy:

~~~java
Thread.sleep(100);
~~~

Thời gian thread được scheduler cấp CPU phụ thuộc tải máy, CI, GC và hệ điều hành. Một khoảng ngủ có thể quá ngắn trên máy chậm hoặc quá dài trên máy nhanh.

Hãy chờ sự kiện có ý nghĩa, ví dụ “T1 đã đọc xong”, “T2 đã lấy khóa”, “T1 đang chờ blocker” hoặc “cả hai đã đến trước INSERT”.

Có thể dùng timeout cho chính barrier/latch để test không treo vô hạn, nhưng timeout chỉ là giới hạn an toàn, không phải công cụ tạo thứ tự.

### 7.4. Chèn điểm đồng bộ tại ranh giới logic

Không phải lúc nào test cũng điều khiển được thời điểm bên trong database. Có thể tạo một service/test seam để đặt barrier:

~~~text
T1: repository.read()
T1: test hook afterRead()
T1: repository.write()

T2: repository.read()
T2: test hook afterRead()
T2: repository.write()
~~~

Hook phải chỉ tồn tại trong test hoặc được tiêm qua interface. Tránh thêm sleep hoặc debug endpoint vào production chỉ để test.

### 7.5. Quan sát lock wait khi cần kiểm tra blocking

Với test deadlock hoặc lock timeout, barrier ở ứng dụng có thể chưa chứng minh session đã lấy khóa. Có thể dùng một connection observer đọc DMV hoặc view lock của DBMS để xác nhận waiter/blocker.

Ví dụ trong SQL Server, test observer có thể theo dõi sys.dm_exec_requests và wait_type; PostgreSQL có pg_stat_activity/pg_blocking_pids; MySQL có Performance Schema data_lock_waits.

Observer cần quyền phù hợp và không nên làm thay đổi lịch đang kiểm thử.

## 8. Tình huống 1: lost update trên cùng một hàng

### 8.1. Bất biến

Nếu hai giao dịch cùng tăng số dư hoặc số lượng, cả hai lần tăng phải được phản ánh trong kết quả cuối.

Giả sử ban đầu counter = 10. T1 tăng 3 và T2 tăng 5. Kết quả đúng là 18.

### 8.2. Lịch cạnh tranh

~~~text
T1: SELECT counter -> 10
T2: SELECT counter -> 10
Barrier
T1: UPDATE counter = 10 + 3
T2: UPDATE counter = 10 + 5
COMMIT cả hai
~~~

Nếu ứng dụng tính giá trị mới ở client rồi ghi giá trị tuyệt đối, một lần tăng có thể bị mất. Giá trị cuối có thể là 13 hoặc 15 thay vì 18.

### 8.3. Các cách triển khai cần so sánh

**Read-modify-write không bảo vệ:**

~~~sql
SELECT counter
FROM account_counter
WHERE account_id = 10;

UPDATE account_counter
SET counter = :value_read + :delta
WHERE account_id = 10;
~~~

**Cập nhật nguyên tử:**

~~~sql
UPDATE account_counter
SET counter = counter + :delta
WHERE account_id = 10;
~~~

**Optimistic concurrency:**

~~~sql
UPDATE account_counter
SET counter = :new_value,
    version = version + 1
WHERE account_id = 10
  AND version = :version_read;
~~~

Nếu row count bằng 0, ứng dụng phải đọc lại và tính lại hoặc báo conflict.

### 8.4. Oracle

- Tổng counter phải bằng giá trị ban đầu cộng tổng delta đã được xác nhận.
- Không có lần tăng đã được chấp nhận nào biến mất.
- Nếu optimistic update có conflict, retry phải tính lại từ dữ liệu mới.
- Test phải xác định request nào được xem là thành công và request nào được retry.

## 9. Tình huống 2: oversell hoặc vượt quota

### 9.1. Bất biến

Tổng số lượng được xác nhận không vượt số lượng có thể cấp:

\[
confirmed\_quantity \le available\_capacity
\]

Ví dụ kho chỉ còn 1 sản phẩm nhưng có 20 request cùng đặt.

### 9.2. Lịch cạnh tranh

- N actor cùng đọc available = 1.
- Dùng barrier cho tất cả hoàn tất đọc.
- Tất cả thử ghi đơn và giảm tồn.
- Thu thập kết quả từng actor.
- Đợi tất cả transaction kết thúc.
- Đọc lại inventory và orders bằng connection độc lập.

### 9.3. Oracle

Nếu nghiệp vụ cho phép chỉ một request thành công:

- Chính xác một đơn được xác nhận.
- Số tồn còn lại bằng 0.
- Không có đơn khác ở trạng thái đã xác nhận cho cùng đơn vị hàng cuối.
- Các request thất bại có mã lỗi hoặc trạng thái chờ phù hợp.

Nếu hệ thống hỗ trợ backorder, oracle phải phản ánh chính sách đó thay vì ép số đơn xác nhận bằng số tồn.

### 9.4. Biến thể cần thử

- Một request hủy đơn trong lúc request khác đặt hàng.
- Batch nhập kho chạy đồng thời với nhiều đơn.
- Hai SKU cùng dùng một quota tổng.
- Một request timeout sau khi đã trừ tồn.
- Retry cùng idempotency key.
- Hai request khác key nhưng cùng người dùng và cùng ý định.

## 10. Tình huống 3: write skew trên nhiều hàng

### 10.1. Bất biến

Ví dụ luôn có ít nhất một người trực:

\[
active\_staff\_count \ge 1
\]

### 10.2. Lịch cạnh tranh

~~~text
Ban đầu A=ON, B=ON

T1 đọc COUNT(ON)=2
T2 đọc COUNT(ON)=2
Barrier sau khi đọc

T1 đặt A=OFF
T2 đặt B=OFF

T1 COMMIT
T2 COMMIT
~~~

Nếu mỗi transaction chỉ ghi hàng của chính nó, SNAPSHOT có thể cho phép cả hai commit vì không có cùng hàng bị sửa.

### 10.3. Oracle

Sau khi tất cả transaction hoàn tất:

~~~sql
SELECT COUNT(*)
FROM staff_shift
WHERE status = 'ON';
~~~

Kết quả phải lớn hơn hoặc bằng 1.

### 10.4. Biến thể

- Giới hạn số người nghỉ cùng lúc.
- Tổng hạn mức tín dụng giữa nhiều tài khoản.
- Số chỗ còn lại của một sự kiện.
- Một khách hàng chỉ có một hợp đồng ACTIVE.
- Nhiều worker cập nhật các dòng quota khác nhau nhưng cùng ảnh hưởng một tổng.

Test cần chạy trên đúng isolation level dự kiến. Nếu production dùng RCSI nhưng test chỉ chạy SERIALIZABLE, test có thể che mất lỗi.

## 11. Tình huống 4: uniqueness race và tạo dữ liệu trùng

### 11.1. Bất biến

Không có hai hàng cùng khóa nghiệp vụ trong phạm vi quy định.

Ví dụ UNIQUE(tenant_id, normalized_email).

### 11.2. Lịch cạnh tranh

~~~text
T1: SELECT email -> không có
T2: SELECT email -> không có
Barrier
T1: INSERT
T2: INSERT
T1/T2: COMMIT hoặc nhận conflict
~~~

### 11.3. Oracle

- Chỉ có một hàng cho khóa nghiệp vụ.
- Một request có thể thành công, request còn lại phải nhận conflict hoặc replay theo hợp đồng.
- Không có hàng mồ côi hoặc tác dụng phụ trùng.
- Cùng email ở tenant khác vẫn được phép nếu phạm vi là tenant.

### 11.4. Biến thể

- Hai request dùng chuỗi email khác hoa/thường nhưng cùng giá trị chuẩn hóa.
- Một request soft delete trong khi request khác tạo lại.
- Hai UPSERT cùng khóa.
- Một đường API và một batch import cùng ghi.
- Cùng key idempotency nhưng payload khác.

## 12. Tình huống 5: phantom và predicate race

### 12.1. Bất biến

Không có hai reservation chồng lấn trong cùng phòng.

Hai khoảng nửa mở \([start, end)\) giao nhau khi:

\[
a.start < b.end \land b.start < a.end
\]

Quy tắc biên phải được xác định trước: một reservation kết thúc đúng lúc reservation khác bắt đầu có thể được coi là không chồng lấn.

### 12.2. Lịch cạnh tranh

~~~text
T1 kiểm tra không có reservation giao với [10:00, 11:00)
T2 kiểm tra không có reservation giao với [10:30, 11:30)
Barrier
T1 INSERT khoảng đầu
T2 INSERT khoảng sau
COMMIT
~~~

Hai truy vấn kiểm tra có thể cùng không tìm thấy hàng trước khi bất kỳ transaction nào ghi.

### 12.3. Oracle

Tìm mọi cặp reservation ACTIVE trong cùng phòng mà khoảng thời gian giao nhau. Kết quả phải rỗng.

### 12.4. Cơ chế bảo vệ và biến thể test

- Exclusion constraint nếu DBMS hỗ trợ.
- SERIALIZABLE hoặc key-range locking.
- Guard row theo room_id.
- Unique slot nếu thời gian được chia thành bucket.
- Chuyển trạng thái ACTIVE/RELEASED đồng thời với INSERT.
- Thay đổi giờ bắt đầu/kết thúc cùng lúc.

Test nên chạy cả cặp khoảng trùng hoàn toàn, giao một phần, lồng nhau và chỉ chạm biên.

## 13. Tình huống 6: chuyển tiền và bảo toàn tổng

### 13.1. Bất biến

Với một chuyển tiền nội bộ:

- Tổng số dư trước và sau bằng nhau.
- Tài khoản nguồn không âm nếu nghiệp vụ cấm thấu chi.
- Một transfer ID chỉ có một cặp debit/credit.
- Debit và credit cùng commit hoặc cùng rollback.

### 13.2. Tình huống cạnh tranh

- Hai transfer A -> B và B -> A.
- Nhiều transfer cùng rút từ một tài khoản.
- Một transfer retry sau timeout.
- Hai transfer khóa tài khoản theo thứ tự khác nhau.
- Hủy transfer đồng thời với xử lý capture/settlement.

### 13.3. Oracle

~~~sql
SELECT SUM(balance)
FROM account;
~~~

Tổng số dư phải bằng tổng ban đầu nếu không có phí hoặc tiền vào/ra ngoài hệ thống. Đồng thời đối chiếu ledger:

~~~sql
SELECT transfer_id
FROM ledger_entry
GROUP BY transfer_id
HAVING SUM(CASE WHEN side = 'DEBIT' THEN amount ELSE -amount END) <> 0;
~~~

Câu truy vấn chỉ minh họa; dấu và đơn vị phải khớp mô hình ledger. Cần kiểm tra một transfer có đúng số dòng theo quy tắc và không có duplicate transfer ID.

### 13.4. Kiểm tra deadlock và retry

Nếu hai luồng khóa A rồi B và B rồi A, có thể xảy ra deadlock. Test nên chứng minh:

- Không có request bị treo vô hạn.
- Deadlock victim được nhận diện.
- Transaction bị chọn làm victim không để lại debit một nửa.
- Retry chạy toàn bộ transfer với cùng operation ID.
- Kết quả cuối có một transfer hoàn chỉnh, không có hai lần ghi sổ.

## 14. Tình huống 7: chuyển trạng thái cạnh tranh

### 14.1. Bất biến

Một đơn hàng chỉ được chuyển qua các transition hợp lệ:

~~~text
PENDING -> PAID -> FULFILLED
    |
    +----> CANCELLED
~~~

Không được có cả PAID và CANCELLED như hai kết quả cuối cùng của cùng một đơn, trừ khi nghiệp vụ có trạng thái refund/compensation riêng.

### 14.2. Lịch cạnh tranh

- Request A thanh toán.
- Request B hủy đơn.
- Cả hai đọc status = PENDING.
- Barrier.
- A cập nhật PAID.
- B cập nhật CANCELLED.
- Cả hai cố commit.

Nếu UPDATE không kiểm tra trạng thái hiện tại hoặc version, một lệnh có thể ghi đè lệnh kia.

### 14.3. Oracle

- Trạng thái cuối thuộc tập transition hợp lệ.
- Ledger/payment record tương ứng trạng thái cuối.
- Không capture tiền cho đơn đã hủy nếu chính sách không cho phép.
- Không có shipment cho đơn chưa được thanh toán.
- Nếu một transition thất bại, client nhận conflict hoặc trạng thái hiện tại phù hợp.

### 14.4. Compare-and-set

Một mẫu bảo vệ:

~~~sql
UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE order_id = :id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Nếu row count bằng 0, transition không còn hợp lệ theo trạng thái đã đọc. Test phải xác nhận service xử lý row count 0 đúng cách.

## 15. Tình huống 8: duplicate request, webhook và message redelivery

### 15.1. Bất biến

Cùng một operation ID chỉ tạo một lần tác dụng nghiệp vụ.

### 15.2. Các lịch cần dựng

**Cùng key đồng thời:**

~~~text
R1: INSERT idempotency key K
R2: INSERT idempotency key K
R1: thực hiện nghiệp vụ và COMMIT
R2: đọc kết quả đã lưu và replay
~~~

**Commit xong nhưng mất response:**

~~~text
R1: tạo đơn + lưu kết quả + COMMIT
R1: response bị mất
R1 retry cùng key K
Server: trả lại order ID cũ
~~~

**Consumer crash trước ACK:**

~~~text
Consumer nhận message M
Ghi nghiệp vụ và inbox marker
COMMIT
Worker crash trước ACK
Broker giao lại M
Consumer nhận ra M đã xử lý
Không áp dụng nghiệp vụ lần nữa
~~~

### 15.3. Oracle

- Một operation ID có tối đa một resource.
- Một payment capture hoặc cấp thưởng chỉ xảy ra một lần.
- Cùng key/cùng payload trả kết quả tương đương.
- Cùng key/khác payload bị từ chối.
- Inbox marker và thay đổi nghiệp vụ commit nguyên tử.
- Outbox có số event đúng theo hợp đồng.

### 15.4. Biến thể

- Key trùng ở hai tenant.
- Key hết hạn rồi request cũ được gửi lại.
- Worker cũ hoàn tất sau khi lease đã được worker mới nhận.
- Provider gửi webhook cùng event ID nhưng khác metadata truyền tải.
- Hai event khác ID nhưng payload giống nhau.

## 16. Tình huống 9: claim job, lease và worker chạy trùng

### 16.1. Bất biến

Tại một thời điểm, chỉ một worker có lease hợp lệ cho một job. Worker mất lease không được ghi kết quả sau worker mới.

### 16.2. Lịch cạnh tranh

- Worker A và B cùng tìm job READY.
- Cả hai cùng thử claim.
- Một worker được claim; worker còn lại phải bỏ qua hoặc lấy job khác.
- A bị pause hoặc mất kết nối.
- Lease A hết hạn.
- B claim lại job.
- A tỉnh lại và cố ghi kết quả.

### 16.3. Oracle

- Không có hai lease hợp lệ chồng lấn theo thời gian.
- Chỉ owner có fencing token/version mới nhất được hoàn tất.
- Job không bị mất sau worker crash.
- Tác dụng phụ không bị thực hiện hai lần nếu worker cũ và mới cùng chạy.
- Job cuối cùng đạt DONE hoặc trạng thái lỗi có thể phục hồi.

### 16.4. Fencing token

Lease một mình có thể không đủ nếu worker cũ vẫn chạy sau khi hết hạn. Mỗi lần claim nên tăng token:

~~~sql
UPDATE work_item
SET owner_id = :worker,
    lease_until = :expiry,
    fencing_token = fencing_token + 1
WHERE job_id = :job
  AND status = 'READY';
~~~

Khi ghi kết quả, worker phải gửi token đã nhận và database kiểm tra nó vẫn là token hiện tại. Worker cũ có token thấp hơn sẽ không thể ghi đè kết quả của worker mới.

## 17. Tình huống 10: deadlock, lock timeout và blocking chain

### 17.1. Bất biến và mục tiêu

Không có dữ liệu dở dang sau khi transaction bị hủy; request phải kết thúc trong giới hạn; giao dịch được retry không tạo tác dụng phụ trùng.

### 17.2. Deadlock có chủ đích

- T1 khóa hàng A.
- T2 khóa hàng B.
- T1 yêu cầu B.
- T2 yêu cầu A.
- Quan sát deadlock report.
- Xác nhận một transaction được chọn làm victim.
- Kiểm tra transaction victim rollback đúng phạm vi.
- Kiểm tra transaction còn lại có thể hoàn tất.

Không assert victim phải luôn là T1 hoặc T2; chính sách chọn victim phụ thuộc DBMS và chi phí rollback.

### 17.3. Blocking chain không có chu trình

- T1 giữ khóa A.
- T2 chờ A và giữ khóa B.
- T3 chờ B.
- T1 commit.
- T2 tiếp tục rồi commit.
- T3 tiếp tục.

Oracle xác nhận chuỗi chờ có thể tiến triển và không bị phân loại nhầm thành deadlock.

### 17.4. Lock timeout

Giữ khóa trong T1, cho T2 chờ với lock timeout ngắn. Xác nhận:

- T2 nhận đúng lỗi timeout.
- Transaction state được xử lý đúng.
- Connection được phục hồi hoặc loại bỏ.
- T1 vẫn có thể commit/rollback.
- Retry không làm nhân đôi thay đổi.

## 18. Tình huống 11: cancellation và timeout quanh COMMIT

### 18.1. Bất biến

Một thao tác đã commit không được thực hiện lại thành một thao tác nghiệp vụ mới chỉ vì client không nhận response.

### 18.2. Các điểm fault injection

Cố ý làm gián đoạn ở các điểm:

1. Trước khi lấy connection.
2. Sau khi lấy connection, trước câu SQL.
3. Sau khi đọc dữ liệu, trước khi ghi.
4. Sau khi ghi nhưng trước COMMIT.
5. Trong lúc gửi COMMIT.
6. Sau COMMIT thành công nhưng trước khi trả response.
7. Sau khi gửi event nhưng trước ACK.
8. Sau khi claim job nhưng trước khi lưu kết quả.

### 18.3. Oracle

- Nếu chắc chắn rollback trước commit, không có thay đổi đã xác nhận.
- Nếu commit outcome không rõ, cùng idempotency key phải truy vấn được kết quả hoặc tiếp tục theo protocol an toàn.
- Không có hai đơn, hai lần capture hoặc hai event nghiệp vụ do retry.
- Connection không sạch không được trả về pool.
- Worker/job có trạng thái có thể phục hồi.

Test timeout cần phân biệt “caller ngừng chờ” với “server đã hủy statement” và “transaction đã rollback”.

## 19. Tình huống 12: foreign key, cascade và vòng đời dữ liệu

### 19.1. Bất biến

Không có hàng con hợp lệ nào tham chiếu đến hàng cha không tồn tại. Các thao tác xóa/cập nhật phải tuân theo chính sách RESTRICT, CASCADE hoặc soft delete.

### 19.2. Lịch cạnh tranh

- T1 INSERT hàng con tham chiếu parent P.
- T2 DELETE hoặc soft delete parent P.
- Hai thao tác chạy đồng thời.
- Quan sát khóa và kết quả commit/rollback.

### 19.3. Oracle

- Nếu INSERT con thành công, parent phải còn hợp lệ theo chính sách.
- Nếu DELETE cha thành công với CASCADE, không còn child thuộc phạm vi cascade.
- Nếu chính sách RESTRICT, parent không bị xóa khi còn child hợp lệ.
- Không có hàng con mồ côi.
- Không có side effect từ trigger/cascade bị lặp khi retry.

## 20. Tình huống 13: batch, API và nhiều đường ghi

Một lỗi đồng thời thường không xuất hiện khi chỉ có một service ghi dữ liệu. Trong production, cùng một bảng có thể được cập nhật bởi:

- API đồng bộ.
- Worker nền.
- Batch import.
- Scheduled reconciliation.
- Admin tool.
- Consumer message.
- Trigger hoặc stored procedure.
- Job migration/backfill.

Hãy đưa các đường ghi vào ma trận. Ví dụ, batch import tạo khách hàng trong lúc API đăng ký cùng email; một job cập nhật trạng thái tồn kho trong lúc checkout; reconciliation ghi ledger trong lúc webhook xử lý payment.

Các test này phát hiện việc một writer bỏ qua chuẩn hóa, guard row, version check hoặc idempotency protocol mà writer khác đang tuân thủ.

## 21. Ma trận mức độ cô lập và loại lịch

Không phải mọi DBMS triển khai isolation level giống nhau. Hãy chạy tình huống quan trọng trên đúng DBMS, phiên bản, cấu hình và isolation level của production.

| Tình huống | READ COMMITTED | REPEATABLE READ | SNAPSHOT/RCSI | SERIALIZABLE |
|---|---|---|---|---|
| Dirty read | Không | Không | Không | Không |
| Non-repeatable read qua nhiều statement | Có thể | Thường bị ngăn | RCSI: có thể; SNAPSHOT: không trong transaction | Bị ngăn |
| Phantom qua nhiều statement | Có thể | Tùy DBMS | RCSI: có thể; SNAPSHOT: snapshot ổn định | Bị ngăn theo semantics |
| Lost update | Phụ thuộc cách đọc/ghi | Phụ thuộc DBMS và pattern | Có thể có conflict hoặc vẫn cần bảo vệ | Lịch được tuần tự hóa, vẫn cần xử lý lỗi |
| Write skew | Có thể | Tùy DBMS | Có thể dưới snapshot isolation | Được ngăn nếu predicate được bảo vệ đúng |
| Writer cùng sửa một hàng | Có thể chờ | Có thể chờ | Có thể conflict | Có thể chờ |
| Deadlock | Có thể | Có thể | Vẫn có thể | Có thể |

Bảng là định hướng kiểm thử, không thay thế tài liệu semantics của từng hệ quản trị. Chẳng hạn, SQL Server RCSI là snapshot ở cấp statement, còn SNAPSHOT là snapshot ở cấp transaction. PostgreSQL REPEATABLE READ có semantics snapshot khác với SQL Server REPEATABLE READ. MySQL InnoDB còn có record/gap/next-key locks và quy tắc riêng cho locking reads.

## 22. Kiểm thử tính công bằng và starvation

Bất biến không chỉ là “không sai dữ liệu”. Một hệ thống có thể giữ đúng dữ liệu nhưng một request liên tục không được phục vụ.

Các câu hỏi:

- Một worker có bị bỏ đói vì READPAST luôn bỏ qua job của nó không?
- Một transaction có thể bị chọn làm deadlock victim lặp lại liên tục không?
- Một tenant có chiếm hết quota hoặc worker slot không?
- Một lock có bị giữ quá lâu khiến các request khác không tiến triển?
- Retry có làm request cũ luôn thua request mới không?

Các metric/test có thể gồm:

- Thời gian chờ p50/p95/p99.
- Số lần retry/victim trên mỗi operation.
- Thời gian từ READY đến CLAIMED.
- Số job hết lease và số lần reclaim.
- Tuổi transaction và lock wait duration.
- Phân bố throughput theo tenant hoặc loại operation.

Không phải mọi test fairness đều có oracle xác định tuyệt đối trong một lần chạy. Hãy đặt ngưỡng và thời gian quan sát có ý nghĩa với SLA.

## 23. Kiểm thử tải và kiểm thử lịch xác định

### 23.1. Kiểm thử lịch xác định

Dùng barrier/latch để ép một lịch cụ thể:

- Cả hai transaction đọc cùng giá trị.
- Cả hai cùng kiểm tra key chưa tồn tại.
- T1 giữ khóa trước khi T2 yêu cầu.
- T2 claim trước khi T1 thử claim.
- Worker cũ bị dừng đúng sau khi lease hết hạn.

Ưu điểm là dễ tái hiện và giải thích. Nhược điểm là chỉ kiểm tra các lịch đã được chọn.

### 23.2. Kiểm thử tải ngẫu nhiên

Chạy nhiều actor trong một khoảng thời gian, random hóa thao tác, key và delay. Sau khi kết thúc, kiểm tra tất cả bất biến.

Ưu điểm là khám phá nhiều interleaving và contention thực tế. Nhược điểm là một lỗi hiếm có thể khó tái hiện.

### 23.3. Kết hợp hai loại

Một chiến lược tốt:

1. Dùng deterministic test cho từng race đã biết.
2. Dùng stress test để khám phá lịch chưa dự đoán.
3. Khi stress test phát hiện lỗi, ghi lại seed, input và trace.
4. Chuyển lịch lỗi thành test xác định.
5. Giữ test hồi quy để ngăn lỗi quay lại.

Stress test không thay thế test xác định cho một bất biến quan trọng.

## 24. Tổ chức test harness trong Java

### 24.1. Một connection cho mỗi actor

Ví dụ khung:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CyclicBarrier bothRead = new CyclicBarrier(2);

Callable<Result> actorA = () -> {
    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        int value = readValue(c);
        bothRead.await(5, TimeUnit.SECONDS);

        updateValue(c, value + 3);
        c.commit();
        return Result.success();
    } catch (Exception ex) {
        return Result.failure(ex);
    }
};

Callable<Result> actorB = () -> {
    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        int value = readValue(c);
        bothRead.await(5, TimeUnit.SECONDS);

        updateValue(c, value + 5);
        c.commit();
        return Result.success();
    } catch (Exception ex) {
        return Result.failure(ex);
    }
};
~~~

Đây là khung minh họa. Cần bảo đảm mỗi actor có connection độc lập, barrier nằm đúng giữa bước đọc và ghi, và lỗi được chuyển về controller để đánh giá. Nếu một actor thất bại trước barrier, actor còn lại phải được giải phóng bằng timeout hoặc cancellation để test không treo.

### 24.2. Controller chờ kết quả và kiểm tra oracle

~~~java
Future<Result> a = pool.submit(actorA);
Future<Result> b = pool.submit(actorB);

Result resultA = a.get(10, TimeUnit.SECONDS);
Result resultB = b.get(10, TimeUnit.SECONDS);

// Mở connection mới, đọc trạng thái đã commit.
// Kiểm tra invariant, không chỉ kiểm tra resultA/resultB.
~~~

Timeout trong test harness là giới hạn để phát hiện test bị treo. Khi hết hạn, controller cần hủy task, đóng connection và thu thập trạng thái DB để chẩn đoán. Không dùng timeout này làm bằng chứng transaction trong database đã rollback.

### 24.3. Đảm bảo cleanup kể cả khi test thất bại

Test đồng thời thường để lại transaction mở nếu assertion ném exception trước cleanup. Hãy dùng:

- try-with-resources cho connection/statement/result set.
- finally để rollback transaction chưa commit.
- Executor shutdown/await termination.
- Barrier timeout.
- Schema/database fixture riêng.
- Cleanup dữ liệu theo test ID.

Nếu connection bị lỗi hoặc protocol state không rõ, đóng/evict connection thay vì trả nó về pool như một connection sạch.

### 24.4. Dùng database thật trong kiểm thử concurrency quan trọng

Database in-memory hoặc mock repository có thể không mô phỏng:

- Lock manager.
- MVCC/version store.
- Gap/next-key locks.
- Unique index conflict.
- Deadlock detector.
- Transaction rollback semantics.
- Driver cancellation.
- Isolation level của production.

Có thể dùng mock cho unit test logic, nhưng test concurrency cần chạy trên cùng engine và phiên bản gần production nhất. Containerized database là lựa chọn hữu ích trong CI nếu cấu hình tương đương.

## 25. Kiểm thử nhiều mức và nhiều cấu hình

Một test suite có thể chia thành các lớp:

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| Unit | Kiểm tra quyết định nghiệp vụ đơn lẻ | Transition PENDING -> PAID |
| Repository integration | Kiểm tra constraint và SQL | UNIQUE, conditional UPDATE |
| Deterministic concurrency | Tái hiện lịch cạnh tranh | Hai transaction cùng đọc trước khi ghi |
| Isolation matrix | Kiểm tra semantics theo isolation | RCSI so với SNAPSHOT |
| Fault injection | Kiểm tra crash/timeout | Mất response sau COMMIT |
| Stress | Khám phá interleaving và contention | 50 worker đặt hàng cùng SKU |
| End-to-end | Kiểm tra nhiều thành phần | API + DB + outbox + consumer |

Không cần chạy toàn bộ stress test ở mọi lần commit nếu chi phí cao. Có thể chạy deterministic test trong CI thường xuyên, còn stress/fault test ở pipeline riêng hoặc trước release.

### 25.1. Ma trận môi trường

Ghi rõ:

- DBMS và phiên bản.
- Isolation level.
- Database options.
- Index và constraint.
- Connection pool size.
- Driver version.
- Transaction manager.
- Lock timeout/query timeout.
- Trigger, cascade và stored procedure.
- ADR/version store nếu dùng SQL Server.
- Autocommit và retry policy.

Nếu test chạy trên cấu hình khác production, kết quả có thể không chuyển giao được.

### 25.2. Test cả trường hợp thành công lẫn rollback

Một race condition thường có hai nhánh hợp lệ:

- Transaction A thắng, B conflict.
- A rollback, B tiếp tục và thành công.

Ví dụ hai request tạo cùng unique key: nếu request đầu rollback, request thứ hai có thể được phép tạo hàng. Test chỉ kiểm tra trường hợp request đầu commit sẽ bỏ sót nhánh rollback.

## 26. Số lượng actor và dữ liệu kiểm thử

### 26.1. Hai actor là điểm bắt đầu, không phải giới hạn

Nhiều race có thể xuất hiện với hai transaction, nhưng một số lỗi chỉ lộ ra khi có nhiều actor:

- N request tranh một quota nhỏ.
- N worker claim một queue.
- Một blocker chặn nhiều waiter.
- Deadlock chu trình ba hoặc nhiều transaction.
- Hot key và lock escalation.
- Pool exhaustion.

Tạo test với 2, 3, 5, 10 hoặc số actor gần tải dự kiến. Số lượng phải đủ để kích hoạt cạnh tranh nhưng vẫn kiểm soát được thời gian và tài nguyên CI.

### 26.2. Dùng dữ liệu nhỏ và dữ liệu lớn

Dữ liệu nhỏ giúp tạo lịch xác định và đọc oracle dễ dàng. Dữ liệu lớn giúp execution plan, index scan, lock escalation và version store gần thực tế hơn.

Ví dụ:

- Một SKU và một hàng tồn để test oversell.
- Nhiều SKU để test lock ordering.
- Một phòng và nhiều reservation để test predicate.
- Một bảng lớn có index để test range locks và scan.

### 26.3. Phân bố dữ liệu có chủ đích

Test chỉ dùng key ngẫu nhiên khác nhau sẽ ít contention. Hãy tạo phân bố:

- Nhiều request cùng hot key.
- Nhiều request trên key độc lập.
- Một tenant tải cao và nhiều tenant tải thấp.
- Giá trị biên như quota = 0, quota = 1.
- Hàng vừa chuyển trạng thái.
- Hàng không tồn tại nhưng nằm trong predicate.
- Khoảng thời gian chỉ chạm biên.

## 27. Kiểm thử lỗi và phục hồi

### 27.1. Transaction bị hủy giữa chừng

Cố tình gây lỗi sau khi ghi một phần dữ liệu nhưng trước COMMIT. Xác nhận toàn bộ thay đổi cần nguyên tử được rollback.

Ví dụ transfer ghi debit trước rồi ném lỗi trước credit. Oracle phải xác nhận không có debit đơn lẻ đã commit.

### 27.2. Deadlock victim

Gây deadlock có kiểm soát và xác nhận ứng dụng:

- Nhận diện đúng mã lỗi.
- Rollback transaction victim.
- Không dùng connection ở trạng thái không hợp lệ.
- Retry toàn bộ đơn vị nghiệp vụ nếu chính sách cho phép.
- Không phát tác dụng phụ lặp.

### 27.3. Serialization failure/update conflict

Với isolation level có thể abort transaction, tạo lịch gây conflict và xác nhận ứng dụng đọc lại dữ liệu trong transaction mới. Không retry câu lệnh cuối dựa trên kết quả đọc cũ.

### 27.4. Commit response bị mất

Dùng proxy/fault injector hoặc test adapter để làm mất response sau khi server xử lý COMMIT. Xác nhận client không tạo operation mới với key khác và có thể truy vấn kết quả cũ.

Đây là test khó nhưng quan trọng với thanh toán, tạo đơn, cấp quyền hoặc thao tác có tác dụng phụ không thể hoàn tác.

### 27.5. Worker crash và lease hết hạn

Dừng worker sau claim, chờ lease hết hạn, cho worker khác claim rồi khởi động lại worker cũ. Xác nhận fencing token ngăn worker cũ ghi kết quả hoặc phát tác dụng phụ.

## 28. Đọc kết quả test: pass, fail hay inconclusive

### 28.1. Pass

- Lịch đã được tạo như dự kiến.
- Kết quả nằm trong tập kết quả được nghiệp vụ cho phép.
- Tất cả bất biến giữ đúng.
- Lỗi conflict/timeout được phân loại và xử lý đúng.
- Không có tác dụng phụ trùng.
- Tất cả transaction, connection và worker được cleanup.

### 28.2. Fail

- Bất biến bị vi phạm.
- Hai actor cùng được cấp một tài nguyên độc quyền.
- Có dữ liệu mồ côi hoặc ledger mất cân bằng.
- Một transaction rollback nhưng tác dụng phụ ngoài vẫn xảy ra hai lần.
- Worker hết lease vẫn ghi đè worker mới.
- Request bị treo quá deadline hoặc connection leak.
- Retry tạo một operation mới ngoài ý muốn.

### 28.3. Inconclusive

- Barrier không đạt đủ actor.
- Một actor lỗi trước điểm đồng bộ.
- Database không dùng đúng isolation/configuration dự kiến.
- Test bị timeout ở controller mà không thu thập được trạng thái DB.
- Oracle đọc nhầm schema/tenant.
- Lịch dự kiến không thực sự xảy ra.
- Environment bị quá tải hoặc thiếu quyền DMV khiến không xác nhận được blocking.

Không nên coi test inconclusive là pass. Ghi trace, trạng thái transaction và lý do để chạy lại hoặc sửa harness.

## 29. Ưu tiên theo rủi ro

Không phải mọi bảng đều cần hàng chục test concurrency. Ưu tiên theo mức thiệt hại và khả năng xảy ra.

Một cách xếp hạng đơn giản:

\[
Risk = Impact \times Likelihood \times ConcurrencyExposure
\]

Đây là thang điểm nội bộ, không phải xác suất toán học. Có thể chấm mỗi yếu tố từ 1 đến 5:

- **Impact:** thiệt hại nếu bất biến bị phá.
- **Likelihood:** tần suất thao tác hoặc khả năng xuất hiện lịch nguy hiểm.
- **Concurrency exposure:** số actor/đường ghi có thể cùng tác động dữ liệu.

Ví dụ ưu tiên cao:

- Thanh toán và ledger.
- Tồn kho/quota/booking.
- Đăng nhập và định danh duy nhất.
- Trạng thái đơn hàng.
- Queue claim và job lease.
- Webhook, message dedup.
- Quyền truy cập và cấp phát tài nguyên.

Ưu tiên thấp hơn có thể là dữ liệu cache hoặc số liệu có thể tính lại, miễn là nghiệp vụ chấp nhận độ trễ và sai số đó.

## 30. Một quy trình tạo bộ test từ đầu

### Bước 1: Viết danh sách bất biến

Làm việc với nghiệp vụ và nhóm vận hành. Viết mỗi quy tắc thành một câu có điều kiện rõ ràng và phạm vi áp dụng.

### Bước 2: Chuyển bất biến thành oracle

Xác định truy vấn SQL, event log, ledger hoặc metric có thể chứng minh quy tắc đúng sau khi tất cả actor kết thúc.

### Bước 3: Liệt kê operation có thể ảnh hưởng

Bao gồm API, batch, worker, webhook, trigger, stored procedure, admin và tác vụ bù trừ.

### Bước 4: Xác định cửa sổ cạnh tranh

Tìm chỗ hai transaction cùng đọc, cùng kiểm tra predicate, cùng claim, cùng cập nhật hoặc lấy khóa theo thứ tự khác nhau.

### Bước 5: Chọn interleaving

Viết timeline cụ thể cho hai hoặc nhiều actor. Chỉ rõ điểm barrier, ai giữ khóa, ai chờ và thời điểm commit/rollback.

### Bước 6: Chọn cơ chế kiểm soát

Dùng constraint, atomic update, optimistic version, explicit locking, SERIALIZABLE, idempotency, outbox hoặc lease/fencing theo đúng bất biến.

### Bước 7: Viết deterministic test

Dùng connection độc lập, barrier/latch và timeout bảo vệ. Không dựa vào sleep để tạo thứ tự.

### Bước 8: Viết stress/fault test

Random hóa thao tác và thêm điểm crash/cancel ở các ranh giới có rủi ro. Lưu seed và trace.

### Bước 9: Chạy trên môi trường tương đương production

Đúng DBMS, version, isolation, index, trigger, driver và connection pool.

### Bước 10: Lưu test như một phần của hợp đồng nghiệp vụ

Khi bất biến thay đổi, cập nhật oracle và scenario. Khi thêm writer mới, thêm nó vào ma trận. Khi thay isolation level hoặc database option, chạy lại test liên quan.

## 31. Mẫu bảng đặc tả một test concurrency

Có thể dùng cấu trúc sau cho từng test:

| Trường | Nội dung cần ghi |
|---|---|
| Test ID | Tên duy nhất |
| Bất biến | Quy tắc phải giữ |
| Dữ liệu ban đầu | Các hàng và giá trị trước test |
| Actor | Các transaction/worker tham gia |
| Operation | API, SQL hoặc message mỗi actor chạy |
| Isolation | Mức cô lập và database option |
| Lịch | Thứ tự thao tác và điểm đồng bộ |
| Kết quả hợp lệ | Các kết quả được nghiệp vụ chấp nhận |
| Kết quả bị cấm | Trạng thái hoặc tác dụng phụ không được xảy ra |
| Oracle | Query/event/metric dùng để xác nhận |
| Cleanup | Rollback, reset fixture, đóng connection |
| Diagnostics | Deadlock report, lock wait, SQLSTATE, trace |
| Lặp lại | Số lần hoặc seed chạy stress |
| Môi trường | DBMS, version, driver, pool và cấu hình |

Ví dụ rút gọn:

~~~text
TEST: INV-OVR-001
Invariant: confirmed orders <= available stock
Initial state: SKU-A available = 1
Actors: 10 independent transactions
Schedule: all read/attempt claim from the same initial stock window
Allowed result: exactly one confirmed order; remaining requests conflict
Forbidden result: negative stock or more than one confirmed order
Oracle: inventory row + confirmed order count
Isolation: production configuration
Diagnostics: SQL errors, lock waits, transaction outcomes
~~~

## 32. Các lỗi thường gặp khi chọn tình huống cạnh tranh

**Chỉ test hai request cùng gọi một API và assert cả hai response.**

Không đủ. Cần biết hai request có thực sự chồng lấn ở cửa sổ nguy hiểm và kiểm tra dữ liệu sau commit.

**Chỉ test hai transaction cập nhật cùng một hàng.**

Bỏ sót write skew và predicate race khi mỗi transaction ghi hàng khác nhau nhưng cùng ảnh hưởng một quy tắc liên hàng.

**Chỉ kiểm tra dữ liệu cuối.**

Có thể bỏ sót hai lần gửi payment, email hoặc event nếu tác dụng phụ không nằm trong database. Cần oracle lịch sử và số lần gọi.

**Dùng sleep để ép interleaving.**

Kết quả phụ thuộc scheduler và tải máy. Dùng barrier/latch hoặc observer xác nhận trạng thái thực tế.

**Chạy test trên H2 rồi suy ra SQL Server/PostgreSQL/MySQL giống nhau.**

Lock manager, MVCC và isolation semantics khác nhau. Test quan trọng phải chạy trên engine production.

**Chỉ chạy một lần.**

Một lần pass không chứng minh mọi lịch đều an toàn. Dùng deterministic schedule cho lỗi đã biết và stress test cho interleaving rộng.

**Không test nhánh rollback.**

Nếu transaction đầu rollback, transaction chờ có thể được phép tiếp tục. Nhánh này thường khác với trường hợp transaction đầu commit.

**Retry chỉ câu SQL cuối.**

Các phép tính trước đó có thể dựa trên snapshot cũ. Retry thường phải chạy lại toàn transaction.

**Không test writer ngoài API chính.**

Batch, trigger, consumer hoặc admin tool có thể bỏ qua protocol mà API chính tuân thủ.

**Không kiểm tra connection và transaction cleanup.**

Test có thể giữ khóa hoặc làm pool cạn, khiến các test sau thất bại không liên quan.

**Đánh đồng timeout test với rollback đã xác nhận.**

Timeout của test controller không chứng minh database đã dừng hoặc rollback. Phải quan sát transaction state và trạng thái đã commit.

## 33. Checklist lựa chọn bất biến và tình huống

Trước khi kết thúc thiết kế test, hãy kiểm tra:

- Bất biến có mô tả điều kiện nghiệp vụ rõ ràng không?
- Phạm vi tenant, trạng thái, thời gian và cách chuẩn hóa đã rõ chưa?
- Bất biến áp dụng cho state, history hay cả hai?
- Những operation nào có thể thay đổi hoặc phá nó?
- Có writer nào ngoài API chính không?
- Có mẫu check-then-act hoặc read-modify-write không?
- Có predicate/range hoặc điều kiện “không tồn tại” không?
- Có hai transaction ghi các hàng khác nhau nhưng cùng ảnh hưởng một bất biến không?
- Có request retry, webhook redelivery hoặc worker crash không?
- Có thao tác lấy nhiều khóa theo thứ tự khác nhau không?
- Có timeout, cancellation hoặc ambiguous COMMIT không?
- Oracle có kiểm tra trạng thái cuối và tác dụng phụ không?
- Lịch có được tạo bằng barrier/latch thay vì sleep không?
- Test dùng connection độc lập và DBMS tương đương production không?
- Có nhánh commit, rollback, conflict và retry không?
- Có stress test và cách chuyển lỗi ngẫu nhiên thành test xác định không?
- Cleanup có luôn đóng connection và kết thúc transaction không?
- Kết quả inconclusive có được phân biệt với pass không?

## 34. Kết luận thiết kế

Một bộ kiểm thử đồng thời tốt được tổ chức quanh các quy tắc mà hệ thống phải bảo vệ. Mỗi bất biến dẫn đến một tập thao tác có thể làm thay đổi nó; mỗi tập thao tác dẫn đến một hoặc nhiều lịch xen kẽ nguy hiểm; mỗi lịch cần một oracle chứng minh kết quả hợp lệ và một cơ chế đồng bộ để tái hiện.

Hãy kiểm tra cả xung đột trên cùng hàng, xung đột giữa nhiều hàng, predicate/range, request trùng, thứ tự khóa, timeout và phục hồi sau crash. Kết hợp lịch xác định để tái hiện lỗi với stress test để khám phá interleaving chưa biết. Khi một test thất bại, lưu lại lịch và trace để biến nó thành regression test ổn định.

Mục tiêu cuối cùng không phải làm cho mọi request đồng thời đều thành công. Mục tiêu là mọi kết quả được chấp nhận đều giữ bất biến, các xung đột bị từ chối hoặc retry theo đúng hợp đồng, và không có transaction hay tác dụng phụ bị bỏ lại trong trạng thái không thể phục hồi.
