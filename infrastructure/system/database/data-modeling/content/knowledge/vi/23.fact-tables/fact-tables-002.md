# Bảng dữ kiện giao dịch, ảnh chụp định kỳ và ảnh chụp tích lũy

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ba kiểu **fact table** thường gặp trong mô hình phân tích: **transaction fact**, **periodic snapshot fact** và **accumulating snapshot fact**.
- Viết đúng **grain** — một hàng đại diện cho điều gì — trước khi chọn cột, khóa, measure và dimension.
- Chọn kiểu bảng phù hợp với câu hỏi về **sự kiện đã xảy ra**, **trạng thái tại mốc thời gian** hoặc **tiến độ của một quy trình nhiều bước**.
- Phân biệt measure **cộng được**, **cộng được theo một số chiều** (*semi-additive*) và **không cộng được**; tránh tính tổng tồn kho qua nhiều ngày hay đếm lặp quy trình.
- Thiết kế khóa nghiệp vụ, dấu thời gian, trường hợp chưa hoàn tất, cơ chế cập nhật, xử lý dữ liệu đến muộn và quy tắc đối soát cho mỗi kiểu fact.
- Đọc và triển khai các ví dụ PostgreSQL về giao dịch kho, tồn kho cuối ngày và tiến độ giao hàng; viết truy vấn KPI không nhầm grain.
- Đánh giá cách triển khai trên warehouse quan hệ/lưu trữ cột, document, đồ thị và pipeline phân tích, đồng thời giữ nguồn giao dịch có thẩm quyền riêng biệt.

Trong module **DATABASE_DATA_MODELING**, hệ thống cần chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng và kiểm chứng được. Ở đường ghi, giao dịch nhập/xuất kho phải giữ đúng số lượng. Ở đường phân tích, người quản lý có thể hỏi **"hôm qua có bao nhiêu lần xuất kho?"**, **"cuối mỗi ngày còn bao nhiêu hàng?"** hoặc **"mỗi kiện mất bao lâu từ lúc tiếp nhận đến khi giao thành công?"**. Ba câu hỏi có trục thời gian, phép đếm và cách cập nhật khác nhau. Chúng là lý do cần phân biệt ba loại **bảng dữ kiện** trong chương này, thay vì ép mọi phép đo vào một bảng chứa cột status và timestamp.

## 1. Bắt đầu từ grain và câu hỏi được đo

**Fact table** lưu các phép đo, dấu mốc hoặc sự kiện có thể phân tích trong một ngữ cảnh xác định. Các trường liên kết tới **dimension** giúp phân nhóm theo ngày, sản phẩm, kho, kênh, nhân viên hoặc trạng thái.

**Grain** là phát biểu chính xác về **một hàng** trong bảng. Ví dụ:

- "Một hàng là **một lần biến động tồn kho vật lý đã ghi nhận** của một sản phẩm tại một kho".
- "Một hàng là **trạng thái tồn kho của một sản phẩm tại một kho vào cuối một ngày kinh doanh**".
- "Một hàng là **toàn bộ tiến độ của một lần xử lý giao hàng (fulfillment attempt)** từ khi mở đến khi kết thúc".

Đó là ba grain khác nhau, cho dù cả ba cùng có productId, warehouseId và timestamp. Phải chọn grain **trước** khi thiết kế bảng hay viết SELECT.

| Câu hỏi của doanh nghiệp | Một hàng phù hợp là gì? | Kiểu fact |
| --- | --- | --- |
| Có bao nhiêu lượt nhập, xuất và điều chỉnh trong ngày? | Một sự kiện biến động kho | **Giao dịch** |
| Tổng số đơn vị hàng đã xuất trong tháng? | Một biến động xuất kho, số lượng có dấu | **Giao dịch** |
| Cuối ngày 31/10 kho A còn bao nhiêu sản phẩm P? | Một trạng thái sản phẩm–kho–ngày | **Ảnh chụp định kỳ** |
| Tồn kho cuối mỗi tuần thay đổi thế nào? | Một snapshot ở mỗi mốc tuần, hoặc snapshot ngày chọn ngày cuối tuần | **Ảnh chụp định kỳ** |
| Bao nhiêu kiện đang chờ đóng gói, đã bàn giao? | Một tiến trình giao hàng ở trạng thái hiện hành | **Ảnh chụp tích lũy** |
| Thời gian trung bình từ nhận yêu cầu đến giao thành công? | Một tiến trình, nhiều mốc thời gian | **Ảnh chụp tích lũy** |
| Bao nhiêu lần một kiện bị giao thất bại rồi thử lại? | Một lần thử/giao dịch trạng thái cụ thể | **Giao dịch** hoặc bảng sự kiện riêng |

Không có quy tắc "mỗi miền chỉ được dùng một kiểu fact". Một warehouse thường có **nhiều fact với các grain bổ sung cho nhau**, mỗi fact phục vụ một lớp câu hỏi.

## 2. Nhìn tổng quát ba cách ghi nhận dữ kiện

~~~mermaid
flowchart TB
    O["Nguồn OLTP: kho và giao hàng"]
    O --> E["Các sự kiện đã commit<br/>nhập / xuất / điều chỉnh"]
    O --> S["Trạng thái tại các mốc chốt<br/>tồn cuối ngày"]
    O --> P["Vòng đời một lần giao hàng<br/>tiếp nhận → đóng gói → bàn giao → giao"]
    E --> F1["Transaction fact<br/>nhiều dòng theo sự kiện"]
    S --> F2["Periodic snapshot fact<br/>một dòng mỗi kỳ"]
    P --> F3["Accumulating snapshot fact<br/>một dòng mỗi tiến trình"]
~~~

| Khía cạnh | Transaction fact | Periodic snapshot fact | Accumulating snapshot fact |
| --- | --- | --- | --- |
| **Grain** | Một sự kiện/giao dịch xảy ra | Một đối tượng tại một thời điểm/kỳ định trước | Một lần thực hiện quy trình có các mốc |
| **Nhịp phát sinh hàng** | Khi có sự kiện | Theo lịch chốt kỳ | Khi quy trình bắt đầu |
| **Cập nhật sau khi tạo** | Thường append; sửa sai bằng bản điều chỉnh hoặc upsert có quy tắc | Có thể restate kỳ nếu dữ liệu đến muộn | **Thường cập nhật cùng một hàng** khi đạt mốc |
| **Dấu thời gian** | Thời gian xảy ra sự kiện | Ngày/mốc snapshot | Nhiều ngày giờ của các bước |
| **Measure chính** | Số lượng/phát sinh, tiền giao dịch, số lượt | Số dư, hàng tồn, số khách hoạt động tại mốc | Độ trễ từng bước, thời gian chu kỳ, trạng thái kết quả |
| **Đếm hàng** | Đếm sự kiện | Đếm đối tượng–kỳ | Đếm lần thực hiện quy trình |
| **Có hàng khi không có hoạt động?** | Thường không | Có thể vẫn có hàng cho kỳ không đổi | Có, nếu quy trình còn mở |
| **Điểm dễ tính sai** | Retry làm trùng, JOIN nhân bản | SUM số dư qua ngày, thiếu kỳ | Dùng trạng thái hiện tại để suy lịch sử, nhiều lần thử bị gộp |

**Điểm phân biệt quan trọng nhất không phải append hay update ở mức vật lý**, vì công nghệ và chính sách nạp dữ liệu có thể khác nhau. Điểm phân biệt là **ý nghĩa grain và câu hỏi được trả lời**.

## 3. Transaction fact: ghi nhận từng sự kiện đã xảy ra

**Transaction fact** lưu một hàng cho một sự kiện nghiệp vụ hoặc giao dịch đo lường, tại mức chi tiết đã xác định. Trong ví dụ kho:

> Một hàng = một lần thay đổi **on-hand quantity** của một sản phẩm tại một kho, sau khi nguồn kho có thẩm quyền ghi nhận thành công.

Mỗi hàng có thể chứa:

- **movementId**: định danh duy nhất và ổn định cho sự kiện phát sinh.
- **productKey, warehouseKey**: các khóa liên kết dimension.
- **occurredAt, businessDate**: thời gian phát sinh và ngày theo lịch nghiệp vụ.
- **movementType**: RECEIPT, DISPATCH, RETURN, ADJUSTMENT...
- **quantityDelta**: số lượng có dấu; nhập dương, xuất âm.
- **sourceVersion/sourceReference**: thông tin đối soát nếu nguồn có.

### Ví dụ số liệu

Sản phẩm P ở kho A có **10 chiếc đầu ngày**:

| movementId | occurredAt | movementType | quantityDelta | Tồn ngay sau sự kiện |
| --- | --- | --- | ---: | ---: |
| M-201 | 09:00 | RECEIPT | +6 | 16 |
| M-202 | 11:30 | DISPATCH | −4 | 12 |

Tổng biến động ngày đó:

\[
\Delta Q_{\text{ngày}} = (+6) + (-4) = +2.
\]

Nếu số đầu kỳ là 10 và không thiếu biến động nào, số cuối kỳ là \(10+2=12\). Nhưng **hai hàng transaction fact không tự cho biết tồn kho tại mọi thời điểm** nếu thiếu số đầu kỳ, thiếu một biến động, hoặc có giao dịch điều chỉnh được ghi trễ.

### Khả năng cộng measure

- **SUM(quantityDelta)** hợp lệ khi muốn tính biến động ròng trong một khoảng hoặc tập sản phẩm cùng đơn vị đo phù hợp.
- **SUM(CASE WHEN quantityDelta < 0 THEN -quantityDelta ELSE 0 END)** có thể tính tổng số lượng xuất, nếu quy ước mọi giá trị âm đều là xuất. Trong thực tế cần lọc **movementType** vì điều chỉnh giảm, hao hụt và xuất bán có thể khác nhau.
- **COUNT(*)** đếm số sự kiện kho, **không** đếm số sản phẩm, số đơn hay số kiện.
- Một sự kiện nhận lại do retry không tạo một biến động mới. Khi nạp lại phải giữ **cùng movementId** hoặc khóa định danh nguồn tương đương.

### Append-only và sửa sai

Transaction fact thường được thiết kế gần với **append-only**, nhưng "thường" không có nghĩa "không bao giờ được sửa". Có hai cách xử lý sai số liệu:

1. **Correction event:** ghi một bản điều chỉnh có dấu, tham chiếu sự kiện gốc, bảo toàn lịch sử phát sinh. Phù hợp khi nguồn nghiệp vụ có khái niệm bút toán điều chỉnh.
2. **Restatement:** thay thế/viết lại một dữ kiện sai và xây lại tổng hợp liên quan theo chính sách công bố. Phù hợp khi nguồn sửa lỗi dữ liệu đã nạp.

Không được vừa cập nhật dòng cũ vừa thêm bản điều chỉnh cho cùng sai sót rồi **tính cả hai**. Chính sách chính thức phải xác định phiên bản nào là nguồn có thẩm quyền.

## 4. Periodic snapshot fact: trạng thái tại một mốc định kỳ

**Periodic snapshot fact** ghi một hàng cho **một đối tượng tại một kỳ chốt**; kỳ có thể là ngày, tuần, tháng hoặc ca làm việc.

> Một hàng = tình trạng tồn kho sản phẩm P tại kho A **cuối ngày kinh doanh D**, theo cùng quy ước cutoff và múi giờ.

Các measure thường gặp:

- **onHandQty**: số lượng vật lý theo quy tắc kế toán kho.
- **reservedQty**: số lượng đã dành cho quyền giữ còn hiệu lực tại thời điểm chốt.
- **availableQty = onHandQty - reservedQty**: số còn có thể cấp theo chính sách mẫu.
- Có thể có inventoryValueVnd nếu đơn giá định giá và thời điểm định giá được xác định rõ.

Trong ví dụ trên, nếu cuối ngày số on-hand là 12, reserved là 3, thì available là 9:

| snapshotDate | product | warehouse | onHandQty | reservedQty | availableQty |
| --- | --- | --- | ---: | ---: | ---: |
| 2026-10-30 | P | A | 10 | 2 | 8 |
| 2026-10-31 | P | A | 12 | 3 | 9 |
| 2026-11-01 | P | A | 12 | 5 | 7 |

Một ngày **không có nhập/xuất**, transaction fact có thể có **0 hàng**; periodic snapshot vẫn có một hàng thể hiện tồn tại cuối ngày. Cần phân biệt "không phát sinh" với "không có dữ liệu do pipeline chưa chốt".

### Semi-additive: tại sao không SUM tồn qua ngày?

Giả sử báo cáo muốn biết **tồn cuối tháng 10** của P tại A. Kết quả là **12**, không phải \(10+12=22\). Phép cộng 10 và 12 thuộc **hai thời điểm** nên không đại diện cho số chiếc cùng tồn tại.

Measure onHandQty thường **semi-additive**:

- Có thể **cộng theo kho tại cùng một thời điểm**, nếu mọi kho được chốt theo cutoff tương thích và số lượng cùng đơn vị.
- Có thể **cộng theo sản phẩm đồng nhất tại cùng một thời điểm** khi nghiệp vụ cho phép.
- **Không cộng qua ngày** để lấy "tồn tháng"; phải chọn giá trị cuối kỳ, đầu kỳ hoặc tính trung bình ngày với định nghĩa rõ ràng.
- Cộng số lượng của các loại hàng đo bằng đơn vị khác nhau (chiếc, kg, hộp) có thể **vô nghĩa** ngay cả cùng ngày.

Tồn bình quân ngày của tháng khác tồn cuối tháng:

\[
\text{AverageDailyOnHand}
= \frac{\sum_{d\in D}\text{OnHandAtEndOfDay}(d)}{|D|},
\]

trong đó \(D\) là **các ngày đã có snapshot hợp lệ theo chính sách**. Nếu thiếu hai ngày do pipeline lỗi, không được tự ý chia cho 30 và ngầm coi ngày thiếu bằng 0. Hãy chọn quy tắc lấp kỳ, gắn nhãn thiếu hoặc chờ dữ liệu hoàn chỉnh.

### Dense hay sparse snapshot?

- **Dense:** tạo một hàng cho mọi đối tượng/kỳ nằm trong phạm vi, kể cả khi giá trị không đổi hoặc bằng 0. Dễ báo cáo nhưng tốn lưu trữ.
- **Sparse:** chỉ tạo hàng khi đối tượng còn hoạt động hoặc khi giá trị khác 0. Tiết kiệm nhưng truy vấn phải biết quy tắc về hàng thiếu.

Nếu một ngày không có snapshot, **NULL/không có hàng không mặc nhiên bằng 0**. Có thể là sản phẩm chưa có, kho ngừng hoạt động, phạm vi sparse hợp lệ hoặc thất bại nạp dữ liệu. Quy tắc khuyết dữ liệu phải công bố trước khi dùng COALESCE.

## 5. Accumulating snapshot fact: một hàng đi qua nhiều mốc của quy trình

**Accumulating snapshot fact** phù hợp quy trình có **điểm bắt đầu, các mốc trung gian và điểm hoàn tất tương đối xác định**, chẳng hạn:

- yêu cầu mua sắm: submitted → approved → ordered → received;
- xét duyệt hồ sơ: applied → reviewed → accepted/rejected;
- giao hàng: requested → picked → packed → handed over → delivered;
- xử lý khoản vay: application → underwriting → approval → disbursement.

Trong ví dụ giao hàng:

> Một hàng = **một lần thực hiện giao hàng có fulfillmentId ổn định**, từ lúc tiếp nhận đến khi kết thúc. Hàng ấy được cập nhật khi tiến trình đạt các mốc mới.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PICKED
    PICKED --> PACKED
    PACKED --> HANDED_OVER
    HANDED_OVER --> DELIVERED
    REQUESTED --> CANCELLED
    PICKED --> CANCELLED
    PACKED --> CANCELLED
    DELIVERED --> [*]
    CANCELLED --> [*]
~~~

Đây là quy trình minh họa; thực tế có thể có giao nhiều lần, giao một phần, hoàn hàng hoặc mở lại. Nếu quy trình có nhánh và vòng lặp, cần xác định grain thận trọng.

| fulfillmentId | requestedAt | pickedAt | packedAt | handedOverAt | deliveredAt | currentStatus |
| --- | --- | --- | --- | --- | --- | --- |
| F-101 | 10/10 08:00 | 10/10 08:12 | 10/10 08:30 | 11/10 09:00 | 11/10 16:00 | DELIVERED |
| F-102 | 10/10 09:00 | 10/10 09:20 | NULL | NULL | NULL | PICKED |
| F-103 | 10/10 10:00 | NULL | NULL | NULL | NULL | CANCELLED |

Mỗi hàng trên là **một tiến trình**, không phải một mốc. Hàng F-101 được bổ sung các timestamp khi sự kiện nghiệp vụ xảy ra. F-102 chưa hoàn tất: **NULL nghĩa là chưa ghi nhận mốc**, không được hiểu thành khoảng thời gian 0.

### Đo thời gian chu kỳ

Với F-101:

- Thời gian tiếp nhận → nhặt hàng: 12 phút.
- Nhặt hàng → đóng gói: 18 phút.
- Bàn giao → giao thành công: 7 giờ.
- Tổng tiếp nhận → giao thành công: 32 giờ.

Các phép trừ thời gian phải dùng cùng chuẩn timestamp và múi giờ rõ ràng. Một mốc ghi nhận trễ nhưng nghiệp vụ xảy ra sớm vẫn phải dùng **event time** đúng, nếu được xác thực, chứ không lấy giờ pipeline nhận thông điệp.

### Vì sao cần nhiều cột ngày?

Một fact tích lũy thường có nhiều **role-playing date/time dimensions**: requestedDate, pickedDate, packedDate, handedOverDate, deliveredDate. Chúng cùng tham chiếu các ngữ nghĩa khác nhau của thời gian. Chỉ một cột createdAt không đủ để đo thời gian chờ qua các bước.

Các chỉ số điển hình:

- Số tiến trình đã mở/đã hoàn tất hiện tại.
- Tỷ lệ giao đúng hạn trong những tiến trình đã đến hạn.
- Phân phối thời gian từ tiếp nhận đến đóng gói hoặc đến giao.
- Số tiến trình đang kẹt ở mốc nhặt hàng và tuổi xử lý.

### Khi mô hình tích lũy không phù hợp

Nếu một kiện có **nhiều lần thử giao**, cột deliveredAt duy nhất không diễn đạt số lần giao thất bại hoặc thời gian giữa các lần thử. Có thể:

1. Giữ **một accumulating snapshot ở grain một fulfillment**, chứa mốc đầu/đích cuối, kết hợp transaction fact riêng ghi mỗi delivery attempt.
2. Chọn **grain một delivery attempt** cho accumulating snapshot nếu từng lần thử có vòng đời độc lập và cần KPI riêng.
3. Mô hình hóa nhiều sự kiện chi tiết, dựng một projection tiến độ cho màn hình hiện tại.

Không tạo các cột attempt1At, attempt2At, attempt3At không giới hạn nếu số lần thử không có trần rõ ràng. Một hàng "một Order" cũng có thể sai nếu một Order được chia thành nhiều kiện giao khác nhau. **Grain phải bám đúng đơn vị quy trình có ID và điểm kết thúc của nó.**

## 6. So sánh khả năng phân tích từ ba fact

Một bảng giao dịch có thể cung cấp lịch sử sự kiện chi tiết, nhưng việc tính một snapshot cần số đầu kỳ, đầy đủ biến động, xử lý correction và chính sách cutoff. Một periodic snapshot trả lời nhanh số cuối ngày, nhưng **không cho biết mọi giao dịch** đã tạo ra số đó. Một accumulating snapshot đo thời gian quy trình thuận tiện, nhưng **mất chi tiết vòng lặp** nếu không lưu thêm transaction event.

| KPI | Fact nguồn ưu tiên | Công thức/điểm chú ý |
| --- | --- | --- |
| Số lần xuất kho trong ngày | Transaction stock movement | COUNT(*) với movementType = DISPATCH |
| Số lượng hàng xuất trong tháng | Transaction stock movement | -SUM(quantityDelta) cho các dòng DISPATCH |
| On-hand cuối tháng | Periodic inventory snapshot | Chọn snapshot cuối kỳ đã hoàn chỉnh |
| Tồn trung bình mỗi ngày | Periodic inventory snapshot | AVG(onHandQty) trên tập ngày đủ dữ liệu |
| Tăng giảm tồn theo kỳ | Snapshot đầu/cuối + transaction đối soát | End - Start; so với SUM(delta) |
| Số fulfillment đang PACKED hiện tại | Accumulating fulfillment | COUNT(*) WHERE currentStatus = 'PACKED' |
| Thời gian trung bình giao thành công | Accumulating fulfillment | AVG(deliveredAt - requestedAt) với tập đã giao |
| Số lần giao thất bại | Transaction fact delivery_attempt | Một hàng cho mỗi lần thử/gặp lỗi |
| Số fulfillment ở PACKED lúc 17:00 ngày cũ | Event history hoặc periodic process snapshot | Accumulating **chỉ có trạng thái hiện tại** thường không đủ |

Một rủi ro thường thấy: dùng accumulating snapshot hiện tại để dựng biểu đồ **số đơn đang chờ ở mỗi trạng thái trong quá khứ**. Khi F-101 đã giao, currentStatus không còn cho biết nó đã ở PACKED lúc 10:00 hôm trước. Muốn lịch sử "as of" phải giữ các event chuyển trạng thái, ảnh chụp định kỳ của backlog hoặc dữ liệu lịch sử có hiệu lực theo thời gian.

## 7. Liên kết với dimension: cùng sự kiện, ba grain khác nhau

Trong mô hình sao, các fact có thể dùng các dimension chuẩn hóa về mặt **ý nghĩa phân tích** (*conformed dimensions*) như sản phẩm, kho và ngày, nhưng **không gộp grain** của ba fact.

~~~mermaid
flowchart LR
    DP["dim_product<br/>sản phẩm, danh mục"]
    DW["dim_warehouse<br/>kho, vùng"]
    DD["dim_date<br/>ngày kinh doanh"]
    FC["fact_stock_movement<br/>một biến động"]
    FP["fact_daily_inventory<br/>một sản phẩm-kho-ngày"]
    FA["fact_fulfillment_progress<br/>một lần fulfillment"]

    DP --> FC
    DW --> FC
    DD --> FC
    DP --> FP
    DW --> FP
    DD --> FP
    DW --> FA
    DD --> FA
~~~

Những dimension tưởng như cùng tên cũng cần xác định **bối cảnh thời gian**:

- Product đổi danh mục hôm nay: báo cáo lịch sử theo danh mục **lúc xuất kho** hay theo danh mục **hiện tại**?
- Warehouse chuyển vùng quản lý: báo cáo theo vùng tại thời điểm giao dịch hay cấu trúc vùng hôm nay?
- Ngày snapshot theo **giờ Việt Nam**, giờ kho địa phương hay UTC? Một ngày nghiệp vụ không nhất thiết trùng ngày UTC.

Nếu cần thuộc tính tại thời điểm giao dịch, fact giữ khóa đến phiên bản dimension đúng hiệu lực (*SCD Type 2*) hoặc giữ snapshot cần thiết. Nếu chỉ muốn thuộc tính hiện tại, có thể dùng một mapping khác. Tránh một JOIN bằng business ID không xét lịch sử khiến một fact khớp nhiều phiên bản dimension và bị nhân bản.

**Drill-across:** có thể tổng hợp các fact riêng về cùng chiều/ngày rồi ghép **kết quả đã tổng hợp**. Không JOIN trực tiếp movement rows với daily snapshot rows theo productId và warehouseId rồi SUM một measure vì một snapshot có thể bị lặp theo số movement.

## 8. Thiết kế lược đồ PostgreSQL minh họa

Ví dụ sau dùng PostgreSQL để mô tả khóa, grain và constraint. Một data warehouse chuyên phân tích có thể dùng lưu trữ cột và cơ chế khóa/partition khác; DDL này không phải cấu hình duy nhất hoặc bắt buộc cho mọi hệ quản trị.

### 8.1. Dimension dùng chung

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_product (
    tenant_id UUID NOT NULL,
    product_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_product_id UUID NOT NULL,
    product_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, product_key),
    UNIQUE (tenant_id, source_product_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE mart.dim_warehouse (
    tenant_id UUID NOT NULL,
    warehouse_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_warehouse_id UUID NOT NULL,
    warehouse_name TEXT NOT NULL,
    timezone_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, warehouse_key),
    UNIQUE (tenant_id, source_warehouse_id)
);
~~~

Dimension có product_key thay thế để ghi nhận phiên bản mô tả khác nhau. Ràng buộc UNIQUE trên (tenant_id, source_product_id, valid_from) **chưa ngăn hai khoảng SCD chồng nhau**; pipeline cần kiểm tra hoặc dùng range constraint thích hợp. warehouse timezone_name phải lấy từ danh mục múi giờ hợp lệ và có chính sách khi kho đổi lịch chốt.

### 8.2. Transaction fact: một biến động tồn kho

~~~sql
CREATE TABLE mart.fact_stock_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    product_key BIGINT NOT NULL,
    warehouse_key BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    movement_type VARCHAR(16) NOT NULL
        CHECK (movement_type IN (
            'RECEIPT', 'DISPATCH', 'RETURN', 'ADJUSTMENT'
        )),
    quantity_delta BIGINT NOT NULL CHECK (quantity_delta <> 0),
    source_reference TEXT,
    load_batch_id UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product(tenant_id, product_key),
    FOREIGN KEY (tenant_id, warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CONSTRAINT valid_stock_movement_sign CHECK (
        movement_type = 'ADJUSTMENT'
        OR (movement_type IN ('RECEIPT', 'RETURN') AND quantity_delta > 0)
        OR (movement_type = 'DISPATCH' AND quantity_delta < 0)
    )
);

CREATE INDEX stock_movement_by_date
    ON mart.fact_stock_movement
        (tenant_id, business_date, warehouse_key, product_key);
~~~

Một movementId chỉ xuất hiện một lần trong cùng tenant, nên chạy lại một batch không được tạo thêm một movement khác cho cùng sự kiện. Nếu nguồn có một giao dịch bao gồm nhiều sản phẩm/dòng, cần định danh **dòng biến động** (movementLineId) làm khóa grain, không lấy transaction header ID rồi vô tình ép nhiều dòng thành một.

### 8.3. Periodic snapshot fact: tồn kho cuối ngày

~~~sql
CREATE TABLE mart.fact_daily_inventory (
    tenant_id UUID NOT NULL,
    snapshot_date DATE NOT NULL,
    product_key BIGINT NOT NULL,
    warehouse_key BIGINT NOT NULL,
    on_hand_qty BIGINT NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty BIGINT NOT NULL CHECK (reserved_qty >= 0),
    available_qty BIGINT NOT NULL CHECK (available_qty >= 0),
    snapshot_batch_id UUID NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        tenant_id, snapshot_date, product_key, warehouse_key
    ),
    FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product(tenant_id, product_key),
    FOREIGN KEY (tenant_id, warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CHECK (reserved_qty <= on_hand_qty),
    CHECK (available_qty = on_hand_qty - reserved_qty)
);

CREATE INDEX daily_inventory_latest_by_product
    ON mart.fact_daily_inventory
        (tenant_id, product_key, warehouse_key, snapshot_date DESC);
~~~

Hai CHECK ở cuối phản ánh **chính sách ví dụ: không cho giữ vượt tồn vật lý và available = onHand - reserved**. Hệ thống thực tế có thể dùng tồn khả dụng tính thêm hàng hỏng, tồn cách ly, tồn về, hạn mức bán âm...; khi đó cần đổi measure và công thức, không mặc định CHECK này luôn đúng.

Khóa chính theo (tenant, ngày, sản phẩm, kho) định nghĩa đúng grain. Để tính tồn **as-of** khi một product_key thay đổi do dimension SCD2, pipeline phải gán đúng phiên bản theo thời điểm snapshot hoặc cung cấp mapping về source_product_id. Không được vô tình đếm cùng tồn nhiều lần ở hai phiên bản dimension trong một ngày.

### 8.4. Accumulating snapshot fact: tiến độ giao hàng

~~~sql
CREATE TABLE mart.fact_fulfillment_progress (
    tenant_id UUID NOT NULL,
    fulfillment_id UUID NOT NULL,
    order_id UUID NOT NULL,
    origin_warehouse_key BIGINT NOT NULL,
    current_status VARCHAR(16) NOT NULL
        CHECK (current_status IN (
            'REQUESTED', 'PICKED', 'PACKED',
            'HANDED_OVER', 'DELIVERED', 'CANCELLED'
        )),
    requested_at TIMESTAMPTZ NOT NULL,
    picked_at TIMESTAMPTZ,
    packed_at TIMESTAMPTZ,
    handed_over_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, fulfillment_id),
    FOREIGN KEY (tenant_id, origin_warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CHECK (delivered_at IS NULL OR delivered_at >= requested_at),
    CHECK (current_status <> 'DELIVERED' OR delivered_at IS NOT NULL),
    CHECK (current_status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE INDEX fulfillment_open_by_warehouse
    ON mart.fact_fulfillment_progress
        (tenant_id, origin_warehouse_key, current_status, requested_at)
    WHERE current_status NOT IN ('DELIVERED', 'CANCELLED');
~~~

Một order_id có thể liên kết **nhiều fulfillmentId** nếu chia kiện hay xử lý lại; không đặt UNIQUE(order_id) chỉ vì muốn một hàng tiện truy vấn. source_version giúp ngăn dữ liệu cũ ghi đè dữ liệu mới, nhưng **version không tự phục hồi các mốc trung gian nếu thông điệp bị thiếu**.

DDL kiểm tra vài điều kiện tối thiểu, chưa chứng minh mọi timestamp có đúng thứ tự thực tế hoặc mọi bước hợp lệ. Khi có giao lại, đảo tuyến hoặc correction, phải chọn một quy trình trạng thái và chính sách chất lượng dữ liệu cụ thể; một CHECK cứng "mọi mốc luôn tăng" có thể loại sai những sự kiện hợp lệ được sửa thời gian.

## 9. Truy vấn đúng kiểu fact, đúng ý nghĩa KPI

### 9.1. Tổng xuất kho trong khoảng ngày: đọc transaction fact

~~~sql
SELECT m.business_date,
       m.warehouse_key,
       m.product_key,
       COUNT(*) AS dispatch_events,
       -SUM(m.quantity_delta) AS dispatched_units
FROM mart.fact_stock_movement AS m
WHERE m.tenant_id = :tenant_id
  AND m.business_date >= DATE '2026-10-01'
  AND m.business_date <  DATE '2026-11-01'
  AND m.movement_type = 'DISPATCH'
GROUP BY m.business_date, m.warehouse_key, m.product_key
ORDER BY m.business_date, m.warehouse_key, m.product_key;
~~~

Không SUM tất cả quantity_delta âm và gọi là "số lượng bán": một ADJUSTMENT giảm hoặc hàng hỏng không phải DISPATCH. Đây là một KPI của **biến động xuất kho**, không tự đồng nhất với số đơn đã bán hay doanh thu.

### 9.2. Tồn cuối kỳ: chọn đúng một snapshot cho mỗi tổ hợp

~~~sql
SELECT s.warehouse_key,
       s.product_key,
       s.on_hand_qty,
       s.reserved_qty,
       s.available_qty
FROM mart.fact_daily_inventory AS s
WHERE s.tenant_id = :tenant_id
  AND s.snapshot_date = DATE '2026-10-31';
~~~

Khi cần ngày cuối **có dữ liệu hợp lệ** trước một cutoff nhưng không chắc đúng ngày 31/10 có snapshot, có thể tìm bản gần nhất **đồng thời công bố rõ ngày thực tế được dùng**:

~~~sql
SELECT DISTINCT ON (s.warehouse_key, s.product_key)
       s.warehouse_key,
       s.product_key,
       s.snapshot_date AS actual_snapshot_date,
       s.on_hand_qty
FROM mart.fact_daily_inventory AS s
WHERE s.tenant_id = :tenant_id
  AND s.snapshot_date <= DATE '2026-10-31'
ORDER BY
    s.warehouse_key, s.product_key, s.snapshot_date DESC;
~~~

Điều kiện **"ngày gần nhất" không đồng nghĩa "cuối tháng đúng nghĩa"**. Nếu snapshot ngày 31/10 bị thiếu, cần cờ dữ liệu chưa hoàn chỉnh hoặc chính sách sử dụng ngày cũ được phê duyệt; không âm thầm báo số của 29/10 là số ngày 31/10.

### 9.3. Thời gian xử lý của những fulfillment đã giao

~~~sql
SELECT
    COUNT(*) AS delivered_fulfillments,
    AVG(
        EXTRACT(EPOCH FROM (delivered_at - requested_at)) / 3600.0
    ) AS avg_lead_time_hours,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (delivered_at - requested_at)) / 3600.0
    ) AS p50_lead_time_hours
FROM mart.fact_fulfillment_progress
WHERE tenant_id = :tenant_id
  AND current_status = 'DELIVERED'
  AND delivered_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND delivered_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

Kết quả đo **thời gian tiếp nhận đến giao của các fulfillment kết thúc thành công trong tháng 10**, không phải thời gian dự kiến của tất cả fulfillment được tạo trong tháng 10. Đó là hai tập mẫu khác nhau. Nếu chỉ tính các case đã hoàn tất, có thể phát sinh **survivorship/selection bias** vì các case quá chậm vẫn còn mở và chưa được tính.

Để phân tích quá hạn của case đang mở, dùng điều kiện cutoff tại thời điểm báo cáo với requested_at và current_status, hoặc giữ periodic snapshot của backlog. Không dùng 0 giờ cho delivered_at NULL.

### 9.4. Đối soát hai loại fact

Với dữ liệu biến động **đầy đủ**, cùng phạm vi kho/sản phẩm, và cùng cutoff:

\[
\text{OnHand}_{D}
=\text{OnHand}_{D-1}
+\sum_{\text{movement trong ngày }D}\text{quantityDelta}.
\]

Có thể truy vấn phát hiện chênh lệch:

~~~sql
WITH movements AS (
    SELECT tenant_id, product_key, warehouse_key,
           SUM(quantity_delta) AS delta_qty
    FROM mart.fact_stock_movement
    WHERE tenant_id = :tenant_id
      AND business_date = DATE '2026-10-31'
    GROUP BY tenant_id, product_key, warehouse_key
)
SELECT curr.product_key,
       curr.warehouse_key,
       prev.on_hand_qty AS previous_on_hand,
       COALESCE(m.delta_qty, 0) AS movement_delta,
       curr.on_hand_qty AS current_on_hand,
       curr.on_hand_qty
         - prev.on_hand_qty
         - COALESCE(m.delta_qty, 0) AS unexplained_difference
FROM mart.fact_daily_inventory AS curr
JOIN mart.fact_daily_inventory AS prev
  ON prev.tenant_id = curr.tenant_id
 AND prev.product_key = curr.product_key
 AND prev.warehouse_key = curr.warehouse_key
 AND prev.snapshot_date = DATE '2026-10-30'
LEFT JOIN movements AS m
  ON m.tenant_id = curr.tenant_id
 AND m.product_key = curr.product_key
 AND m.warehouse_key = curr.warehouse_key
WHERE curr.tenant_id = :tenant_id
  AND curr.snapshot_date = DATE '2026-10-31'
  AND curr.on_hand_qty
    <> prev.on_hand_qty + COALESCE(m.delta_qty, 0);
~~~

Truy vấn chỉ so sánh những tổ hợp có **cả hai snapshot**, không phát hiện ngày hoặc đối tượng bị thiếu hoàn toàn; cần kiểm tra độ đầy đủ song song. Nó cũng giả định hai snapshot và transaction fact được ánh xạ tới **cùng phiên bản product_key/warehouse_key**, và mọi biến động on-hand nằm trong fact. Nếu SCD2 đổi product_key qua hai ngày, phải đối chiếu bằng định danh nguồn chuẩn hoặc ánh xạ lịch sử trước khi dùng công thức.

Nếu có điều chỉnh backdated hay chênh lệch thời gian cutoff, sai khác không nhất thiết là lỗi nguồn giao dịch: cần đối chiếu chính sách thời gian và dữ liệu đã chốt.

## 10. Xử lý dữ liệu đến trễ và cập nhật accumulating snapshot

Ba kiểu fact có các chính sách cập nhật khác nhau.

### Transaction fact: idempotent ingestion

Nạp một sự kiện kho theo **movementId của nguồn**. Nếu retry cùng eventId, không nhân đôi sự kiện; nếu payload khác cho cùng ID, phải kiểm tra phiên bản/quy trình correction thay vì âm thầm bỏ qua:

~~~sql
-- Minh họa cho dữ liệu đã được ánh xạ đúng dimension.
INSERT INTO mart.fact_stock_movement (
    tenant_id, movement_id, product_key, warehouse_key,
    occurred_at, business_date, movement_type,
    quantity_delta, load_batch_id
) VALUES (
    :tenant_id, :movement_id, :product_key, :warehouse_key,
    :occurred_at, :business_date, :movement_type,
    :quantity_delta, :load_batch_id
)
ON CONFLICT (tenant_id, movement_id) DO NOTHING;

-- Với conflict, pipeline phải so sánh hash/field bản ghi đã có
-- hoặc áp dụng chính sách version/correction ở tầng nạp.
~~~

ON CONFLICT DO NOTHING chỉ là bảo vệ **không chèn trùng khóa**; nó không xác nhận hai payload có cùng ý nghĩa. Pipeline phải có cảnh báo khi nguồn gửi lại cùng ID nhưng dữ liệu khác, hoặc quy tắc cập nhật có thẩm quyền nếu nguồn cho phép correction.

### Periodic snapshot: chốt kỳ và restatement

Một snapshot ngày D được tạo sau cutoff theo dữ liệu đủ điều kiện của ngày D. Khi movement của D đến sau, có hai lựa chọn tùy hợp đồng báo cáo:

- **Restate** snapshot D và các snapshot kỳ sau bị ảnh hưởng, đồng thời cập nhật aggregate/report cache tương ứng. Gắn load_version hoặc snapshot_batch_id để truy vết.
- **Đóng băng** kỳ đã công bố và ghi điều chỉnh sang kỳ mở sau theo chuẩn nghiệp vụ, đồng thời cung cấp báo cáo chênh lệch nếu cần.

Không áp dụng cả hai mà không phân biệt, vì sẽ đếm điều chỉnh hai lần. Với báo cáo tồn kho **as-of historical**, việc thay đổi dữ liệu kỳ cũ phải có chính sách version và đối soát.

### Accumulating snapshot: cập nhật hàng cùng fulfillmentId

Tình huống: F-101 REQUESTED version 1, sau đó PICKED version 2, PACKED version 3, HANDED_OVER version 4, DELIVERED version 5. Nếu event version 5 tới trước version 3, một UPDATE đơn giản "chỉ xử lý version lớn hơn" có thể **bỏ mất packedAt** khi tới sự kiện version 3.

Một cách an toàn là **xây projection đầy đủ của tiến trình** từ nguồn/nhật ký sự kiện có thứ tự, sau đó UPSERT **toàn bộ trạng thái** với source_version mới hơn:

~~~sql
-- Input là bản trạng thái ĐẦY ĐỦ được tái dựng:
-- mọi mốc đã biết, kể cả mốc cũ, phải xuất hiện trong incoming snapshot.
INSERT INTO mart.fact_fulfillment_progress AS target (
    tenant_id, fulfillment_id, order_id, origin_warehouse_key,
    current_status, requested_at, picked_at, packed_at,
    handed_over_at, delivered_at, cancelled_at, source_version
) VALUES (
    :tenant_id, :fulfillment_id, :order_id, :origin_warehouse_key,
    :current_status, :requested_at, :picked_at, :packed_at,
    :handed_over_at, :delivered_at, :cancelled_at, :source_version
)
ON CONFLICT (tenant_id, fulfillment_id)
DO UPDATE SET
    current_status = EXCLUDED.current_status,
    requested_at = EXCLUDED.requested_at,
    picked_at = EXCLUDED.picked_at,
    packed_at = EXCLUDED.packed_at,
    handed_over_at = EXCLUDED.handed_over_at,
    delivered_at = EXCLUDED.delivered_at,
    cancelled_at = EXCLUDED.cancelled_at,
    source_version = EXCLUDED.source_version,
    refreshed_at = CURRENT_TIMESTAMP
WHERE target.source_version < EXCLUDED.source_version;
~~~

Đây **không phải** cách xử lý an toàn cho một event **chỉ chứa trường vừa thay đổi**: nếu EXCLUDED.packed_at là NULL vì event Delivered không mang packedAt, đoạn SQL sẽ xóa mất dấu mốc trước. Muốn dùng partial events, phải hợp nhất có ngữ nghĩa và xử lý correction, hoặc tích lũy/rebuild từ event history.

Nếu phát hiện thiếu version giữa chuỗi sự kiện, pipeline có thể chờ bổ sung, yêu cầu snapshot đầy đủ từ nguồn có thẩm quyền hoặc đánh dấu projection chưa hoàn chỉnh. Một version lớn không chứng minh mọi bước nghiệp vụ đã được quan sát.

### Tách thời gian nghiệp vụ và thời gian nạp

| Trường | Ý nghĩa | Tác động |
| --- | --- | --- |
| occurredAt / deliveredAt | Mốc nghiệp vụ được xác thực | Phân nhóm báo cáo, đo thời gian xử lý |
| businessDate / snapshotDate | Ngày theo lịch nghiệp vụ | Lọc ngày, cutoff, so sánh kỳ |
| recordedAt | Thời điểm nguồn ghi nhận | Đối soát sự kiện đến muộn |
| loadedAt / refreshedAt | Thời điểm warehouse nạp hoặc tái tính | Đo freshness và latency pipeline |
| sourceVersion | Thứ tự trạng thái từ nguồn, trong phạm vi ID | Ngăn bản cũ ghi đè bản mới |

Không đổi deliveredAt thành giờ ETL xử lý để che sự kiện đến muộn; như vậy KPI thời gian giao sẽ bị sai.

## 11. Ví dụ Java: bảo toàn định danh và ngày nghiệp vụ khi ETL

Ứng dụng Java có thể phát ra sự kiện sau khi transaction OLTP commit, hoặc pipeline Java có thể ánh xạ sự kiện vào bảng fact. Đoạn mã thuần Java 17 sau mô tả cách chuyển **thời điểm xảy ra** sang **ngày kinh doanh của kho**, không lấy thời điểm consumer nhận:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;
import java.util.UUID;

record StockMovementEvent(
        UUID eventId,
        UUID tenantId,
        UUID productId,
        UUID warehouseId,
        Instant occurredAt,
        long quantityDelta) {
    StockMovementEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(productId);
        Objects.requireNonNull(warehouseId);
        Objects.requireNonNull(occurredAt);
        if (quantityDelta == 0) {
            throw new IllegalArgumentException("No physical movement");
        }
    }
}

record MovementFactKey(UUID tenantId, UUID movementId) {}

record MovementProjection(
        MovementFactKey key,
        LocalDate businessDate,
        Instant occurredAt,
        long quantityDelta) {}

final class StockMovementFactMapper {
    static MovementProjection map(
            StockMovementEvent event, ZoneId warehouseZone) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(warehouseZone);
        return new MovementProjection(
            new MovementFactKey(event.tenantId(), event.eventId()),
            event.occurredAt().atZone(warehouseZone).toLocalDate(),
            event.occurredAt(),
            event.quantityDelta());
    }
}
~~~

Ghi chú:

- **eventId của nguồn** được dùng lại làm movementId trong fact, giúp retry không tạo khóa mới.
- ZoneId phải lấy theo **quy ước nghiệp vụ có thẩm quyền và hiệu lực lịch sử**; không hard-code múi giờ hiện tại của server.
- Nếu ngày kinh doanh kết thúc vào 04:00 thay vì 00:00, phải điều chỉnh hàm phân loại theo cutoff của kho; phép toLocalDate() trên chỉ hợp lệ với ngày đổi mốc lúc nửa đêm.
- Mapper không cấp quyền sửa tồn kho. Giao dịch giữ/chuyển hàng phải được xác nhận ở **nguồn OLTP có thẩm quyền**; fact chỉ phục vụ phân tích.

## 12. Chất lượng dữ liệu: cùng grain phải có hợp đồng nạp

Khi thiết kế từng fact, cần một **hợp đồng dữ liệu** về sự kiện/kỳ/tiến trình:

| Hạng mục | Transaction | Periodic snapshot | Accumulating snapshot |
| --- | --- | --- | --- |
| Khóa nguồn | movementId hoặc transactionLineId | tenant + ngày + product + warehouse | tenant + fulfillmentId |
| Tính duy nhất | Một sự kiện không đếm hai lần | Một snapshot cho mỗi tổ hợp/kỳ | Một hàng hiện tại cho mỗi quy trình |
| Điều kiện xuất hiện hàng | Sự kiện đã ghi nhận thành công | Kỳ đã chốt trong phạm vi | Quy trình đã bắt đầu |
| Cách xử lý NULL | Không có trường thiết yếu thì từ chối/quarantine | Hàng thiếu khác giá trị bằng 0 | Mốc chưa xảy ra là NULL |
| Cập nhật | Correction/restatement có quy tắc | Thay lại kỳ theo chính sách | UPSERT trạng thái tiến trình |
| Độ tươi | Offset/LSN hoặc event watermark | Snapshot completeness/cutoff | source_version, refreshedAt |
| Đối soát | Số lượng/số sự kiện theo nguồn | Số dư, số đối tượng, quy tắc cutoff | Số process và các mốc, lịch sử transition |

### Cảnh báo những sai lệch thường gặp

1. **Thiếu sự kiện:** transaction fact thiếu một DISPATCH sẽ làm SUM(delta) không khớp snapshot; có thể có lỗi CDC hoặc định nghĩa event.
2. **Nhân đôi dữ liệu:** cùng movementId được ingest hai lần vì pipeline tạo ID mới ở mỗi retry.
3. **Hàng snapshot thiếu:** ngày D không có bản ghi vì batch fail; dashboard COALESCE thành 0 khiến tồn kho trông đã hết.
4. **Sai grain trong JOIN:** mỗi snapshot ngày ghép với từng movement cùng ngày, rồi SUM(onHandQty) bị nhân với số movement.
5. **Tích lũy mất mốc:** chỉ lưu event mới nhất hoặc cập nhật NULL lên mốc cũ khi UPSERT.
6. **Sai tiêu chí thời gian:** dùng loadedAt để nhóm ngày giao; late events chuyển sai kỳ.
7. **Quy trình chia kiện:** một orderId có hai fulfillment; lấy orderId làm khóa accumulating snapshot khiến một kiện ghi đè kiện kia.
8. **Giá trị không cùng đơn vị:** cộng kg với chiếc, hoặc cộng số tiền khác currency mà không có chính sách chuẩn hóa.

### Kiểm thử thiết kế bằng những trường hợp biên

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Nạp lại M-201 với cùng payload | Transaction fact vẫn có đúng một hàng |
| Nạp M-201 cùng ID nhưng delta khác | Có cảnh báo/conflict hoặc quy trình correction, không im lặng đếm sai |
| Không phát sinh kho ngày D | Snapshot D vẫn có giá trị nếu thiết kế dense |
| Thiếu snapshot D do lỗi batch | Trạng thái thiếu dữ liệu được công bố; không coi bằng 0 |
| Movement ngày D đến muộn sau khi đã chốt | Restatement/adjustment theo chính sách, báo cáo và đối soát nhất quán |
| Event DELIVERED tới trước PACKED | Accumulating snapshot không xóa dấu mốc; tái dựng/trì hoãn có kiểm soát |
| Fulfillment chưa giao | deliveredAt NULL; KPI giao thành công không coi đó là 0 giờ |
| Order chia hai kiện | Hai fulfillmentId khác nhau; không gộp thành một tiến trình |
| JOIN movement và daily snapshot | Không tính tổng tồn trực tiếp sau JOIN ở grain giao dịch |

## 13. Tối ưu lưu trữ theo kiểu fact và workload

Ba fact thường có các pattern truy cập khác nhau:

**Transaction fact** thường lớn rất nhanh. Phân vùng theo thời gian sự kiện/ngày nghiệp vụ nếu hệ quản trị và khối lượng phù hợp; cluster/sort theo tenant, date, dimension được lọc nhiều. Cần tránh tạo quá nhiều partition nhỏ và nhớ rằng correction có thể ảnh hưởng kỳ cũ.

**Periodic snapshot** có thể lớn hơn số sự kiện trong những giai đoạn ít hoạt động nếu tạo hàng dày cho mọi product–warehouse–date. Quyết định dense/sparse, nén dữ liệu, partition theo kỳ và chính sách lưu lâu dài. Truy vấn thường tìm **kỳ cuối/đầu** hoặc so sánh kỳ, nên bố trí truy cập theo ngày và đối tượng.

**Accumulating snapshot** thường nhỏ hơn fact sự kiện nếu mỗi quy trình chỉ một hàng, nhưng cập nhật tương đối thường xuyên trên các case còn mở. Một số hệ thống cột tối ưu append hơn update, nên pipeline có thể ghi log sự kiện, sau đó **MERGE** theo batch để tạo bản current snapshot. Có thể lưu thêm lịch sử phiên bản snapshot nếu cần xem trạng thái tại những ngày cũ.

Không phải warehouse nào cũng thực thi FOREIGN KEY như PostgreSQL, cũng không phải engine nào cập nhật một hàng với chi phí giống nhau. Chọn chỉ mục, partition, micro-batch và cơ chế MERGE theo sản phẩm cụ thể và kết quả đo lường, thay vì cố chuyển nguyên cách tối ưu OLTP sang OLAP.

### Nhiều nguồn và mốc thời gian không đồng nhất

Để phân tích chuỗi "đơn đặt → nhặt hàng → giao", các mốc có thể đến từ Sales, WMS và hãng vận chuyển. Cần thống nhất:

- định danh nào là **một fulfillment attempt**;
- mốc được ghi khi **yêu cầu**, khi **xác nhận thực hiện** hay khi **sự kiện vật lý xảy ra**;
- cách xử lý chênh lệch đồng hồ giữa các nguồn;
- phiên bản và quyền sửa các mốc đã công bố;
- SLA so với lịch làm việc hay thời gian thực trôi qua;
- thời điểm warehouse có thể tuyên bố dữ liệu **complete through** cho báo cáo.

Nếu các định nghĩa này không có, bảng đủ cột timestamp vẫn có thể cho lead time sai.

## 14. So sánh cách triển khai ở các mô hình dữ liệu

| Công nghệ / mô hình | Ứng viên triển khai | Điểm phải giữ nguyên |
| --- | --- | --- |
| **Quan hệ** | Ba bảng fact, dimension, PK theo grain, index theo thời gian | Tính duy nhất, cutoff, transaction dữ liệu nguồn và logic KPI |
| **Document** | Một document sự kiện; một document snapshot ngày; một document tiến trình cập nhật | Grain của từng document và xử lý phiên bản/atomic update |
| **Đồ thị** | Node sự kiện, tiến trình, hàng hóa và cạnh giữa bước | Quan hệ đồ thị không tự là số đo hay một snapshot đầy đủ |
| **Warehouse cột/lakehouse** | Transaction files, partition snapshots, MERGE accumulating, semantic layer | Late data, idempotency, grain, measure, lịch sử dimension |

Ví dụ trong document database, việc nhúng một mảng tất cả movement vào document tồn kho có thể khiến document phình lớn và thay đổi mọi lần phát sinh. Lưu **movement riêng**, **snapshot định kỳ riêng** và **current fulfillment riêng** thường dễ quản trị theo grain; nhưng không có quy tắc tuyệt đối — phải xét giới hạn atomicity và workload của hệ quản trị cụ thể.

Trong graph database, việc duyệt đường đi của một kiện qua các sự kiện là lợi thế truy vấn quan hệ, nhưng để tính median thời gian giao theo tháng vẫn phải xác định **một lần giao là gì**, mốc thời gian nào và xử lý bản trùng ra sao.

Mô hình vật lý có thể khác nhau, song định nghĩa của transaction, periodic snapshot và accumulating snapshot vẫn nằm ở **ý nghĩa của một bản ghi**, không ở cú pháp CREATE TABLE.

## 15. Quy trình quyết định dùng loại fact nào

Khi một bên nghiệp vụ yêu cầu "tạo bảng fact để báo cáo", hãy đi theo trình tự:

1. **Viết câu hỏi và hành động mong muốn:** đếm sự kiện, biết tồn tại mốc, hay đo tiến độ một quy trình?
2. **Chọn grain bằng một câu:** một hàng là một sự kiện, một đối tượng–kỳ, hay một process instance?
3. **Ghi khóa duy nhất và phạm vi tenant:** eventId, (date, product, warehouse), fulfillmentId...
4. **Xác định measure:** số phát sinh có dấu, số dư tại mốc, hay lead time các bước.
5. **Phân loại tính cộng được:** theo thời gian, theo kho, theo sản phẩm, theo kênh; chỉ cộng khi ý nghĩa và đơn vị cho phép.
6. **Chọn dimension và thời điểm hiệu lực:** sản phẩm/danh mục/kho/ngày, SCD2 hoặc snapshot theo chính sách.
7. **Thiết kế đường nạp:** batch/CDC/event, high-watermark, idempotency, correction, restatement và lưu dấu nguồn.
8. **Xác định trạng thái chưa hoàn tất:** ngày snapshot thiếu, process chưa tới mốc, sự kiện đến trễ; không mặc định bằng 0.
9. **Viết phép đối soát:** tổng movement với chênh lệch snapshot; số process với nguồn; mốc tích lũy với log trạng thái.
10. **Thử dữ liệu biên và đo hiệu năng:** JOIN làm nhân bản, retry, late event, split process, nhiều kỳ và truy vấn khối lượng lớn.

Đầu ra tốt là một **data contract** ghi rõ grain, measure, nguồn, ngày nghiệp vụ, khóa, cách cập nhật, quyền truy cập và quy tắc công bố số liệu.

## 16. Bài tập thực hành: quản lý phiếu xử lý bảo hành

**Tình huống:** Trung tâm bảo hành xử lý thiết bị từ lúc khách gửi yêu cầu đến lúc hoàn trả. Mỗi RepairCase có caseId, customerId, deviceId và có thể được mở lại sau khi kết thúc. Một ca có thể có nhiều lượt kiểm tra, thay linh kiện, yêu cầu khách bổ sung thông tin; mỗi ngày lãnh đạo muốn biết số ca đang chờ, còn kỹ thuật viên muốn đo thời gian từ lúc tiếp nhận đến khi xử lý xong.

**Yêu cầu 1 — Chọn ba grain:** đề xuất:

- Transaction fact cho những sự kiện nào?
- Periodic snapshot fact ở mốc nào, một hàng cho đối tượng nào?
- Accumulating snapshot fact cần một caseId hay một **caseCycleId** khi một ca có thể mở lại?

**Yêu cầu 2 — Thiết kế bảng:** chọn business key, time columns, measure, dimension và những trường NULL hợp lệ. Nêu một ràng buộc UNIQUE/PK cho mỗi fact.

**Yêu cầu 3 — Tính KPI:** viết cách tính số lượt sửa chữa trong tháng, backlog cuối ngày, số ca hoàn tất, p50 thời gian xử lý và tỷ lệ ca trễ SLA. Chọn loại fact phù hợp cho từng KPI.

**Yêu cầu 4 — Trường hợp biên:** nguồn gửi "RepairCompleted" hai lần; một lần kiểm tra đã diễn ra hôm trước nhưng hôm nay mới đồng bộ; ca bị mở lại và có hai vòng sửa; khách đổi địa chỉ sau khi gửi yêu cầu. Hãy cho biết bảng nào cập nhật, bảng nào thêm sự kiện, có cần snapshot thuộc tính lịch sử không.

**Yêu cầu 5 — Đối soát:** thiết kế ít nhất hai phép thử để phát hiện transaction event bị thiếu hoặc accumulating snapshot có thời điểm không nhất quán.

### Một hướng giải tham khảo

**Transaction fact** ở grain **một sự kiện trạng thái/hành động repair**, với eventId, caseCycleId, eventType, occurredAt và technicianId. Đếm lượt RepairCompleted dựa vào các sự kiện duy nhất theo chính sách; nếu một lần sửa có nhiều step, không dùng COUNT(*) không lọc.

**Periodic snapshot** ở grain **một caseCycle còn hoạt động hoặc trong phạm vi báo cáo tại cuối ngày**, với snapshotDate, currentStatus, waitingHoursAsOfCutoff, slaBreachedFlag. Có thể chọn dense snapshot cho mọi cycle còn mở và thêm quy tắc xác định cycle đóng không còn xuất hiện từ ngày nào. Đếm backlog lịch sử bằng snapshot đúng ngày, không dùng trạng thái hiện tại của case.

**Accumulating snapshot** ở grain **một lần xử lý độc lập (caseCycleId)**, có openedAt, firstInspectedAt, partsOrderedAt, repairCompletedAt, returnedAt, currentStatus; cập nhật khi đi qua các mốc. Nếu một case đóng rồi mở lại, tạo cycle mới để không ghi đè chu kỳ trước. Nếu nghiệp vụ cần đo thời gian cộng dồn nhiều vòng trong cùng case, báo cáo có thể tổng hợp theo caseId từ các cycle, nhưng không làm mất grain gốc.

Một ca có thể có nhiều lần kiểm tra hoặc yêu cầu linh kiện nên transaction fact giữ chi tiết vòng lặp. Nếu cần snapshot trường hợp "đang chờ khách lúc 17:00 ngày 15/10", periodic snapshot hoặc event history sẽ trả lời chính xác hơn accumulating snapshot hiện tại.

**Kiểm thử:** một eventId lặp không làm tăng số lượt; snapshot cuối ngày được đối chiếu với các transition đến cutoff; caseCycleId của lần mở lại không trùng cycle cũ; repairCompletedAt không được dùng loadedAt của ETL; kỳ chưa chốt phải có nhãn độ tươi và không bị mặc định là 0.

## 17. Checklist rà soát thiết kế và kết luận

- Mỗi fact có **một grain xác định bằng lời**, khóa và phạm vi duy nhất tương ứng không?
- Transaction fact ghi **sự kiện thực tế** hay vô tình lưu trạng thái hiện tại và ghi đè lịch sử?
- Periodic snapshot xác định **cutoff, timezone, mật độ hàng, completeness** và chính sách thiếu kỳ chưa?
- Accumulating snapshot có ID của **một process instance**, các milestone hợp lệ và cách xử lý lặp/mở lại chưa?
- Measure được phân loại additive, semi-additive, non-additive đúng theo chiều phân tích và đơn vị đo chưa?
- Có tránh SUM tồn qua ngày, COUNT(*) sai grain và JOIN trực tiếp fact khác grain làm nhân dữ liệu không?
- SCD/thuộc tính lịch sử, snapshot giá và role-playing date có được chọn theo câu hỏi báo cáo không?
- EventId và sourceVersion có được giữ khi retry, late arrival hoặc thay đổi dữ liệu không?
- Nếu reprocess một kỳ, report cache, snapshot sau đó và kiểm tra đối soát có được cập nhật nhất quán không?
- Bảng accumulating có thể bị mất milestone khi partial event đến không đúng thứ tự không?
- OLTP vẫn bảo vệ trạng thái nghiệp vụ, còn fact phân tích không tự trở thành nguồn cấp quyền giao dịch chứ?
- Các phép thử dữ liệu trùng, ngày thiếu, correction, chia quy trình và chênh lệch số liệu đã có chưa?

**Kết luận:** **Transaction fact** ghi những điều đã xảy ra ở grain sự kiện; **periodic snapshot fact** trả lời trạng thái của đối tượng tại từng mốc chốt; **accumulating snapshot fact** mô tả một quy trình đi qua nhiều dấu mốc trong một hàng được cập nhật. Chọn đúng kiểu fact không chỉ giúp truy vấn nhanh hơn mà còn quyết định **cách đếm, cách cộng, cách đối soát và cách giải thích KPI**. Với grain, khóa, dấu thời gian, quy tắc cập nhật và chất lượng dữ liệu rõ ràng, ba loại fact có thể cùng tồn tại, bổ sung cho nhau mà không làm mất ý nghĩa nghiệp vụ của nguồn dữ liệu giao dịch.
