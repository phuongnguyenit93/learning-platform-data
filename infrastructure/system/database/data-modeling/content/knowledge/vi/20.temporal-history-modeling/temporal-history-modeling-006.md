# Mô hình hai chiều thời gian để xử lý điều chỉnh hồi tố

## 1. Bài toán: một quyết định mới làm thay đổi cách hiểu về quá khứ

Trong **DATABASE_DATA_MODELING**, việc chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu cần làm rõ không chỉ **thực thể, quan hệ, khóa và ràng buộc**, mà còn cả **hai câu hỏi thời gian**: giá trị có hiệu lực khi nào trong nghiệp vụ, và hệ thống đã biết hoặc chấp nhận giá trị ấy từ khi nào.

Hãy xét hợp đồng dịch vụ số **9001** với đơn giá thuê bao:

- Ban đầu, hệ thống biết đơn giá là **100.000 VND/tháng**, có hiệu lực từ **01/01/2026**.
- Ngày **10/03/2026**, hệ thống nhận một quyết định cho biết giá mới **120.000 VND/tháng** có hiệu lực hồi tố từ **01/02/2026**.
- Ngày **20/03/2026**, bộ phận nghiệp vụ đính chính: quyết định ngày 10/03 đã nhập **sai ngày hiệu lực**. Giá 120.000 thực ra phải áp dụng từ **15/02/2026**, nên từ 01/02 đến trước 15/02 vẫn phải là 100.000.

Tại ngày 15/03, hệ thống từng tin mức giá của **10/02** là **120.000**. Sau điều chỉnh ngày 20/03, mức giá có hiệu lực của **10/02** theo thông tin mới nhất là **100.000**. Cả hai kết quả đều quan trọng cho những câu hỏi khác nhau:

> “Giá nào được coi là đúng cho ngày 10/02 theo thông tin đã xác nhận hiện nay?”

> “Khi phát hành hóa đơn vào ngày 15/03, hệ thống lúc ấy đã ghi nhận giá nào cho ngày 10/02?”

Nếu lưu đè một hàng giá hiện tại, câu hỏi thứ hai không còn lời giải. Nếu chỉ ghi lịch sử các lần cập nhật mà không lưu ngày hiệu lực, câu hỏi thứ nhất có thể sai. Để giữ **lịch sử của chính các diễn giải về quá khứ**, cần xem xét **mô hình hai chiều thời gian — bitemporal data modeling**.

Bài học thuộc chương **Thời gian và lịch sử**, tập trung vào cách biểu diễn, cập nhật và kiểm chứng khi một quyết định được ghi nhận muộn, bị sửa ngày hiệu lực hoặc bị thay thế hồi tố. Nội dung vận dụng tư duy mô hình hóa trong cơ sở dữ liệu quan hệ, đồng thời chỉ ra cách chuyển ý tưởng sang document, graph và kho phân tích.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **thời gian có hiệu lực nghiệp vụ** với **thời gian hệ thống ghi nhận**, giải thích vì sao điều chỉnh hồi tố có thể làm thay đổi câu trả lời cho cùng một ngày nghiệp vụ.
2. Thiết kế bảng bitemporal với hai khoảng thời gian, khóa nghiệp vụ và quy tắc chống chồng lấn đúng theo **cả hai chiều**.
3. Thực hiện một lần điều chỉnh hồi tố bằng cách **đóng thời kỳ kiến thức cũ, chia lại các khoảng hiệu lực và mở thời kỳ kiến thức mới**.
4. Viết truy vấn theo hai tham số thời gian, kiểm chứng kết quả trước/sau sửa và phân biệt chúng với dữ liệu giao dịch đã chốt.
5. Nhận diện những giới hạn về đồng thời, thời điểm commit, sự kiện đến muộn, lịch sử không đầy đủ, retention và chi phí vận hành.

## 2. Hai trục thời gian mang hai ý nghĩa khác nhau

### 2.1. Valid time: khi nào thông tin đúng trong nghiệp vụ?

**Valid time** là thời gian mà một giá trị được nghiệp vụ xem là có hiệu lực. Ví dụ đơn giá 120.000 VND chỉ có hiệu lực từ 15/02/2026, dù quyết định được hệ thống ghi nhận vào tháng 3.

Đối với giá trị kéo dài theo ngày, thường dùng khoảng:

~~~text
valid_period = [valid_from, valid_to)
~~~

Khoảng **[15/02, không giới hạn)** bắt đầu đúng ngày 15/02 và chưa có ngày kết thúc được xác định. Khoảng **[01/01, 15/02)** gồm ngày 01/01 đến hết 14/02, nhưng không chứa ngày 15/02.

**Valid time không nhất thiết là thời điểm một nhân viên bấm nút lưu**, cũng không nhất thiết là thời điểm khách hàng ký quyết định. Một quyết định có thể được ký ngày 05/03 nhưng quy định hiệu lực từ 01/02.

### 2.2. Known/system time: khi nào hệ thống chấp nhận thông tin?

**Known time**, còn gọi là **recorded/system time** khi được định nghĩa phù hợp, biểu diễn thời kỳ hệ thống coi một phiên bản là thông tin đang được chấp nhận. Dùng khoảng:

~~~text
known_period = [known_from, known_to)
~~~

Nếu phiên bản được ghi nhận ngày 10/03 và bị thay thế ngày 20/03:

~~~text
known_period = [10/03/2026, 20/03/2026)
~~~

Phiên bản ấy **vẫn tồn tại trong lịch sử**, nhưng không còn được hệ thống coi là cách hiểu mới nhất kể từ 20/03. Điều này cho phép truy vấn **“hệ thống đã tin điều gì vào 15/03?”**.

Cần định nghĩa chính xác ý nghĩa **“hệ thống biết”**. Trong một giải pháp ứng dụng tự quản lý bitemporal, đó có thể là thời điểm thông tin được chấp nhận vào nguồn dữ liệu có thẩm quyền. Đây **không tự động là thời điểm transaction đã commit**. Để chứng minh chính xác trạng thái đã commit tại mọi thời điểm tuyệt đối, cần cơ chế system-versioning hoặc commit ordering với bảo đảm phù hợp, không chỉ một cột thời gian lấy trước COMMIT.

### 2.3. Không nhầm với thời gian của sự kiện và pipeline

| Mốc thời gian | Câu hỏi giải quyết | Ví dụ |
|---|---|---|
| **Valid time** | Giá có hiệu lực trong nghiệp vụ từ khi nào? | 15/02 |
| **Decision/occurred time** | Quyết định hoặc hành động thực tế xảy ra khi nào? | Quyết định được ký 09/03 |
| **Received time** | Hệ thống nhận tài liệu/thông điệp khi nào? | API nhận vào 10/03 |
| **Known time** | Hệ thống chấp nhận phiên bản thông tin khi nào? | Thông tin được ghi nhận ngày 10/03 |
| **Processing time** | Worker xử lý dữ liệu lúc nào? | Worker chạy lại ngày 11/03 |
| **Commit time** | Transaction trở nên bền vững, khả kiến theo quy tắc DB khi nào? | Mốc commit của transaction |

Các mốc có thể gần nhau trong ứng dụng đơn giản nhưng khác nhau khi sự kiện đến trễ, xử lý lại hoặc có thay đổi hồi tố. Việc có sáu cột timestamp chưa bảo đảm hệ thống đã mô hình hóa đúng; phải biết mỗi cột dùng để trả lời câu hỏi gì và do nguồn nào cấp.

## 3. Theo dõi cùng một hợp đồng qua ba lần thay đổi hiểu biết

Ta chọn **ngày nghiệp vụ** để đánh dấu valid time và **thời điểm UTC** để đánh dấu known time. Quy ước mọi khoảng là **đầu đóng, cuối mở**: [from, to).

### 3.1. Lần ghi nhận đầu tiên: 01/01

Ngày 01/01 lúc 08:00 UTC, hệ thống biết hợp đồng 9001 có mức giá 100.000 kể từ ngày 01/01:

~~~text
Phiên bản V1
Giá:          100.000
Valid:        [01/01, +∞)
Known:        [01/01 08:00 UTC, +∞)
~~~

Nếu được hỏi trong tháng 2, với kiến thức hệ thống lúc đó, mọi ngày từ 01/01 đều có giá 100.000.

### 3.2. Lần thay đổi thứ nhất: 10/03, hiệu lực hồi tố từ 01/02

Ngày 10/03 lúc 09:00 UTC, hệ thống nhận quyết định giá 120.000 có hiệu lực từ 01/02. Phải giữ điều mà hệ thống từng tin trước ngày 10/03, đồng thời tạo timeline hiệu lực mới:

~~~text
V1 (thông tin cũ):
  100.000, valid [01/01, +∞)
           known [01/01 08:00, 10/03 09:00)

V2 (theo hiểu biết mới):
  100.000, valid [01/01, 01/02)
           known [10/03 09:00, +∞)

V3 (theo hiểu biết mới):
  120.000, valid [01/02, +∞)
           known [10/03 09:00, +∞)
~~~

**Không được xóa V1**: nó là bằng chứng rằng trước thời điểm 10/03 hệ thống từng tin giá 100.000 áp dụng liên tục.

### 3.3. Lần đính chính thứ hai: 20/03, ngày hiệu lực đúng là 15/02

Ngày 20/03 lúc 09:00 UTC, doanh nghiệp xác nhận ngày hiệu lực 01/02 ở quyết định trước đã bị nhập sai. Giá 120.000 phải bắt đầu từ 15/02.

Ta đóng **known_period** của V2 và V3 ở mốc 20/03, sau đó tạo hai đoạn hiệu lực mới:

~~~text
V2 (kiến thức từ 10/03 đến trước 20/03):
  100.000, valid [01/01, 01/02)
           known [10/03 09:00, 20/03 09:00)

V3 (kiến thức từ 10/03 đến trước 20/03):
  120.000, valid [01/02, +∞)
           known [10/03 09:00, 20/03 09:00)

V4 (kiến thức từ 20/03):
  100.000, valid [01/01, 15/02)
           known [20/03 09:00, +∞)

V5 (kiến thức từ 20/03):
  120.000, valid [15/02, +∞)
           known [20/03 09:00, +∞)
~~~

Tất cả các phiên bản từ V1 tới V5 vẫn được lưu, vì mỗi phiên bản chứng minh **một cách hiểu có hiệu lực trong một thời kỳ hệ thống ghi nhận nhất định**.

### 3.4. Bảng trạng thái sau hai lần điều chỉnh

| Phiên bản | Số tiền | Khoảng hiệu lực nghiệp vụ | Khoảng thông tin được hệ thống chấp nhận |
|---|---:|---|---|
| V1 | 100.000 | [01/01, +∞) | [01/01 08:00, 10/03 09:00) |
| V2 | 100.000 | [01/01, 01/02) | [10/03 09:00, 20/03 09:00) |
| V3 | 120.000 | [01/02, +∞) | [10/03 09:00, 20/03 09:00) |
| V4 | 100.000 | [01/01, 15/02) | [20/03 09:00, +∞) |
| V5 | 120.000 | [15/02, +∞) | [20/03 09:00, +∞) |

Các mốc **known time** ở đây đều thuộc năm 2026 và tính theo UTC. Trong bảng rút gọn, ngày ở **valid time** cũng thuộc năm 2026.

Đồ thị khái niệm dưới đây thể hiện hai lần thay đổi hiểu biết:

~~~mermaid
flowchart TD
    A["01/01: Biết giá 100.000<br/>cho toàn kỳ từ 01/01"] --> B["10/03: Quyết định 120.000<br/>hiệu lực từ 01/02"]
    B --> C["Đóng V1<br/>Tạo V2 + V3"]
    C --> D["20/03: Đính chính<br/>mốc đúng là 15/02"]
    D --> E["Đóng V2 + V3<br/>Tạo V4 + V5"]
~~~

Đây là chuỗi **phiên bản của kiến thức hệ thống**. Giá nghiệp vụ tại một ngày có thể thay đổi khi ta đổi thời điểm đánh giá kiến thức, dù bản thân ngày cần hỏi không đổi.

## 4. Truy vấn bitemporal thực chất dùng hai tham số

Gọi:

- **B** (*business time*): ngày nghiệp vụ cần xác định giá có hiệu lực.
- **K** (*knowledge time*): thời điểm ta muốn đứng vào để xem **hệ thống đã chấp nhận thông tin nào**.

Một hàng được chọn nếu đồng thời:

~~~text
valid_from <= B < valid_to
known_from <= K < known_to
~~~

Với biên trên không giới hạn, coi mọi thời điểm sau biên dưới là nằm trong khoảng.

### 4.1. Cùng ngày nghiệp vụ, kết quả thay đổi theo K

| B: ngày cần tính giá | K: hệ thống biết vào | Giá phải trả về | Phiên bản |
|---|---|---:|---|
| 10/02 | 01/03 lúc 12:00 | 100.000 | V1 |
| 10/02 | 15/03 lúc 12:00 | 120.000 | V3 |
| 10/02 | 21/03 lúc 12:00 | 100.000 | V4 |
| 20/02 | 15/03 lúc 12:00 | 120.000 | V3 |
| 20/02 | 21/03 lúc 12:00 | 120.000 | V5 |
| 15/02 | 21/03 lúc 12:00 | 120.000 | V5 |
| 14/02 | 21/03 lúc 12:00 | 100.000 | V4 |

Đặc biệt, hai hàng **B = 10/02, K = 15/03** và **B = 10/02, K = 21/03** khác nhau. Đó chính là lý do tồn tại của bitemporal trong xử lý điều chỉnh hồi tố.

Nếu **K** sớm hơn thời điểm hệ thống ghi nhận đầu tiên, truy vấn không trả bản ghi. Nó có nghĩa **không có thông tin đã được ghi nhận trong lịch sử đang lưu ở K**, chứ không tự động có nghĩa hợp đồng không tồn tại.

### 4.2. Tại sao chỉ dùng updated_at là sai?

Một hàng đang chứa giá 100.000 cho tháng 2, với **updated_at = 20/03**, không nói được ngày 15/03 hệ thống từng tin tháng 2 có giá 120.000. Ngay cả khi có audit log “ngày 20/03 sửa mức giá”, còn phải biết **đoạn valid time nào bị sửa** và **các đoạn nào từng được hệ thống chấp nhận**.

Mô hình bitemporal biểu diễn trực tiếp hai điều kiện thời gian, giúp truy vấn không phải dựa vào suy luận không rõ ràng từ các lệnh UPDATE rời rạc.

## 5. Cách thiết kế khóa và ràng buộc cho hai chiều thời gian

Một bản ghi bitemporal có thể được hiểu là **một khẳng định của hệ thống về giá trị tại các ngày nghiệp vụ**.

Với hợp đồng dịch vụ, chọn:

- **Thực thể gốc:** hợp đồng, định danh bằng **contract_id**.
- **Loại giá:** **rate_kind**, ví dụ BASE hoặc ADDON. Mỗi loại là một tập giá có quy tắc riêng.
- **Giá trị phiên bản:** **monthly_amount**.
- **Hai khoảng:** **valid_period** theo ngày nghiệp vụ và **known_period** theo timestamp.
- **Bằng chứng:** **decision_ref**, **correction_reason** và tham chiếu tới quyết định được điều chỉnh.
- **Khóa kỹ thuật:** **version_id**, chỉ nhận diện hàng, không đại diện cho thứ tự hiệu lực.

Bất biến quan trọng:

> Với một cặp **(contract_id, rate_kind)** và một cặp thời điểm **(B, K)**, có **tối đa một** mức giá được hệ thống chấp nhận có hiệu lực.

Để kiểm tra, **hai phiên bản chỉ xung đột nếu chúng có cùng khóa nghiệp vụ và chồng nhau đồng thời trên cả valid time và known time**.

### 5.1. Vì sao không cấm mọi khoảng valid chồng nhau?

V1 và V3 đều có valid period chứa ngày 10/02. Nhưng V1 chỉ được hệ thống chấp nhận trước 10/03, còn V3 bắt đầu được chấp nhận từ 10/03. Chúng **không cùng đúng tại một cặp (B, K)**.

Nếu đặt một constraint cấm valid overlap trên mọi hàng bất kể known period, database sẽ từ chối lưu V3, tức không thể ghi lịch sử điều chỉnh hồi tố.

Ngược lại, nếu không kiểm tra known time, hai hàng cùng valid period và cùng known period có thể cùng trả về, khiến một cặp (B, K) cho hai mức giá.

### 5.2. Điều kiện giao nhau theo hai chiều

Với hai hàng A và B cùng khóa nghiệp vụ:

~~~text
conflict(A, B) =
    overlaps(A.valid_period, B.valid_period)
    AND overlaps(A.known_period, B.known_period)
~~~

Đây là ràng buộc **hai chiều**, khác với một hệ thống chỉ quản lý lịch hiệu lực mới nhất. Nó phải được thực thi đủ an toàn dưới ghi đồng thời, thay vì chỉ kiểm tra trước khi INSERT bằng một truy vấn không khóa.

## 6. Lược đồ PostgreSQL minh họa

PostgreSQL có kiểu **daterange** cho khoảng ngày và **tstzrange** cho khoảng timestamp có timezone. Toán tử **@>** kiểm tra một khoảng chứa điểm thời gian; **&&** kiểm tra hai khoảng giao nhau.

Dưới đây là lược đồ **bitemporal do ứng dụng quản lý**, không phải cơ chế system-versioning tự động của PostgreSQL:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE service_contract (
    contract_id   bigint PRIMARY KEY,
    contract_code text NOT NULL UNIQUE
);

CREATE TABLE contract_rate_bitemporal (
    version_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contract_id       bigint NOT NULL
                      REFERENCES service_contract(contract_id),
    rate_kind         text NOT NULL,
    monthly_amount    numeric(14, 2) NOT NULL
                      CHECK (monthly_amount >= 0),
    valid_period      daterange NOT NULL,
    known_period      tstzrange NOT NULL,
    decision_ref      text NOT NULL,
    correction_of     text,
    correction_reason text,

    CONSTRAINT ck_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),
    CONSTRAINT ck_known_period
        CHECK (
            NOT isempty(known_period)
            AND NOT lower_inf(known_period)
            AND lower_inc(known_period)
            AND NOT upper_inc(known_period)
        ),

    CONSTRAINT ex_one_rate_for_each_business_and_known_time
        EXCLUDE USING gist (
            contract_id WITH =,
            rate_kind WITH =,
            valid_period WITH &&,
            known_period WITH &&
        )
);
~~~

Ý nghĩa các ràng buộc:

| Thành phần | Trách nhiệm |
|---|---|
| **PRIMARY KEY(version_id)** | Phân biệt từng phiên bản được lưu |
| **FOREIGN KEY(contract_id)** | Phiên bản thuộc hợp đồng tồn tại |
| **NOT NULL** | Không để khóa và hai khoảng trở thành NULL, làm kiểm tra mất hiệu lực |
| **CHECK NOT isempty** | Cấm khoảng rỗng |
| **CHECK NOT lower_inf** | Buộc mỗi phiên bản có điểm bắt đầu rõ |
| **CHECK lower_inc AND NOT upper_inc** | Thống nhất khoảng nửa mở **[from, to)** |
| **EXCLUDE USING gist** | Cấm hai hàng cùng contract_id và rate_kind chồng nhau **trên cả hai trục** |

Hỗ trợ của **btree_gist** cho phép kết hợp phép so sánh bằng trên khóa thường với toán tử giao khoảng trong GiST. Cấu trúc **EXCLUDE** bảo vệ tính **duy nhất tại (B, K)**, nhưng không tự bảo đảm **mọi ngày đều có giá**. Nếu nghiệp vụ yêu cầu đúng một mức giá ở mọi ngày hoạt động, cần kiểm tra thêm **khoảng trống** trên lát cắt known time mới nhất và phạm vi ngày hoạt động của hợp đồng.

Một thuộc tính như **currency_code** không có trong bảng minh họa vì giả định tiền tệ là thuộc tính cố định của hợp đồng hoặc toàn bộ ví dụ dùng VND. Nếu mỗi hợp đồng có nhiều loại tiền tệ đồng thời, phải thêm currency vào **khóa nghiệp vụ và constraint**, nếu không hai giá độc lập có thể bị cấm nhầm.

### 6.1. Khóa tự tăng không phải trục thời gian

**version_id = 5** chỉ nói đây là một hàng khác **version_id = 4**. Nó không nói giá V5 có hiệu lực muộn hơn mọi giá trị khác trong valid time. Một quyết định có hiệu lực hồi tố từ tháng 2 có thể được chèn tháng 3 sau một quyết định có hiệu lực tương lai từ tháng 7.

Vì vậy truy vấn “giá áp dụng tại B với kiến thức K” phải lọc **hai khoảng**, không phải chọn **MAX(version_id)**.

### 6.2. Dùng khoảng nửa mở để giữ biên chuyển tiếp

~~~text
Giá 100.000: valid [01/01, 15/02)
Giá 120.000: valid [15/02, +∞)
~~~

Ngày **15/02** chỉ thuộc giá 120.000. Nếu hai khoảng đóng cả hai đầu, ngày chuyển tiếp có thể khớp cả hai mức giá; nếu dùng “hết 14/02 23:59:59”, hệ thống có nguy cơ tạo gap khi kiểu timestamp hỗ trợ phần giây nhỏ hơn.

Với **daterange** theo ngày, mốc 15/02 là **ngày đầu tiên được bao gồm của phiên bản sau**. Với **tstzrange** theo thời điểm, biên phải cũng được loại trừ theo logic tương tự.

## 7. Ghi nhận ban đầu: tạo phiên bản V1

Chạy dữ liệu minh họa trong một cơ sở dữ liệu thử nghiệm:

~~~sql
INSERT INTO service_contract (contract_id, contract_code)
VALUES (9001, 'CONTRACT-9001');

INSERT INTO contract_rate_bitemporal (
    contract_id,
    rate_kind,
    monthly_amount,
    valid_period,
    known_period,
    decision_ref
)
VALUES (
    9001,
    'BASE',
    100000,
    daterange(DATE '2026-01-01', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-01-01 08:00:00+00',
        NULL, '[)'
    ),
    'RATE-INITIAL'
);
~~~

Mốc thời gian ghi nhận ở ví dụ là **giá trị cố định để học và kiểm chứng**. Ứng dụng thực tế không được tự gán tùy ý thời điểm đã biết; cần một chính sách lấy thời gian thống nhất và bảo đảm nguồn dữ liệu quyết định đã được xác nhận.

Trước điều chỉnh, một truy vấn B = 10/02, K = 01/03 sẽ trả 100.000.

## 8. Điều chỉnh hồi tố lần thứ nhất: 10/03

Quyết định **RATE-MAR10** cho biết giá 120.000 có hiệu lực từ 01/02. Hệ thống phải đóng thời kỳ kiến thức ban đầu và tạo hai đoạn valid time được chấp nhận kể từ 10/03.

Quy trình chung:

1. Khóa phạm vi hợp đồng để tránh hai tác vụ sửa lịch giá cạnh tranh.
2. Đọc các phiên bản **known_period hiện mở** và xác định timeline hiệu lực đang được chấp nhận.
3. Xác minh thời điểm cắt chuyển đổi kiến thức **K1**, nguồn quyết định và các khoảng bị ảnh hưởng.
4. Đóng known_period của những bản ghi sẽ được thay thế tại K1.
5. Tạo các đoạn valid time mới, tất cả cùng bắt đầu known_period tại K1.
6. Kiểm tra kết quả và commit nguyên tử.

Với dữ liệu chỉ có V1, thao tác SQL minh họa:

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

UPDATE contract_rate_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-03-10 09:00:00+00',
    '[)'
)
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
RETURNING version_id;

-- Phải có đúng 1 hàng V1 bị đóng.
-- Nếu không đúng, ứng dụng/stored procedure phải ROLLBACK,
-- xác định lại timeline và xử lý xung đột.

INSERT INTO contract_rate_bitemporal (
    contract_id, rate_kind, monthly_amount,
    valid_period, known_period,
    decision_ref, correction_reason
)
VALUES
(
    9001, 'BASE', 100000,
    daterange(DATE '2026-01-01', DATE '2026-02-01', '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-10 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR10', 'Giữ giá cũ trước ngày hiệu lực mới'
),
(
    9001, 'BASE', 120000,
    daterange(DATE '2026-02-01', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-10 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR10', 'Thay đổi giá có hiệu lực hồi tố'
);

COMMIT;
~~~

**Không được commit nếu UPDATE tác động sai số hàng dự kiến.** Đoạn SQL minh họa trình tự thao tác; trong code sản xuất phải kiểm tra kết quả **RETURNING**, quyền phê duyệt, idempotency và mọi quy tắc liên quan **trước khi cho phép COMMIT**.

Việc UPDATE **known_period** của V1 là thao tác đóng thời kỳ kiến thức cũ; nó không xóa V1. Các mốc valid của V1 vẫn được giữ nguyên để chứng minh hệ thống từng tin gì. Nếu yêu cầu kiểm toán bắt buộc mọi bản ghi lưu trữ là **append-only về mặt vật lý**, có thể cần event/audit log bất biến hoặc system-versioning chuyên dụng, vì cập nhật cột known_period vẫn là một UPDATE.

## 9. Đính chính hồi tố lần thứ hai: 20/03

Ngày 20/03, bộ phận nghiệp vụ xác nhận rằng ngày hiệu lực mới **không phải 01/02 mà là 15/02**. Mốc mới là **K2 = 20/03 09:00 UTC**.

Hệ thống đang có hai phiên bản known-open, V2 và V3. Chúng phải được đóng tại K2, rồi thay bằng V4 và V5. Dù giá 100.000 trước ngày 01/02 không thay đổi, V2 vẫn có thể được đóng và thay bằng V4 để hình thành một **snapshot đầy đủ của timeline có hiệu lực** cho thời kỳ kiến thức mới.

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

UPDATE contract_rate_bitemporal
SET known_period = tstzrange(
    lower(known_period),
    TIMESTAMPTZ '2026-03-20 09:00:00+00',
    '[)'
)
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
RETURNING version_id;

-- Phải có đúng 2 hàng (V2, V3) bị đóng.
-- Nếu khác, ROLLBACK, đọc lại các phiên bản hiện mở.

INSERT INTO contract_rate_bitemporal (
    contract_id, rate_kind, monthly_amount,
    valid_period, known_period,
    decision_ref, correction_of, correction_reason
)
VALUES
(
    9001, 'BASE', 100000,
    daterange(DATE '2026-01-01', DATE '2026-02-15', '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-20 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR20', 'RATE-MAR10',
    'Đính chính ngày bắt đầu giá mới'
),
(
    9001, 'BASE', 120000,
    daterange(DATE '2026-02-15', NULL, '[)'),
    tstzrange(
        TIMESTAMPTZ '2026-03-20 09:00:00+00',
        NULL, '[)'
    ),
    'RATE-MAR20', 'RATE-MAR10',
    'Giá mới chỉ có hiệu lực từ 15/02'
);

COMMIT;
~~~

**Vì sao đóng cả V2 dù mức giá trước tháng 2 không đổi?** Ở chiến lược minh họa này, mỗi lần điều chỉnh tạo **một tập các đoạn hợp lệ cho toàn bộ lịch giá**, giúp truy vấn “timeline theo K” dễ kiểm tra và đối soát. Một chiến lược khác có thể chỉ đóng/mở **những đoạn bị ảnh hưởng** và giữ các đoạn không thay đổi tiếp tục có known_period mở; khi đó phải tính toán cẩn thận để không tạo gap hoặc overlap trong bất kỳ lát cắt K nào.

Hai chiến lược đều có thể hợp lệ. Điều quan trọng là quy ước nhất quán, lưu được thông tin cũ, có thể truy vấn theo mọi K trong phạm vi retention, và thực thi nguyên tử.

### 9.1. Không suy ra số hàng cần đóng từ một phép UPDATE chung

Ví dụ chỉ có hai phiên bản known-open trước ngày 20/03. Trong thực tế hợp đồng có thể có nhiều giai đoạn giá khác nhau, quyết định đã lên lịch tương lai hoặc những điều chỉnh hợp lệ trước đó. Một câu lệnh đóng tất cả bản known-open nhưng chỉ chèn lại hai hàng sẽ **làm mất các giai đoạn khác**.

Vì vậy thuật toán tổng quát phải **đọc timeline thực tế**, tính một tập khoảng mới đầy đủ hoặc chỉ cập nhật những đoạn bị ảnh hưởng, rồi kiểm tra tính phủ và toàn vẹn trước khi ghi.

### 9.2. Bản đính chính phải chỉ ra nguồn và lý do

**decision_ref = RATE-MAR20** nói quyết định nào xác nhận timeline mới. **correction_of = RATE-MAR10** nói quyết định nào đang được điều chỉnh. **correction_reason** giải thích lỗi ngày hiệu lực.

Nếu cần truy vết trách nhiệm chi tiết, có thể tách bảng **rate_decision** chứa thông tin người duyệt, chứng từ, thời gian nhận, thời gian phê duyệt và trạng thái xử lý. Bảng bitemporal liên kết tới quyết định đó bằng khóa ngoại. Không nhồi toàn bộ payload tài liệu và dữ liệu cá nhân vào mỗi hàng phiên bản khi chỉ cần tham chiếu.

## 10. Truy vấn “as of” theo cả ngày nghiệp vụ và thời điểm biết

Sau khi ghi đủ V1–V5, truy vấn kiểu PostgreSQL:

~~~sql
SELECT
    version_id,
    monthly_amount,
    valid_period,
    known_period,
    decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND valid_period @> DATE '2026-02-10'
  AND known_period @>
      TIMESTAMPTZ '2026-03-15 12:00:00+00';
~~~

**Kết quả kỳ vọng: 120.000 (V3)**, vì ở 15/03 hệ thống đang chấp nhận giá 120.000 cho ngày 10/02.

Giữ ngày nghiệp vụ 10/02, thay thời điểm hệ thống biết:

~~~sql
SELECT monthly_amount, decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND valid_period @> DATE '2026-02-10'
  AND known_period @>
      TIMESTAMPTZ '2026-03-21 12:00:00+00';
~~~

**Kết quả kỳ vọng: 100.000 (V4)**. Hai truy vấn chỉ khác **K**, không khác **B**.

### 10.1. Truy vấn timeline theo một mốc kiến thức

Muốn xem **toàn bộ lịch giá mà hệ thống đã chấp nhận vào 15/03**, không cố định B mà chỉ lọc K:

~~~sql
SELECT
    monthly_amount,
    lower(valid_period) AS valid_from,
    upper(valid_period) AS valid_to,
    decision_ref
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND known_period @>
      TIMESTAMPTZ '2026-03-15 12:00:00+00'
ORDER BY lower(valid_period), version_id;
~~~

Trả về hai đoạn V2 và V3. Thay K thành 21/03 sẽ trả về V4 và V5.

### 10.2. Truy vấn lịch có hiệu lực theo hiểu biết hiện nay

~~~sql
SELECT
    monthly_amount,
    valid_period
FROM contract_rate_bitemporal
WHERE contract_id = 9001
  AND rate_kind = 'BASE'
  AND upper_inf(known_period)
ORDER BY lower(valid_period);
~~~

Điều kiện **upper_inf(known_period)** chọn các bản ghi có khoảng kiến thức **chưa đóng**. Đây là cách hữu ích khi ứng dụng luôn duy trì một tập phiên bản known-open đại diện cho hiểu biết mới nhất.

Nếu cần xác định giá **hôm nay** theo lịch của một thị trường cụ thể, phải kết hợp lọc **valid_period chứa ngày nghiệp vụ hiện tại**. Một bản known-open cũng có thể có hiệu lực **trong tương lai**.

### 10.3. Không có hàng không có nghĩa giá bằng 0

Nếu B trước ngày hợp đồng được ghi nhận có hiệu lực, hoặc K trước lần hệ thống biết đầu tiên, truy vấn có thể không có hàng. Khi đó cần phân biệt **“không có dữ liệu trong phạm vi được lưu”**, **“chưa được phê duyệt”**, **“hợp đồng chưa có hiệu lực”** và **“hệ thống chưa ghi nhận”**. Không biến kết quả rỗng thành giá 0, giá đầu tiên hoặc giá hiện tại theo một quy tắc ngầm.

## 11. Thuật toán điều chỉnh hồi tố cho timeline có nhiều phiên bản

Ví dụ V1–V5 đơn giản vì chỉ có một loại giá và ít đoạn hiệu lực. Trong một hệ thống thực tế, một thay đổi hồi tố có thể giao với nhiều phiên bản đã ghi:

~~~text
Theo kiến thức hiện tại:
[01/01, 01/03)  → A
[01/03, 01/06)  → B
[01/06, 01/09)  → C
[01/09, +∞)     → D

Đính chính:
[15/02, 15/07) phải áp dụng giá X

Kết quả hợp lệ có thể là:
[01/01, 15/02) → A
[15/02, 15/07) → X
[15/07, 01/09) → C
[01/09, +∞)    → D
~~~

Không thể chỉ thay giá ở hàng B, vì khoảng điều chỉnh cắt qua **cuối A, toàn bộ B và đầu C**.

### 11.1. Các bước tính timeline mới

1. **Xác định khóa nghiệp vụ** — ví dụ hợp đồng 9001, loại giá BASE.
2. **Khóa phạm vi cập nhật** — nhằm xử lý các quyết định cạnh tranh có thứ tự.
3. **Đọc lát cắt known-open hiện tại** — danh sách phiên bản valid time được chấp nhận.
4. **Chuẩn hóa quyết định hồi tố** — xác minh ngày bắt đầu/kết thúc, kiểu tiền tệ, mức giá, nguồn phê duyệt và các quy tắc khoảng.
5. **Tính tập điểm cắt** — lấy tất cả đầu/cuối của các khoảng cũ và mới; sắp xếp để tạo những đoạn nhỏ không giao nhau.
6. **Gán giá trị cho từng đoạn** — theo quy tắc ưu tiên quyết định; giữ nguyên đoạn không bị tác động.
7. **Kiểm tra bất biến trước ghi** — không có hai mức giá cạnh tranh ở cùng B; các khoảng trống được cho phép hoặc phát hiện.
8. **Đóng/mở known-period với cùng một mốc K cho quyết định** — tạo tập phiên bản bitemporal phù hợp.
9. **Commit nguyên tử** — nếu bất kỳ phần nào thất bại, rollback toàn bộ.
10. **Phát thông báo có khả năng retry và đối soát** — khi các hệ thống khác phải cập nhật dữ liệu đọc nhanh hoặc kho phân tích.

Nếu nhóm có quy tắc **không được ghi đè quyết định giá cao hơn quyền phê duyệt**, thuật toán phải từ chối hoặc đưa yêu cầu vào trạng thái chờ xét duyệt. Không tự xem quyết định có timestamp muộn hơn là quyết định đúng hơn.

### 11.2. Các bất biến nên kiểm tra cả trước và sau ghi

| Bất biến | Cách kiểm tra |
|---|---|
| Mỗi phiên bản có valid/known period không rỗng | CHECK, kiểm tra dữ liệu đầu vào |
| Không có hai giá cùng được chấp nhận tại một (B, K) | Exclusion constraint trên cả hai range |
| Nếu nghiệp vụ cần phủ giá liên tục thì không có gap | Kiểm tra timeline tại từng lát K cần thiết |
| Mỗi sửa đổi có nguồn và lý do | Khóa tham chiếu/quy trình phê duyệt |
| Các đoạn không bị quyết định tác động được giữ đúng | So sánh timeline trước/sau ở các khoảng ngoài phạm vi điều chỉnh |
| Sự kiện gửi lại không tạo bản đính chính giả | Idempotency key của quyết định |
| Các trạng thái đã từng biết vẫn truy vấn được | Kiểm thử as-of với K trước và sau lần điều chỉnh |
| Những giao dịch đã chốt giữ nguyên dữ liệu gốc | So sánh snapshot giao dịch trước/sau sửa |

## 12. Đồng thời, thứ tự ghi nhận và tính nguyên tử

Hai nhân viên có thể đồng thời sửa cùng lịch giá:

- A phê duyệt thay đổi giá từ 01/03.
- B đính chính một quyết định trước đó và thay đổi giá từ 15/02.

Nếu cả hai đọc cùng timeline, tự tính các đoạn rồi ghi, kết quả có thể mất thay đổi của một người hoặc tạo chồng lấn. Mô hình bitemporal có hai trục thời gian nhưng **không tự giải quyết cạnh tranh transaction**.

### 12.1. Khóa theo thực thể nghiệp vụ

Trong PostgreSQL, có thể khóa hàng **service_contract** khi sửa một loại giá của hợp đồng:

~~~sql
BEGIN;

SELECT contract_id
FROM service_contract
WHERE contract_id = 9001
FOR UPDATE;

-- Sau khi có khóa:
-- 1. Đọc các phiên bản known-open.
-- 2. Tính timeline mới.
-- 3. Đóng known-period cũ và tạo known-period mới.
-- 4. Kiểm tra số hàng, ràng buộc, nguồn quyết định.
-- 5. COMMIT hoặc ROLLBACK.
~~~

Cách này tuần tự hóa các sửa đổi dùng cùng hàng hợp đồng, với điều kiện mọi đường ghi tuân thủ giao thức. Nếu hợp đồng có nhiều loại giá độc lập, có thể tạo **rate_scope** riêng cho mỗi contract_id + rate_kind để khóa chi tiết hơn.

Ngoài khóa, cần **optimistic revision** nếu lệnh được phê duyệt dựa trên timeline đã xem trước đó. Khi revision đã thay đổi, người duyệt phải xác nhận lại thay vì ứng dụng tự ghép hai quyết định có thể mâu thuẫn.

### 12.2. Một mốc cutover cho cả lần điều chỉnh

Khi đóng các phiên bản cũ và tạo phiên bản mới trong cùng quyết định, cần dùng **một mốc K thống nhất** cho tất cả các hàng liên quan. Nếu mỗi INSERT/UPDATE lấy timestamp riêng, có thể hình thành khoảng giữa hai bản được hệ thống xem là đúng hoặc tạo chồng lấn không chủ ý.

Mốc K phải lớn hơn thời điểm bắt đầu của những phiên bản đang được thay thế, theo chính sách ghi nhận. Khi retry, phải xác định lần thử lại dùng lại quyết định nào và có được phép tạo **một lần ghi nhận mới** hay không.

Một lần ghi nhận với timestamp ở cấp ứng dụng **không tự chứng minh thời điểm commit chính xác**. Nếu cần truy vấn lịch sử theo từng microsecond đúng như trạng thái transaction đã trở nên khả kiến, phải đánh giá cơ chế temporal của hệ quản trị, transaction sequence, commit metadata và mức độ tin cậy của đồng hồ.

### 12.3. Khi chuyển dữ liệu sang dịch vụ khác

Nếu bảng rate bitemporal nằm ở database A còn projection đọc nhanh, message broker hoặc kho phân tích nằm ở hệ thống khác, hai nơi không mặc nhiên có transaction chung.

Có thể dùng **transactional outbox**: ghi trạng thái bitemporal và thông điệp cần phát trong cùng transaction tại A, rồi worker gửi thông điệp có retry. Consumer phải idempotent vì việc phát lại có thể tạo giao nhận trùng. Ngoài ra cần theo dõi độ trễ projection và khả năng đối soát khi có lỗi.

Một sự kiện “RATE-MAR20 accepted” nên mang **mã quyết định, revision, khoảng bị ảnh hưởng và cơ sở dữ liệu có thẩm quyền**, không chỉ một số tiền mới, nếu consumer cần tái dựng hoặc kiểm tra các ảnh hưởng hồi tố.

## 13. Giữ bằng chứng khi sửa lịch sử liên quan đến giao dịch đã chốt

Ví dụ ngày **15/03** doanh nghiệp phát hành hóa đơn cho ngày sử dụng **10/02**, dựa trên thông tin lúc đó rằng giá là **120.000**. Ngày 20/03 dữ liệu được đính chính về 100.000 cho ngày 10/02.

Có ba sự thật cần tồn tại đồng thời:

1. Ngày 10/02, theo thông tin **hiện đã được chấp nhận**, đơn giá hiệu lực là **100.000**.
2. Ngày 15/03, hệ thống **từng biết** đơn giá của ngày 10/02 là **120.000**.
3. Hóa đơn phát hành ngày 15/03 **thực tế đã tính** mức giá 120.000; số tiền đã chốt không được tự sửa khi JOIN lại dữ liệu bitemporal.

Vì vậy hóa đơn hoặc dòng hóa đơn nên giữ **mức giá/tiền thực dùng**, loại tiền tệ, kỳ tính, mốc chốt và căn cứ tính phí:

~~~text
invoice_line
  invoice_line_id
  invoice_id
  contract_id
  service_date
  charged_unit_price
  charged_amount
  currency_code
  finalized_at
  rate_decision_ref
  rate_version_id (nếu hữu ích)
~~~

**rate_version_id** có thể trỏ tới V3 đã từng được hệ thống chấp nhận tại lúc hóa đơn tính phí. Vì V3 vẫn còn trong bảng bitemporal với known_period đã đóng, có thể tra được căn cứ lịch sử. Nhưng bản hóa đơn cũng nên lưu giá trị tiền đã chốt để tránh phải phụ thuộc vào diễn giải của mô hình lịch sử sau migration.

Nếu điều chỉnh hồi tố làm phát sinh chênh lệch, doanh nghiệp cần **chứng từ điều chỉnh, hoàn tiền hoặc bút toán bù trừ** theo quy tắc tài chính. Bitemporal trả lời “điều gì được coi là đúng và đã từng được biết”, không tự quyết định việc xử lý tiền, thuế hay thời điểm ghi nhận kế toán.

## 14. Ghi nhận sai, thay đổi quyết định và thông tin đến trễ

Không phải mọi sự kiện hồi tố đều là cùng một loại:

| Tình huống | Ngữ nghĩa | Cách mô hình nên phản ánh |
|---|---|---|
| **Sai nhập liệu** | Ngày hiệu lực đúng từ đầu nhưng hệ thống từng nhập sai | Giữ lịch sử kiến thức sai, ghi quyết định đính chính và ngày ghi nhận |
| **Quyết định mới có hiệu lực lùi** | Nghiệp vụ đến nay mới phê duyệt việc áp dụng từ quá khứ | Lưu quyết định mới, valid time lùi, known time bắt đầu khi chấp nhận |
| **Thông điệp đến trễ** | Sự kiện đã xảy ra nhưng hệ thống nhận sau | Phân biệt occurred/valid time với received/known time |
| **Hủy quyết định** | Một quyết định trước đây bị rút lại | Đóng cách hiểu cũ, tạo cách hiểu mới; lưu căn cứ rút lại |
| **Tranh chấp chưa giải quyết** | Hai nguồn khẳng định các giá trị trái nhau | Lưu trạng thái tranh chấp/nguồn chưa phê duyệt; không giả định cả hai là sự thật được chấp nhận |
| **Sửa thời gian phát hành báo cáo** | Báo cáo đã khóa nhưng dữ liệu nguồn thay đổi | Version báo cáo/snapshot và nghiệp vụ tái phát hành nếu cần |

Bitemporal là cách lưu **những khẳng định đã được hệ thống chấp nhận**; nó không phải máy xác định sự thật khách quan. Khi nguồn đầu vào mâu thuẫn, đội nghiệp vụ phải chọn quy tắc phê duyệt, quyền ưu tiên, cách xử lý tranh chấp và việc thông báo cho các bên.

### 14.1. Không nhập thiếu mốc thời gian bằng ngày giả

Nếu quyết định chỉ ghi “áp dụng từ giữa tháng 2” mà không xác định ngày chính xác, không nên tự tạo **15/02** như một thực tế đã xác minh. Có thể lưu trạng thái pending, độ chính xác thời gian, nguồn xác nhận hoặc khoảng không chắc chắn và chờ phê duyệt trước khi đưa vào timeline chính thức.

**Một khoảng được biểu diễn rõ** không đồng nghĩa **nguồn của khoảng đã đáng tin**. Cần tách kiểm tra cấu trúc dữ liệu khỏi kiểm tra bằng chứng nghiệp vụ.

## 15. Chỉ mục, truy vấn lớn và lưu trữ lịch sử

Số bản ghi bitemporal có thể tăng nhanh hơn lịch sử một trục: một lần đính chính có thể đóng và tạo lại nhiều đoạn valid time. Càng nhiều lần hồi tố, càng nhiều lớp known time.

Mẫu truy vấn phổ biến:

| Nhu cầu | Điều kiện | Gợi ý thiết kế |
|---|---|---|
| Mức giá tại (B, K) | Khóa nghiệp vụ + valid chứa B + known chứa K | GiST hỗ trợ range; đo selectivity thực tế |
| Timeline theo kiến thức hiện nay | Khóa nghiệp vụ + known_period chưa đóng | Chỉ mục từng phần hoặc projection |
| Timeline theo K lịch sử | Khóa nghiệp vụ + known chứa K | Chỉ mục range/khóa phù hợp |
| Tất cả quyết định ghi nhận trong ngày | Known_from trong một ngày, decision_ref | Chỉ mục theo nguồn quyết định và thời gian ghi nhận |
| Báo cáo số lượng hợp đồng bị sửa hồi tố | Lọc theo quyết định và khoảng bị tác động | Bảng quyết định, luồng sự kiện và kho phân tích |
| API giá hiện tại khối lượng lớn | B = ngày nghiệp vụ hiện tại; K = kiến thức hiện nay | Projection được đồng bộ và đối soát |

Đừng tạo chỉ mục chỉ từ trực giác. Cần dùng **EXPLAIN (ANALYZE, BUFFERS)** trên dữ liệu đủ lớn để kiểm tra kế hoạch thực thi. Chỉ mục GiST của exclusion constraint phục vụ cả bảo vệ bất biến và có thể hỗ trợ một số truy vấn, nhưng chưa chắc là tốt nhất cho mọi báo cáo theo ngày/khóa.

Một chỉ mục bổ sung tùy workload:

~~~sql
CREATE INDEX ix_contract_rate_current_known
ON contract_rate_bitemporal
USING gist (contract_id, rate_kind, valid_period)
WHERE upper_inf(known_period);
~~~

Chỉ mục này hướng tới các bản ghi **known-period còn mở** để tra lịch giá đang được chấp nhận. Nó không tự bảo vệ ràng buộc bitemporal; exclusion constraint vẫn cần được giữ.

### 15.1. Phân vùng và constraint toàn cục

Nếu phân vùng bảng theo thời điểm known_from, hai hàng cùng hợp đồng có thể thuộc hai phân vùng nhưng vẫn vi phạm bất biến **chồng valid lẫn known**. Không nên giả định ràng buộc trên từng phân vùng tự động loại trừ xung đột xuyên mọi phân vùng hoặc trên mọi phiên bản PostgreSQL.

Trước khi partitioning, cần kiểm chứng hỗ trợ thực tế của hệ quản trị, lựa chọn partition key và cách bảo đảm **constraint có hiệu lực toàn cục theo khóa nghiệp vụ**. Nếu không, cân nhắc cơ chế khóa/điều phối riêng hoặc thiết kế vật lý khác.

### 15.2. Retention và dữ liệu cá nhân

Bitemporal chỉ trả lời được những thời kỳ còn được lưu. Nếu xóa V1 theo chính sách retention, truy vấn K vào tháng 2 có thể không còn câu trả lời đúng; API cần cho biết **phạm vi lịch sử đáng tin còn tồn tại**, thay vì trả dữ liệu rỗng rồi suy ra “không có giá”.

Dữ liệu lịch sử còn có thể chứa thông tin cá nhân hoặc thông tin nhạy cảm. Nên tách dữ liệu cần lưu làm chứng cứ khỏi payload nhận dạng, áp dụng quyền truy cập, mã hóa, ẩn danh/xóa theo chính sách hiện hành và lưu bằng chứng ở mức tối thiểu cần thiết.

## 16. Bitemporal với document, graph và kho phân tích

Trong **DATABASE_DATA_MODELING**, cùng một yêu cầu “giá trị tại B theo hiểu biết ở K” có thể được giải bằng các mô hình dữ liệu khác nhau. Cần giữ nguyên **ngữ nghĩa của hai trục**, không chỉ đổi hình thức lưu trữ.

| Loại hệ thống | Biểu diễn khả thi | Điểm cần kiểm soát |
|---|---|---|
| **Quan hệ** | Mỗi phiên bản là hàng; valid/known range; exclusion constraint | Ghi nguyên tử, ràng buộc theo hai chiều, truy vấn as-of |
| **Document** | Collection phiên bản; mỗi document lưu validFrom/To và knownFrom/To | Kích thước tài liệu, transaction nhiều document, ngăn overlap dưới ghi đồng thời |
| **Graph** | Phiên bản node và edge có hai khoảng thời gian | Truy vấn đường đi tại (B, K), tính nhất quán của quan hệ lịch sử |
| **Kho phân tích** | Dimension theo phiên bản hiệu lực và lịch sử nạp/sửa; lưu phiên bản báo cáo | Late-arriving dimension, join fact, định nghĩa lịch sử kiến thức |
| **Event store** | Sự kiện quyết định bất biến + projection bitemporal | Replay, schema evolution, idempotency, thứ tự và sửa hồi tố |

### 16.1. Document: hai trục không nằm gọn trong một current document

Một phiên bản đơn giá có thể biểu diễn:

~~~json
{
  "contractId": 9001,
  "rateKind": "BASE",
  "monthlyAmount": 120000,
  "validFrom": "2026-02-01",
  "validTo": null,
  "knownFrom": "2026-03-10T09:00:00Z",
  "knownTo": "2026-03-20T09:00:00Z",
  "decisionRef": "RATE-MAR10"
}
~~~

Đó là V3. Sau đính chính, document V3 **vẫn phải truy vấn được** theo K ngày 15/03. Nếu hệ thống chỉ UPDATE một document “giá hiện tại” mà không giữ document phiên bản, lịch sử kiến thức sẽ mất.

Không nên nhúng lịch sử không giới hạn vào một document của hợp đồng nếu có nguy cơ vượt kích thước hoặc gây ghi lại payload lớn. Collection phiên bản riêng có thể tốt hơn; nhưng phải có cơ chế transaction/conditional writes để ngăn hai quyết định ghi đè timeline đồng thời.

### 16.2. Graph: lịch sử của quan hệ cũng có hai trục

Giả sử nhân viên 42 thuộc phòng A theo hiểu biết ban đầu, sau đó hệ thống nhận được quyết định rằng nhân viên đã chuyển sang phòng B từ tuần trước. Cần lưu những phiên bản của **edge MEMBER_OF** với cả valid time và known time; chỉ phiên bản hóa node Employee là không đủ.

Khi truy vấn đồ thị tổ chức tại **(B, K)**, mọi cạnh và thuộc tính ảnh hưởng đến kết quả phải được lọc theo cùng hai tham số thời gian. Nếu một đường đi gồm Employee → Team → Department, không thể dùng valid time cho cạnh thứ nhất rồi dùng “hiện tại” cho cạnh thứ hai và gọi đó là tổ chức tại B.

### 16.3. Kho phân tích: SCD Type 2 chưa chắc là bitemporal

**Slowly Changing Dimension Type 2** thường lưu phiên bản thuộc tính theo khoảng hiệu lực, hữu ích cho báo cáo lịch sử. Nhưng một bảng có **effective_from/effective_to** và timestamp nạp dữ liệu không tự động trả lời “tại K hệ thống đã biết gì”, nếu bản cũ bị ghi đè hoặc không lưu thời điểm nó hết là kiến thức được chấp nhận.

Nếu tổ chức cần tái hiện báo cáo đã phát hành trước một lần correction, có thể cần **known time**, **snapshot/version báo cáo** hoặc một event log đủ để tái dựng. Hãy làm rõ yêu cầu: tái tính số liệu theo thông tin hiện nay khác với giải thích vì sao báo cáo trước đây từng có số liệu cũ.

## 17. Ma trận kiểm thử cho điều chỉnh hồi tố

Dùng timeline V1–V5 đã được ghi ở các phần trước. Mỗi truy vấn theo **B = ngày nghiệp vụ** và **K = thời điểm hệ thống đã biết**.

| B | K (UTC) | Giá kỳ vọng | Giải thích |
|---|---|---:|---|
| 31/12/2025 | 21/03/2026 12:00 | Không có | Trước valid_from đầu tiên |
| 10/02/2026 | 01/03/2026 12:00 | 100.000 | V1 |
| 10/02/2026 | 15/03/2026 12:00 | 120.000 | V3 |
| 10/02/2026 | 21/03/2026 12:00 | 100.000 | V4 |
| 20/02/2026 | 15/03/2026 12:00 | 120.000 | V3 |
| 20/02/2026 | 21/03/2026 12:00 | 120.000 | V5 |
| 14/02/2026 | 21/03/2026 12:00 | 100.000 | Trước biên chuyển giá |
| 15/02/2026 | 21/03/2026 12:00 | 120.000 | Đúng biên chuyển giá |
| 10/02/2026 | 10/03/2026 09:00 | 120.000 | Đúng biên known-period mới |
| 10/02/2026 | 20/03/2026 09:00 | 100.000 | Đúng biên known-period sau đính chính |
| 10/02/2026 | 01/01/2026 07:00 | Không có | Trước lần biết đầu tiên |

Các kiểm thử bổ sung nên bao gồm:

1. **Đóng known-period nhưng thiếu INSERT mới:** phải rollback transaction, không tạo khoảng không có thông tin ở K sau cutover.
2. **Chồng hai trục:** cố chèn hai hàng cùng contract/rate_kind mà valid và known đều giao nhau; exclusion constraint phải từ chối.
3. **Chồng một trục nhưng không chồng trục còn lại:** phiên bản cũ và mới được phép giao valid time nếu known_period không giao.
4. **Ghi đồng thời:** hai đính chính cùng hợp đồng không tạo ra hai timeline cùng được chấp nhận tại một K.
5. **Idempotency:** gửi lại quyết định RATE-MAR20 không tạo một lớp known mới vô nghĩa hoặc nhân bản các đoạn.
6. **Đoạn không bị tác động:** sau correction, giá ngoài khoảng được sửa phải giữ đúng theo quyết định nghiệp vụ.
7. **Tác động nhiều đoạn:** một correction giao ba phiên bản hiệu lực phải chia chính xác các phần đầu/giữa/cuối.
8. **Chứng từ đã chốt:** hóa đơn 15/03 vẫn chứng minh mức giá thực dùng dù giá mới nhất cho ngày 10/02 đã thay đổi.
9. **Sự kiện đến muộn:** occurred time, received time và known time được ghi đúng nguồn, không trộn để suy ra thứ tự.
10. **Múi giờ và độ phân giải:** valid date theo lịch thị trường và known timestamptz không bị chuyển sai ngày.
11. **Retention:** truy vấn K ngoài phạm vi dữ liệu được giữ có phản hồi rõ ràng về giới hạn lịch sử.

Bảng kiểm thử theo **cặp (B, K)** đóng vai trò một hợp đồng dữ liệu: dù chuyển lưu trữ sang document, graph hay event store, các câu trả lời nghiệp vụ phải tương đương nếu cùng nguồn dữ liệu và cùng quy tắc.

## 18. Bài thực hành: điều chỉnh hồi tố về quyền truy cập

Một hệ thống cấp quyền theo hợp đồng có yêu cầu:

> “Khách hàng được mở quyền PREMIUM từ ngày có hiệu lực hợp đồng. Quyết định nâng cấp có thể đến muộn hoặc bị sửa ngày hiệu lực. Bộ phận hỗ trợ phải biết khách **đáng lẽ có quyền** tại ngày D theo thông tin hiện nay, và tại thời điểm K hệ thống từng **ghi nhận quyền** của khách như thế nào.”

Tình huống:

- 01/05, hệ thống ghi nhận quyền BASIC có hiệu lực từ 01/05.
- 10/06, bộ phận kinh doanh gửi quyết định PREMIUM có hiệu lực hồi tố từ 20/05.
- 15/06, phát hiện hợp đồng quy định PREMIUM chỉ có hiệu lực từ 01/06; quyết định 10/06 cần đính chính.

Hãy thực hiện:

1. Định nghĩa thực thể **customer_entitlement**, loại quyền và hai trục thời gian. Chọn ngày nghiệp vụ cho valid time và timestamp cho known time.
2. Mô hình hóa snapshot bitemporal sau mỗi lần ghi nhận. Giữ lại phiên bản kiến thức cũ để truy vấn tại K trước lần đính chính.
3. Viết bất biến: nếu mỗi khách chỉ có một cấp BASIC/PREMIUM tại một cặp (B, K), các hàng cạnh tranh phải không được chồng lấn đồng thời trên cả hai range.
4. Xác định quyền tại **B = 25/05, K = 12/06** và tại **B = 25/05, K = 16/06**. Kết quả lần lượt là **PREMIUM** và **BASIC**.
5. Kiểm tra quyền tại **B = 02/06, K = 16/06**. Kết quả phải là **PREMIUM**.
6. Mô tả giao dịch đóng các known-period cũ, chia lại valid-period và tạo các known-period mới ở một mốc K thống nhất.
7. Giải thích vì sao lịch sử quyền **đã được hệ thống thực sự cấp trên máy chủ** có thể khác lịch sử **quyền đáng lẽ có hiệu lực theo hợp đồng**. Nếu cần chứng minh ai truy cập tài nguyên lúc nào, còn cần audit/access log độc lập.
8. Đề xuất cơ chế xử lý phiên khách đã bị từ chối truy cập trước khi đính chính; đó là một vấn đề nghiệp vụ và vận hành, không thể được sửa chỉ bằng phép UPDATE lịch sử.

**Tiêu chí đánh giá:** lược đồ có hai khoảng rõ ràng; trục known không bị ghi đè làm mất lịch sử; khóa nghiệp vụ và constraint phù hợp; truy vấn as-of cho hai K chính xác; có cơ chế ghi nguyên tử và giữ chứng cứ truy cập thực tế.

## 19. Checklist chốt thiết kế

Trước khi chọn bitemporal để xử lý điều chỉnh hồi tố, nhóm phát triển cần thống nhất:

- **Câu hỏi:** hệ thống chỉ cần giá trị có hiệu lực hiện đang được chấp nhận, hay còn cần tái tạo thông tin hệ thống **đã từng tin vào K**?
- **Định nghĩa hai thời gian:** valid date/timestamp có nghĩa gì; known time lấy từ thành phần nào; có cần bảo đảm mốc commit chính xác không?
- **Khóa nghiệp vụ:** cùng những thuộc tính nào thì hai phiên bản được coi là cạnh tranh tại một cặp (B, K)?
- **Biên:** hai khoảng dùng quy ước **[from, to)** nhất quán, bao gồm cách biểu diễn vô hạn và giá trị chưa xác định chưa?
- **Ràng buộc:** có chống chồng lấn đồng thời trên cả valid và known; có phát hiện gap nếu nghiệp vụ yêu cầu phủ kín không?
- **Quy trình correction:** đọc và khóa timeline, tính lại mọi đoạn bị ảnh hưởng, giữ đoạn không đổi, đóng phiên bản cũ và mở phiên bản mới trong cùng transaction chưa?
- **Bằng chứng:** mọi lần sửa có nguồn, người duyệt, lý do và tham chiếu quyết định trước; có cần event log append-only không?
- **Chứng từ:** hóa đơn, quyền đã cấp hoặc báo cáo đã phát hành có giữ bằng chứng riêng để không bị tính lại âm thầm khi lịch sử hiệu lực đổi không?
- **Vận hành:** retry, idempotency, ghi đồng thời, độ trễ projection, retention và phạm vi có thể truy vấn đã rõ chưa?
- **Hiệu năng:** chỉ mục và phân vùng được kiểm chứng bằng workload thật, đồng thời vẫn bảo vệ bất biến xuyên các cấu trúc lưu trữ chưa?

**Nguyên tắc kết luận:** một lần điều chỉnh hồi tố có thể thay đổi **điều gì được coi là đúng cho ngày B**, nhưng không được xóa đi **điều hệ thống đã từng chấp nhận vào thời điểm K**. Mô hình hai chiều thời gian giữ cả hai lời giải bằng cách lưu mỗi giá trị theo **khoảng hiệu lực nghiệp vụ** và **khoảng kiến thức của hệ thống**, xử lý thay đổi bằng transaction, khóa và ràng buộc thích hợp. Chỉ khi hai trục thời gian được định nghĩa nhất quán và có thể truy vấn lại, các quyết định trong quá khứ mới có căn cứ đủ rõ để kiểm chứng và tiến hóa cùng nghiệp vụ.
