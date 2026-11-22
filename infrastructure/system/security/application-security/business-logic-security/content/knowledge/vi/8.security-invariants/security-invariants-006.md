# Invariant migration — Chuyển đổi bất biến nghiệp vụ an toàn

## 1. Khi quy tắc mới gặp dữ liệu và chương trình cũ

Trong chương **Security Invariants** của module **Business Logic Security** (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`), **invariant migration** là quá trình đưa hệ thống từ cách biểu đạt hoặc thực thi một bất biến sang cách mới, đồng thời kiểm soát tính đúng của dữ liệu và hành động trong suốt quá trình.

Thay đổi có thể là:

- Tăng mức bảo đảm: từ “đã có phê duyệt” sang “được phê duyệt cho đúng phiên bản nội dung”.
- Đổi mô hình dữ liệu: từ một cờ boolean sang đối tượng quyết định có scope và bằng chứng.
- Đổi nơi thực thi: từ một transaction trong một dịch vụ sang cơ chế phối hợp giữa nhiều dịch vụ.
- Thay quy tắc nghiệp vụ: từ một lần hoàn toàn bộ sang nhiều lần hoàn một phần có hạn mức chung.

Khó khăn không nằm riêng ở việc thêm cột. Hệ thống có thể còn dữ liệu không đủ chứng minh quy tắc mới, worker cũ đang xử lý, message đã phát và tác động bên ngoài không thể hoàn tác bằng rollback database.

Mục tiêu cần đạt là:

> Quy tắc đích có ý nghĩa rõ ràng; dữ liệu được phân loại trung thực; mọi hành động trong giai đoạn chuyển tiếp có bảo đảm đã định; việc cutover không tạo cơ hội bỏ qua quyền, phê duyệt, hạn mức hoặc tính duy nhất.

Một migration hoàn tất về schema chưa chứng minh invariant mới đã được giữ.

## 2. Phân biệt những thứ đang thay đổi

### 2.1. Bất biến, cách biểu đạt và cơ chế thực thi

| Thành phần | Ví dụ | Rủi ro khi nhầm lẫn |
| --- | --- | --- |
| Bất biến | Đơn được xác nhận phải có phê duyệt đúng nội dung | Đổi dữ liệu nhưng giữ lời khẳng định cũ mơ hồ |
| Cách biểu đạt | `approval = true` đổi thành `approvedRevision` và bằng chứng | Gán dữ liệu mới mà không có căn cứ |
| Cơ chế thực thi | Domain guard, constraint, khóa hoặc kiểm soát phiên bản | Nghĩ rằng cột mới tự bảo vệ mọi đường ghi |
| Ranh giới nhất quán | Một transaction hoặc giao thức nhiều dịch vụ | Mất tính nguyên tử khi di chuyển trách nhiệm |
| Phạm vi áp dụng | Mọi hành động mới từ cutover, hoặc toàn bộ dữ liệu | Gọi dữ liệu lịch sử chưa xác minh là đã thỏa quy tắc mới |

Một migration có thể thay một hoặc nhiều thành phần. Kế hoạch cần nói rõ phần nào giữ nguyên, phần nào được thay và vì sao.

### 2.2. Quy tắc được tăng cường hay chỉ đổi biểu diễn?

Nếu chỉ đổi biểu diễn, cần chứng minh dữ liệu mới giữ cùng ý nghĩa với dữ liệu cũ.

Nếu tăng cường quy tắc, không được mặc nhiên cho rằng mọi trạng thái hợp lệ cũ đều hợp lệ theo quy tắc mới.

Ví dụ:

```text
Dữ liệu cũ:
    approved = true

Quy tắc mới cần:
    đúng người duyệt
    đúng đối tượng
    đúng phiên bản nội dung
    quyết định có nguồn gốc đáng tin cậy
```

Một boolean không chứa đủ thông tin để suy ra tất cả các thành phần đó.

Nếu chính sách được nới lỏng hợp lệ, cần ghi rõ thay đổi thẩm quyền và điều kiện. Bỏ kiểm tra chỉ để dữ liệu cũ đi qua mà không có quyết định nghiệp vụ không phải là bằng chứng migration an toàn.

### 2.3. Invariant mới có thể áp dụng theo thời điểm hoặc tập đối tượng

Có hai mục tiêu khác nhau:

```text
Mục tiêu tiến tới:
    Mọi lần xác nhận theo chính sách mới từ cutover
    đều dùng bằng chứng phê duyệt đúng nội dung.

Mục tiêu toàn bộ:
    Mọi đơn trong phạm vi dữ liệu tuyên bố,
    gồm cả lịch sử, đều chứng minh được quy tắc mới.
```

Mục tiêu tiến tới có thể đạt trong khi vẫn còn dữ liệu lịch sử chưa xác minh. Khi đó phải thể hiện đúng phạm vi, bảo vệ các hành động tiếp theo và có cách quản lý phần còn lại.

Không dùng nhãn “legacy” để bỏ qua quy tắc đối với một hành động mới mà chính sách đã yêu cầu áp dụng invariant mới.

## 3. Ví dụ xuyên suốt: từ cờ phê duyệt sang phê duyệt theo revision

### 3.1. Mô hình cũ

Giả sử hệ thống lưu:

```text
Order
    tenantId
    orderId
    status
    approved
    total
    updatedAt
```

Lệnh xác nhận chủ yếu dựa vào `status = APPROVED` và `approved = true`.

Một số đơn có lịch sử phê duyệt kèm snapshot đáng tin cậy. Một số chỉ có cờ boolean hoặc log không đủ để xác định nội dung người duyệt đã xem.

Đây là mô hình giả định phục vụ bài học, không phải kết luận về mã nguồn thực tế.

### 3.2. Mô hình đích

Mô hình mới có thêm:

```text
contentRevision
approvalEvidence
approvedRevision
approvedBy
approvalModelVersion
rowVersion
```

Trong đó:

- `contentRevision` thay đổi khi nội dung ảnh hưởng quyết định duyệt thay đổi.
- `approvedRevision` chỉ phiên bản mà quyết định thực sự áp dụng.
- `approvalEvidence` liên kết tới bằng chứng có nguồn gốc đáng tin cậy.
- `rowVersion` giúp phát hiện cập nhật cạnh tranh theo thiết kế.
- `approvalModelVersion` phân biệt ngữ nghĩa biểu diễn, do hệ thống kiểm soát.

Các trường liên quan tới quyết định như số lượng, giá, giảm giá, tiền tệ hoặc người nhận phải được xác định theo chính sách của luồng.

### 3.3. Bất biến đích

Với một lần xác nhận thuộc chính sách mới:

```text
CONFIRM được chấp nhận
⇒ đúng tenant và đối tượng
   ∧ actor có quyền xác nhận
   ∧ trạng thái nguồn cho phép
   ∧ có bằng chứng phê duyệt hợp lệ
   ∧ approvedRevision = contentRevision đang được xác nhận
   ∧ không tạo thêm kết quả cho cùng nghĩa vụ ngoài chính sách
```

Phần cốt lõi của migration là đưa dữ liệu và các đường ghi tới khả năng thực thi mệnh đề này.

### 3.4. Không tạo bằng chứng bằng cách sao chép hiện trạng

Một cách điền dữ liệu nguy hiểm:

```text
Nếu approved = true:
    contentRevision = 1
    approvedRevision = 1
```

Sau phép gán, hai số bằng nhau. Nhưng nếu nội dung đã bị sửa sau lần phê duyệt cũ, sự bằng nhau được tạo ra không chứng minh điều gì về quyết định thật.

Tương tự, hash của nội dung hiện tại chỉ giúp nhận diện nội dung đó. Nó không chứng minh một người có thẩm quyền đã duyệt nó trong quá khứ.

## 4. Kiểm kê dữ liệu, đường ghi và thẩm quyền

### 4.1. Phân loại theo bằng chứng

| Nhóm dữ liệu | Điều biết được | Hướng xử lý có thể áp dụng |
| --- | --- | --- |
| Chưa có quyết định duyệt | Không cần giữ hiệu lực một quyết định cũ | Khởi tạo revision và tiếp tục quy trình mới |
| Có bằng chứng duyệt gắn với snapshot, nội dung hiện tại khớp | Có cơ sở chuyển nghĩa của quyết định nếu các điều kiện khác đạt | Chuyển đổi có đối chiếu và lưu provenance |
| Có bằng chứng duyệt nhưng nội dung hiện tại khác | Quyết định không chứng minh nội dung hiện tại | Vô hiệu hóa hiệu lực cũ cho hành động mới, yêu cầu xử lý phù hợp |
| Chỉ có cờ hoặc bằng chứng không đủ | Chưa chứng minh được điều kiện mới | Đánh dấu chưa xác minh, yêu cầu duyệt lại hoặc xử lý theo chính sách |
| Đã có nghĩa vụ hoặc tác động bên ngoài | Không thể coi như chưa xảy ra | Đối soát, bảo vệ bước tiếp theo và sửa chữa có dấu vết |

“Có log” chưa chắc là “có bằng chứng”. Log cần đủ liên kết giữa người quyết định, đối tượng và nội dung được quyết định theo yêu cầu.

Việc snapshot khớp cũng cần dùng biểu diễn có ý nghĩa và nguồn lịch sử đáng tin cậy. Không chỉ so một cột total nếu quyết định còn bao gồm người nhận hoặc các trường khác.

### 4.2. Đừng xử lý đơn đã thực hiện như đơn nháp

Nếu một đơn đã confirmed và tiền đã được thu, không nên tự đổi thành draft để buộc duyệt lại rồi vô tình chạy lại quá trình.

Có thể cần phân loại lịch sử, hạn chế hành động tiếp theo, xác minh hoặc tạo điều chỉnh. Cách làm phụ thuộc nghĩa vụ đã phát sinh và chính sách xử lý thiếu bằng chứng.

Giữ dữ liệu lịch sử để điều tra không có nghĩa cho phép dùng nó làm căn cứ cho mọi hành động mới.

### 4.3. Kiểm kê mọi đường có thể ghi

```text
API người dùng
API quản trị
Job theo lịch
Consumer và worker retry
Luồng nhập dữ liệu
Script sửa chữa
Tích hợp đối tác
Migration hoặc backfill khác
Các phiên bản cũ còn triển khai
```

Nếu một đường sửa giá không tăng revision, invariant mới có thể bị phá dù tất cả API chính đã được cập nhật.

### 4.4. Kiểm kê quyền chọn mô hình

Người gọi không được tự gửi `approvalModelVersion = 1` để chọn quy tắc cũ.

Quyền quyết định phiên bản áp dụng, phân loại legacy và trạng thái migration phải thuộc thành phần có thẩm quyền. Một điều kiện SQL chỉ áp dụng kiểm tra khi version bằng 2 không đủ nếu client hoặc writer cũ vẫn có thể tự hạ version.

## 5. Định nghĩa bảo đảm cho giai đoạn chuyển tiếp

### 5.1. Cần một hợp đồng chuyển tiếp

Gọi:

```text
I_old: quy tắc và cách biểu đạt cũ.
I_new: bất biến đích.
I_bridge: các điều kiện bắt buộc trong thời gian cùng tồn tại.
```

Không thể chỉ yêu cầu “đọc được cả hai schema”. Cần nói những hành động nào được chấp nhận trên từng nhóm dữ liệu và từ thời điểm nào phải áp dụng I_new.

Một I_bridge cho ví dụ có thể gồm:

1. Không tạo bằng chứng phê duyệt nếu không có nguồn đủ tin cậy.
2. Từ mốc áp dụng mới, mọi xác nhận liên quan đi qua đường quyết định thực thi I_new; dữ liệu chưa đủ điều kiện không được xác nhận bằng fallback boolean.
3. Bản ghi đã chuyển sang ngữ nghĩa mới không bị writer cũ sửa theo cách bỏ qua revision.
4. Migration không chạy lại một nghĩa vụ hay tác động đã thực hiện.
5. Các đối tượng chưa giải quyết được có trạng thái và người xử lý rõ ràng.
6. Định danh nghiệp vụ, tenant và liên kết bằng chứng không bị đổi ngoài quy trình.

Mốc áp dụng có thể theo toàn hệ thống hoặc từng nhóm tenant do máy chủ kiểm soát. Phạm vi từng đợt phải rõ và không cho caller tự chọn luật yếu hơn.

### 5.2. Chọn cách xử lý đường cũ

Tùy khả năng triển khai, có thể cần:

- Bản tương thích có khả năng đọc cũ nhưng mọi ghi nhạy cảm giữ quy tắc mới.
- Định tuyến qua một đường quyết định chung đã được bảo vệ.
- Tạm giữ các hành động không thể thực hiện an toàn trong thời gian chuyển đổi.
- Thu hồi khả năng ghi của worker hoặc công cụ chưa hỗ trợ.
- Chuyển từng nhóm dữ liệu sau khi các writer liên quan đã sẵn sàng.

Nếu một chương trình cũ vẫn có quyền sửa nội dung mà không tham gia giao thức revision, thêm cột hoặc feature flag ở chương trình mới chưa ngăn được nó.

Đọc tương thích và ghi tương thích là hai yêu cầu khác nhau.

### 5.3. Không dùng mức trung bình để kết luận bảo đảm

“99% đơn đã backfill” không chứng minh mọi hành động mới đều đúng. Một phần nhỏ dữ liệu chưa xử lý vẫn có thể là mục tiêu dễ tiếp cận.

Readiness cần dựa trên cả:

```text
Nhóm nào đã đạt điều kiện?
Nhóm nào còn bị giữ hoặc hạn chế?
Có đường nào đi vòng điều kiện đó không?
Những writer nào còn hoạt động?
```

Số lượng giúp vận hành; điều kiện chấp nhận quyết định bảo đảm.

## 6. Mở rộng schema và triển khai khả năng tương thích

### 6.1. Thêm dữ liệu mới mà không bịa nghĩa cho dữ liệu cũ

Giai đoạn mở rộng có thể thêm các trường hoặc bảng cần thiết, cho phép biểu đạt “chưa xác minh” một cách rõ ràng.

Không nên dùng giá trị mặc định khiến:

```text
chưa có bằng chứng
```

bị diễn giải thành:

```text
đã duyệt đúng phiên bản.
```

Ví dụ, revision ban đầu phục vụ mô hình mới có thể được khởi tạo có kiểm soát. Việc đó không tự kéo theo `approvedRevision` và bằng chứng duyệt.

### 6.2. Tách phiên bản biểu diễn khỏi quyền bỏ kiểm tra

`approvalModelVersion` mô tả cách dữ liệu cần được hiểu. Nó không phải một tham số mà client có thể hạ để xin dùng quy trình cũ.

Nếu có constraint chỉ kiểm tra các bản ghi version mới, vẫn phải có cơ chế kiểm soát việc tạo hoặc sửa bản ghi version cũ sau cutover.

Một ràng buộc có điều kiện không bảo vệ được quy tắc nếu actor có thể tự thay điều kiện để thoát khỏi ràng buộc.

### 6.3. Xác định nguồn có thẩm quyền trong dual write

Nếu cần giữ cả trường cũ và mới trong một thời gian, phải định nghĩa:

```text
Nguồn nào quyết định nội dung?
Nguồn nào quyết định hiệu lực phê duyệt?
Các trường cũ được suy ra từ đâu?
Nếu hai biểu diễn khác nhau, hành động nào được phép?
```

Nếu cùng một database, các ghi liên quan thường cần nằm trong cùng transaction của quyết định.

Nếu ghi sang hai dịch vụ, không giả định hai lần ghi riêng là nguyên tử. Outbox và đồng bộ có thể truyền thay đổi bền vững, nhưng còn độ trễ và trạng thái chưa hoàn tất. Đường ra quyết định phải xét điều đó.

### 6.4. Tránh dual read trở thành đường hạ bảo đảm

Một fallback nguy hiểm:

```text
Nếu không có approvedRevision:
    dùng approved = true để cho confirm.
```

Fallback này giữ lại đúng điểm yếu mà migration muốn loại bỏ.

Có thể đọc dữ liệu cũ để hiển thị lịch sử hoặc phân loại. Quyền cho phép một hành động mới phải dựa vào chính sách và bằng chứng thích hợp cho hành động đó.

## 7. Backfill theo bằng chứng và có kiểm soát cạnh tranh

### 7.1. Mỗi bản ghi cần một quyết định chuyển đổi

Một luồng có thể là:

```text
1. Tải đối tượng trong đúng tenant.
2. Đọc nội dung và bằng chứng lịch sử cần thiết.
3. Đối chiếu các trường thuộc quyết định.
4. Phân loại:
       đủ bằng chứng để chuyển;
       cần duyệt lại;
       cần đối soát hoặc xử lý thủ công.
5. Ghi kết quả theo trạng thái và phiên bản mong đợi.
6. Lưu nguồn bằng chứng và định danh lần chuyển đổi.
```

Cách phân loại phải nhất quán và có thể kiểm tra lại. Không nên chọn kết quả “đã duyệt” chỉ để đạt tỷ lệ hoàn thành cao.

### 7.2. Nếu nội dung thay đổi trong lúc backfill

Giả sử:

```text
A đọc snapshot và thấy khớp quyết định cũ.
B sửa nội dung.
A ghi approvedRevision cho nội dung hiện tại mà không phát hiện B.
```

Migration đã tự tạo một quyết định sai.

Có thể sử dụng khóa phù hợp hoặc cập nhật có điều kiện. Ví dụ sau chỉ minh họa nhánh đã có đủ bằng chứng và một baseline revision được xác định hợp lệ:

```sql
UPDATE purchase_order
SET content_revision = :baseline_revision,
    approved_revision = :verified_approved_revision,
    approval_evidence_id = :verified_evidence_id,
    approval_model_version = 2,
    row_version = row_version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND approval_model_version = 1
  AND row_version = :expected_row_version;
```

Các tham số “verified” phải đến từ bước xác minh được bảo vệ, không phải từ request hoặc phép sao chép mặc định.

Số dòng tác động bằng 0 có nghĩa điều kiện không còn khớp; cần đọc lại hoặc đưa vào xử lý thích hợp. Không bỏ điều kiện rồi ghi đè để lô chạy tiếp.

Điều kiện quan trọng: mọi writer có thể thay dữ liệu đang được kiểm chứng phải tham gia cơ chế version hoặc giao thức phối hợp tương đương. Nếu writer cũ không tăng `rowVersion`, chỉ so version không phát hiện được thay đổi của nó.

### 7.3. Backfill phải chịu được chạy lại và lỗi một phần

Một tác vụ chuyển đổi nên biết:

```text
Đối tượng nào đã hoàn tất?
Quy tắc chuyển đổi và phiên bản nào được dùng?
Nguồn bằng chứng nào đã được áp dụng?
Đối tượng nào bị xung đột hoặc chưa đủ thông tin?
Nếu chạy lại, có tạo thêm quyết định hoặc sự kiện không?
```

Checkpoint giúp tiếp tục công việc nhưng không thay thế tính đúng theo từng bản ghi. Một lô có thể đã commit một phần trước khi tiến trình dừng.

Không chạy lại lệnh thu tiền, hoàn tiền hoặc gửi hàng chỉ vì tác vụ đang “tạo lại dữ liệu” cho migration. Chuẩn hóa lịch sử và thực hiện tác động mới cần được phân biệt.

### 7.4. Dữ liệu không đủ bằng chứng cần một lối xử lý thật

Với đơn chưa có nghĩa vụ cuối, có thể yêu cầu duyệt lại hoặc giữ hành động cho tới khi đủ điều kiện.

Với đơn đã phát sinh tác động, cần đối soát và quyết định sửa chữa phù hợp. Nếu có điều chỉnh, giữ liên kết với giao dịch gốc thay vì xóa lịch sử thiếu sót.

Không gán một người dùng hệ thống làm approver chỉ để vượt constraint khi không có quyết định tương ứng.

## 8. Cập nhật mọi đường ghi trước khi dựa vào revision mới

### 8.1. Nội dung thay đổi phải được nhận diện nhất quán

Một command sửa nội dung có ý nghĩa cần:

```text
Kiểm tra quyền và trạng thái.
Tính nội dung và tổng từ nguồn có thẩm quyền.
Tăng contentRevision.
Vô hiệu hóa quyết định không còn khớp.
Cập nhật biểu diễn tương thích nếu cần.
Lưu nhất quán và phát sự kiện theo cơ chế đã chọn.
```

Một command duyệt cần ràng buộc quyết định với revision mà người duyệt đã xem. Một command xác nhận cần đối chiếu lại và bảo vệ quyết định trước cạnh tranh.

Công cụ quản trị hoặc job không được chỉ sửa total, recipient hay status mà bỏ bước tương ứng.

### 8.2. Message cũ không được tự chuyển thành ý định mới

Một command cũ có thể không mang `expectedContentRevision`.

Không nên tự điền revision hiện tại rồi thực hiện, vì actor có thể đã quyết định trên nội dung khác.

Cần chính sách cho message cũ: xác minh từ bằng chứng đủ tin cậy, chuyển sang quy trình đánh giá lại, từ chối có theo dõi hoặc cách chuyển đổi được đặc tả.

Tương tự, command có tenant hoặc actor chưa rõ không được chạy bằng tenant mặc định hay toàn bộ quyền của service.

### 8.3. Giữ nguyên danh tính nghiệp vụ và xử lý retry

Một command đã hoàn thành theo chính sách trước đó có thể được gửi lại sau migration. Cần nhận diện tác động gốc và trả kết quả theo hợp đồng, không thực hiện lại chỉ vì model version đã đổi.

Nếu command mới cần quy tắc mới, không được dùng kết quả idempotency của một command khác nội dung hoặc khác phạm vi để bỏ kiểm tra.

Định danh nghĩa vụ và tính duy nhất phải xuyên qua các đường cũ và mới. Hai bảng hoặc hai service mỗi bên chống trùng riêng chưa bảo đảm toàn hệ thống không thực hiện hai lần.

### 8.4. Rào writer cũ phải có hiệu lực thực tế

Có thể dùng một thế hệ ghi hoặc phiên bản hợp đồng để phân biệt writer được phép. Nhưng một trường `migrationEpoch` chỉ được chương trình mới kiểm tra không ngăn chương trình cũ bỏ qua trường đó.

Rào có thể cần nằm ở đường ghi chung, quyền database, cơ chế dữ liệu hoặc việc dừng và thu hồi quyền của consumer cũ theo kế hoạch.

Cần kiểm chứng rằng writer cũ thật sự không còn tạo được trạng thái trái quy tắc trong phạm vi đã chuyển.

## 9. Cutover dựa trên điều kiện, rồi mới thu hẹp mô hình cũ

### 9.1. Các điều kiện sẵn sàng

Một nhóm dữ liệu có thể chuyển sang chỉ ra quyết định bằng mô hình mới khi:

- Các writer liên quan đã tham gia giao thức mới hoặc bị ngăn ghi nhạy cảm.
- Dữ liệu đủ bằng chứng đã được chuyển đúng.
- Dữ liệu chưa đủ bằng chứng có đường xử lý hoặc bị giới hạn theo chính sách.
- Command cũ và tác vụ đang chờ được phân loại.
- Constraint và authorization cần thiết có hiệu lực trên cấu hình thực tế.
- Đã kiểm tra concurrency, replay và các tổ hợp phiên bản còn tồn tại.
- Có quan sát và quy trình phục hồi cho lỗi sau cutover.

Không cần mọi dữ liệu lịch sử trở thành “đã xác minh” nếu mục tiêu đã chọn chỉ áp dụng tiến tới, nhưng không được để lịch sử chưa rõ làm căn cứ tự động cho hành động mới trái quy tắc.

### 9.2. Shadow comparison chỉ quan sát, không tạo quyền

Có thể tính thử quyết định theo mô hình mới để so sánh với mô hình cũ.

Kết quả so sánh giúp phát hiện khác biệt, nhưng không phải bằng chứng rằng người có thẩm quyền đã đưa ra một quyết định còn thiếu. Cũng cần bảo đảm đường shadow không phát tác động thật hoặc sửa dữ liệu như một quyết định chính thức.

Các sai khác cần được giải thích theo chính sách và dữ liệu. Không chỉnh quy tắc mới chỉ để hai tỷ lệ giống nhau.

### 9.3. Thu hẹp và loại bỏ phần cũ

Sau khi không còn consumer hoặc đường ghi hợp lệ phụ thuộc vào biểu diễn cũ, có thể tiến tới bỏ fallback, quyền ghi và các trường không cần thiết theo kế hoạch.

Trước khi xóa dữ liệu hoặc bảng hỗ trợ, cần xét:

```text
Message có thể replay bao lâu?
Bản ghi idempotency hoặc tombstone còn bảo vệ điều gì?
Công cụ điều tra cần bằng chứng nào?
Rollback hoặc phục hồi có cần dữ liệu đó không?
```

Loại bỏ một thành phần là một thay đổi có tác động bảo mật, không chỉ là dọn schema.

## 10. Khi migration di chuyển nơi thực thi bất biến

### 10.1. Đổi chủ sở hữu dữ liệu có thể đổi bảo đảm

Giả sử giới hạn hoàn tiền trước đây được giữ trong một transaction:

```text
refundedConfirmed + refundReserved <= refundableLimit
```

Sau khi tách dịch vụ, một service quản lý số tiền đã thu, một service khác quản lý lệnh hoàn. Hai service cùng đọc “còn đủ” rồi tự cập nhật không tự tạo ra cùng mức bảo đảm cũ.

Cần xác định thành phần hoặc giao thức nào có thẩm quyền chiếm hạn mức và cách mọi đường thực hiện tham gia.

### 10.2. Giữ một điểm quyết định có thể lập luận

Các thiết kế có thể dựa vào:

- Một nơi cấp reservation cho hạn mức chung.
- Một giao thức chuyển quyền sử dụng tài nguyên có định danh và chống lặp.
- Phân bổ hạn mức thành các phần độc lập, trong đó tổng phần cấp không vượt giới hạn chung.
- Một mô hình trạng thái chờ và phối hợp phù hợp với yêu cầu nghiệp vụ.

Mỗi lựa chọn cần chứng minh các điều kiện riêng. Ví dụ, phân bổ hạn mức chỉ đúng nếu việc cấp, thu hồi và chuyển phần được phân bổ không làm cùng một phần được dùng ở hai nơi.

Outbox giúp ghi nhận ý định phát tin cùng transaction cục bộ. Nó không tự làm một kiểm tra xuyên hai service trở thành nguyên tử.

### 10.3. Không để hai nơi đồng thời là nguồn quyết định độc lập

Trong thời gian chạy song song, service cũ và mới có thể mỗi bên đều nghĩ mình còn quyền thực hiện.

Cần một quy tắc sở hữu có hiệu lực:

```text
Đối tượng nào do nơi nào quyết định?
Từ mốc hoặc thế hệ nào?
Lệnh đang chờ thuộc bên nào?
Retry được định tuyến ra sao?
Bên cũ bị ngăn tạo tác động mới bằng cơ chế nào?
```

Chỉ sao chép dữ liệu giữa hai bên không giải quyết được việc cả hai cùng ra quyết định. Các định danh và cơ chế chống trùng cũng cần hoạt động trên toàn nghĩa vụ, không bị chia tách theo nơi lưu trữ mới.

## 11. Kiểm chứng dữ liệu và hành vi trong quá trình migration

### 11.1. Oracle phải theo đúng phạm vi áp dụng

Với mục tiêu áp dụng tiến tới, một oracle có thể là:

```text
Với mỗi lần xác nhận được chấp nhận:
    Nếu đối tượng thuộc phạm vi đã cutover tại thời điểm quyết định:
        phiên bản policy phải được hệ thống cho phép;
        tenant và đối tượng phải khớp bằng chứng;
        nội dung được xác nhận phải có phê duyệt tương ứng;
        số lần tác động phải tuân theo tính duy nhất nghiệp vụ.
```

Không chỉ lọc những bản ghi tự ghi version mới rồi kết luận an toàn. Một writer cũ có thể tạo bản ghi version cũ sau cutover; đó chính là hành vi cần phát hiện.

Nếu mục tiêu là toàn bộ dữ liệu, cần một kiểm tra tương ứng trên toàn bộ phạm vi đã tuyên bố, gồm cả phần lịch sử. Mục tiêu đó đòi hỏi kế hoạch xử lý những trường hợp không có bằng chứng.

### 11.2. Ma trận kiểm thử

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Đơn chưa duyệt được chuyển | Có revision hợp lệ nhưng không tự có phê duyệt |
| Có snapshot duyệt khớp đủ dữ liệu | Chuyển đúng quyết định và provenance |
| Snapshot khác nội dung hiện tại | Không gắn hiệu lực duyệt cho nội dung mới |
| Chỉ có boolean approved | Không tự tạo bằng chứng bằng revision mặc định |
| Hai tenant có ID cục bộ trùng | Không đối chiếu hoặc ghi nhầm bằng chứng |
| Người dùng sửa trong lúc backfill | Không gán phê duyệt dựa trên snapshot lỗi thời |
| Writer cũ không hỗ trợ revision cố ghi | Bị ngăn hoặc xử lý theo hợp đồng chuyển tiếp, không phá dữ liệu mới |
| Client chọn model version cũ | Không hạ quy tắc áp dụng |
| Backfill dừng sau một số commit rồi chạy lại | Không nhân đôi quyết định, sự kiện hoặc tác động |
| Backfill và approve chạy đồng thời | Không ghi đè quyết định hoặc nội dung mới hơn |
| Reader cũ gặp bản ghi chưa xác minh | Không dùng nhãn cũ để cho phép hành động mới trái quy tắc |
| Message cũ thiếu revision | Không tự áp dụng ý định cho nội dung hiện tại |
| Retry command đã hoàn thành trước migration | Không tạo lần xác nhận hoặc thanh toán mới |
| Đường cũ và mới cùng nhận một nghĩa vụ | Chỉ có số tác động được chính sách cho phép |
| Đơn confirmed lịch sử thiếu bằng chứng | Không bị chạy lại như đơn mới hoặc được gọi là đã xác minh vô căn cứ |
| Lỗi giữa hai ghi tương thích | Không tạo quyết định từ biểu diễn chưa nhất quán |
| Shadow chạy cùng luồng chính | Không tạo tác động nghiệp vụ thật |
| Cutover từng nhóm | Đúng nhóm được áp dụng và không có đường tự chọn nhóm yếu hơn |
| Rollback sau khi có dữ liệu mới | Không làm chương trình cũ ghi sai ngữ nghĩa mới |
| Khôi phục backup rồi replay | Không quên tác động ngoài hệ thống đã xảy ra |
| Xóa bảng hoặc trường cũ | Không làm mất bằng chứng hoặc bảo vệ replay còn cần |
| Hoàn tất migration | Luồng hợp lệ vẫn tạo, duyệt và xác nhận được |

Ma trận là kế hoạch minh họa, không phải kết quả đã chạy trên repository.

### 11.3. Kiểm tra ở nhiều cấp

Unit test phù hợp với cách phân loại dữ liệu, ánh xạ snapshot và guard.

Integration test cần thiết cho constraint, transaction, khóa, optimistic locking và cập nhật cạnh tranh.

Kiểm thử hợp đồng cần cho tổ hợp reader, writer, producer và consumer khác phiên bản.

Kiểm thử phục hồi cần cho checkpoint, lỗi một phần, replay và tác động ngoài hệ thống.

Một test dữ liệu backfill đúng khi không có traffic chưa chứng minh hệ thống đúng khi các writer chạy đồng thời.

### 11.4. Kiểm tra quyền thực thi và cấu hình thật

Nếu kế hoạch dựa vào việc writer cũ không còn được ghi, cần kiểm tra quyền hoặc đường ghi thực tế của nó.

Nếu dựa vào constraint, cần xác nhận constraint có hiệu lực trên các dữ liệu và đường tác động liên quan.

Nếu dựa vào version, cần xác định writer nào tăng version và câu lệnh nào có thể bỏ qua.

Không nên kiểm thử bằng một role hạn chế rồi vận hành bằng role có quyền bỏ qua chính sách mà không đánh giá khác biệt.

## 12. Rollback, sửa tiến tới và giới hạn của hoàn tác

### 12.1. Rollback code không tự đảo ngược ngữ nghĩa dữ liệu

Một chương trình cũ có thể đọc cột approved, nhưng không hiểu:

```text
contentRevision
approvedRevision
bằng chứng chưa xác minh
command đang gắn với revision
quy tắc phân loại legacy
```

Nếu cho nó ghi lại, nó có thể làm mất liên kết mà migration mới tạo.

Kế hoạch rollback cần nói phiên bản nào còn giữ được bảo đảm, những đường ghi nào tiếp tục bị rào và dữ liệu nào không thể đổi ngược mà vẫn giữ đủ nghĩa.

### 12.2. Không khôi phục khả năng bỏ qua để giảm lỗi

Sau cutover, một số đối tượng có thể bị chặn vì thiếu bằng chứng. Bật lại fallback boolean sẽ làm chúng đi qua, nhưng đồng thời hạ bảo đảm đã cam kết.

Cần phân biệt lỗi triển khai với dữ liệu thật sự không đủ điều kiện. Hướng xử lý có thể là sửa code, bổ sung bằng chứng hợp lệ, yêu cầu duyệt lại hoặc giải quyết theo quy trình ngoại lệ có thẩm quyền.

Ngoại lệ cũng phải có phạm vi và không được giả mạo quyết định đã xảy ra.

### 12.3. Tác động bên ngoài cần đối soát riêng

Khôi phục một backup cũ không hoàn tác khoản thu, khoản hoàn hoặc hàng đã giao.

Nếu dữ liệu nội bộ lùi về trước một tác động, hệ thống cần nhận diện nghĩa vụ gốc và đối chiếu trước khi mở lại xử lý có thể tạo tác động mới.

Giữ định danh ổn định, lịch sử cần thiết và cơ chế chống lặp là một phần của kế hoạch phục hồi. Không chỉ sao lưu schema mới.

### 12.4. Sửa tiến tới có thể giữ được nhiều thông tin hơn

Khi một bản ghi mới đã có bằng chứng và liên kết đầy đủ, có thể phù hợp hơn khi sửa lỗi bằng một phiên bản tương thích tiếp theo thay vì ép dữ liệu trở về biểu diễn cũ làm mất thông tin.

Nếu cần điều chỉnh dữ liệu hoặc sổ cái, nên giữ liên kết và lý do của điều chỉnh theo mô hình nghiệp vụ.

Lựa chọn rollback hay sửa tiến tới cần dựa trên khả năng giữ invariant, trạng thái tác động và kế hoạch đã được kiểm chứng.

## 13. Theo dõi tiến độ và điều kiện hoàn tất

### 13.1. Các số liệu cần có ý nghĩa nghiệp vụ

Có thể theo dõi:

| Nhóm tín hiệu | Mục đích |
| --- | --- |
| Số đối tượng theo phân loại | Biết phần đã xác minh, cần duyệt lại và cần đối soát |
| Xung đột khi backfill | Phát hiện dữ liệu thay đổi và cơ chế retry |
| Writer cũ bị từ chối | Xác nhận còn đường ghi chưa chuyển hoặc routing sai |
| Hành động mới dùng biểu diễn cũ | Phát hiện đường hạ bảo đảm sau cutover |
| Chênh lệch giữa hai biểu diễn | Kiểm tra dual write hoặc quy tắc ánh xạ |
| Command tồn đọng theo phiên bản | Chuẩn bị xử lý và loại bỏ phần cũ |
| Vi phạm invariant hoặc constraint | Phát hiện dữ liệu hay hành vi sai |
| Tác động trùng hoặc chưa xác định | Giữ kiểm soát nghĩa vụ ngoài hệ thống |
| Thời gian chờ xử lý dữ liệu thiếu bằng chứng | Tránh nhóm chưa giải quyết bị bỏ quên |

Số liệu phải có scope và mốc quan sát phù hợp. Khi dữ liệu vẫn phát sinh, tổng ở hai thời điểm khác nhau không đủ để kết luận mất hoặc nhân đôi bản ghi.

### 13.2. Đối soát từ nguồn có thẩm quyền

Cần kiểm tra quan hệ giữa:

```text
Nội dung hoặc snapshot được xác nhận
Bằng chứng phê duyệt
Phiên bản biểu diễn và policy áp dụng
Command và kết quả
Tác động hoặc nghĩa vụ bên ngoài
Lịch sử chuyển đổi
```

Việc count hai bảng bằng nhau không chứng minh bằng chứng được gắn đúng đơn hoặc đúng người duyệt.

Một tiến trình kiểm tra lại phải tránh tự sửa dữ liệu để hai bên trông giống nhau mà mất thông tin về nguyên nhân.

### 13.3. Tiêu chí hoàn tất cần ghi rõ phạm vi

Một migration có thể đạt mốc hoàn tất đã chọn khi:

1. Mọi hành động thuộc phạm vi đích đều được thực thi bằng quy tắc và cơ chế đích.
2. Không còn writer có thể đi vòng các điều kiện bắt buộc.
3. Dữ liệu được phân loại và xử lý theo chính sách; phần chưa xác minh không bị trình bày sai hoặc dùng sai.
4. Tính duy nhất, tenant và danh tính nghiệp vụ được giữ qua đường cũ và mới.
5. Message tồn đọng, replay và phục hồi có cách xử lý.
6. Có bằng chứng cho concurrency, tổ hợp phiên bản và các nhánh lỗi quan trọng.
7. Phần cũ được giữ hoặc loại bỏ theo điều kiện đã định.
8. Các ngoại lệ và rủi ro còn lại có người theo dõi và điều kiện xem lại.

Nếu mục tiêu chỉ áp dụng tiến tới, báo cáo cần nói điều đó. Không đổi tên thành “toàn bộ lịch sử đã đạt invariant mới” khi dữ liệu cũ vẫn không đủ bằng chứng.

### 13.4. Những cách làm thường khiến migration thất bại về bảo mật

| Cách làm | Hậu quả |
| --- | --- |
| Điền approvedRevision từ revision hiện tại cho mọi đơn approved | Tạo sự khớp giả giữa quyết định và nội dung |
| Dùng client model version để chọn rule | Tạo đường hạ bảo đảm |
| Dual write không có nguồn quyết định rõ | Hai biểu diễn có thể cho kết luận khác nhau |
| Dựa vào rowVersion trong khi writer cũ không tăng nó | Không phát hiện đủ cập nhật cạnh tranh |
| Chỉ bảo vệ endpoint chính | Job và công cụ quản trị có thể phá invariant |
| Tạo ID nghĩa vụ mới khi chuyển hệ thống | Mất khả năng nhận diện tác động đã xảy ra |
| Giải quyết legacy bằng cách chạy lại workflow | Có thể thu, hoàn hoặc gửi hàng lần nữa |
| Xóa dữ liệu chống lặp quá sớm | Replay cũ có thể trông như command mới |
| Rollback code mà mở lại quyền ghi cũ | Dữ liệu mới bị sửa bằng ngữ nghĩa không phù hợp |
| Chỉ đo tỷ lệ backfill | Không biết hành động ngoài nhóm đã chuyển có đi vòng không |

## 14. Mẫu kế hoạch invariant migration

```text
Tên migration:
Phạm vi và người sở hữu:

Bất biến cũ:
Bất biến đích:
Thay đổi về cách biểu đạt:
Thay đổi về nơi thực thi:
Mục tiêu tiến tới hay toàn bộ dữ liệu:

Dữ liệu và bằng chứng:
Các nhóm dữ liệu:
Điều kiện đủ để chuyển:
Dữ liệu không thể chứng minh:
Chính sách với nghĩa vụ đã phát sinh:
Provenance cần giữ:

Hợp đồng chuyển tiếp:
Mốc áp dụng:
Writer và reader còn tồn tại:
Các hành động bị giữ hoặc giới hạn:
Cách ngăn hạ phiên bản:
Cách giữ tenant và quyền:

Kế hoạch kỹ thuật:
Mở rộng schema:
Nguồn quyết định trong dual write:
Quy tắc dual read:
Giao thức cạnh tranh:
Backfill và checkpoint:
Xử lý lỗi một phần và chạy lại:
Command cũ, retry và idempotency:

Cutover:
Điều kiện sẵn sàng:
Nhóm chuyển:
Cách xác minh writer cũ đã bị rào:
Constraint và cấu hình cần có:
Cách loại bỏ fallback và phần cũ:

Kiểm chứng:
Oracle:
Dữ liệu đối chứng:
Concurrency:
Tổ hợp phiên bản:
Replay và phục hồi:
Bằng chứng và giới hạn kết luận:

Rollback hoặc sửa tiến tới:
Điều kiện được phép:
Dữ liệu không thể đổi ngược:
Tác động ngoài hệ thống cần đối soát:

Vận hành:
Metric và cảnh báo:
Đối soát:
Người xử lý ngoại lệ:
Tiêu chí hoàn tất:
Rủi ro còn lại và điều kiện xem lại:
```

Với ví dụ phê duyệt theo revision, điều cần chứng minh sau cutover là một nội dung mới không thể được xác nhận bằng cờ hoặc quyết định cũ không đủ bằng chứng. Dữ liệu lịch sử chưa rõ phải tiếp tục được quản lý trung thực, còn các đường ghi và phục hồi phải giữ cùng ý nghĩa đó.
