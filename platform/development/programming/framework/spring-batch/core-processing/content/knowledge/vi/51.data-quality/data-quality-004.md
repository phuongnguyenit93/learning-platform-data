# Đối chiếu tổng input và output trong Spring Batch: kiểm soát chất lượng dữ liệu

Một Spring Batch job kết thúc với trạng thái `COMPLETED` chưa đủ chứng minh rằng mọi dữ liệu cần xử lý đã đến đúng nơi, không bị thiếu, không trùng và không sai giá trị. Ví dụ job đọc 10.000 giao dịch từ CSV nhưng chỉ tạo 9.997 dòng trong database: ba dòng chênh lệch có thể là giao dịch bị lọc đúng quy tắc, bị skip sau lỗi dữ liệu, bị ghi trùng và bỏ qua bằng UPSERT, hoặc thật sự bị thất lạc. Nếu không có phép **đối chiếu input–output (reconciliation)**, những trường hợp này rất khó phân biệt.

Trong chủ đề **Spring Batch Core Processing → Data quality**, “đối chiếu tổng input và output” là việc chứng minh bằng số đếm, tổng giá trị và định danh nghiệp vụ rằng **dữ liệu nguồn đã được giải thích đầy đủ và dữ liệu đích phù hợp với quy tắc xử lý**. Trọng tâm không chỉ là so sánh hai con số; phải xác định rõ *đang đếm gì*, *đếm ở thời điểm nào* và *những phép biến đổi nào làm thay đổi số lượng hoặc giá trị*.

Bài học sử dụng Spring Batch 5.x trở lên với chunk-oriented processing, `StepExecution`, `JobRepository`, JDBC và một bộ dữ liệu CSV nhỏ để minh họa. Các nguyên tắc cũng áp dụng cho ETL, nhập đơn hàng, thanh toán, báo cáo, đồng bộ dữ liệu và các pipeline đọc/ghi ngoài cơ sở dữ liệu.

## 1. Vì sao cần đối chiếu khi job đã báo COMPLETED?

`BatchStatus.COMPLETED` chủ yếu cho biết job hoặc step đã hoàn tất theo luồng điều khiển được cấu hình. Trạng thái đó vẫn có thể xuất hiện khi:

- Processor cố ý trả `null` để **filter** các dòng không thuộc phạm vi nghiệp vụ.
- Step được phép **skip** một số record lỗi trong giới hạn cho phép.
- Writer dùng `INSERT ... ON CONFLICT DO NOTHING`, làm nhiều item được gửi tới writer nhưng ít hàng mới xuất hiện.
- Writer ghi một item thành nhiều bản ghi ở đích, hoặc gộp nhiều item vào một bản ghi.
- Các đầu ra ở hệ thống khác database có độ trễ hoặc chỉ bảo đảm *at-least-once*.
- Một file đầu ra đã được tạo nhưng vẫn thiếu dòng, sai encoding hoặc chưa được công bố an toàn.
- Dữ liệu đích có sẵn bản ghi từ lần chạy trước, khiến số hàng cuối không phản ánh riêng lần chạy hiện tại.

Ngược lại, `FAILED` không có nghĩa mọi kết quả đã được rollback. Trong chunk-oriented step, các chunk trước đã commit thường vẫn tồn tại khi chunk sau thất bại. Bởi vậy, phép đối chiếu phải kiểm tra **trạng thái dữ liệu thực tế**, không chỉ trạng thái execution.

### Ba câu hỏi nền tảng

1. **Input là gì?** Toàn bộ dòng vật lý trong file, dòng dữ liệu sau header, item được reader parse thành công, hay tập bản ghi nghiệp vụ duy nhất?
2. **Output là gì?** Số item gửi tới writer, số item được `writeCount` ghi nhận, số hàng đã commit, số giao dịch duy nhất hay tổng tiền đã công bố?
3. **Chênh lệch nào được phép?** Filter, skip, hủy bản ghi, gộp, tách, deduplicate, chuyển đổi tiền tệ và làm tròn có được mô tả trong hợp đồng dữ liệu không?

Nếu chưa trả lời các câu hỏi này, công thức `inputCount == outputCount` có thể gây báo động sai hoặc bỏ sót lỗi.

## 2. Các cấp độ đối chiếu

| Cấp độ | Chỉ tiêu đối chiếu | Ví dụ | Phát hiện được gì? |
|---|---|---|---|
| **Số lượng (count)** | Số dòng, item, record hoặc business key | 7 dòng nguồn → 4 dòng đích + 3 dòng được giải thích | Thiếu/thừa theo số lượng |
| **Giá trị (control total)** | Tổng số tiền, khối lượng, điểm hoặc số lượng hàng hóa | Tổng tiền hợp lệ 200.00 → tổng tiền đích 200.00 | Sai tổng giá trị dù số dòng bằng nhau |
| **Định danh (key reconciliation)** | Tập ID nguồn được chấp nhận so với tập ID đích | `TX-001, TX-002, TX-006, TX-007` | Thiếu một ID và trùng ID khác dù hai count bằng nhau |
| **Phân nhóm** | Count và sum theo ngày, nguồn, trạng thái, loại tiền | USD đúng nhưng VND thiếu 1 record | Lỗi bị che khi chỉ xem tổng toàn cục |
| **Nội dung** | Giá trị từng field, checksum có quy tắc ổn định | Cùng ID nhưng amount khác | Record hiện diện nhưng dữ liệu sai |
| **Tính thời điểm** | Snapshot, cutoff, watermark, version | File phiên bản v2 so với output v2 | Đang đối chiếu hai tập dữ liệu khác kỳ |
| **Tính duy nhất** | Số record trùng khóa nghiệp vụ | Một `event_id` phải xuất hiện một lần | Duplicate do retry/restart hoặc nguồn |

Không phải job nào cũng cần tất cả mức. Với import tiền tệ hoặc nghiệp vụ ảnh hưởng tài chính, **count + sum + key** thường mạnh hơn count đơn lẻ. Với output tổng hợp many-to-one, cần so sánh trên cùng “đơn vị hạt” (*grain*) thay vì ép số hàng nguồn và đích phải bằng nhau.

## 3. Xác định grain và tập dữ liệu được đối chiếu

**Grain** là đơn vị mà mỗi bản ghi đại diện. Ví dụ:

- Input: một dòng CSV = một sự kiện thanh toán.
- Output: một hàng `ledger_entry` = một sự kiện thanh toán được chấp nhận.
- Hoặc output: một hàng `daily_summary` = tổng tiền của cả một ngày và loại tiền.

Ở trường hợp đầu, có thể kỳ vọng số sự kiện hợp lệ bằng số hàng đích. Ở trường hợp sau, vài nghìn sự kiện nguồn có thể được gộp thành chỉ vài hàng tổng hợp; hai count vật lý không nên bằng nhau.

Đồng thời cần chốt **ranh giới dữ liệu**:

| Thành phần | Ví dụ | Quy tắc |
|---|---|---|
| `businessDate` | `2026-11-15` | Là ngày nghiệp vụ, không tự suy từ thời điểm chạy. |
| `sourceId` | `warehouse-A` | Xác định nguồn, tránh gộp nhiều feed khác nhau. |
| `sourceVersion` | `v1` hoặc checksum nguồn | Phân biệt file đã thay đổi so với lần trước. |
| `batchKey` | `2026-11-15:warehouse-A:v1` | Khóa liên kết input, output và kết quả đối chiếu. |
| `cutoffTime` | Mốc lấy snapshot cố định | Không so sánh input trước cutoff với output đang thay đổi sau cutoff. |
| `currency` | `VND` hoặc `USD` | Không cộng gộp tiền khác loại khi chưa có quy tắc quy đổi. |

Trước khi đọc file hoặc query nguồn đang thay đổi, nên có **manifest/snapshot**: tên nguồn logic, phiên bản, thời điểm chốt, số dòng dữ liệu kỳ vọng và checksum nếu phù hợp. Chỉ đếm lại nguồn đang phát sinh giao dịch trong lúc job chạy có thể cho kết quả khác nhau dù batch hoàn toàn đúng.

## 4. Hiểu đúng bộ đếm Spring Batch

`StepExecution` cung cấp các bộ đếm quan trọng cho một lần thực thi step. Những giá trị này hữu ích để giải thích đường đi của item nhưng **không thay thế phép kiểm chứng độc lập tại nguồn và đích**.

| Trường `StepExecution` | Ý nghĩa thường dùng trong chunk-oriented step |
|---|---|
| `getReadCount()` | Số item đã được reader đọc thành công theo ghi nhận của step. |
| `getReadSkipCount()` | Số item/lần đọc lỗi được skip trong giai đoạn read. |
| `getFilterCount()` | Số item được processor lọc, thường khi `process(...)` trả `null`. |
| `getProcessSkipCount()` | Số item lỗi ở processor và được skip. |
| `getWriteCount()` | Số item được step ghi nhận đã ghi thành công qua writer. |
| `getWriteSkipCount()` | Số item được skip ở giai đoạn writer. |
| `getCommitCount()` | Số lần commit được ghi nhận. |
| `getRollbackCount()` | Số lần rollback được ghi nhận. |
| `getStatus()` / `getExitStatus()` | Trạng thái và kết quả thực thi step. |

Chú ý cách diễn giải:

- `readCount` là **item đã được đọc thành công**, không nhất thiết là số dòng vật lý trong file. Header, dòng trống, callback bỏ qua dòng và cấu hình reader có thể thay đổi quan hệ này.
- `readSkipCount` không bắt buộc bao gồm mọi dòng vật lý bị bỏ qua do cấu hình reader; một số dòng có thể không được tạo thành item ngay từ đầu.
- `filterCount` thường phản ánh processor trả `null` theo chính sách. Đó không phải lỗi cần báo động nếu đúng hợp đồng.
- `writeCount` đo số item theo mô hình Spring Batch, **không bảo đảm cùng số hàng đã commit** khi writer làm UPSERT bỏ qua bản ghi, tách/gộp, hoặc ghi ra hệ thống không transactional.
- Các counter có ngữ nghĩa gắn với `StepExecution`; khi job restart tạo execution mới hoặc step được chạy lại, không được cộng bừa các counter từ mọi lịch sử để suy ra số record duy nhất cuối cùng.

### Một phương trình đếm với giả định rõ ràng

Trong một **step hoàn tất**, mỗi item đọc thành công tạo tối đa một output item, filter và skip loại item khỏi writer, không có transformation one-to-many và writer thực sự ghi một hàng mỗi item, thì một kiểm tra logic hữu ích là:

\[
\text{readCount} =
\text{filterCount} + \text{processSkipCount} +
\text{writeSkipCount} + \text{writeCount}
\]

Ở mức file nguồn, nếu **mọi dòng dữ liệu** đều được reader phân loại thành một item đọc thành công hoặc một lỗi đọc được skip và không có dòng dữ liệu bị bỏ qua ngầm, thì:

\[
\text{sourceDataLines} = \text{readCount} + \text{readSkipCount}
\]

Hai đẳng thức là **invariant có điều kiện**, không phải công thức luôn đúng cho mọi cấu hình Spring Batch. Với retry phức tạp, writer có side effect, multi-resource writer, reader tự bỏ dòng, kết quả writer không theo 1:1 hoặc job dừng giữa chừng, cần điều chỉnh cách đếm và nguồn số liệu. Với dữ liệu quan trọng, luôn đối chiếu thêm **output thực tế đã commit**.

## 5. Ví dụ xuyên suốt: bảy dòng đầu vào, bốn bản ghi đầu ra

Giả sử job nhận CSV thanh toán. Quy tắc nghiệp vụ: amount dương được ghi, amount bằng 0 được filter, amount âm bị từ chối tại processor, chuỗi amount không parse được bị skip ở reader. Mỗi item được chấp nhận tạo một record đích.

`payments-test.csv`:

~~~csv
event_id,customer,amount
TX-001,An,100.00
TX-002,Binh,50.00
TX-003,Chi,abc
TX-004,Dung,0.00
TX-005,Ha,-20.00
TX-006,Lan,30.50
TX-007,Mai,19.50
~~~

Dòng đầu là header; có **7 dòng dữ liệu**. Dự kiến:

| Event | Amount | Kết quả | Tầng quyết định |
|---|---:|---|---|
| `TX-001` | 100.00 | Ghi | Writer |
| `TX-002` | 50.00 | Ghi | Writer |
| `TX-003` | `abc` | Read skip vì parse sai kiểu | Reader |
| `TX-004` | 0.00 | Filter theo quy tắc giả định | Processor |
| `TX-005` | -20.00 | Process skip vì validation | Processor |
| `TX-006` | 30.50 | Ghi | Writer |
| `TX-007` | 19.50 | Ghi | Writer |

Sau một lần thực thi hoàn chỉnh, với cấu hình fault tolerance phù hợp và không có retry/write skip phát sinh ngoài dự kiến:

~~~text
sourceDataLines  = 7
readCount        = 6
readSkipCount    = 1
filterCount      = 1
processSkipCount = 1
writeSkipCount   = 0
writeCount       = 4
outputRows       = 4
acceptedAmount   = 200.00
outputAmount     = 200.00
~~~

Phép đối chiếu:

~~~text
Nguồn:                7 dòng dữ liệu
  ├─ Read skip:       1  (TX-003)
  └─ Read thành công: 6
       ├─ Filter:       1  (TX-004)
       ├─ Process skip: 1  (TX-005)
       └─ Ghi:          4  (TX-001, TX-002, TX-006, TX-007)

7 = 1 + 1 + 1 + 4
Tổng tiền chấp nhận: 100.00 + 50.00 + 30.50 + 19.50 = 200.00
Tổng tiền đã lưu:    200.00
~~~

Điểm đáng chú ý: **7 không bằng 4 là kết quả đúng**, vì ba dòng chênh lệch có nguyên nhân đã được phân loại. Nếu chỉ kiểm tra `sourceDataLines == outputRows`, bài test sẽ báo lỗi sai. Ngược lại, nếu chỉ xem `writeCount == 4` mà database chỉ thực sự có ba hàng, dữ liệu vẫn đang bị thiếu.

### Định nghĩa số “được chấp nhận”

Một cách gọi rõ ràng:

\[
\text{acceptedInputCount}
= \text{sourceDataLines}
- \text{readRejectedCount}
- \text{filteredCount}
- \text{processRejectedCount}
\]

Với ví dụ này, `acceptedInputCount = 4`. Cần phân biệt **rejected** với **filtered**:

- *Rejected*: dữ liệu không thể hoặc không được xử lý theo hợp đồng, thường cần báo cáo lỗi/quarantine.
- *Filtered*: dữ liệu hợp lệ nhưng bị loại đúng quy tắc nghiệp vụ.

Không nên gộp cả hai thành “lost records”. Tỷ lệ dữ liệu lỗi, tỷ lệ filter và số liệu cần xử lý lại có ý nghĩa vận hành khác nhau.

## 6. Đối chiếu bằng số lượng vẫn có thể bỏ sót lỗi

Giả sử đầu vào hợp lệ gồm bốn ID `A, B, C, D`, database sau job cũng có bốn hàng nhưng là `A, B, C, C`. So sánh count cho kết quả 4 == 4, nhưng vẫn **thiếu D và trùng C**.

Một trường hợp khác: input có các amount `100` và `200`; output có `150` và `150`. Số record vẫn bằng nhau, tổng vẫn bằng 300, nhưng **giá trị của từng record sai**.

Do đó với dữ liệu quan trọng, nên kiểm chứng theo nhiều chiều:

| Kiểm tra | Trả lời câu hỏi |
|---|---|
| `COUNT(*)` | Có bao nhiêu hàng đích? |
| `COUNT(DISTINCT event_id)` | Có bao nhiêu khóa sự kiện duy nhất? |
| Tập `event_id` chấp nhận trừ tập `event_id` đích | ID nào bị thiếu? |
| Tập đích trừ tập chấp nhận | ID nào là thừa? |
| `SUM(amount)` theo business group | Có sai tổng giá trị không? |
| So sánh amount theo `event_id` | Bản ghi có mặt nhưng dữ liệu có đúng không? |
| Checksum/canonical digest có quy tắc | Nội dung đã chuẩn hóa có tương đương không? |

Tập ID và so sánh bản ghi theo khóa thường là **chứng cứ mạnh hơn** một cặp tổng số. Nếu dữ liệu lớn, có thể đối chiếu bằng join, anti-join hoặc tổng hợp có index; không cần tải tất cả ID về JVM.

## 7. Lưu bằng chứng input độc lập với output

Muốn đối chiếu đáng tin cậy, phải xác định “số liệu kỳ vọng” từ nguồn độc lập với thao tác ghi đích. Nếu job chỉ vừa ghi ra bốn hàng rồi tự tuyên bố “expected output = bốn hàng đã ghi”, phép kiểm tra trở nên vô nghĩa.

Một **source manifest** đơn giản có thể chứa:

~~~json
{
  "batchKey": "2026-11-15:warehouse-A:v1",
  "sourceId": "warehouse-A",
  "businessDate": "2026-11-15",
  "sourceVersion": "v1",
  "fileName": "payments-2026-11-15.csv",
  "dataLineCount": 7,
  "fileSha256": "<digest-of-original-file>",
  "encoding": "UTF-8"
}
~~~

`fileSha256` là checksum minh họa, nên được tính từ **bytes của file đã chốt**, không phải từ file thay đổi trong khi job đang chạy. Manifest cần nêu cách đếm header và dòng trắng; `dataLineCount=7` trong ví dụ **không tính header**. Không dùng checksum để thay thế quy tắc business key hoặc kiểm chứng riêng từng item.

Một snapshot có thể được tạo bởi upstream data contract, bước preflight độc lập hoặc quá trình tiếp nhận file trước khi job xử lý. Nếu manifest do cùng reader tự tính, nó vẫn hữu ích cho vận hành nhưng mức độ độc lập của phép kiểm tra thấp hơn; cần hiểu nguồn gốc con số.

### Theo dõi tình trạng từng record bằng quarantine/audit

Để giải thích sự chênh lệch, có thể lưu trạng thái xử lý ở nơi phù hợp:

~~~text
batchKey=2026-11-15:warehouse-A:v1
TX-001 -> ACCEPTED
TX-002 -> ACCEPTED
line 4 -> READ_REJECTED
TX-004 -> FILTERED
TX-005 -> PROCESS_REJECTED
TX-006 -> ACCEPTED
TX-007 -> ACCEPTED
~~~

Lưu ý: dòng đọc lỗi có thể chưa tạo được `event_id`, vì vậy cần một định danh nguồn như `sourceLineNumber` hoặc opaque record reference để đối chiếu. Audit/quarantine có thể chứa dữ liệu nhạy cảm; chỉ lưu phần cần thiết và áp dụng quyền truy cập/retention phù hợp.

Nếu audit ghi trong listener **ngoài transaction**, một lần retry hoặc rollback có thể tạo bản ghi audit trùng. Hãy thiết kế khóa idempotency cho từng event/trạng thái hoặc phối hợp transaction phù hợp. Không suy ra số dòng audit bằng số item thực chỉ vì listener được gọi một lần trong một thử nghiệm đơn giản.

## 8. Đối chiếu output đã commit bằng SQL

Giả sử writer ghi vào bảng PostgreSQL:

~~~sql
CREATE TABLE processed_payment (
    batch_key VARCHAR(120) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, event_id)
);
~~~

`batch_key` gắn output với một kỳ/phiên bản xử lý. Ràng buộc khóa chính giúp chống ghi trùng cùng sự kiện trong batch. Nếu nghiệp vụ đòi hỏi một event ID duy nhất trên **mọi batch**, cần điều chỉnh ràng buộc unique theo chính sách đó; khóa gồm batch key chỉ bảo vệ trong phạm vi batch.

Sau khi step ghi hoàn tất, đối chiếu với **database đích**:

~~~sql
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT event_id) AS distinct_events,
    COALESCE(SUM(amount), 0.00) AS output_amount
FROM processed_payment
WHERE batch_key = :batchKey;
~~~

Với ví dụ ở mục 5, kết quả kỳ vọng là:

~~~text
output_rows    = 4
distinct_events = 4
output_amount  = 200.00
~~~

Điểm mạnh của query này là số hàng và số tiền phản ánh **dữ liệu cuối đã được database nhìn thấy**, không chỉ số item mà step từng gọi writer. Tuy nhiên, nếu job đang chạy và các chunk liên tục commit, query có thể thấy một trạng thái trung gian. Nên đối chiếu sau khi bước ghi kết thúc hoặc dưới một snapshot/isolation được xác định phù hợp.

### Kiểm tra trùng khóa

Nếu bảng chưa có ràng buộc unique hoặc cần tra dữ liệu lịch sử:

~~~sql
SELECT event_id, COUNT(*) AS occurrences
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY event_id
HAVING COUNT(*) > 1;
~~~

Kết quả query lý tưởng là **không có hàng**. Nhưng `COUNT(DISTINCT event_id)` chỉ kiểm tra trùng ID trong phạm vi dữ liệu đã lọc; nó không chứng minh mọi expected ID đều có mặt.

### Tìm ID thiếu hoặc thừa

Giả sử hệ thống có staging table `accepted_payment` chứa danh sách **đầu vào đã được chấp nhận**, được lưu với trạng thái nhất quán:

~~~sql
-- Những event được chấp nhận nhưng chưa có trong output.
SELECT a.event_id
FROM accepted_payment a
LEFT JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND p.event_id IS NULL;

-- Những event có trong output nhưng không thuộc tập được chấp nhận.
SELECT p.event_id
FROM processed_payment p
LEFT JOIN accepted_payment a
  ON a.batch_key = p.batch_key
 AND a.event_id = p.event_id
WHERE p.batch_key = :batchKey
  AND a.event_id IS NULL;
~~~

Cả hai query lý tưởng trả về **0 hàng**, khi hợp đồng yêu cầu mapping 1:1. Tập `accepted_payment` cần được thiết kế là nguồn kỳ vọng đủ độc lập; nếu nó chỉ được tạo sau bằng cách copy từ `processed_payment`, phép anti-join mất ý nghĩa.

### Tìm sai giá trị trên cùng khóa

~~~sql
SELECT
    a.event_id,
    a.expected_amount,
    p.amount AS actual_amount
FROM accepted_payment a
JOIN processed_payment p
  ON p.batch_key = a.batch_key
 AND p.event_id = a.event_id
WHERE a.batch_key = :batchKey
  AND a.expected_amount <> p.amount;
~~~

Với `NUMERIC/DECIMAL` chính xác, so sánh được theo đơn vị đã chuẩn hóa. Nếu có quy tắc rounding, quy đổi tiền tệ hoặc định lượng dung sai, phải dùng expected amount đã áp dụng đúng quy tắc đó; không dùng so sánh khác biệt một cách tùy ý.

## 9. Đối chiếu tổng giá trị tiền tệ

Đếm đủ số hàng chưa chắc tổng tiền đúng. Với dữ liệu tài chính, control total là chỉ số quan trọng:

\[
\text{expectedOutputAmount}
= \sum_{\text{item accepted}} \text{transformedAmount}
\]

\[
\text{amountDifference}
= \text{actualOutputAmount}
- \text{expectedOutputAmount}
\]

Trong ví dụ:

~~~text
expectedOutputAmount = 100.00 + 50.00 + 30.50 + 19.50
                     = 200.00
actualOutputAmount   = 200.00
amountDifference     = 0.00
~~~

### Không cộng khác loại tiền

Nếu input có VND và USD, tổng `SUM(amount)` toàn bảng có thể không có ý nghĩa nghiệp vụ. Hãy đối chiếu theo currency:

~~~sql
SELECT
    currency,
    COUNT(*) AS row_count,
    COALESCE(SUM(amount), 0.00) AS amount_total
FROM processed_payment
WHERE batch_key = :batchKey
GROUP BY currency;
~~~

Query này giả định schema mở rộng có cột `currency`. Nếu job quy đổi tiền tệ, phải chốt tỷ giá, thời điểm tỷ giá, quy tắc làm tròn và expected amount sau chuyển đổi; không so sánh trực tiếp tổng tiền nguyên bản với tổng đã quy đổi.

### Dùng BigDecimal thay vì double

Trong Java, giá trị tiền tệ nên dùng `BigDecimal` hoặc kiểu số chính xác phù hợp, tránh dùng `double` để đối chiếu số tiền:

~~~java
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal("200.00");
BigDecimal actual = new BigDecimal("200.00");

boolean equalByValue = expected.compareTo(actual) == 0;
BigDecimal difference = actual.subtract(expected);
~~~

`BigDecimal.equals(...)` còn so sánh scale: `200.0` và `200.00` có thể không `equals` dù bằng nhau về giá trị. Nếu hợp đồng không yêu cầu scale giống hệt, dùng `compareTo(...) == 0`. Trong các nghiệp vụ cần quy tắc rounding, hãy áp dụng đúng `scale` và `RoundingMode` được xác định trước khi so sánh.

### Dung sai khi đối chiếu

Với dữ liệu không phải tiền tệ, phép đối chiếu đôi khi cho phép một dung sai:

\[
|\text{actual} - \text{expected}| \le \text{tolerance}
\]

Không chọn một tolerance lớn chỉ để test đi qua. Dung sai phải bắt nguồn từ hợp đồng chuyển đổi, độ chính xác phép đo hoặc rounding được chấp nhận. Với tiền kế toán theo đơn vị nhỏ nhất đã chuẩn hóa, nhiều hệ thống yêu cầu sai lệch **bằng 0**.

## 10. Đặt reconciliation trong luồng Job

Một thiết kế thường dùng là tách khâu nhận input, xử lý/ghi và đối chiếu:

~~~mermaid
flowchart TD
    A["Preflight: chốt snapshot/manifest input"] --> B["Load: đọc, xử lý và ghi theo chunk"]
    B --> C["Reconcile: đếm và đối chiếu dữ liệu đích"]
    C --> D{"Đạt hợp đồng chất lượng?"}
    D -->|Đạt| E["Publish: công bố đầu ra"]
    D -->|Không đạt| F["Job FAILED / chờ đối soát"]
~~~

Với output quan trọng, bước **publish** nên xảy ra **sau khi reconciliation đạt**, chẳng hạn chuyển dữ liệu từ staging sang tập được công bố, thay pointer version, hoặc phát sự kiện “batch ready”. Nếu publish được thực hiện trong từng writer chunk trước khi kiểm tra tổng, người dùng phía sau có thể đã tiêu thụ đầu ra sai trước khi step reconciliation phát hiện.

Ví dụ job theo Spring Batch 5.x:

~~~java
@Bean
Job importPaymentsJob(
        JobRepository jobRepository,
        Step preflightStep,
        Step loadPaymentsStep,
        Step reconcilePaymentsStep,
        Step publishPaymentsStep) {

    return new JobBuilder("importPaymentsJob", jobRepository)
        .start(preflightStep)
        .next(loadPaymentsStep)
        .next(reconcilePaymentsStep)
        .next(publishPaymentsStep)
        .build();
}
~~~

Các step ở đây là bean đã được cấu hình riêng. Theo flow tuyến tính mặc định, step tiếp theo chỉ được chạy khi luồng chuyển trạng thái cho phép; nếu `reconcilePaymentsStep` báo `FAILED`, job không tiếp tục qua bước công bố trong flow thành công thông thường.

Tách thành step giúp monitoring trả lời được: **load đã chạy thành công nhưng reconciliation thất bại**, thay vì chỉ thấy một exception vô danh ở cuối writer.

## 11. Một Tasklet đối chiếu count và amount sau khi ghi

Giả sử preflight đã lưu kỳ vọng trong bảng riêng `batch_expected_total`:

~~~sql
CREATE TABLE batch_expected_total (
    batch_key VARCHAR(120) PRIMARY KEY,
    expected_rows BIGINT NOT NULL,
    expected_amount NUMERIC(18, 2) NOT NULL
);
~~~

Bảng này chứa **số lượng và tổng tiền đã được chuẩn hóa cho tập item được chấp nhận**. Các số liệu phải được tạo từ nguồn kỳ vọng đáng tin cậy, theo chính sách skip/filter đã biết, và được giữ bền vững để đối chiếu. Nó không nên chỉ lấy lại `COUNT(*)`/`SUM(amount)` từ bảng output.

Một `Tasklet` minh họa dùng `JdbcTemplate`:

~~~java
import java.math.BigDecimal;

import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.jdbc.core.JdbcTemplate;

record Totals(long count, BigDecimal amount) {}

public class ReconcilePaymentsTasklet implements Tasklet {

    private final JdbcTemplate jdbc;

    public ReconcilePaymentsTasklet(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String batchKey = (String) chunkContext.getStepContext()
            .getJobParameters().get("batchKey");

        Totals expected = jdbc.queryForObject("""
                SELECT expected_rows, expected_amount
                FROM batch_expected_total
                WHERE batch_key = ?
                """,
            (rs, rowNum) -> new Totals(
                rs.getLong("expected_rows"),
                rs.getBigDecimal("expected_amount")),
            batchKey);

        Totals actual = jdbc.queryForObject("""
                SELECT COUNT(*) AS row_count,
                       COALESCE(SUM(amount), 0.00) AS amount_total
                FROM processed_payment
                WHERE batch_key = ?
                """,
            (rs, rowNum) -> new Totals(
                rs.getLong("row_count"),
                rs.getBigDecimal("amount_total")),
            batchKey);

        if (expected == null || actual == null
                || expected.count() != actual.count()
                || expected.amount().compareTo(actual.amount()) != 0) {
            throw new IllegalStateException(
                "RECONCILIATION_MISMATCH for batch key");
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Để đăng ký `Tasklet` như một step:

~~~java
@Bean
Step reconcilePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("reconcilePaymentsStep", jobRepository)
        .tasklet(
            new ReconcilePaymentsTasklet(jdbcTemplate),
            transactionManager)
        .build();
}
~~~

Một số điều kiện của ví dụ:

1. `batchKey` là job parameter có giá trị đã được xác thực. Job phải cung cấp nó khi launch, và bảng expectation phải có một hàng tương ứng.
2. Số lượng kỳ vọng ở bảng `batch_expected_total` là **số item cuối cùng đáng lẽ phải được ghi** sau filter/reject hợp lệ, không phải số dòng vật lý ban đầu.
3. `processed_payment` được đối chiếu theo batch key, giúp tránh trộn dữ liệu lần chạy khác.
4. Khi mismatch, tasklet ném exception, khiến step reconciliation thất bại và bước publish phía sau không được thực thi theo flow thành công.
5. Message lỗi cố ý không đưa dữ liệu thô của khách hàng vào log. Để điều tra, có thể ghi summary count/sum an toàn hoặc audit có quyền truy cập thích hợp.

Đây là ví dụ tối giản **count + sum**, chưa thay thế kiểm tra khóa thiếu/thừa, sai từng amount, việc đối chiếu theo currency hoặc những điều kiện đặc biệt của job. Trong môi trường production, nên biểu diễn lỗi bằng error code rõ, lưu báo cáo reconciliation và thêm các phép kiểm chứng đúng hợp đồng.

### Đánh dấu kết quả và công bố sau đối chiếu

Nếu muốn lưu `PASS`/`FAIL` vào một bảng audit, hãy thiết kế vòng đời kết quả rõ ràng: snapshot input, các giá trị expected/actual, sai lệch, thời điểm, job/step execution ID và phiên bản dữ liệu. Đừng ghi `PASS` trước khi các kiểm tra cần thiết hoàn thành. Nếu một lần chạy thất bại rồi restart, quyết định cách ghi đè hoặc version hóa audit để không có nhiều bản `PASS`/`FAIL` mâu thuẫn mà không rõ thứ tự.

Với yêu cầu công bố nguyên tử ở mức cả batch, có thể ghi output vào staging theo `batchKey`, đối chiếu, rồi **công bố phiên bản** qua một transaction/pointer swap tương ứng. Bản thân các commit theo chunk không cung cấp atomicity cho toàn bộ job.

## 12. Đối chiếu khi có filter, skip và writer không theo 1:1

Không phải mọi chênh lệch đều có cùng ý nghĩa. Phải mô tả cách giải thích theo từng pipeline.

| Kiểu xử lý | Ví dụ | Công thức hợp lý |
|---|---|---|
| 1:1 thuần, không skip/filter | Một input event → một output row | `acceptedInputCount == outputCount` |
| Filter có chủ đích | Loại event amount = 0 | `sourceCount = filtered + rejected + accepted` |
| Skip dữ liệu lỗi | CSV sai kiểu hoặc invalid field | `sourceCount = readRejected + processRejected + filtered + accepted`, dưới giả định mỗi dòng được phân loại một lần |
| Deduplicate | 2 event trùng business key → 1 row | So sánh `COUNT(DISTINCT businessKey)` và số output duy nhất; thống kê số duplicate |
| 1:n | Một đơn hàng tạo nhiều dòng chi tiết | So sánh số order nguồn với `COUNT(DISTINCT order_id)` ở đích và số dòng chi tiết dựa trên mapping |
| n:1 | Nhiều giao dịch → một tổng theo ngày/currency | So sánh số nhóm, tập group key và tổng amount, không yêu cầu số hàng bằng nhau |
| Chuyển đổi giá trị | Phí, thuế, FX, rounding | So sánh expected sau transform với actual sau transform |
| Nhiều đích | Database + file + broker | Đối chiếu riêng từng đích theo kỳ/version; nêu độ trễ và semantics của từng hệ thống |

### Deduplication

Giả sử nguồn có ba dòng `A, B, B` và chính sách chỉ giữ một sự kiện trên mỗi business key. `sourceDataLines=3` còn output rows = 2 có thể hoàn toàn đúng, nhưng cần báo rõ:

~~~text
sourceDataLines = 3
duplicateLines  = 1
acceptedUnique  = 2
outputUnique    = 2
~~~

Nếu writer làm `ON CONFLICT DO NOTHING`, `writeCount` có thể không tương ứng trực tiếp với số hàng mới chèn; hãy dùng SQL đích để xác minh uniqueness và số hàng thực.

### Many-to-one và 1:n

Khi processor/writer tạo output dạng tổng hợp, phép đối chiếu cần cùng grain:

~~~sql
-- Ví dụ: kỳ vọng nguồn đã chuẩn hóa theo ngày và currency.
SELECT business_date, currency, SUM(amount) AS expected_total
FROM accepted_payment
WHERE batch_key = :batchKey
GROUP BY business_date, currency;
~~~

So sánh từng nhóm này với bảng tổng hợp đích theo cùng `business_date`/`currency`. Một tổng toàn cục trùng nhau vẫn có thể che lỗi phân bổ tiền giữa hai currency hoặc hai ngày.

Trong output 1:n, kiểm tra tập khóa cha và quan hệ khóa ngoại giữa cha–con có thể quan trọng hơn so sánh một tổng số hàng.

## 13. Restart, retry và vì sao không được cộng counter một cách máy móc

Giả sử `JobInstance` xử lý ngày 15 có execution đầu tiên `FAILED` sau khi đã commit hai chunk. Một execution sau đó restart và hoàn tất. Có thể nhìn thấy hai `JobExecution` và nhiều `StepExecution` trong `JobRepository`.

~~~text
JobInstance=410
  |
  +-- JobExecution=8102 FAILED
  |     chunk 1 và 2 đã commit
  |
  +-- JobExecution=8103 COMPLETED
        tiếp tục phần cần xử lý
~~~

Không nên cộng `writeCount` của cả hai execution rồi mặc định đó là số hàng duy nhất trong database:

- Một số item có thể được replay do rollback hoặc checkpoint/cơ sở dữ liệu nghiệp vụ ở transaction khác nhau.
- Writer có thể UPSERT hoặc bỏ duplicate.
- Một step có thể được chạy lại từ đầu, hoặc được skip trên restart tùy cấu hình.
- Dữ liệu từ lần chạy trước có thể đã tồn tại trong bảng đích.
- Một số side effect ngoài database có thể xảy ra ở attempt cũ và chưa được kiểm soát idempotency.

**Phép đối chiếu cuối cùng phải dựa trên tập dữ liệu đích theo business key/version sau khi recovery**, kết hợp snapshot nguồn và audit của các bước xử lý. `StepExecution` hữu ích để hiểu từng attempt, nhưng không phải nguồn duy nhất xác nhận trạng thái nghiệp vụ cuối.

### Giữ cùng batch key qua restart

Khi restart cùng một `JobInstance`, sử dụng identifying JobParameters ổn định và gắn output với cùng business key. Nếu mỗi lần restart lại đổi `batchKey` theo timestamp, dữ liệu cũ và mới nằm ở hai phạm vi khác nhau; phép đếm có thể báo thiếu hoặc che trùng.

Nếu nghiệp vụ thực sự cần xử lý lại kỳ đã hoàn tất với dữ liệu nguồn phiên bản v2, tạo **sourceVersion/revision mới có nghĩa nghiệp vụ** và định nghĩa cách công bố kết quả v2 so với v1. Không đơn thuần thêm random run ID rồi so số hàng của tất cả phiên bản với cùng kỳ.

### Transaction và đối chiếu sau commit

Với JDBC writer tham gia transaction của chunk, lỗi giữa chunk thường rollback cả các thay đổi chưa commit của chunk. Các chunk đã commit vẫn tồn tại. Nếu database đích và `JobRepository` không nằm trong cùng transaction, một crash ở điểm nhạy cảm có thể làm checkpoint và output không đồng bộ; idempotency và reconciliation trở nên đặc biệt quan trọng.

Nếu writer gọi API/broker không transactional, một request timeout không chứng minh side effect chưa xảy ra. Cần tra trạng thái ở đích theo event ID hoặc sử dụng idempotency key/outbox trước khi quyết định phát lại, rồi đối chiếu kết quả cuối khi đích đã đạt trạng thái có thể kiểm chứng.

## 14. Partitioning và xử lý song song

Với `PartitionStep`, remote chunking hoặc nhiều worker song song, phép đối chiếu cần tránh đếm trùng trên các partition.

Ví dụ nguồn được chia theo:

~~~text
partition-0: event_id A000-A999
partition-1: event_id B000-B999
partition-2: event_id C000-C999
~~~

Các dải cần **không chồng lấn và bao phủ đủ input** theo hợp đồng. Nếu partition 0 và 1 cùng đọc một event, cộng `readCount` có thể lớn hơn số event nguồn duy nhất mà không nhất thiết báo lỗi writer.

Hướng kiểm soát:

1. Xác định predicate/range chính xác cho từng partition, cả điểm đầu/cuối.
2. Dùng **business key duy nhất** làm định danh item và output.
3. Tổng hợp count theo partition và **kiểm tra tập khóa** ở mức toàn job.
4. Đối chiếu với snapshot nguồn cùng cutoff, tránh phân hoạch trên tập dữ liệu đang thay đổi.
5. Khi partition được retry hoặc worker chạy lại, deduplicate theo record/batch key trước khi tính kết quả cuối.

Nếu cần metric theo partition, có thể lưu `partitionId` trong audit, nhưng không dùng việc cộng tất cả callback hoặc execution attempts để tính số event duy nhất. Phép tổng cuối nên theo tập dữ liệu bền vững đã chuẩn hóa.

## 15. Kết quả đối chiếu có thể dùng để điều khiển Job

Một reconciliation step có thể trả về ba trạng thái nghiệp vụ khác nhau:

| Kết quả | Điều kiện | Hành động |
|---|---|---|
| **PASS** | Count/key/sum phù hợp hợp đồng; không có sai lệch không cho phép | Cho phép publish/đánh dấu batch sẵn sàng. |
| **PASS_WITH_REJECTS** | Reject/skip nằm trong chính sách cho phép, tất cả trường hợp đã được giải thích và audit | Có thể publish nếu nghiệp vụ cho phép, hiển thị reject report. |
| **FAIL** | Thiếu/thừa ID, sai sum, vượt giới hạn reject, dữ liệu chưa đủ hoặc snapshot không tương thích | Dừng publish, báo lỗi, giữ kết quả staging để điều tra. |

Đây là tên trạng thái **do ứng dụng tự định nghĩa**, không phải `BatchStatus` mặc định của Spring Batch. Có thể ánh xạ chúng qua `ExitStatus` và điều khiển flow, nhưng cần đảm bảo **không đánh dấu job thành công** khi dữ liệu chưa đạt tiêu chuẩn được công bố.

### Khi có dữ liệu lỗi được phép bỏ qua

Một hệ thống có thể cho phép tối đa 0,5% dòng lỗi, hoặc tối đa 10 bản ghi không hợp lệ. Nhưng chỉ điều kiện “tỷ lệ dưới ngưỡng” chưa đủ:

- Các record lỗi có được phân loại và lưu đúng không?
- Có loại giao dịch nào **không được phép skip** dù tổng tỷ lệ thấp không?
- Tổng tiền của các item được chấp nhận có khớp với output không?
- Có duplicate hoặc item bị thiếu nhưng chưa được ghi nhận là reject không?

Ngưỡng chất lượng phải là quy tắc nghiệp vụ được thống nhất, không được thêm tùy ý chỉ để giảm số lần job thất bại.

## 16. Logging và dashboard cho reconciliation

Một log tóm lược nên chứa định danh batch và các con số, không dump toàn bộ dữ liệu nguồn hoặc dữ liệu khách hàng:

~~~json
{
  "event": "batch.reconciliation.completed",
  "batchKey": "2026-11-15:warehouse-A:v1",
  "jobName": "importPaymentsJob",
  "jobExecutionId": 8103,
  "result": "PASS",
  "sourceDataLines": 7,
  "readRejected": 1,
  "filtered": 1,
  "processRejected": 1,
  "expectedOutputRows": 4,
  "actualOutputRows": 4,
  "expectedAmount": "200.00",
  "actualAmount": "200.00",
  "missingKeys": 0,
  "unexpectedKeys": 0
}
~~~

Đây là schema minh họa cho **structured logging**, không phải JSON được Spring Batch tạo mặc định. Trong hệ thống có dữ liệu nhạy cảm, ngay cả tổng tiền theo nhóm nhỏ cũng có thể phải giới hạn quyền xem; không đưa raw item, email, số tài khoản hoặc toàn bộ file vào log.

Với metrics, có thể theo dõi:

- Tổng số batch đối chiếu `PASS`/`FAIL` theo `jobName` và `sourceId` hữu hạn.
- Số record reject, filter, missing/unexpected và duplicate theo kỳ.
- Số batch có chênh lệch amount khác 0 theo currency.
- Thời gian từ lúc nhận source đến lúc reconciliation hoàn tất.
- Tuổi của batch `FAILED` chưa được sửa.

Không gắn mọi `eventId`, `jobExecutionId` hoặc `correlationId` duy nhất vào metric tag thường xuyên: cardinality có thể tăng rất lớn. Giữ ID chi tiết trong log/audit/tracing; dùng metric cho các chỉ tiêu tổng hợp.

### Báo cáo đối chiếu nên lưu gì?

Một bản báo cáo bền vững có thể gồm:

~~~text
batchKey
sourceVersion / fileChecksum
jobInstanceId / jobExecutionId
sourceDataLines / parsedItems / rejectedItems / filteredItems
expectedOutputCount / actualOutputCount
expectedTotalsByCurrency / actualTotalsByCurrency
missingKeyCount / unexpectedKeyCount / duplicateKeyCount
result / errorCode / completedAt
~~~

Với yêu cầu audit, báo cáo còn có thể liên kết tới danh sách ID thiếu/thừa được lưu trong khu vực có kiểm soát quyền truy cập. Metadata được chốt theo một kỳ/phiên bản và thời điểm đối chiếu sẽ hữu ích khi job được restart hoặc khi cần điều tra dữ liệu sau nhiều tuần.

## 17. Kiểm thử đối chiếu input–output

Một bộ test chất lượng nên dùng dữ liệu đủ nhỏ để có thể liệt kê từng sự kiện và lý do có/không có ở đích:

| Tình huống | Input | Kỳ vọng reconciliation |
|---|---|---|
| 1:1 hợp lệ | 3 dòng hợp lệ, 3 output | `PASS` với count và sum đúng. |
| Có read skip | Một dòng `amount=abc` | Dòng lỗi được giải thích ở read reject, output các dòng còn lại đúng. |
| Có filter | Một dòng `amount=0` | Filter count tăng; không tính vào expected output. |
| Có process skip | Một dòng amount âm | Reject theo policy, có dấu vết xử lý, output còn lại đúng. |
| Count bằng nhưng key sai | Output thiếu A và có E thừa | Key reconciliation **FAIL** dù count bằng. |
| Count bằng nhưng amount sai | Amount của một ID bị thay đổi | Value reconciliation **FAIL** dù count bằng. |
| Duplicate ID | Nguồn có A, B, B | Chính sách deduplicate được áp dụng; count distinct và duplicate count đúng. |
| Writer UPSERT bỏ duplicate | Writer nhận nhiều item cùng ID | Output physical rows và business key đúng; không suy từ `writeCount`. |
| Chunk cuối một item | 3 item, chunk size 2 | Đủ ba output, không bỏ chunk cuối. |
| Lỗi writer giữa chunk | Chunk ghi một phần rồi exception | Rollback như thiết kế; không đếm dữ liệu chưa commit như output cuối. |
| Restart sau chunk đã commit | JobExecution đầu FAILED, lần sau COMPLETED | Output cuối đủ và duy nhất theo batch key. |
| Many-to-one | Nhiều giao dịch → một daily summary | So sánh theo nhóm và sum, không ép số hàng bằng nhau. |
| Nhiều currency | VND và USD | Chênh lệch trong từng currency được phát hiện. |
| Input thay đổi giữa hai lần đếm | File v1 bị thay bằng v2 | Phát hiện mismatch source version/checksum, không công bố kết quả khó xác minh. |

Trong integration test, nên để job ghi vào database test có dữ liệu đầu vào cố định, sau đó query thực tế và assert `expectedOutputCount`, `expectedAmount` cùng tập khóa. Test chỉ assert `BatchStatus.COMPLETED` hoặc `writeCount == 3` chưa đủ chứng minh chất lượng đầu ra.

### Ví dụ kỳ vọng bằng Java

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.math.BigDecimal;
import java.util.Set;

// actualRows được query từ database test theo batchKey.
assertThat(actualRows).hasSize(4);

Set<String> actualIds = actualRows.stream()
    .map(PaymentRow::eventId)
    .collect(java.util.stream.Collectors.toSet());

assertThat(actualIds).containsExactlyInAnyOrder(
    "TX-001", "TX-002", "TX-006", "TX-007");

BigDecimal actualAmount = actualRows.stream()
    .map(PaymentRow::amount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

assertThat(actualAmount.compareTo(new BigDecimal("200.00")))
    .isZero();
~~~

`PaymentRow` và `actualRows` là những đối tượng do test tạo từ dữ liệu đích; ví dụ tập trung vào kỳ vọng. Cần thêm phép kiểm chứng không có duplicate nếu `Set` có thể làm mất thông tin trùng: kiểm tra `actualRows.size() == actualIds.size()` hoặc unique constraint/database query.

## 18. Những sai lầm thường gặp

**“Job COMPLETED tức dữ liệu đã đúng.”** COMPLETED có thể kèm filter/skip, còn writer có thể UPSERT, ghi file hoặc API ngoài với semantics riêng. Phải kiểm tra dữ liệu cuối theo hợp đồng.

**“Input count phải luôn bằng output count.”** Sai khi có filter, reject, deduplicate, gộp hoặc tách. Hãy xác định grain và các chuyển đổi trước khi so sánh.

**“readCount là số dòng file.”** Header, dòng trắng, lỗi parse và quy tắc đọc làm hai khái niệm khác nhau. Nếu muốn số dòng vật lý, phải có bước inventory với quy ước đếm rõ.

**“writeCount là số hàng đã commit.”** Không phải bảo đảm tổng quát, đặc biệt với UPSERT, writer tạo nhiều hàng/item hoặc side effect ngoài transaction. Query đích sau commit là cần thiết.

**“Nếu count bằng nhau thì không thể mất dữ liệu.”** Có thể thiếu ID A và thừa ID E. Key reconciliation phát hiện lỗi mà count đơn lẻ không thấy.

**“Nếu sum bằng nhau thì từng bản ghi đúng.”** Hai amount có thể sai theo hướng triệt tiêu nhau. So sánh theo key hoặc từng nhóm quan trọng.

**“Cộng tất cả writeCount của các JobExecution là ra số output.”** Restart/retry, replay, chunk rollback và UPSERT làm kết quả cộng không đồng nhất với số record duy nhất bền vững.

**“Có thể đối chiếu input live với output cuối.”** Nguồn có thể thay đổi trong lúc batch chạy. Cần cùng snapshot, cutoff hoặc version để tránh so sánh hai tập dữ liệu khác nhau.

**“Mọi sai lệch dưới một tỷ lệ nhỏ đều được bỏ qua.”** Với tiền tệ hoặc giao dịch bắt buộc, chỉ một record thiếu cũng có thể nghiêm trọng. Ngưỡng phải được xác định theo nghiệp vụ.

**“Đối chiếu từ chính bảng output là đủ độc lập.”** Nếu expected được tính bằng cách đọc lại output mà không kiểm tra nguồn, dữ liệu thiếu có thể bị hợp thức hóa. Phải có bằng chứng nguồn hoặc accepted staging tương ứng.

**“Dữ liệu đúng ở DB là job đã xong.”** Nếu output còn cần được công bố ra file, message broker hoặc hệ khác, phải xác định và kiểm chứng trạng thái từng đích. Database staging đúng chưa đồng nghĩa người tiêu thụ nhận đúng.

## 19. Quy trình áp dụng trong một job thực tế

1. **Định nghĩa hợp đồng dữ liệu.** Chốt grain, business key, kỳ xử lý, currency, quy tắc filter/skip/dedup/transform và tiêu chí `PASS`.
2. **Chốt nguồn.** Tạo source manifest/snapshot hoặc watermark, có count và checksum theo quy tắc rõ ràng.
3. **Theo dõi từng hướng xử lý.** Dùng `StepExecution` counters và audit/quarantine phù hợp để phân loại read reject, process reject, filter, duplicate và output accepted.
4. **Ghi dữ liệu đích có khả năng replay an toàn.** Chọn unique business key, transaction chunk, idempotent writer hoặc cơ chế tương ứng.
5. **Query output đã commit.** Đối chiếu count, distinct keys, sum và dữ liệu theo từng nhóm quan trọng.
6. **Phát hiện missing/extra/mismatched keys.** Với dữ liệu quan trọng, không dừng lại ở tổng số hoặc tổng tiền.
7. **Tách reconciliation step khỏi load step.** Chỉ publish đầu ra khi đạt điều kiện chất lượng, hoặc công bố rõ trạng thái có reject đã được phép.
8. **Hỗ trợ retry/restart.** Giữ batch key/source version ổn định, xem metadata execution như lịch sử attempt và đối chiếu lại dữ liệu bền vững cuối cùng.
9. **Lưu kết quả có thể truy vết.** Ghi summary count/sum, chênh lệch, execution IDs, kết quả và thời điểm đối chiếu mà không lộ dữ liệu nhạy cảm.
10. **Kiểm thử cả trường hợp sai lệch.** Gây thiếu ID, thừa ID, amount sai, duplicate, rollback, restart và input đổi phiên bản để đảm bảo reconciliation thật sự phát hiện vấn đề.

## Kết luận

**Đối chiếu tổng input và output** trong Spring Batch là việc chứng minh rằng toàn bộ dữ liệu nguồn đã được **giải thích đúng đường đi** và kết quả đích **khớp với hợp đồng nghiệp vụ**. `readCount`, `writeCount`, skip/filter counters và trạng thái `COMPLETED` là thông tin vận hành hữu ích, nhưng chưa thay thế việc đếm dữ liệu đã commit và kiểm tra key, sum, snapshot hoặc phiên bản.

Với pipeline 1:1 có filter/skip, nên giải thích đầy đủ phương trình **nguồn = được chấp nhận + đã lọc + đã từ chối**, rồi xác minh **đầu ra thực tế = tập được chấp nhận** theo số lượng, giá trị và định danh. Với pipeline gộp/tách, deduplication hoặc nhiều đích, điều chỉnh phép đối chiếu theo grain và semantics tương ứng. Khi reconciliation trở thành một bước chính thức trước publish, chất lượng dữ liệu được kiểm soát bằng bằng chứng có thể kiểm chứng ngay cả khi job retry, restart hoặc chạy phân tán.
