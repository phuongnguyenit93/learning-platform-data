# Thời điểm có hiệu lực nghiệp vụ và thời điểm hệ thống ghi nhận

## 1. Vì sao một thay đổi dữ liệu có thể có hai thời điểm khác nhau?

Trong chương **Thời gian và lịch sử** của **DATABASE_DATA_MODELING**, một quyết định quan trọng là xác định thời điểm mà mỗi giá trị **đúng trong nghiệp vụ** và thời điểm mà **hệ thống ghi nhận hoặc biết được giá trị đó**. Đây là phần của việc chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý có thể kiểm chứng. Chỉ thêm một cột **updated_at** thường không giải quyết được câu hỏi này.

Giả sử khách hàng 501 đang dùng gói **BASIC**. Đến ngày 12/04, hệ thống nhận được xác nhận rằng khách đã chuyển sang gói **PRO** với **ngày có hiệu lực là 08/04**. Có ít nhất hai câu hỏi khác nhau:

- **“Khách đang dùng gói gì vào ngày 10/04 theo thông tin đã được xác nhận hiện nay?”** Câu trả lời là **PRO**.
- **“Nếu đứng tại ngày 10/04, lúc đó hệ thống đang ghi nhận khách dùng gói gì?”** Câu trả lời là **BASIC**, bởi quyết định có hiệu lực từ 08/04 chỉ được ghi nhận vào 12/04.

Cả hai câu trả lời đều hợp lệ; chúng có **ngữ cảnh thời gian khác nhau**. Nếu chỉ giữ phiên bản mới nhất, hệ thống có thể trả lời câu đầu nhưng mất cơ sở để trả lời câu sau. Nếu chỉ giữ lịch sử cập nhật mà không lưu ngày hiệu lực, hệ thống biết rằng ngày 12/04 có thay đổi, nhưng không xác định được giá trị PRO áp dụng cho ngày 10/04.

Bài học này tập trung vào cách phân biệt hai trục thời gian, biểu diễn chúng trong dữ liệu quan hệ và áp dụng nguyên tắc tương tự cho document, graph và dữ liệu phân tích.

### Mục tiêu sau bài học

Người học cần có khả năng:

1. Phân biệt **valid time** với **recorded/system time** và không nhầm chúng với thời gian xảy ra sự kiện hay thời gian xử lý.
2. Diễn giải được hai câu hỏi **“đúng vào khi nào?”** và **“hệ thống biết điều đó từ khi nào?”** trong tình huống có dữ liệu đến muộn, ghi nhận sai hoặc thay đổi hồi tố.
3. Chọn mô hình chỉ có một trục thời gian hay mô hình **bitemporal** dựa trên yêu cầu nghiệp vụ.
4. Thiết kế khoảng hiệu lực, khóa, ràng buộc chống chồng lấn và truy vấn **as-of** trên cả hai trục.
5. Nhận diện giới hạn về transaction, tính nhất quán, nguồn thời gian, dữ liệu cũ, múi giờ và chi phí vận hành.

## 2. Hai trục thời gian cốt lõi

### 2.1. Thời điểm có hiệu lực nghiệp vụ — valid time

**Valid time** là khoảng thời gian một thông tin được coi là đúng trong thế giới nghiệp vụ đang mô hình hóa. Ví dụ:

- Mức giá hợp đồng áp dụng từ ngày 01/07 đến trước ngày 01/10.
- Nhân viên thuộc bộ phận A từ 01/01 đến trước 01/04.
- Quyền thành viên PRO có hiệu lực từ 08/04, dù hệ thống nhận được quyết định này vào 12/04.
- Một địa chỉ giao hàng là địa chỉ đã được khách xác nhận cho một đơn tại thời điểm chốt đơn.

Valid time có thể nằm trong quá khứ, hiện tại hoặc tương lai so với ngày ghi nhận. Nó do **quy tắc nghiệp vụ** định nghĩa. Một giá có hiệu lực từ 00:00 theo múi giờ của chi nhánh khác với một giá có hiệu lực từ 00:00 UTC; phải chọn cách diễn giải trước khi lưu.

Nhiều nghiệp vụ dùng **khoảng hiệu lực** thay vì một thời điểm đơn lẻ:

~~~text
[valid_from, valid_to)
~~~

Ký hiệu **[a, b)** nghĩa là bao gồm thời điểm a và loại trừ b. Nếu gói BASIC kết thúc vào đúng 00:00 ngày 08/04, còn PRO bắt đầu lúc đó, hai khoảng không trùng biên.

### 2.2. Thời điểm hệ thống ghi nhận — recorded/system time

**Recorded time** trong thiết kế ứng dụng thường là thời điểm hệ thống tiếp nhận hoặc lưu một thông tin vào nguồn dữ liệu có thẩm quyền. Nó trả lời: **“Từ lúc nào hệ thống có thông tin này?”**

Với dữ liệu phiên bản hóa, ta thường cần cả một **khoảng hệ thống ghi nhận**:

~~~text
[recorded_from, recorded_to)
~~~

- **recorded_from**: khi phiên bản bắt đầu được hệ thống xem là thông tin đang biết/đang chấp nhận.
- **recorded_to**: khi phiên bản ấy được thay thế hoặc bị bác bỏ trong hệ thống; có thể chưa có giá trị nếu vẫn là thông tin mới nhất.

Cần phân biệt hai mức bảo đảm:

- **Timestamp ứng dụng tự ghi**, ví dụ **recorded_at = now()**, cho biết mốc thời gian do ứng dụng hoặc database lấy trong lúc xử lý.
- **System/transaction time với ngữ nghĩa chặt chẽ** phản ánh thời gian phiên bản trở nên khả kiến theo lịch sử transaction của cơ sở dữ liệu. Nếu cần tái dựng chính xác trạng thái đã được commit ở mọi thời điểm, timestamp lấy trước commit không mặc nhiên đủ.

Trong tài liệu này, **recorded/known time** là trục “hệ thống đã chấp nhận biết gì”; với ví dụ PostgreSQL tự xây dựng, giá trị được **ứng dụng quản lý**. Không nên gọi đó là tính năng system-versioning tự động của PostgreSQL.

### 2.3. Bảng phân biệt các loại thời gian thường gặp

| Khái niệm | Câu hỏi trả lời | Ví dụ | Có thể khác valid time? |
|---|---|---|---|
| **Valid time** | Giá trị này có hiệu lực trong nghiệp vụ từ bao giờ? | PRO có hiệu lực từ 08/04 | Là mốc tham chiếu |
| **Recorded/known time** | Hệ thống ghi nhận/chấp nhận giá trị từ bao giờ? | Hệ thống nhận quyết định ngày 12/04 | Có |
| **Event/occurred time** | Hành động thực tế đã xảy ra khi nào? | Khách ký yêu cầu ngày 06/04 | Có |
| **Received/ingestion time** | Dữ liệu đến API hoặc pipeline lúc nào? | API nhận thông báo ngày 11/04 | Có |
| **Processing time** | Một worker xử lý thông điệp lúc nào? | Worker xử lý lại ngày 13/04 | Có |
| **Commit time** | Transaction trở nên bền vững/khả kiến theo hệ quản trị khi nào? | Transaction commit sau bước kiểm tra | Có |

Trong một tác vụ đơn giản, các mốc có thể rất gần nhau; trong hệ thống phân tán, nhập liệu thủ công, kết nối ngoại tuyến và điều chỉnh hồi tố, chúng có thể chênh lệch nhiều ngày. Không gộp hai khái niệm chỉ vì thử nghiệm ban đầu cho ra timestamp gần bằng nhau.

Ví dụ: lúc 09:00 ngày 12/04, nhân viên nhập quyết định PRO có hiệu lực 08/04; thông điệp được gửi từ dịch vụ đối tác lúc 08:55 và xử lý xong lúc 09:02. Đó là các mốc khác nhau, dù tất cả liên quan đến cùng một thay đổi.

## 3. Theo dõi một tình huống có ghi nhận muộn

Đặt các thời điểm theo UTC để tránh mơ hồ trong ví dụ:

- **01/04/2026 00:00**: BASIC có hiệu lực.
- **01/04/2026 08:00**: hệ thống ghi nhận BASIC.
- **08/04/2026 00:00**: PRO có hiệu lực theo quyết định sau này được xác nhận.
- **12/04/2026 09:00**: hệ thống mới ghi nhận quyết định đổi sang PRO, có hiệu lực hồi tố từ 08/04.

~~~mermaid
flowchart LR
    A["01/04 00:00<br/>BASIC có hiệu lực"] --> B["08/04 00:00<br/>PRO có hiệu lực"]
    B --> C["12/04 09:00<br/>Hệ thống mới ghi nhận PRO"]
~~~

<em>Trong sơ đồ, vị trí trên trục ngang là thứ tự thời gian minh họa, không thể hiện khoảng cách theo tỷ lệ.</em>

Tại các thời điểm ghi nhận khác nhau, hệ thống có các phiên bản “sự thật đang biết” khác nhau:

| Hệ thống được hỏi **như đã biết vào** | Ngày nghiệp vụ cần xem | Trả lời |
|---|---|---|
| 10/04 lúc 12:00 | 05/04 lúc 12:00 | BASIC |
| 10/04 lúc 12:00 | 10/04 lúc 12:00 | BASIC |
| 13/04 lúc 12:00 | 05/04 lúc 12:00 | BASIC |
| 13/04 lúc 12:00 | 10/04 lúc 12:00 | PRO |
| 13/04 lúc 12:00 | 13/04 lúc 12:00 | PRO |

Hàng thứ hai và hàng thứ tư có cùng **ngày nghiệp vụ 10/04**, nhưng câu trả lời khác nhau vì **mốc kiến thức của hệ thống** khác nhau. Nếu bỏ trục recorded time, một truy vấn về 10/04 có thể vô tình áp dụng dữ liệu đã được chỉnh sửa sau thời điểm mà người dùng muốn kiểm tra.

### 3.1. Cần lưu ba khoảng phiên bản

Sau khi hệ thống ghi nhận thay đổi ngày 12/04, lịch sử hai trục thời gian có thể biểu diễn như sau:

| Phiên bản | Giá trị | Hiệu lực nghiệp vụ | Khoảng hệ thống ghi nhận |
|---|---|---|---|
| v1 | BASIC | [01/04, ∞) | [01/04 08:00, 12/04 09:00) |
| v2 | BASIC | [01/04, 08/04) | [12/04 09:00, ∞) |
| v3 | PRO | [08/04, ∞) | [12/04 09:00, ∞) |

**v1** là điều hệ thống từng tin: BASIC có hiệu lực từ 01/04 về sau. Khi biết quyết định hồi tố, hệ thống **không xóa v1**, mà đóng khoảng ghi nhận của nó. **v2** và **v3** thể hiện thông tin nghiệp vụ hiện được hệ thống chấp nhận.

Điểm cần hiểu: các hàng v1 và v3 **chồng nhau về valid time** từ 08/04 trở đi nhưng **không chồng nhau về recorded time**. Đây là hành vi đúng của mô hình bitemporal: hai phiên bản cùng đề cập đến một ngày nghiệp vụ, nhưng đúng theo những trạng thái kiến thức khác nhau.

### 3.2. Hai chiều truy vấn as-of

Gọi:

- **B** = thời điểm nghiệp vụ muốn hỏi (*business time*).
- **K** = thời điểm muốn đứng vào để xem hệ thống đã biết gì (*knowledge/recorded time*).

Truy vấn bitemporal có dạng khái niệm:

~~~text
AS_OF(B, K)
= phiên bản có valid_from <= B < valid_to
  và recorded_from <= K < recorded_to
~~~

Nếu không có hàng thỏa mãn, kết luận phải là **không có thông tin phù hợp trong phạm vi dữ liệu đang giữ**; không tự suy ra BASIC hoặc một giá trị mặc định. Nếu có hơn một hàng khi nghiệp vụ quy định mỗi khách chỉ có một gói tại một thời điểm, mô hình đang vi phạm ràng buộc hoặc quá trình sửa đổi chưa nhất quán.

## 4. Khi nào một trục thời gian là đủ?

Không phải mọi bảng đều cần hai trục thời gian. Quyết định dựa trên **câu hỏi cần trả lời và bằng chứng phải lưu**.

| Nhu cầu | Mô hình có thể đủ | Ví dụ |
|---|---|---|
| Chỉ đọc giá trị mới nhất, quá khứ không cần truy vấn | Bản hiện tại, **updated_at** phục vụ đồng bộ | Cấu hình hiển thị tức thời |
| Cần xem lịch sử những lần hệ thống thay đổi, không có hiệu lực hồi tố | Các phiên bản theo thời điểm ghi nhận | Timeline trạng thái xử lý nội bộ |
| Cần biết giá trị áp dụng tại ngày nghiệp vụ, các quyết định không cần truy về “đã biết khi nào” | Các phiên bản theo valid time | Lịch áp dụng mức phí đã chốt |
| Cần kiểm tra cả giá trị có hiệu lực lúc X và hệ thống đã biết gì lúc Y | **Bitemporal** | Hợp đồng chỉnh hiệu lực hồi tố, đối soát hóa đơn bị khiếu nại |
| Chỉ cần tái hiện báo cáo theo lô xử lý | Lưu bản chụp theo kỳ hoặc version báo cáo; cân nhắc bitemporal nếu cần | Báo cáo tháng đã khóa sổ |

Một điểm tinh tế: **lưu riêng valid_from và recorded_at trên mỗi hàng không tự động thành mô hình bitemporal**. Để trả lời “hệ thống biết gì ở K”, phải lưu được cả các phiên bản đã bị thay thế cùng thời điểm chúng hết hiệu lực trong hệ thống, hoặc một chuỗi sự kiện bất biến đủ thông tin để tái dựng lịch sử kiến thức.

Tương tự, một bảng lịch sử mọi lần **UPDATE** có thể trả lời “cột thay đổi lúc nào” nhưng không chắc trả lời được “giá trị nào có hiệu lực cho kỳ tính phí nào” nếu không có valid time.

## 5. Thiết kế lược đồ quan hệ với hai khoảng thời gian

Phần này dùng PostgreSQL để minh họa một **bảng lịch sử do ứng dụng quản lý**. Ý tưởng cũng áp dụng cho cơ sở dữ liệu quan hệ khác, dù cú pháp kiểu range, chỉ mục và ràng buộc có thể khác.

### 5.1. Chọn kiểu dữ liệu và biểu diễn khoảng

Nên chọn rõ đơn vị thời gian trước khi viết DDL:

- Nếu quyền gói có hiệu lực đến **giây hoặc microsecond**, lưu **timestamptz** và xác định quy tắc UTC/múi giờ hiển thị.
- Nếu nghiệp vụ chỉ có **ngày lịch tại một khu vực**, kiểu **date** hoặc ngày địa phương kèm timezone nghiệp vụ có thể rõ nghĩa hơn. Đừng ngầm đổi ngày “01/05 theo Hà Nội” thành UTC 00:00 khi quy tắc chỉ nói ngày địa phương.
- Mỗi khoảng dùng dạng nửa mở **[bắt đầu, kết thúc)**. **NULL/unbounded upper** có thể biểu diễn chưa có ngày kết thúc; đây là “chưa kết thúc theo thông tin hiện có”, không nhất thiết “sẽ tồn tại vĩnh viễn”.
- Tránh trộn đơn vị và độ chính xác của các nguồn; timestamp làm tròn đến giây có thể khiến hai lần đổi trong một giây không phân biệt được nếu không có thêm sequence hoặc operation ID.

PostgreSQL có kiểu **tstzrange** để lưu khoảng timestamp có múi giờ:

~~~sql
SELECT tstzrange(
    TIMESTAMPTZ '2026-04-01 00:00:00+00',
    TIMESTAMPTZ '2026-04-08 00:00:00+00',
    '[)'
) AS basic_effective_period;
~~~

Một giá trị **tstzrange** mang hai biên trong cùng một cột; toán tử **@>** hỏi khoảng có chứa một thời điểm, còn **&&** kiểm tra hai khoảng có giao nhau hay không.

### 5.2. Bảng bitemporal và ràng buộc không chồng lấn

Giả định một khách tại một cặp thời điểm **(B, K)** chỉ được có **một** gói đang có hiệu lực. Cấu trúc:

~~~sql
-- btree_gist cho phép dùng dấu = của bigint cùng toán tử range trong GiST.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE customer_plan_bitemporal (
    version_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id       bigint NOT NULL,
    plan_code         text NOT NULL,
    valid_period      tstzrange NOT NULL,
    known_period      tstzrange NOT NULL,
    source_ref        text NOT NULL,
    correction_reason text,

    CONSTRAINT ck_valid_period_bounds
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),
    CONSTRAINT ck_known_period_bounds
        CHECK (
            NOT isempty(known_period)
            AND NOT lower_inf(known_period)
            AND lower_inc(known_period)
            AND NOT upper_inc(known_period)
        ),

    CONSTRAINT ex_one_plan_per_business_and_known_time
        EXCLUDE USING gist (
            customer_id WITH =,
            valid_period WITH &&,
            known_period WITH &&
        )
);
~~~

Ý nghĩa của ràng buộc loại trừ **EXCLUDE**:

> Với cùng một **customer_id**, không cho phép hai hàng đồng thời chồng nhau cả về **valid_period** và **known_period**.

Nếu hai hàng chỉ chồng về valid time nhưng thuộc **những thời kỳ kiến thức khác nhau**, chúng được phép cùng tồn tại; đó chính là cơ sở của ghi nhận hồi tố. Nếu nghiệp vụ cho phép khách đồng thời có nhiều loại gói, cần thêm **plan_category** hoặc loại quan hệ vào ràng buộc thay vì vô tình cấm dữ liệu hợp lệ.

**EXCLUDE** chống chồng lấn nhưng **không tự bảo đảm không có khoảng trống**. Nếu nghiệp vụ bắt buộc mỗi khách có đúng một gói liên tục, phải kiểm tra thêm tính liền mạch của các khoảng hợp lệ. Một khóa chính **version_id** chỉ định danh hàng; nó không thay thế ràng buộc ý nghĩa thời gian.

Cần quản lý quyền ghi vào bảng và quy tắc sửa đổi theo transaction; ràng buộc trong DDL không tự phát hiện bản lịch sử bị thiếu ở một sự kiện không hề được ghi.

### 5.3. Ghi nhận ban đầu

Giả sử hệ thống biết khách 501 dùng BASIC từ 01/04 và ghi nhận thông tin đó lúc 08:00 cùng ngày:

~~~sql
INSERT INTO customer_plan_bitemporal (
    customer_id, plan_code, valid_period, known_period, source_ref
)
VALUES (
    501,
    'BASIC',
    tstzrange(
        TIMESTAMPTZ '2026-04-01 00:00:00+00',
        NULL, '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-01 08:00:00+00',
        NULL, '[)'
    ),
    'registration-501'
);
~~~

Mốc thời gian trong ví dụ được viết cố định để dễ kiểm chứng. Trong hệ thống thực tế, **recorded_from** cần được tạo nhất quán từ nguồn thời gian đáng tin của hệ thống ở lúc phiên bản được ghi nhận; còn **valid_from** được lấy từ quyết định nghiệp vụ đã được xác thực.

### 5.4. Sửa đổi hiệu lực hồi tố và bảo toàn kiến thức cũ

Lúc 09:00 ngày 12/04, quyết định chuyển PRO từ 08/04 đã được phê duyệt. Hệ thống cần:

1. Đóng **known_period** của các phiên bản đang đại diện cho kiến thức mới nhất.
2. Tạo phiên bản BASIC chỉ có hiệu lực đến trước 08/04.
3. Tạo phiên bản PRO có hiệu lực từ 08/04.
4. Thực hiện các thay đổi nguyên tử trong một transaction, kèm nguồn quyết định.

Với **dữ liệu minh họa chỉ có một khoảng cũ**, các thao tác sau cho ra đúng bảng ở phần 3:

~~~sql
BEGIN;

UPDATE customer_plan_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-04-12 09:00:00+00',
    '[)'
)
WHERE customer_id = 501
  AND upper_inf(known_period);

INSERT INTO customer_plan_bitemporal (
    customer_id, plan_code, valid_period,
    known_period, source_ref, correction_reason
)
VALUES
(
    501, 'BASIC',
    tstzrange(
        TIMESTAMPTZ '2026-04-01 00:00:00+00',
        TIMESTAMPTZ '2026-04-08 00:00:00+00',
        '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-12 09:00:00+00',
        NULL, '[)'
    ),
    'decision-2026-04-12', 'Chốt lại ngày hiệu lực'
),
(
    501, 'PRO',
    tstzrange(
        TIMESTAMPTZ '2026-04-08 00:00:00+00',
        NULL, '[)'
    ),
    tstzrange(
        TIMESTAMPTZ '2026-04-12 09:00:00+00',
        NULL, '[)'
    ),
    'decision-2026-04-12', 'Chốt lại ngày hiệu lực'
);

COMMIT;
~~~

Đây là **mẫu diễn giải một lần chỉnh sửa đã biết dữ liệu đầu vào**, chưa phải stored procedure có thể dùng trực tiếp cho mọi thay đổi. Trong sản phẩm thực tế cần đọc các khoảng đang có, tính lại **toàn bộ các đoạn bị ảnh hưởng**, bảo vệ khỏi cập nhật đồng thời (khóa bản ghi gốc hoặc dùng chiến lược transaction/phiên bản thích hợp), kiểm tra số hàng được cập nhật và xử lý retry. Nếu hai thay đổi cạnh tranh cùng áp dụng cho khách 501, không được để mỗi giao dịch tự suy đoán rằng mình là quyết định mới nhất.

Thao tác **UPDATE known_period** không xóa phiên bản cũ: nó “đóng” khoảng mà hệ thống đã từng xem phiên bản đó là hiện hành. Tuy nhiên nếu yêu cầu kiểm toán đòi mọi byte của bảng lịch sử phải bất biến, hãy lưu thêm event/audit append-only hoặc dùng cơ chế versioning của DB đáp ứng yêu cầu, thay vì mặc nhiên coi cập nhật metadata là bất biến vật lý.

**Giới hạn thời gian transaction:** trong ví dụ, mốc **09:00** là thời gian ghi nhận theo quy ước ứng dụng. Nó có thể không trùng thời điểm commit. Nếu phải chứng minh chính xác “một transaction đã commit và có thể đọc được lúc nào”, cần cơ chế system-versioning/commit ordering đủ chặt, chứ không chỉ thêm **NOW()** và cho rằng thời điểm commit đã được lưu.

## 6. Truy vấn một hoặc hai trục thời gian

### 6.1. Theo nghiệp vụ tại B và theo hiểu biết hiện nay

Bài toán: “Theo thông tin hiện đã chấp nhận, ngày 10/04 khách dùng gói nào?”

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> statement_timestamp();
~~~

Theo dữ liệu ví dụ sau 12/04, kết quả là **PRO**. Cột **source_ref** giúp truy về quyết định đã xác nhận. Không bỏ điều kiện **known_period**: nếu bỏ, cả phiên bản BASIC cũ và PRO mới có thể khớp ngày 10/04.

### 6.2. Theo nghiệp vụ tại B và theo hiểu biết tại K

Bài toán: “Nếu đứng vào lúc 12:00 ngày 10/04, hệ thống khi đó cho rằng gói có hiệu lực lúc 12:00 ngày 10/04 là gì?”

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00';
~~~

Kết quả là **BASIC**; quyết định ghi nhận ngày 12/04 chưa nằm trong kiến thức của hệ thống ở thời điểm K.

Nếu vẫn hỏi về ngày nghiệp vụ 10/04 nhưng thay K thành 13/04:

~~~sql
SELECT plan_code, source_ref
FROM customer_plan_bitemporal
WHERE customer_id = 501
  AND valid_period @> TIMESTAMPTZ '2026-04-10 12:00:00+00'
  AND known_period @> TIMESTAMPTZ '2026-04-13 12:00:00+00';
~~~

Kết quả là **PRO**. Hai câu lệnh khác nhau **chỉ tại thời điểm K**, minh họa giá trị cốt lõi của bitemporal.

### 6.3. Truy vấn một trục và mất mát ngữ nghĩa

Giả sử bảng chỉ có **customer_id, plan_code, valid_from, valid_to**. Ta có thể tìm gói hiệu lực tại ngày 10/04 theo dữ liệu đang có, nhưng không thể biết rằng đến ngày 10/04 hệ thống từng nghĩ đó là BASIC. Ngược lại, bảng chỉ có **changed_at, old_value, new_value** cho biết sự kiện cập nhật ngày 12/04, nhưng nếu không ghi quyết định có hiệu lực từ 08/04 thì không thể xác định PRO áp dụng từ ngày nào.

Trong bảng bitemporal, hai điều kiện truy vấn **valid_period chứa B** và **known_period chứa K** tạo thành một “lát cắt” từ hai trục. Các lệnh chỉ lấy dữ liệu mới nhất theo **ORDER BY recorded_at DESC LIMIT 1** không giải quyết trọn vẹn câu hỏi này nếu dữ liệu có nhiều khoảng nghiệp vụ hoặc nhiều phiên bản hồi tố.

### 6.4. Không đồng nhất “đã biết” với “đã công bố”

Một bảng có thể ghi nhận quyết định đã được phê duyệt từ ngày 12/04 nhưng không công bố cho khách cho đến ngày 13/04. Nếu yêu cầu hỏi “khách **đã được thông báo** điều gì lúc K?”, cần thêm dấu mốc công bố/giao nhận riêng. Trục **known time** của database chỉ phản ánh kiến thức được hệ thống đó xác nhận, không tự bao hàm trạng thái truyền thông, email đã gửi hay thời gian đối tác nhận được dữ liệu.

## 7. Các tình huống phải làm rõ khi mô hình hóa

### 7.1. Dữ liệu đến muộn

Thiết bị ngoại tuyến ghi nhận thời điểm hoàn thành kiểm tra lúc 14:00, nhưng chỉ đồng bộ lên máy chủ lúc 17:00. Nếu nghiệp vụ cần báo cáo công việc hoàn thành theo giờ thực tế, **valid/event time = 14:00** có ý nghĩa; nếu kiểm toán yêu cầu chứng minh “máy chủ biết từ khi nào”, **recorded time = 17:00** phải được lưu.

Cần phân biệt dữ liệu đến muộn với dữ liệu sai. Một thiết bị có thể ghi sai đồng hồ hoặc người dùng sửa thủ công mốc hiệu lực; hệ thống cần xác thực nguồn, mức tin cậy, chữ ký/định danh sự kiện và quyền cho phép sửa hồi tố.

### 7.2. Ghi nhận trước, hiệu lực trong tương lai

Bộ phận giá phê duyệt ngày 10/06 rằng bảng giá mới có hiệu lực ngày 01/07. Khi đó:

~~~text
recorded_from = 10/06
valid_from    = 01/07
~~~

Ngày 15/06, hệ thống đã **biết** giá tương lai nhưng không được dùng giá đó cho giao dịch phát sinh ngày 15/06. Một lỗi thường gặp là lấy phiên bản vừa ghi vào database làm “giá hiện tại” mà không lọc theo valid time.

Với thay đổi có lịch trước, cần xác định cơ chế kích hoạt có đồng nghĩa với hiệu lực hay không: bản ghi có thể có hiệu lực theo truy vấn từ ngày 01/07 dù không có worker chạy đúng 00:00; nếu phải phát thông báo hoặc cập nhật projection, cần cơ chế chạy lịch và xử lý trễ.

### 7.3. Sửa sai, đính chính và thay đổi hồi tố

Ba sự kiện khác nhau cần cách biểu diễn khác nhau:

- **Sửa lỗi nhập liệu:** ngày hiệu lực gốc là 08/04 nhưng nhân viên nhập nhầm 09/04. Lịch sử ghi lại dữ liệu hệ thống từng tin, sau đó phiên bản được đính chính.
- **Quyết định nghiệp vụ mới có hiệu lực hồi tố:** đến 12/04 mới quyết định chuyển gói từ 08/04. Cần lưu nguồn phê duyệt và đánh giá hệ quả đối với các giao dịch đã phát sinh.
- **Hủy một quyết định trước đây:** một thay đổi từng được chấp nhận bị rút lại. Cần biết liệu trạng thái mới áp dụng từ ngày hủy hay sửa lại toàn bộ khoảng hiệu lực trong quá khứ.

Bitemporal chỉ ghi lại **phiên bản kiến thức về hiệu lực**; nó không tự quy định phải hoàn tiền, phát hóa đơn điều chỉnh hay sửa sổ cái. Các tác động tài chính nên được mô hình hóa bằng nghiệp vụ điều chỉnh có chứng cứ thay vì tùy tiện viết lại giao dịch đã chốt.

### 7.4. Mâu thuẫn giữa hai nguồn dữ liệu

Một đối tác ghi gói PRO có hiệu lực 08/04, trong khi hợp đồng ký số cho biết 09/04. Không nên tự chọn nguồn có **recorded_at** muộn nhất là đúng. Cần quy định quyền ưu tiên của nguồn, quy trình phê duyệt, trạng thái tranh chấp và cách lưu thông tin chưa được xác thực. Trục recorded time cho biết hệ thống đã nhận/chấp nhận giá trị **khi nào**, không chứng minh giá trị ấy **đúng**.

### 7.5. Không biết chính xác mốc hiệu lực

Bản ghi cũ chỉ nói “áp dụng trong tháng 4” hoặc “bắt đầu từ đầu quý” mà không biết ngày. Không nên bịa thời điểm chi tiết. Có thể lưu **độ chính xác của mốc thời gian** hoặc trạng thái **unknown**, cùng nguồn và quy tắc suy diễn. Khoảng không chắc chắn cần được phân biệt với một khoảng hiệu lực đã được xác minh.

## 8. Ràng buộc, toàn vẹn và ghi đồng thời

### 8.1. Những bất biến cần xác định

Một hệ thống gói dịch vụ theo thời gian có thể đòi các bất biến sau:

1. Một khách chỉ có tối đa một gói chính cho mỗi cặp thời điểm **(B, K)**.
2. Mỗi khoảng valid và known có biên bắt đầu rõ ràng, không rỗng, kết thúc sau bắt đầu.
3. Mỗi lần điều chỉnh có nguồn dữ liệu/quyết định tham chiếu được.
4. Các khoảng được công nhận hiện tại không chồng lấn bất hợp lệ; nếu quy tắc yêu cầu liên tục, không bỏ sót khoảng ngày.
5. Phiên bản trước khi điều chỉnh vẫn truy vấn lại được theo recorded time.
6. Mọi thay đổi liên quan được commit nguyên tử; không có “đã đóng phiên bản cũ nhưng chưa ghi phiên bản mới”.
7. Ghi nhận trùng do retry không tạo thêm bản lịch sử tương đương.

Trong SQL minh họa, **CHECK** ngăn khoảng rỗng, **EXCLUDE** ngăn chồng lấn theo hai trục, nhưng những quy tắc về **phủ kín khoảng**, **chấp thuận quyết định**, **đủ nguồn**, **trình tự sửa đổi** và **không trùng nghiệp vụ** còn cần xử lý ở lớp giao dịch/ứng dụng hoặc cơ chế database bổ sung.

### 8.2. Khóa logic khi điều chỉnh cả dòng thời gian

Hai giao dịch đồng thời cùng điều chỉnh khách 501 có thể đọc cùng lịch sử và cùng tính ra những đoạn valid khác nhau. Nếu chỉ kiểm tra từng INSERT, một giao dịch có thể thất bại do **EXCLUDE** nhưng ứng dụng vẫn phải biết cách retry hoặc giải quyết xung đột.

Một phương án là khóa thực thể gốc **customer 501** trong suốt transaction, đọc các phiên bản kiến thức hiện tại, tính lại khoảng, đóng các phiên bản cũ và thêm phiên bản mới. Có thể kết hợp optimistic version trên thực thể gốc, mức cô lập phù hợp và **idempotency key** của quyết định. Hãy kiểm tra hành vi khi không có hàng gốc để khóa hoặc khi có nhiều hệ thống ghi.

Không nên tạo timestamp ở từng câu lệnh độc lập cho các bước đóng/mở một quyết định nếu điều đó tạo ra khoảng trống giữa **recorded_to** của phiên bản cũ và **recorded_from** của phiên bản mới. Lấy một mốc logic chung cho toàn bộ quyết định, đồng thời hiểu giới hạn về mốc commit như phần 2.

### 8.3. Bản lịch sử và bản hiện tại

Đọc truy vấn bitemporal nhiều lần trên một thực thể có số phiên bản lớn có thể tốn chi phí. Một bảng/projection **current_plan** hoặc cache phục vụ API thời gian thực có thể hữu ích, nhưng phải xác định đâu là nguồn có thẩm quyền. Nếu current_plan là projection, cần cơ chế transaction/outbox/đồng bộ, phát lại và đối soát khi dữ liệu chậm hoặc bị sửa.

Đối soát tối thiểu là: với mỗi khách tại thời điểm hiện tại, tra bản ghi bitemporal ở **(B = now, K = now)** và so sánh với projection đang phục vụ đọc. Sự khác biệt có thể hợp lệ trong giới hạn độ trễ đã cam kết hoặc là lỗi dữ liệu; cần đo và cảnh báo rõ.

## 9. Chỉ mục, phân vùng và hiệu năng

Hai trục thời gian đồng nghĩa truy vấn có thể lọc bằng **entity_id + B + K**, thường khó tối ưu hơn một bảng trạng thái thông thường.

- **GiST / SP-GiST cho range:** PostgreSQL hỗ trợ toán tử chứa thời điểm và giao nhau; ràng buộc **EXCLUDE USING gist** ở phần 5 vừa hỗ trợ toàn vẹn vừa có cấu trúc chỉ mục cho một số dạng truy vấn.
- **B-tree cho khóa tra cứu:** khóa chính **version_id** hoặc khóa của thực thể vẫn hữu ích; cần đo truy vấn thực tế bằng **EXPLAIN (ANALYZE, BUFFERS)** trước khi bổ sung nhiều chỉ mục.
- **Tìm phiên bản đang được ghi nhận:** điều kiện **upper_inf(known_period)** giới hạn các phiên bản kiến thức hiện tại; có thể cân nhắc chỉ mục từng phần nếu workload thường xuyên đọc nhóm này.
- **Phân vùng lịch sử:** lượng điều chỉnh lớn có thể cần phân vùng theo recorded time hoặc thực thể; phải kiểm tra cách bảo toàn ràng buộc không chồng lấn **qua các phân vùng**. Không mặc nhiên giả định ràng buộc loại trừ ở một phân vùng áp dụng toàn cục.
- **Lưu giữ và lưu trữ lạnh:** quy định retention cho từng loại giá trị, quy trình xóa/ẩn danh dữ liệu cá nhân và nghĩa vụ giữ chứng cứ. Nếu xóa phiên bản cũ, các truy vấn **as-of K** trước thời điểm giữ dữ liệu có thể không còn câu trả lời đầy đủ; API phải công bố phạm vi thời gian có thể truy vấn.

Chi phí lưu trữ tăng theo số lần **thay đổi kiến thức**, không chỉ theo số lần thực thể thực sự đổi trạng thái. Một lần sửa quyết định áp dụng cho nhiều khoảng valid có thể cần đóng và tạo lại nhiều hàng. Dữ liệu dài hạn nên có chiến lược nén, archive hoặc chuyển phân tích theo yêu cầu thật, tránh tạo lịch sử bitemporal cho mọi cột chỉ vì hệ quản trị hỗ trợ.

## 10. Các mô hình dữ liệu khác biểu diễn hai trục ra sao?

Trong phạm vi **DATABASE_DATA_MODELING**, cùng một câu hỏi nghiệp vụ có thể triển khai trên nhiều loại cơ sở dữ liệu. Đừng chọn công nghệ trước khi xác định rõ ngữ nghĩa thời gian.

| Mô hình | Cách biểu diễn thường gặp | Điểm cần kiểm soát |
|---|---|---|
| **Quan hệ** | Mỗi phiên bản là một hàng; valid/known range; khóa, exclusion và transaction | Kiểm tra overlap, tính nguyên tử, hiệu năng truy vấn hai trục |
| **Document** | Collection phiên bản, mỗi document có **validFrom/To** và **knownFrom/To**, liên kết bằng entity ID | Tránh mảng lịch sử tăng vô hạn trong một document, tính nhất quán khi sửa nhiều phiên bản |
| **Graph** | Phiên bản node **và** edge, mỗi quan hệ có mốc hiệu lực và ghi nhận | Truy vấn đường đi tại (B, K) phải lọc nhất quán từng node và edge |
| **Kho phân tích** | Dimension theo phiên bản (**SCD Type 2**) và thời điểm tải/điều chỉnh; có thể bổ sung hai trục | Batch load trễ, dimension đến muộn, ảnh hưởng tới join fact đã chốt |
| **Event store** | Sự kiện chấp nhận quyết định cùng valid time và thời điểm lưu; projection tái dựng theo quy tắc | Event time khác order of recording, replay logic, schema evolution, correction |

**SCD Type 2** thường quản lý phiên bản theo khoảng hiệu lực. Chỉ có cặp **effective_from/to** không mặc nhiên là bitemporal; muốn biết báo cáo ngày xưa đã dùng phiên bản nào, cần thêm trục kiến thức hoặc version báo cáo đã lưu.

**CDC** có thể vận chuyển thay đổi từ database sang kho phân tích, nhưng lịch sử CDC không tự tạo ra valid time nếu ứng dụng chưa ghi nhận ngày hiệu lực nghiệp vụ. Ngược lại, một event store có cả occurred_at và recorded_at vẫn cần định nghĩa cách tính trạng thái hiệu lực; sắp xếp event theo thời điểm nhận được không tự xử lý đúng quyết định hồi tố.

## 11. Những lỗi phổ biến và cách sửa thiết kế

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Dùng **updated_at** để đại diện ngày hiệu lực | Tính phí sai cho thay đổi có hiệu lực hồi tố/tương lai | Lưu valid time riêng theo quy tắc nghiệp vụ |
| Ghi đè bản ghi cũ khi sửa ngày hiệu lực | Không tái dựng được hệ thống từng biết gì | Giữ phiên bản theo recorded/known time |
| Chỉ lưu **recorded_from**, bỏ lúc bị thay thế | Khó truy vấn as-of một cách trực tiếp, dễ chọn nhầm phiên bản | Có known interval hoặc event log có thứ tự đủ để tái dựng |
| Sắp xếp theo timestamp để giải quyết mọi xung đột | Sự kiện đến trễ/sai đồng hồ làm mất quyết định hợp lệ | Quy tắc ưu tiên, version, idempotency và nguồn có thẩm quyền |
| Dùng khoảng đóng cả hai đầu **[from, to]** không nhất quán | Trùng giá trị ở mốc chuyển tiếp | Quy ước nửa mở **[from, to)** |
| Coi **NOW()** là thời điểm commit chính xác | Có thể báo sai khi chứng minh trạng thái đã commit ở một thời điểm | Chọn ngữ nghĩa recorded time rõ ràng; dùng cơ chế transaction-time đủ bảo đảm nếu bắt buộc |
| Chỉ ràng buộc **UNIQUE(customer_id, valid_from)** | Hai khoảng bắt đầu khác nhau vẫn có thể chồng lấn | Kiểm tra overlap toàn khoảng theo trục phù hợp |
| Chỉ phiên bản hóa thực thể mà quên quan hệ | Truy vấn tổ chức/sở hữu trong quá khứ sai | Gắn hiệu lực cho quan hệ/edge hoặc bảng liên kết |
| Xóa lịch sử sau retention mà không công bố giới hạn | Truy vấn lịch sử âm thầm thiếu bản ghi | Trả trạng thái “ngoài phạm vi dữ liệu” và lưu metadata phạm vi |
| Viết lại hóa đơn đã chốt dựa trên valid time mới | Mất dấu vết tài chính | Điều chỉnh qua nghiệp vụ bù trừ, lưu liên kết quyết định và hóa đơn |

## 12. Bộ kiểm thử dữ liệu theo hai trục

Dùng tập dữ liệu ở phần 3, kiểm tra các truy vấn theo cả hai biến thời gian. Các thời điểm đều tính theo UTC.

| B: ngày nghiệp vụ | K: thời điểm hệ thống biết | Kết quả kỳ vọng |
|---|---|---|
| 31/03/2026 12:00 | 13/04/2026 12:00 | Không có gói trong dữ liệu |
| 05/04/2026 12:00 | 10/04/2026 12:00 | BASIC |
| 10/04/2026 12:00 | 10/04/2026 12:00 | BASIC |
| 10/04/2026 12:00 | 13/04/2026 12:00 | PRO |
| 08/04/2026 00:00 | 13/04/2026 12:00 | PRO (đúng biên bắt đầu) |
| 07/04/2026 23:59:59 | 13/04/2026 12:00 | BASIC |
| 10/04/2026 12:00 | 01/04/2026 07:00 | Chưa có thông tin được ghi nhận |
| 10/04/2026 12:00 | 12/04/2026 09:00 | PRO (đúng biên ghi nhận mới) |

Ngoài các phép thử bảng, cần kiểm chứng:

1. **Chồng lấn:** chèn thêm một gói khác có valid và known period cùng giao nhau cho cùng khách; ràng buộc phải từ chối.
2. **Không chồng:** hai hàng chung valid period nhưng known period không giao nhau phải được chấp nhận.
3. **Atomicity:** mô phỏng lỗi khi thêm phiên bản mới; transaction không để lại phiên bản cũ bị đóng dở.
4. **Đồng thời:** hai yêu cầu chỉnh cùng khách phải được serialize, xung đột hoặc retry an toàn theo quy tắc.
5. **Idempotency:** phát lại cùng quyết định không sinh thêm các khoảng trùng hoặc một phiên bản “đính chính” giả.
6. **Múi giờ:** hợp đồng định nghĩa hiệu lực theo ngày địa phương; chuyển đổi sang thời điểm UTC phải đúng cả khi có DST ở những múi giờ áp dụng.
7. **Ghi nhận muộn và nhiều lần sửa:** sau hai lần hiệu chỉnh ngày hiệu lực, truy vấn theo từng K lịch sử phải tái tạo đúng những gì từng được chấp nhận.
8. **Đối soát projection:** bảng hiện tại/cache phải trùng với lát cắt mới nhất theo quy tắc độ trễ.
9. **Retention:** truy vấn ngoài khoảng lịch sử được giữ phải trả trạng thái thiếu dữ liệu tường minh.

Bảng kiểm thử là một **hợp đồng về ngữ nghĩa thời gian**: nếu đổi cấu trúc lưu trữ từ bảng version sang event store hoặc document collection, các đáp án nghiệp vụ vẫn phải nhất quán.

## 13. Bài thực hành: thiết kế lịch sử giá theo thời gian

Một công ty áp dụng giá dịch vụ theo khu vực. Nhân viên giá thường duyệt bảng giá hôm nay nhưng cho hiệu lực từ đầu tháng sau; đôi khi phát hiện một mức giá đã được nhập sai và phải đính chính cho kỳ trước. Bộ phận hỗ trợ cần trả lời:

> “Với hợp đồng số 9001, mức giá nào có hiệu lực ngày 15/07 theo thông tin hiện nay? Và khi hóa đơn được phát hành ngày 16/07, hệ thống lúc đó đang ghi nhận giá nào?”

Hãy thiết kế bằng các bước:

1. Xác định thực thể **contract_price**, khóa nhận dạng hợp đồng + loại giá/khu vực, nguồn phê duyệt và căn cứ xuất hóa đơn.
2. Chỉ rõ thời điểm nghiệp vụ **B = 15/07** và thời điểm kiến thức **K = lúc hóa đơn được hệ thống tạo hoặc chốt**, có thể khác ngày ghi trên hóa đơn.
3. Chọn biểu diễn **valid_period** và **known_period**, quy ước đầu/cuối nửa mở, timezone và độ chính xác.
4. Mô tả quá trình đổi giá có hiệu lực tương lai, sau đó một lần đính chính hồi tố; mỗi thay đổi phải giữ được lát cắt kiến thức trước nó.
5. Đặt bất biến chống hai mức giá cùng có hiệu lực tại một cặp **(B, K)** cho cùng loại giá, đồng thời xác định có bắt buộc luôn có một mức giá hay không.
6. Viết hai truy vấn as-of với cùng B nhưng khác K, dự kiến kết quả và trường hợp không có dữ liệu.
7. Đề xuất cách giữ bằng chứng giá đã dùng để chốt hóa đơn: lưu tham chiếu tới phiên bản giá/ảnh chụp điều khoản đã áp dụng, thay vì để hóa đơn luôn tính lại theo lịch sử giá mới nhất.

**Gợi ý mở rộng:** nếu ngày 20/07 hệ thống biết giá có hiệu lực từ 10/07 thấp hơn giá ban đầu, truy vấn **(B = 15/07, K = 16/07)** phải vẫn giải thích giá hệ thống đã dùng khi tạo hóa đơn. Truy vấn **(B = 15/07, K = 21/07)** phản ánh giá hiệu lực mới được đính chính. Việc xử lý khoản chênh lệch là **một nghiệp vụ điều chỉnh hóa đơn riêng**, không phải hậu quả tự động của câu truy vấn.

## 14. Checklist chốt thiết kế

Trước khi phê duyệt một lược đồ temporal, nhóm phát triển và người phụ trách nghiệp vụ nên thống nhất:

- **Định nghĩa:** giá trị nào có hiệu lực vào B, hệ thống nào được coi là nguồn có thẩm quyền khi hỏi “đã biết ở K”?
- **Nguồn thời gian:** valid time do quyết định nào cung cấp, recorded time do thành phần nào cấp, và có cần commit-time chính xác không?
- **Lược đồ:** khoảng thời gian và múi giờ được biểu diễn ra sao, có phiên bản trước và nguồn chỉnh sửa không?
- **Ràng buộc:** có cho phép khoảng trống hoặc chồng lấn; khóa nào xác định một thực thể và loại giá trị theo thời gian?
- **Transaction:** sửa hồi tố được chia khoảng và ghi nguyên tử thế nào, xử lý retry và ghi đồng thời ra sao?
- **Truy vấn:** định nghĩa as-of **(B, K)**, phạm vi retention và phản hồi khi dữ liệu thiếu đã được kiểm thử chưa?
- **Hậu quả nghiệp vụ:** quyết định mới có làm thay đổi báo cáo/hóa đơn đã chốt hay yêu cầu nghiệp vụ điều chỉnh tách biệt?
- **Khả năng tiến hóa:** khi đổi schema, đổi công nghệ lưu trữ hoặc chuyển dữ liệu lịch sử, có bảo toàn các câu trả lời theo B và K không?

Điểm cốt lõi của **thời gian và lịch sử** là phân biệt **sự thật có hiệu lực ở thế giới nghiệp vụ** với **thông tin hệ thống đã ghi nhận tại một thời điểm**. Hai trục này có thể bằng nhau, nhưng khi khác nhau, một mô hình chỉ có **updated_at** hoặc chỉ có **valid_from** không đủ để diễn giải cả hai. Thiết kế tốt phải làm rõ câu hỏi thời gian trước, rồi chọn cấu trúc, ràng buộc, chỉ mục và cơ chế ghi phù hợp để câu trả lời luôn có thể kiểm chứng.
