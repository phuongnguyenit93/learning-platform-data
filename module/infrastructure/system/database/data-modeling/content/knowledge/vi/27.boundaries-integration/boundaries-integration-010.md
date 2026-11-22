# Theo dõi nguồn gốc của dữ liệu được sao chép hoặc tổng hợp

Một báo cáo hiển thị **doanh số ròng 800.000 VND** cho một khách hàng doanh nghiệp trong ngày. Con số đến từ đâu? Có bao nhiêu dòng đơn hàng và giao dịch hoàn tiền góp vào? Được tính theo ngày đặt, ngày thanh toán hay ngày hoàn tiền? Tại thời điểm báo cáo chạy, những nguồn dữ liệu nào đã đồng bộ xong? Nếu một giao dịch bị sửa hoặc quy tắc tính thay đổi, ta xác định được **những chỉ số và bảng đích bị ảnh hưởng** hay không?

Đó là bài toán **theo dõi nguồn gốc dữ liệu (data lineage / data provenance)**: mô tả **dữ liệu ở đâu ra, đã đi qua những bước nào, theo quy tắc và phiên bản nào, tại thời điểm nào, rồi xuất hiện ở đâu**. Khi dữ liệu được sao chép giữa dịch vụ, chuyển từ OLTP sang kho phân tích, chuẩn hóa nhiều nguồn hoặc tổng hợp thành dashboard, chỉ biết tên bảng đích là chưa đủ để giải thích hay kiểm toán kết quả.

Bài thuộc chương **Ranh giới và tích hợp** của mô-đun **DATABASE_DATA_MODELING**. Mục tiêu là thiết kế ranh giới dữ liệu với grain, khóa, nguồn chuẩn, lịch sử và các ràng buộc rõ ràng; lưu bằng chứng cho thao tác sao chép và biến đổi; truy ngược từ một số liệu tổng hợp tới bản ghi nguồn; đồng thời tránh đánh đồng **lineage**, **nhật ký thao tác**, **tracing yêu cầu** và **bảo đảm dữ liệu đã đồng bộ đầy đủ**.

## 1. Vì sao sao chép và tổng hợp làm nguồn gốc trở nên khó thấy?

Trong hệ thống nhỏ, một bảng có thể vừa là nơi nhập liệu vừa là nơi hiển thị. Khi hệ thống phát triển, thông tin thường đi qua nhiều ranh giới:

~~~text
Order Service (PostgreSQL)
    -> outbox / CDC / batch export
    -> landing / raw zone
    -> bảng chuẩn hóa
    -> bảng fact
    -> tổng hợp theo ngày
    -> dashboard / API / file chia sẻ
~~~

Mỗi bước có thể làm thay đổi cách biểu diễn:

- **Đổi tên và kiểu dữ liệu:** source có cột **amount_minor_units**, kho lưu **amount_vnd**.
- **Đổi grain:** nhiều dòng đơn trở thành một hàng **doanh số theo tenant–ngày**.
- **Lọc dữ liệu:** loại sự kiện bị hủy, bản ghi sai miền hoặc dữ liệu chưa qua kiểm chứng.
- **Khử trùng:** nhiều thông điệp retry của cùng một sự kiện chỉ được tính một lần.
- **Ghép thêm thông tin:** liên kết dòng giao dịch với khách hàng, sản phẩm, vùng hoặc tỷ giá.
- **Quy đổi và tính toán:** làm tròn, áp chính sách hoàn tiền, cộng trừ, phân loại theo kỳ.
- **Thay đổi trạng thái theo thời gian:** nguồn sửa thông tin nhưng bản sao hoặc dashboard chưa nhận kịp.

Nếu không ghi lại **quan hệ giữa đầu vào và đầu ra**, người xem số liệu chỉ nhìn thấy kết quả cuối, không thể biết kết quả đó được hình thành thế nào.

### 1.1. Ví dụ sai lệch khó giải thích

Hai dashboard cùng lấy dữ liệu bán hàng nhưng trả kết quả khác nhau:

| Dashboard | Kết quả | Cách tính thực tế |
| --- | ---: | --- |
| A: doanh số đơn đặt | 900.000 VND | Tổng giá trị các dòng đơn được xác nhận trong ngày 20/11 |
| B: doanh số sau hoàn | 800.000 VND | 900.000 VND trừ 100.000 VND hoàn tiền ghi nhận cùng ngày |

Hai kết quả có thể **đều đúng**, nếu từ điển chỉ số và thời điểm ghi nhận khác nhau. Lỗi không nhất thiết nằm ở SQL; lỗi có thể là cả hai dashboard dùng chung nhãn mơ hồ **revenue** mà không có định nghĩa và metadata nguồn gốc.

### 1.2. Ba câu hỏi cần được trả lời

1. **Nguồn:** Những hệ thống, dataset, phiên bản và bản ghi nào được dùng?
2. **Biến đổi:** Chạy quy tắc nào, bằng job/version nào, với các tham số và thời điểm chốt dữ liệu nào?
3. **Đích:** Những bản ghi, chỉ số, dashboard hoặc API nào phụ thuộc kết quả ấy?

Truy vấn **từ nguồn tới các đích phụ thuộc** giúp đánh giá tác động khi sửa dữ liệu hoặc đổi schema (*impact analysis*). Truy vấn **từ đích về các nguồn đóng góp** giúp giải thích một con số (*root cause / audit trail*). Cả hai hướng đều quan trọng.

## 2. Phân biệt lineage, provenance, audit log và distributed tracing

| Khái niệm | Tập trung vào | Ví dụ câu hỏi |
| --- | --- | --- |
| **Data lineage** | Đường đi và quan hệ phụ thuộc của dữ liệu qua các dataset/cột/bước xử lý | Bảng báo cáo này phụ thuộc bảng nguồn nào? |
| **Data provenance** | Bằng chứng cụ thể giải thích dữ liệu hoặc kết quả được tạo như thế nào | Hàng doanh số 800.000 dùng chính xác những sự kiện nào và công thức nào? |
| **Audit log** | Ai/hệ thống nào đã đọc, sửa, xóa, phê duyệt; khi nào | Ai hiệu chỉnh số tiền hoàn lại lúc 15:00? |
| **Distributed trace** | Một yêu cầu chạy qua service nào và mất bao lâu | HTTP request tạo đơn đi qua Order, Payment và Notification thế nào? |
| **Data observability** | Chất lượng, độ mới, số lượng, schema, lỗi pipeline | Bản sao đã trễ 30 phút hay thiếu 500 dòng? |
| **Data catalog / contract** | Ý nghĩa, chủ sở hữu, grain, schema và chính sách sử dụng | Trường **net_sales_vnd** được định nghĩa, sở hữu và làm mới bởi ai? |

Các công cụ có thể kết hợp, nhưng **không đồng nhất**:

- Một **trace_id** chứng minh những service đã tham gia xử lý request, **không tự chứng minh** mọi record trong báo cáo bắt nguồn từ request đó.
- Một **audit log** ghi ai sửa số tiền, **không tự nối** số tiền ấy đến mọi bảng tổng hợp cần tính lại.
- Một DAG pipeline cho thấy bảng A → B → C, **không đủ** để giải thích cụ thể hàng C nào phụ thuộc hàng A nào.
- Một dòng **ingested_at** cho biết khi nào bản sao được nhận, **không xác nhận** nguồn đã chuyển đủ mọi sự kiện.

Trong bài, dùng **lineage** theo nghĩa rộng, có thể gồm metadata ở mức dataset, job, cột và bản ghi; gọi **provenance** khi cần chứng cứ chính xác cho một kết quả cụ thể.

## 3. Chốt nguồn chuẩn, grain và ranh giới trước khi chọn công cụ

### 3.1. Nguồn chuẩn (source of truth) theo từng sự thật

Một hệ thống có thể có nhiều nguồn chuẩn, **mỗi nguồn sở hữu một loại sự thật**:

| Sự thật | Chủ sở hữu ví dụ | Dữ liệu sao chép |
| --- | --- | --- |
| Dòng đơn được xác nhận, giá đã chốt | **Order Service** | CDC/raw orders, fact sale |
| Hoàn tiền đã quyết toán | **Payment/Refund Service** | raw refunds, fact refund |
| Tên khách hàng hiện hành | **Customer Service** | dim_customer hiện hành |
| Phân khúc khách hàng theo lịch sử | Nguồn khách hàng cùng chính sách SCD | Các phiên bản dim_customer |
| Doanh số ròng theo ngày | **Quy tắc phân tích được phê duyệt** | Bảng tổng hợp/report |

Bảng tổng hợp là **dẫn xuất** từ các sự thật nguồn. Nó có thể là **nguồn được phục vụ** (*serving source*) cho dashboard, nhưng không trở thành nơi phán quyết số tiền đơn hàng gốc có đúng hay không.

Khi một bản sao có vẻ khác nguồn, phải biết:

- Nó được phép trễ bao lâu?
- Có đang lưu **ảnh chụp lịch sử** thay vì giá trị hiện hành không?
- Có áp dụng quy tắc lọc/chuẩn hóa khác không?
- Có đang chờ bản ghi từ hệ thống khác để hoàn tất không?

Không nên mặc định “bản sao cũ là sai” khi nó biểu diễn dữ liệu **as-of** tại một thời điểm đã công bố.

### 3.2. Một hàng biểu diễn điều gì?

Lineage chính xác bắt đầu bằng **grain** của từng lớp:

~~~text
raw_sale_events:
    một phiên bản nguồn của một dòng bán đã xác nhận

raw_refund_events:
    một phiên bản nguồn của một sự kiện hoàn tiền đã quyết toán

run_financial_events:
    một sự kiện tài chính chuẩn hóa trong một lần chạy pipeline

daily_tenant_sales:
    một tenant trong một ngày báo cáo, thuộc một lần chạy pipeline
~~~

Nếu bỏ **run_id** khỏi định danh kết quả nhưng vẫn muốn giữ nhiều lần chạy lịch sử, các lần tính có thể **ghi đè lẫn nhau**. Nếu bỏ **source_event_id**, không thể khử trùng sự kiện retry hoặc truy ngược chính xác. Nếu dùng ngày **ingested_at** thay cho ngày nghiệp vụ mà không xác nhận, chỉ số có thể bị ghi sang kỳ khác.

### 3.3. Thông tin tối thiểu của một record được sao chép

Một bản sao có thể lưu hoặc liên kết tới:

| Metadata | Mục đích |
| --- | --- |
| **source_system / source_dataset** | Xác định nguồn sở hữu và bảng/luồng nguyên thủy |
| **source_record_id** | Khóa bản ghi ổn định trong phạm vi nguồn |
| **source_version / source_sequence** | Phân biệt các phiên bản và thứ tự sửa cùng một record |
| **occurred_at / effective_at** | Thời điểm nghiệp vụ xảy ra hoặc có hiệu lực |
| **ingested_at** | Thời điểm hệ thống đích nhận bản sao |
| **run_id** | Job/batch nào tạo ra bản ghi |
| **transform_version** | Phiên bản quy tắc, mã hoặc cấu hình đã áp dụng |
| **source_cutoff / watermark** | Tập dữ liệu được phép đọc đến mốc nào, mức độ hoàn tất của nguồn |
| **quality_status / rejection_reason** | Bản ghi được chấp nhận, cách ly hay loại bỏ vì sao |

Không phải mọi bảng fact đều cần **mọi trường** nằm trực tiếp trên hàng. Có thể liên kết qua bảng metadata chạy job hoặc một kho lineage riêng. Yêu cầu quan trọng là **có thể truy ra thông tin một cách nhất quán với chi phí phù hợp**.

## 4. Các mức độ lineage và chi phí của từng mức

| Mức | Ví dụ | Trả lời được | Giới hạn |
| --- | --- | --- | --- |
| **Dataset/table-level** | raw_sales → financial_events → daily_sales | Dataset nào phụ thuộc dataset nào? | Không biết hàng nào góp vào số cụ thể |
| **Column-level** | raw_sales.gross_vnd → signed_amount_vnd → gross_vnd | Cột đích tính từ cột nguồn nào? | Không mô tả đầy đủ điều kiện lọc hay bản ghi |
| **Job/run-level** | run 9001, transform v1.0, cutoff 00:00 | Lần chạy nào tạo phiên bản báo cáo? | Không thay thế source ID của từng hàng |
| **Record-level** | (raw_sales, O1001-L1, rev1) → event E → hàng ngày T01/20-11 | Một hàng báo cáo chịu tác động của những record nào? | Tốn lưu trữ và quản lý ID |
| **Contribution-level** | event E góp +300.000 VND cho gross | Tại sao tổng có giá trị này? | Phải bảo toàn phép tính, filter, dấu, phân bổ |
| **Field/value-level** | currency, tỷ giá, chính sách round tạo ra amount_vnd | Giá trị này được quy đổi cụ thể thế nào? | Đòi hỏi metadata và kiểm thử chi tiết |

**Không cần mức record-level cho mọi dữ liệu.** Dataset-level cùng run/version và kiểm thử đối soát có thể đủ cho một bảng tổng hợp vô danh phục vụ thử nghiệm. Ngược lại, nếu báo cáo tài chính cần giải thích từng giao dịch hoặc phát hiện ảnh hưởng của một khoản hoàn tiền, chỉ ghi tên DAG là không đủ.

### 4.1. Quan hệ nguồn–đích thường là nhiều–nhiều

Một bản ghi nguồn có thể góp vào nhiều bảng/metric; một hàng tổng hợp thường lấy từ nhiều nguồn. Có thể hình dung lineage là **đồ thị có hướng**:

~~~mermaid
flowchart LR
    SALES[("Order Service: sale lines")]
    REFUNDS[("Refund Service: refund events")]
    RAW1[("Raw sales: immutable versions")]
    RAW2[("Raw refunds: immutable versions")]
    RUN["Transform v1.0 / run 9001"]
    EVENTS[("Normalized financial events")]
    DAILY[("Daily tenant sales")]
    DASH["Dashboard"]
    AUDIT["Lineage / run metadata"]
    SALES --> RAW1
    REFUNDS --> RAW2
    RAW1 --> RUN
    RAW2 --> RUN
    RUN --> EVENTS
    EVENTS --> DAILY
    DAILY --> DASH
    RUN -. "version, cutoff" .-> AUDIT
    EVENTS -. "source ID / revision" .-> AUDIT
    DAILY -. "run ID / grain" .-> AUDIT
~~~

Đường nét liền là luồng biến đổi/đọc; các liên kết metadata lưu bằng chứng. Nếu pipeline có **JOIN**, **dedup** hoặc **lọc**, đồ thị dataset chỉ là một phần của câu chuyện: cần ghi lại **quy tắc chọn và loại bản ghi**.

## 5. Tình huống xuyên suốt: doanh số ròng theo tenant và ngày

Giả sử một nền tảng SaaS xử lý giao dịch cho nhiều **tenant**. Ta cần chỉ số phân tích:

> **net_sales_vnd** của một tenant trong ngày địa phương Việt Nam = tổng giá trị các dòng bán **đã xác nhận** xảy ra trong ngày, trừ tổng tiền của các **sự kiện hoàn đã quyết toán** xảy ra trong cùng ngày.

Đây là **định nghĩa minh họa của doanh số ròng theo sự kiện**; nó **không mặc nhiên là doanh thu kế toán**. Một khoản hoàn trong ngày 21/11 cho đơn đã bán ngày 20/11 sẽ được trừ **vào ngày 21/11**, vì chỉ số chọn ngày xảy ra hoàn tiền. Nếu nghiệp vụ muốn điều chỉnh trở lại ngày bán gốc, quy tắc tính và lineage phải thay đổi.

Các quyết định được xác nhận cho ví dụ:

1. **Order Service** sở hữu các dòng bán đã xác nhận. Mỗi dòng có **source_event_id** duy nhất trong nguồn và **source_version** tăng khi sửa.
2. **Refund Service** sở hữu các sự kiện hoàn đã quyết toán. Mỗi event hoàn có ID và revision riêng.
3. Hai nguồn đều dùng **VND**, mỗi giá trị tiền là số VND nguyên dương. Không thực hiện quy đổi ngoại tệ trong ví dụ.
4. Bản sao raw giữ **các phiên bản nguồn bất biến** thay vì chỉ giữ giá trị mới nhất.
5. Mỗi lần chạy pipeline có **run_id**, **transform_version** và **source_cutoff_at** cố định.
6. Pipeline chọn **phiên bản cao nhất đã được nhận trước cutoff** của mỗi source event, rồi chỉ lấy phiên bản **chưa bị xóa**.
7. **Sale** đóng góp số dương; **refund** đóng góp số âm. Grain chuẩn hóa là **một source event được chọn trong một lần chạy**.
8. Bảng tổng hợp có grain **(run_id, tenant_id, report_date)**; giữ nhiều lần chạy để giải thích các kết quả đã công bố.

Đường đi dữ liệu:

~~~mermaid
flowchart TD
    OS["Order Service: dòng bán"]
    RS["Refund Service: hoàn tiền"]
    RAW_S[("raw_sale_versions")]
    RAW_R[("raw_refund_versions")]
    SELECT["Chọn revision theo cutoff"]
    NORMALIZE["Chuẩn hóa VND, dấu và ngày"]
    LEDGER[("run_financial_events")]
    GROUP["GROUP BY tenant, report_date"]
    DAILY[("daily_tenant_sales")]
    REPORT["Dashboard / data API"]
    RUN[("etl_runs: run_id + version + cutoff")]
    OS --> RAW_S
    RS --> RAW_R
    RAW_S --> SELECT
    RAW_R --> SELECT
    SELECT --> NORMALIZE
    NORMALIZE --> LEDGER
    LEDGER --> GROUP
    GROUP --> DAILY
    DAILY --> REPORT
    RUN -. "cấu hình" .-> SELECT
    RUN -. "dấu vết" .-> LEDGER
    RUN -. "phiên bản" .-> DAILY
~~~

### 5.1. Vì sao cần trung gian sự kiện chuẩn hóa?

Nếu bảng **daily_tenant_sales** chỉ chứa số tổng, ta vẫn biết kết quả thuộc tenant/ngày, nhưng khó xác định **những sự kiện nguồn đã đóng góp bao nhiêu**. Bảng **run_financial_events** giữ một hàng cho từng event đã chọn, cùng dataset nguồn, ID, revision, run và số tiền đóng góp.

Khi ấy:

- Có thể truy **tổng → các sự kiện chuẩn hóa → đúng revision raw**.
- Có thể tính lại tổng bằng SQL để kiểm chứng.
- Có thể xác định một source event đang góp vào **hàng tổng hợp nào**.
- Có thể so sánh hai lần chạy theo cùng hoặc khác cutoff/version.

Điểm đánh đổi là số hàng sự kiện chuẩn hóa có thể lớn. Với hệ thống hàng tỷ sự kiện, cần cân nhắc phân vùng, retention, indexing, lưu metadata ở mức khác nhau hoặc khả năng truy lại raw từ object storage. Không nên nhân toàn bộ bản ghi nguồn vào mọi bảng chỉ để “có lineage”.

## 6. DDL PostgreSQL: nguồn raw bất biến và metadata lần chạy

Các đoạn SQL ở mục 6–9 là **một ví dụ nhất quán** chạy trên database PostgreSQL hoặc schema thực hành trống, theo đúng thứ tự. Để tránh phụ thuộc vào dữ liệu ngoài bài, mã nguồn trong ví dụ sử dụng các tên dataset cố định **raw_sales** và **raw_refunds**; mỗi source ID được giả định duy nhất trong **từng dataset**.

### 6.1. Lưu các phiên bản dòng bán

~~~sql
CREATE TABLE raw_sale_versions (
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    gross_vnd NUMERIC(20, 0) NOT NULL CHECK (gross_vnd > 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    ingested_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (source_event_id, source_version)
);
~~~

**Grain:** một phiên bản do Order Service phát hành cho một sự kiện dòng bán. Hai phiên bản của cùng source_event_id có thể khác số tiền hoặc thời điểm hiệu lực khi có hiệu chỉnh.

**is_deleted** trong ví dụ là dấu hủy bản ghi nguồn theo cơ chế correction/tombstone. Mô hình minh họa giả định tombstone vẫn mang đủ các trường bắt buộc; hệ nguồn thực tế có thể gửi tombstone chỉ gồm khóa và revision, khi đó staging/chuẩn hóa cần thiết kế riêng. **Không** biến việc hủy đơn thương mại thành xóa raw tùy tiện: quy tắc ghi nhận sự kiện điều chỉnh phải được xác nhận.

### 6.2. Lưu các phiên bản sự kiện hoàn tiền

~~~sql
CREATE TABLE raw_refund_versions (
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version > 0),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    refund_vnd NUMERIC(20, 0) NOT NULL CHECK (refund_vnd > 0),
    currency_code CHAR(3) NOT NULL CHECK (currency_code = 'VND'),
    ingested_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (source_event_id, source_version)
);
~~~

Một dòng bán có thể có **nhiều sự kiện hoàn từng phần**. Không dùng order_id làm khóa event hoàn. Nếu nguồn gửi mỗi lần hoàn một event ID, refund R01 và R02 phải được xác định rõ, không nhân bản do retry.

**Lưu ý về tính duy nhất:** trong ví dụ, source_event_id duy nhất **trong dataset**. Nếu dịch vụ nguồn chỉ cam kết duy nhất **theo tenant** hoặc theo một stream partition, khóa raw phải bổ sung tenant_id/stream_id tương ứng; không được áp đặt UNIQUE toàn cục làm từ chối các sự kiện hợp lệ.

### 6.3. Bảng metadata pipeline run

~~~sql
CREATE TABLE etl_runs (
    run_id BIGINT PRIMARY KEY,
    transform_name TEXT NOT NULL,
    transform_version TEXT NOT NULL,
    source_cutoff_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL
        CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);
~~~

Trong production, có thể lưu thêm **code_commit_sha**, image/container digest, cấu hình tính toán, danh sách dataset/version, idempotency key, người/luồng kích hoạt, schema version và checkpoint/watermark của **từng nguồn**. Một **source_cutoff_at** chung trong ví dụ chỉ giới hạn các hàng được ingest trước mốc đó; **nó không chứng minh hai nguồn đồng bộ hoàn tất đến cùng mốc thời gian nghiệp vụ**.

### 6.4. Bảng sự kiện đã chuẩn hóa có dấu vết nguồn

~~~sql
CREATE TABLE run_financial_events (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    source_dataset TEXT NOT NULL
        CHECK (source_dataset IN ('raw_sales', 'raw_refunds')),
    source_event_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    source_ingested_at TIMESTAMPTZ NOT NULL,
    event_kind TEXT NOT NULL
        CHECK (event_kind IN ('SALE', 'REFUND')),
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    report_date DATE NOT NULL,
    signed_amount_vnd NUMERIC(20, 0) NOT NULL,
    PRIMARY KEY (run_id, source_dataset, source_event_id),
    CHECK (
        (event_kind = 'SALE' AND signed_amount_vnd > 0)
        OR
        (event_kind = 'REFUND' AND signed_amount_vnd < 0)
    )
);
~~~

Khóa **(run_id, source_dataset, source_event_id)** đảm bảo **mỗi source event được chọn nhiều nhất một lần trong cùng run**. **source_version** ghi chính xác revision đã chọn. Vì dữ liệu đến từ **hai bảng raw khác nhau**, một FOREIGN KEY đa hình theo source_dataset không được biểu diễn tự động bằng một FK SQL thông thường; sự khớp revision được kiểm tra ở bước nạp và truy vấn đối soát. Nếu cần FK khai báo đầy đủ, có thể dùng bảng registry nguồn chung hoặc hai bảng lineage riêng.

### 6.5. Bảng tổng hợp có phiên bản theo lần chạy

~~~sql
CREATE TABLE daily_tenant_sales (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    tenant_id TEXT NOT NULL,
    report_date DATE NOT NULL,
    gross_vnd NUMERIC NOT NULL CHECK (gross_vnd >= 0),
    refund_vnd NUMERIC NOT NULL CHECK (refund_vnd >= 0),
    net_vnd NUMERIC
        GENERATED ALWAYS AS (gross_vnd - refund_vnd) STORED,
    PRIMARY KEY (run_id, tenant_id, report_date)
);

CREATE INDEX idx_financial_events_run_day
ON run_financial_events (run_id, tenant_id, report_date);
~~~

**net_vnd** có thể âm trong một ngày hoàn tiền nhiều hơn bán mới; không thêm ràng buộc **net_vnd >= 0** chỉ vì chưa thấy giá trị âm trong dữ liệu mẫu. **NUMERIC** cho tổng tiền giúp tránh phụ thuộc vào giới hạn tổng của số nguyên máy, đổi lại có chi phí lưu trữ/tính toán riêng.

Giữ **run_id trong khóa** cho phép có nhiều phiên bản báo cáo của cùng tenant/ngày. Một bảng hoặc view **latest_successful_report** phục vụ dashboard có thể trỏ tới phiên bản được công bố theo chính sách; nó không thay thế bản ghi run hoặc bằng chứng nguồn.

## 7. Dữ liệu mẫu: hai hệ nguồn, hai kiểu sự kiện

Nạp năm sự kiện bán và hai sự kiện hoàn. Tất cả đều ở revision 1, được ingest trước mốc chạy mẫu:

~~~sql
INSERT INTO raw_sale_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, gross_vnd, currency_code, ingested_at
) VALUES
    ('O1001-L1', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 300000, 'VND',
     TIMESTAMPTZ '2026-11-20 09:01:00+07'),
    ('O1001-L2', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 200000, 'VND',
     TIMESTAMPTZ '2026-11-20 09:02:00+07'),
    ('O1002-L1', 1, 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-20 11:00:00+07', 400000, 'VND',
     TIMESTAMPTZ '2026-11-20 11:02:00+07'),
    ('O1003-L1', 1, 'T01', 'O1003',
     TIMESTAMPTZ '2026-11-21 09:00:00+07', 150000, 'VND',
     TIMESTAMPTZ '2026-11-21 09:04:00+07'),
    ('O2001-L1', 1, 'T02', 'O2001',
     TIMESTAMPTZ '2026-11-20 14:00:00+07', 700000, 'VND',
     TIMESTAMPTZ '2026-11-20 14:03:00+07');

INSERT INTO raw_refund_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, refund_vnd, currency_code, ingested_at
) VALUES
    ('RF1001', 1, 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-20 16:00:00+07', 100000, 'VND',
     TIMESTAMPTZ '2026-11-20 16:01:00+07'),
    ('RF1002', 1, 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-21 15:00:00+07', 50000, 'VND',
     TIMESTAMPTZ '2026-11-21 15:01:00+07');
~~~

Các nguồn trong ví dụ đã xác nhận tiền bán và hoàn là số cuối cùng của **từng event**. Nếu Order Service còn phát cả event cập nhật trạng thái DRAFT/CONFIRMED của cùng dòng, không được cộng tất cả trạng thái như các giao dịch mới. Phải định nghĩa loại event nào là đóng góp tài chính và cách chọn revision hiện hành.

### 7.1. Kết quả mong đợi trước khi chạy ETL

| tenant_id | report_date | Số tiền bán | Số tiền hoàn | Doanh số ròng |
| --- | --- | ---: | ---: | ---: |
| T01 | 2026-11-20 | 900.000 | 100.000 | 800.000 |
| T01 | 2026-11-21 | 150.000 | 50.000 | 100.000 |
| T02 | 2026-11-20 | 700.000 | 0 | 700.000 |

Đây là **tính toán theo ngày xảy ra sale/refund** và múi giờ **Asia/Ho_Chi_Minh**. Ví dụ chưa có thuế, vận chuyển, quy đổi tiền tệ hoặc ghi nhận doanh thu kế toán. Trong báo cáo thật, các điều kiện này phải nằm trong **data contract và phiên bản phép tính**.

## 8. Pipeline có thể truy vết: từ raw đến event chuẩn hóa

Để mỗi báo cáo có thể tái tạo, một lần chạy phải đóng băng **ít nhất** phiên bản logic và phạm vi đầu vào. Trong ví dụ:

~~~text
run_id             = 9001
transform_name     = daily_net_sales
transform_version  = v1.0
source_cutoff_at   = 2026-11-22 00:00:00 +07
report timezone    = Asia/Ho_Chi_Minh
~~~

**source_cutoff_at** giới hạn thời điểm hệ thống **nhận** raw event; nó không phải thời điểm giao dịch xảy ra. Dòng được giao dịch ngày 20/11 nhưng nhận ngày 23/11 **không thuộc** lần chạy 9001. Nhờ đó người xem có thể giải thích tại sao hai lần chạy với cutoff khác nhau cho số khác nhau.

### 8.1. Chọn đúng phiên bản source event

Nếu một source_event_id có các revision 1, 2, 3, ta cần chọn **revision cao nhất đã được ingest trước cutoff**. Trong PostgreSQL có thể dùng **DISTINCT ON** với thứ tự tường minh:

~~~sql
SELECT DISTINCT ON (source_event_id)
    source_event_id,
    source_version,
    gross_vnd,
    ingested_at,
    is_deleted
FROM raw_sale_versions
WHERE ingested_at <= TIMESTAMPTZ '2026-11-22 00:00:00+07'
ORDER BY
    source_event_id,
    source_version DESC,
    ingested_at DESC;
~~~

**Không lọc is_deleted = FALSE trước khi chọn revision.** Nếu phiên bản mới nhất là tombstone, lọc tombstone trước sẽ khiến một revision cũ của cùng event sống lại sai. Chọn revision trước, sau đó mới loại những event mà **revision đã chọn** đánh dấu deleted.

Quy tắc giả định **source_version tăng đơn điệu cho từng source_event_id**; nếu nguồn không cam kết như vậy, phải dùng source sequence/commit log position hoặc một thứ tự tin cậy khác. Chỉ dùng thời gian nhận để chọn “mới nhất” có thể sai khi sự kiện đến không đúng thứ tự.

### 8.2. Chạy chuẩn hóa và tổng hợp trong một transaction

Đoạn sau tiếp nối dữ liệu mẫu ở mục 7. Nó tạo run, chọn phiên bản của hai nguồn, ánh xạ về sự kiện có số tiền dương/âm, tổng hợp theo **tenant_id và report_date**, rồi đánh dấu run thành công:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO etl_runs (
    run_id, transform_name, transform_version,
    source_cutoff_at, started_at, status
) VALUES (
    9001, 'daily_net_sales', 'v1.0',
    TIMESTAMPTZ '2026-11-22 00:00:00+07',
    CURRENT_TIMESTAMP, 'RUNNING'
);

WITH config AS (
    SELECT run_id, source_cutoff_at
    FROM etl_runs
    WHERE run_id = 9001
),
sales_latest AS (
    SELECT DISTINCT ON (s.source_event_id)
        s.*
    FROM raw_sale_versions AS s
    CROSS JOIN config AS c
    WHERE s.ingested_at <= c.source_cutoff_at
    ORDER BY
        s.source_event_id,
        s.source_version DESC,
        s.ingested_at DESC
),
refunds_latest AS (
    SELECT DISTINCT ON (r.source_event_id)
        r.*
    FROM raw_refund_versions AS r
    CROSS JOIN config AS c
    WHERE r.ingested_at <= c.source_cutoff_at
    ORDER BY
        r.source_event_id,
        r.source_version DESC,
        r.ingested_at DESC
)
INSERT INTO run_financial_events (
    run_id, source_dataset, source_event_id, source_version,
    source_ingested_at, event_kind, tenant_id, order_id,
    occurred_at, report_date, signed_amount_vnd
)
SELECT
    c.run_id,
    'raw_sales',
    s.source_event_id,
    s.source_version,
    s.ingested_at,
    'SALE',
    s.tenant_id,
    s.order_id,
    s.occurred_at,
    (s.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    s.gross_vnd
FROM sales_latest AS s
CROSS JOIN config AS c
WHERE NOT s.is_deleted

UNION ALL

SELECT
    c.run_id,
    'raw_refunds',
    r.source_event_id,
    r.source_version,
    r.ingested_at,
    'REFUND',
    r.tenant_id,
    r.order_id,
    r.occurred_at,
    (r.occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
    -r.refund_vnd
FROM refunds_latest AS r
CROSS JOIN config AS c
WHERE NOT r.is_deleted;

INSERT INTO daily_tenant_sales (
    run_id, tenant_id, report_date, gross_vnd, refund_vnd
)
SELECT
    run_id,
    tenant_id,
    report_date,
    SUM(
        CASE WHEN event_kind = 'SALE'
             THEN signed_amount_vnd ELSE 0 END
    ) AS gross_vnd,
    SUM(
        CASE WHEN event_kind = 'REFUND'
             THEN -signed_amount_vnd ELSE 0 END
    ) AS refund_vnd
FROM run_financial_events
WHERE run_id = 9001
GROUP BY run_id, tenant_id, report_date;

UPDATE etl_runs
SET status = 'SUCCEEDED',
    completed_at = clock_timestamp()
WHERE run_id = 9001;

COMMIT;
~~~

Vì dữ liệu raw được nạp trước khi bắt đầu và transaction dùng **REPEATABLE READ**, các câu truy vấn nhìn thấy một snapshot nhất quán tại thời điểm transaction. **Tính tái lập giữa nhiều lần chạy vẫn đòi hỏi nguồn raw bất biến, retention đủ lâu và quy tắc lựa chọn revision ổn định**. Chỉ ghi cutoff mà cho phép sửa trực tiếp raw hoặc backdate ingested_at thì không đủ.

**Các lưu ý quan trọng:**

- **UNION ALL** phù hợp vì nguồn sale và refund là hai tập sự kiện khác nhau; nếu dùng UNION loại trùng không có chủ đích, một event có thể bị mất.
- **source_dataset** đi cùng **source_event_id**, tránh nhầm ID giống nhau ở hai hệ thống.
- **source_version** và **source_ingested_at** được giữ nguyên để truy đúng bản raw.
- **report_date** tính từ **occurred_at** theo múi giờ đã xác nhận, không suy từ **ingested_at**.
- **run_id** được đặt trên cả sự kiện chuẩn hóa và hàng tổng hợp, để không trộn hai lần chạy.
- Trong bản mẫu, tất cả giá trị tiền đã là VND; nếu có ngoại tệ, phải gắn **currency, fx_rate_id, rate_timestamp, round_policy/version** và không cộng số tiền khác tiền tệ trực tiếp.
- **status = SUCCEEDED** nghĩa phần SQL đã hoàn tất, **không tự chứng minh** đầu vào từ hai nguồn đã hoàn chỉnh. Cần thêm kiểm tra và quy tắc công bố ở mục 11.

Nếu transaction thất bại trước COMMIT, các bản ghi run/event/tổng hợp của transaction này được rollback. Trong pipeline nhiều hệ thống hoặc lưu ở object storage, một SQL transaction đơn không bao trùm tất cả các bước; phải dùng staging, checkpoint và cơ chế publish có kiểm soát, không giả định có giao dịch phân tán miễn phí.

### 8.3. Xem kết quả của một lần chạy

~~~sql
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.gross_vnd,
    d.refund_vnd,
    d.net_vnd,
    r.transform_version,
    r.source_cutoff_at
FROM daily_tenant_sales AS d
JOIN etl_runs AS r ON r.run_id = d.run_id
WHERE d.run_id = 9001
  AND r.status = 'SUCCEEDED'
ORDER BY d.tenant_id, d.report_date;
~~~

Kết quả mong đợi:

| run_id | tenant | ngày | gross_vnd | refund_vnd | net_vnd |
| ---: | --- | --- | ---: | ---: | ---: |
| 9001 | T01 | 2026-11-20 | 900000 | 100000 | 800000 |
| 9001 | T01 | 2026-11-21 | 150000 | 50000 | 100000 |
| 9001 | T02 | 2026-11-20 | 700000 | 0 | 700000 |

Tổng cộng có **7 bản ghi ở run_financial_events** (5 sale, 2 refund), tạo **3 hàng ở daily_tenant_sales**. Các con số được dự kiến từ dữ liệu mẫu; bài không khẳng định đã chạy database thực tế.

## 9. Truy ngược và truy xuôi nguồn gốc bằng SQL

### 9.1. Từ một số tổng về những sự kiện đóng góp

Vì hàng tổng hợp có **run_id, tenant_id, report_date**, có thể nối về đúng grain của các sự kiện chuẩn hóa:

~~~sql
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    e.event_kind,
    e.order_id,
    e.signed_amount_vnd,
    e.source_ingested_at
FROM daily_tenant_sales AS d
JOIN run_financial_events AS e
  ON e.run_id = d.run_id
 AND e.tenant_id = d.tenant_id
 AND e.report_date = d.report_date
WHERE d.run_id = 9001
  AND d.tenant_id = 'T01'
  AND d.report_date = DATE '2026-11-20'
ORDER BY e.source_dataset, e.source_event_id;
~~~

Kết quả có bốn sự kiện:

| source_dataset | source_event_id | source_version | event_kind | signed_amount_vnd |
| --- | --- | ---: | --- | ---: |
| raw_refunds | RF1001 | 1 | REFUND | -100000 |
| raw_sales | O1001-L1 | 1 | SALE | 300000 |
| raw_sales | O1001-L2 | 1 | SALE | 200000 |
| raw_sales | O1002-L1 | 1 | SALE | 400000 |

Đối chiếu trực tiếp:

~~~text
Gross     = 300000 + 200000 + 400000 = 900000
Refund    = 100000
Net sales = 300000 + 200000 + 400000 - 100000 = 800000
~~~

Đây là **contribution-level lineage đơn giản**: mỗi event đóng góp nguyên một số tiền có dấu vào một tenant/ngày. Nếu pipeline phân bổ một event cho **nhiều dimension hoặc nhiều hàng đích** (ví dụ chia khoản giảm giá theo tỷ trọng dòng hàng), cần một bảng đóng góp chi tiết hoặc đủ metadata về **tỷ lệ phân bổ/rounding**; không thể chỉ JOIN theo ngày và cho rằng đó là chứng minh chính xác.

### 9.2. Từ sự kiện chuẩn hóa tới đúng revision của bản raw

~~~sql
SELECT
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    e.signed_amount_vnd,
    s.gross_vnd AS original_sale_vnd,
    r.refund_vnd AS original_refund_vnd
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE e.run_id = 9001
  AND e.tenant_id = 'T01'
  AND e.report_date = DATE '2026-11-20'
ORDER BY e.source_dataset, e.source_event_id;
~~~

Với sale, số dương của **signed_amount_vnd** phải khớp **gross_vnd** từ raw. Với refund, số âm phải bằng **-refund_vnd**. Nếu truy vấn không tìm được bản raw tương ứng, có thể dữ liệu nguồn bị dọn quá sớm, khóa lineage sai, hoặc nguồn được di chuyển mà không giữ được khả năng định vị.

**Nguyên tắc:** **(source_dataset, source_event_id, source_version)** là danh tính chứng cứ. Chỉ lưu order_id không đủ, vì một đơn có thể có nhiều dòng bán, nhiều refund và nhiều revision.

### 9.3. Từ một bản nguồn tới những báo cáo bị ảnh hưởng

Giả sử Refund Service thông báo có vấn đề với event **RF1001**. Truy vấn downstream impact:

~~~sql
SELECT
    e.source_dataset,
    e.source_event_id,
    e.source_version,
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.net_vnd,
    r.transform_version
FROM run_financial_events AS e
JOIN daily_tenant_sales AS d
  ON d.run_id = e.run_id
 AND d.tenant_id = e.tenant_id
 AND d.report_date = e.report_date
JOIN etl_runs AS r ON r.run_id = d.run_id
WHERE e.source_dataset = 'raw_refunds'
  AND e.source_event_id = 'RF1001'
ORDER BY d.run_id, d.report_date;
~~~

Với dữ liệu mẫu chỉ có run 9001, ta tìm được hàng **T01 / 2026-11-20 / run 9001**. Khi có nhiều lần chạy, source event có thể ảnh hưởng **nhiều phiên bản báo cáo**, tùy revision và quy tắc lựa chọn ở từng run.

Truy vấn trên chỉ liệt kê **hàng tổng hợp trong hệ thống mẫu**. Với một tổ chức có thêm bảng dashboard, data mart hoặc xuất file, cần lưu tiếp **dataset-level edges** và **publish metadata** để biết kết quả cuối cùng đã được chia sẻ ở đâu.

### 9.4. Đối chiếu kết quả tổng hợp với chứng cứ

Đừng chỉ tin bảng tổng hợp vì job được đánh dấu SUCCEEDED. Có thể phát hiện số tổng không còn khớp sự kiện cùng run:

~~~sql
WITH recalculated AS (
    SELECT
        run_id,
        tenant_id,
        report_date,
        SUM(CASE WHEN event_kind = 'SALE'
                 THEN signed_amount_vnd ELSE 0 END) AS gross_vnd,
        SUM(CASE WHEN event_kind = 'REFUND'
                 THEN -signed_amount_vnd ELSE 0 END) AS refund_vnd
    FROM run_financial_events
    GROUP BY run_id, tenant_id, report_date
)
SELECT
    d.run_id,
    d.tenant_id,
    d.report_date,
    d.gross_vnd,
    d.refund_vnd,
    c.gross_vnd AS recalculated_gross_vnd,
    c.refund_vnd AS recalculated_refund_vnd
FROM daily_tenant_sales AS d
JOIN recalculated AS c
  ON c.run_id = d.run_id
 AND c.tenant_id = d.tenant_id
 AND c.report_date = d.report_date
WHERE d.gross_vnd <> c.gross_vnd
   OR d.refund_vnd <> c.refund_vnd;
~~~

Trên dữ liệu mẫu, truy vấn **không trả hàng nào**. Vì dùng INNER JOIN, nó **không phát hiện** một group chỉ có ở bảng event nhưng không có ở bảng tổng hợp, hoặc ngược lại. Muốn kiểm tra đầy đủ phải dùng **FULL OUTER JOIN** trên khóa group, hoặc đối soát tập khóa bằng **EXCEPT hai chiều**; không chỉ so sánh giá trị của những group khớp nhau.

Ví dụ kiểm tra hàng group thiếu hoặc thừa:

~~~sql
WITH source_groups AS (
    SELECT DISTINCT run_id, tenant_id, report_date
    FROM run_financial_events
)
SELECT run_id, tenant_id, report_date
FROM source_groups
EXCEPT
SELECT run_id, tenant_id, report_date
FROM daily_tenant_sales;

SELECT run_id, tenant_id, report_date
FROM daily_tenant_sales
EXCEPT
SELECT DISTINCT run_id, tenant_id, report_date
FROM run_financial_events;
~~~

Cả hai truy vấn phải rỗng đối với run đã hoàn tất nếu bảng tổng hợp được định nghĩa đúng bằng các sự kiện ấy. Việc dữ liệu đã khớp **không tự chứng minh** các source event được nhận đầy đủ hoặc cách tính là đúng nghiệp vụ; đó là các kiểm tra riêng.

## 10. Sao chép qua ranh giới dịch vụ: hợp đồng sự kiện và điểm đặt dấu vết

Ở ranh giới Order Service → kho phân tích, có thể chọn **batch export**, **outbox**, **CDC**, hoặc consumer đọc từ event stream. Không kỹ thuật nào tự giải quyết lineage nếu thông điệp thiếu danh tính và ngữ nghĩa cần thiết.

### 10.1. Phần envelope thông điệp đáng giữ

Ví dụ một event nguồn:

~~~json
{
  "event_id": "O1001-L1",
  "event_type": "OrderLineConfirmed",
  "schema_version": 2,
  "aggregate_id": "O1001",
  "aggregate_version": 1,
  "tenant_id": "T01",
  "occurred_at": "2026-11-20T09:00:00+07:00",
  "published_at": "2026-11-20T09:00:01+07:00",
  "payload": {
    "line_no": 1,
    "currency_code": "VND",
    "gross_vnd": 300000
  }
}
~~~

Đây chỉ là một **hợp đồng sự kiện minh họa**. Trong nhiều hệ thống, **event_id là ID bất biến của một sự kiện**, còn thay đổi nội dung nghiệp vụ sẽ tạo **sự kiện điều chỉnh mới**, chứ không có nhiều revision dưới cùng event_id. Bài SQL dùng **source_event_id + source_version** cho nguồn cập nhật phiên bản; nếu dùng kiến trúc event sourcing bất biến, cần chuyển cách chọn nguồn tương ứng, không gán version mới cho event cũ một cách máy móc.

| Trường | Vai trò |
| --- | --- |
| event_id | Idempotency/dedup ở phạm vi được nguồn cam kết |
| event_type | Xác định sự kiện này có phải đóng góp cho chỉ số hay không |
| schema_version | Giải mã payload và quản lý tương thích |
| aggregate_id, aggregate_version | Liên kết đối tượng gốc, kiểm soát thứ tự theo aggregate |
| tenant_id | Định tuyến, phân quyền và phân tích theo khách hàng |
| occurred_at | Thời điểm nghiệp vụ |
| published_at | Thời điểm dịch vụ phát event; không bằng occurred_at trong mọi trường hợp |
| source log position / partition / offset | Bằng chứng vị trí trong stream và phục hồi checkpoint nếu có |
| correlation_id / trace_id | Liên kết luồng xử lý, hữu ích nhưng không thay thế event_id |

Không bắt buộc nhét **mọi trường** vào payload nghiệp vụ. Có thể giữ metadata trong envelope/header hoặc registry phù hợp, miễn là consumer **đọc được và duy trì liên kết** tới source event.

### 10.2. Batch, CDC và outbox có những yêu cầu lineage khác nhau

| Cơ chế | Dấu vết nên giữ | Rủi ro cần xử lý |
| --- | --- | --- |
| **Batch export** | dataset, file/object path, checksum, snapshot ID, extract time, run ID | Trùng file, xuất thiếu phần dữ liệu, nguồn thay đổi giữa hai trang |
| **CDC** | table/primary key, operation, source commit position, transaction ID, schema version | Thứ tự, tombstone, snapshot ban đầu và CDC bắt kịp, retention log |
| **Transactional outbox** | outbox event ID, aggregate ID/version, source transaction, publish checkpoint | Gửi lặp, consumer retry, lỗi sau commit trước publish |
| **Event stream** | topic, partition, offset, event ID, producer/schema version, consumer checkpoint | Consumer replay, reorder giữa partition, schema evolution |
| **API polling** | resource ID/version, ETag hoặc change token, page cursor, collected_at | Không nhìn thấy xóa, mất cập nhật giữa các lần poll, giới hạn API |

**Transactional outbox** giúp ghi trạng thái nghiệp vụ và thông điệp outbox trong cùng transaction nguồn, giảm nguy cơ “ghi đơn thành công nhưng quên phát sự kiện”. Nó **không** biến hệ thống thành exactly-once end-to-end: publisher và consumer vẫn có thể xử lý lặp, nên downstream cần khóa sự kiện và idempotent ingestion.

**CDC** giúp theo dõi thao tác thay đổi ở database, nhưng một UPDATE trong bảng vận hành không nhất thiết tương đương **một sự kiện kinh doanh mới cần cộng doanh số**. Phải hiểu logic nguồn: có thể dùng CDC để dựng snapshot/ảnh hiện hành, hoặc dùng sự kiện tài chính độc lập được xác nhận, thay vì SUM mọi phiên bản row.

### 10.3. Điều kiện để cùng một record không bị tính hai lần

Định nghĩa **khóa bất biến** và thứ tự cập nhật:

~~~text
source identity = (source_dataset, source_event_id)
source revision = source_version
selected version for run = highest accepted revision by cutoff
normalized grain = (run_id, source_dataset, source_event_id)
~~~

Trong ETL, kiểm tra:

1. Retry với **cùng ID + cùng revision + cùng payload** phải không tạo bản ghi raw trùng.
2. **Cùng ID + cùng revision nhưng khác payload** là xung đột chất lượng dữ liệu, không âm thầm chọn bản ghi đến cuối.
3. Revision cao hơn phải được xử lý theo quy tắc correction, kể cả tombstone.
4. Lỗi mapping hoặc amount âm/tiền tệ lạ phải được cách ly hoặc báo lỗi rõ.
5. Cùng event chỉ góp **một lần** trong một run; nếu thuộc nhiều chỉ số, mỗi chỉ số có cách cộng/đếm được định nghĩa riêng.

**Idempotency** là tính chất phải đạt qua những đường nạp lại/retry có thể xảy ra. **SELECT DISTINCT** ở cuối pipeline không phải chiến lược toàn vẹn nếu bản ghi bị trùng có hai số tiền hoặc có hai bản cập nhật ngữ nghĩa khác nhau.

## 11. Cutoff, watermark, snapshot và mức độ hoàn tất

### 11.1. Bốn loại thời điểm không được trộn

| Trường thời gian | Trả lời | Ví dụ |
| --- | --- | --- |
| **occurred_at** | Giao dịch xảy ra khi nào? | Dòng bán xác nhận ngày 20/11 |
| **source_committed_at / source_sequence** | Hệ nguồn ghi thay đổi khi nào/vị trí nào? | Log transaction hoặc sequence 581 |
| **published_at / ingested_at** | Thông điệp được phát và bản sao được nhận khi nào? | Event nhận ngày 23/11 |
| **report_generated_at / published_at** | Người dùng được xem kết quả từ khi nào? | Báo cáo công bố sáng 24/11 |

Một giao dịch có **occurred_at = 20/11** nhưng **ingested_at = 23/11** là dữ liệu **đến trễ**. Nếu báo cáo theo ngày xảy ra, sau khi nhận bù cần tính lại ảnh hưởng cho **20/11**, không tự cộng vào **23/11** chỉ vì đó là ngày nhận.

### 11.2. Cutoff không tương đương watermark nguồn đã hoàn tất

**Cutoff** trong mã SQL mẫu:

~~~text
Chỉ lấy raw có ingested_at <= 2026-11-22 00:00 +07.
~~~

Nó trả lời **“chúng ta đã nhìn thấy gì trước mốc nhận này?”**. Nó **không** trả lời **“mọi giao dịch nguồn xảy ra trước mốc này đã được nhận đủ chưa?”**.

Để báo cáo hoàn chỉnh, pipeline có thể cần:

- **Checkpoint/offset CDC** đã xử lý tới một vị trí nguồn tin cậy.
- **Watermark event-time** theo từng nguồn/partition và chính sách độ trễ cho phép.
- Trạng thái **source complete** cho file/batch hoặc ngày nghiệp vụ.
- Số lượng, checksum hoặc tổng tiền đối chiếu với export nguồn theo cùng grain.
- Chính sách **late-arrival window** và việc công bố lại số liệu khi có correction muộn.

Với hai nguồn Sale và Refund, **watermark phải được hiểu cho cả hai**. Nếu sale đã cập nhật đến cuối ngày nhưng refund trễ một ngày, không thể gọi báo cáo “đầy đủ” chỉ dựa trên một nguồn.

### 11.3. Snapshot nhất quán khác việc đọc từng bảng ở thời điểm khác nhau

Một pipeline có thể đọc **orders** lúc 10:00 và **refunds** lúc 10:10. Trong khoảng đó có refund mới: số liệu có thể không tương ứng với một điểm thời gian chung nếu không có chính sách chốt. Các lựa chọn tùy hệ thống:

- Snapshot transaction nhất quán trong cùng database.
- CDC/checkpoint theo log của từng nguồn kết hợp ngưỡng hoàn tất.
- Versioned object snapshot và manifest chỉ rõ dataset/version đầu vào.
- Định nghĩa báo cáo **as-of từng nguồn**, công khai rằng hai mốc không tuyệt đối đồng thời.

Giữa **hai cơ sở dữ liệu độc lập**, một transaction PostgreSQL ở kho phân tích **không tạo snapshot phân tán** tại cùng thời điểm nguồn. Nếu nghiệp vụ cần tính nhất quán mạnh xuyên dịch vụ, phải xây dựng một giao thức hoặc chính sách nghiệp vụ phù hợp, không giả định có sẵn.

### 11.4. “Dữ liệu đến trễ” và “sửa quá khứ” là hai trường hợp

**Late-arriving event:** event RF1003 xảy ra ngày 20/11 nhưng chỉ được nhận ngày 23/11; trước đó báo cáo không có event ấy.

**Correction/revision:** event RF1001 đã được nhận với refund 100.000, sau đó nguồn phát revision 2 sửa thành 120.000. Phiên bản mới **thay thế phiên bản cũ** theo mô hình snapshot-version của bài, không được cộng 100.000 + 120.000 như hai lần hoàn.

Hai tình huống dẫn đến tính lại cùng ngày nhưng cách chống trùng khác nhau. Để hỗ trợ truy vết, cần biết record **mới xuất hiện** hay **revision mới của record cũ**.

## 12. Hiệu chỉnh, tính lại (backfill) và phiên bản quy tắc

### 12.1. Ví dụ một event hoàn được sửa

Sau khi đã công bố run 9001, Refund Service gửi bản sửa:

~~~sql
INSERT INTO raw_refund_versions (
    source_event_id, source_version, tenant_id, order_id,
    occurred_at, refund_vnd, currency_code, ingested_at
) VALUES (
    'RF1001', 2, 'T01', 'O1001',
    TIMESTAMPTZ '2026-11-20 16:00:00+07', 120000, 'VND',
    TIMESTAMPTZ '2026-11-23 09:00:00+07'
);
~~~

Run 9001 có cutoff **2026-11-22 00:00 +07**, nên **vẫn tham chiếu revision 1** và giữ kết quả **800.000 VND** cho T01 ngày 20/11. Một run **9002** mới với cutoff sau **23/11 09:00 +07**, cùng transform v1.0, sẽ chọn **revision 2** và tính:

~~~text
T01, ngày 20/11:
  Gross  = 900000
  Refund = 120000
  Net    = 780000
~~~

Để chạy lại trên schema minh họa, sử dụng cùng quy trình SQL ở mục 8.2 nhưng **thay run_id = 9001 thành 9002 và source_cutoff_at thành mốc mới**. Không chạy nguyên script với run_id trùng vì primary key sẽ từ chối; không UPDATE/DELETE dòng run 9001 để che mất số đã công bố.

**Lưu ý:** nếu source dùng immutable event với event điều chỉnh độc lập, không được dùng “chọn revision cao nhất” thay cho quy tắc cộng event điều chỉnh. Phải làm rõ **event vs snapshot change** ngay tại hợp đồng nguồn.

### 12.2. Khác biệt kết quả phải có thể giải thích

Một báo cáo chênh lệch giữa hai run nên trả lời:

~~~text
Report: tenant T01 / date 2026-11-20
Run cũ: 9001, v1.0, cutoff 22/11 00:00, net 800000
Run mới: 9002, v1.0, cutoff 24/11 00:00, net 780000

Delta: -20000 VND
Source: raw_refunds / RF1001
Chọn revision cũ: 1, refund 100000
Chọn revision mới: 2, refund 120000
Lý do: correction được ingest ngày 23/11
~~~

Không chỉ lưu cột **last_updated_at** trên báo cáo: nó không cho biết lần chạy nào, nguồn nào, revision nào và quy tắc nào đã gây chênh lệch.

Một truy vấn đối chiếu số tổng theo run:

~~~sql
SELECT
    old.tenant_id,
    old.report_date,
    old.net_vnd AS net_run_9001,
    new.net_vnd AS net_run_9002,
    new.net_vnd - old.net_vnd AS delta_vnd
FROM daily_tenant_sales AS old
JOIN daily_tenant_sales AS new
  ON new.tenant_id = old.tenant_id
 AND new.report_date = old.report_date
WHERE old.run_id = 9001
  AND new.run_id = 9002;
~~~

Đây là phép so trên **những group có mặt ở cả hai run**. Nếu dữ liệu mới làm xuất hiện group mới hoặc mất group do tombstone, cần **FULL OUTER JOIN** cùng chính sách xử lý NULL/thay đổi phạm vi, không để INNER JOIN che group mới.

### 12.3. Đổi công thức còn khác sửa nguồn

Giả sử phiên bản v1.0 dùng ngày **hoàn tiền thực tế**, nhưng v2.0 đổi sang điều chỉnh khoản hoàn về **ngày bán ban đầu**. Kết quả báo cáo khác dù tất cả raw record không đổi. Trong trường hợp này, provenance phải giữ:

- **transform_version** và phiên bản mã/config đã triển khai.
- Định nghĩa nghiệp vụ và người phê duyệt thay đổi.
- Tập nguồn và cutoff được dùng để so sánh công bằng.
- Quy tắc JOIN refund → sale gốc và cách phân bổ khi một refund liên quan nhiều dòng.
- Quy tắc xử lý refund thiếu tham chiếu, nhiều currency hoặc sai mốc thời gian.

**Không nên tái sử dụng tên “v1.0” cho hai công thức khác nhau.** Trong vận hành nghiêm ngặt, gắn **code SHA/image digest** và version chính sách với từng run để có thể tái tạo cả cách triển khai, không chỉ tên phiên bản do con người đặt.

### 12.4. Backfill có kiểm soát

Khi cần tái tính một khoảng quá khứ:

1. Xác định **lý do**: late event, correction, thay đổi công thức hay sửa lỗi pipeline.
2. Đóng băng **tập đầu vào theo phiên bản và cutoff**.
3. Chọn **phạm vi ảnh hưởng**: tenant, ngày, đơn, partition hoặc toàn bộ dataset.
4. Chạy vào **staging/version mới**, không ghi đè báo cáo đã công bố khi chưa đối soát.
5. So sánh khóa nguồn, số sự kiện, checksum/tổng tiền và delta theo từng group.
6. Ghi metadata **run, transform_version, cutoff, người phê duyệt và nguyên nhân**.
7. Chỉ **publish** phiên bản mới sau khi qua kiểm tra và điều kiện chốt nguồn.
8. Giữ khả năng **rollback về phiên bản công bố trước** theo chính sách retention.

Lineage vừa giúp **tìm đúng các phần cần backfill**, vừa giúp người sử dụng giải thích vì sao một chỉ số ngày cũ thay đổi.

## 13. Lưu metadata lineage theo mức dataset, cột và record

Một data catalog hoặc pipeline orchestrator có thể ghi đồ thị **dataset dependencies**. Ở mức giản lược, dùng bảng:

~~~sql
CREATE TABLE dataset_lineage_edges (
    run_id BIGINT NOT NULL REFERENCES etl_runs(run_id),
    input_dataset TEXT NOT NULL,
    output_dataset TEXT NOT NULL,
    relation_kind TEXT NOT NULL
        CHECK (relation_kind IN ('COPY', 'NORMALIZE', 'AGGREGATE')),
    PRIMARY KEY (run_id, input_dataset, output_dataset)
);

INSERT INTO dataset_lineage_edges
    (run_id, input_dataset, output_dataset, relation_kind)
VALUES
    (9001, 'raw_sale_versions', 'run_financial_events',
     'NORMALIZE'),
    (9001, 'raw_refund_versions', 'run_financial_events',
     'NORMALIZE'),
    (9001, 'run_financial_events', 'daily_tenant_sales',
     'AGGREGATE');
~~~

Những cạnh này ghi **bảng nào góp vào bảng nào trong lần chạy 9001**; nó không thay thế cặp **source_event_id + source_version** lưu ở bảng sự kiện. Nếu có các dashboard, data mart và file xuất downstream, tiếp tục ghi cạnh từ **daily_tenant_sales** tới phiên bản dataset/artefact đã xuất bản.

### 13.1. Truy vấn các bước phụ thuộc theo run

~~~sql
WITH RECURSIVE downstream AS (
    SELECT
        input_dataset,
        output_dataset,
        1 AS hop,
        ARRAY[input_dataset, output_dataset] AS path
    FROM dataset_lineage_edges
    WHERE run_id = 9001
      AND input_dataset = 'raw_refund_versions'

    UNION ALL

    SELECT
        d.input_dataset,
        e.output_dataset,
        d.hop + 1,
        d.path || e.output_dataset
    FROM downstream AS d
    JOIN dataset_lineage_edges AS e
      ON e.run_id = 9001
     AND e.input_dataset = d.output_dataset
    WHERE NOT e.output_dataset = ANY(d.path)
)
SELECT DISTINCT output_dataset, hop, path
FROM downstream
ORDER BY hop, output_dataset;
~~~

Với dữ liệu minh họa, kết quả đi từ **raw_refund_versions → run_financial_events → daily_tenant_sales**. Điều kiện chống lặp trong path giúp tránh đi vòng vô hạn khi metadata bị cấu hình thành chu trình. Trong công cụ production, cần lưu thêm **dataset version**, môi trường, namespace, chủ sở hữu và loại quan hệ; tên bảng một mình có thể trùng ở các hệ thống.

### 13.2. Column-level lineage cần biểu diễn cả điều kiện và công thức

Ví dụ metadata quy tắc:

| Cột đích | Nguồn trực tiếp | Biến đổi |
| --- | --- | --- |
| run_financial_events.signed_amount_vnd | raw_sale_versions.gross_vnd | Dấu **dương**, sau khi chọn revision và loại tombstone |
| run_financial_events.signed_amount_vnd | raw_refund_versions.refund_vnd | Nhân **-1**, sau khi chọn revision và loại tombstone |
| run_financial_events.report_date | raw.*.occurred_at | Đổi timezone **Asia/Ho_Chi_Minh** và lấy ngày |
| daily_tenant_sales.gross_vnd | run_financial_events.signed_amount_vnd | **SUM** trên event_kind = SALE cùng run/tenant/ngày |
| daily_tenant_sales.refund_vnd | run_financial_events.signed_amount_vnd | **-SUM** trên event_kind = REFUND cùng run/tenant/ngày |
| daily_tenant_sales.net_vnd | gross_vnd, refund_vnd | **gross_vnd - refund_vnd** |

Nếu chỉ ghi cặp **cột nguồn → cột đích** mà bỏ điều kiện **event_kind**, **chọn revision**, **JOIN key** và **quy tắc ngày**, lineage ở mức cột vẫn chưa đủ giải thích kết quả. Một biểu thức phụ thuộc cùng nhiều nguồn hoặc một bản ghi nguồn được phân bổ theo tỷ lệ có thể cần metadata chi tiết hơn.

### 13.3. Khi nào cần bảng bridge đóng góp?

Trong ví dụ, mỗi event chuẩn hóa thuộc đúng **một tenant/ngày**; có thể tái tạo danh sách đóng góp từ bảng **run_financial_events** bằng JOIN như mục 9. Vì vậy **không bắt buộc** tạo thêm bảng lineage bridge.

Giả sử sau này một khoản giảm giá chung của đơn được phân bổ vào nhiều dòng, nhiều sản phẩm hoặc nhiều cost center. Khi ấy **một source event góp vào nhiều hàng đích**. Có thể dùng một bảng đóng góp:

~~~text
report_contributions(
    run_id,
    report_dataset,
    report_row_key,
    source_dataset,
    source_event_id,
    source_version,
    allocation_rule_version,
    contribution_vnd
)
~~~

Mỗi hàng nói **record nguồn nào đóng góp bao nhiêu vào record đích nào và theo quy tắc nào**. Bảng này có thể rất lớn: một event tham gia 10 báo cáo sẽ tạo ít nhất 10 liên kết. Cần xem chi phí lưu trữ, retention và phương án tái tính từ dữ liệu nguồn bất biến.

Nếu không lưu bridge chi tiết, ít nhất phải giữ **input snapshot manifest, code/config version và định danh nguồn ổn định** để truy hồi được các đóng góp khi cần. Chỉ hứa “có thể tính lại” mà raw đã hết hạn retention thì không đáp ứng khả năng kiểm toán.

### 13.4. Dataset identity, version và thời điểm công bố

Tên **daily_tenant_sales** có thể trỏ tới nhiều kết quả khác nhau: v1.0/run9001, v1.0/run9002, v2.0/run9003. Một data product cần phân biệt:

~~~text
dataset_id       = analytics.daily_tenant_sales
logical_version  = v1.0
physical_version = run_id 9001
published_at     = thời điểm kết quả được công bố
valid_for        = phạm vi tenant/ngày và định nghĩa metric
source_manifest  = danh sách source/version/cutoff
~~~

Một bước **publish** có thể cập nhật view hoặc pointer tới phiên bản đã được kiểm tra, trong một thao tác có tính nguyên tử phù hợp với nền tảng. Điều này giúp dashboard không trộn một phần dữ liệu run cũ và một phần run mới trong cùng lần đọc.

## 14. Đo chất lượng, độ mới và tính đầy đủ của pipeline

### 14.1. Các kiểm tra tối thiểu trước khi công bố

| Lớp | Kiểm tra | Nếu thất bại |
| --- | --- | --- |
| **Raw** | Schema được hỗ trợ, ID/revision hợp lệ, currency đúng | Quarantine và báo source owner |
| **Raw** | Không có cùng ID/revision nhưng hai payload mâu thuẫn | Không tự chọn một hàng “may mắn” |
| **Nguồn** | Checkpoint/watermark đủ theo chính sách | Chưa công bố là dữ liệu hoàn chỉnh |
| **Normalize** | Sale dương, refund âm, report_date đúng timezone | Kiểm tra mapping/rule version |
| **Normalize** | Một event được chọn một lần trong run | Kiểm tra dedup/source identity |
| **Normalize** | Mỗi event giữ đúng source_dataset, source_event_id, source_version | Kiểm tra link provenance |
| **Aggregate** | Tổng của các event khớp gross/refund/net từng group | Từ chối publish nếu không đối soát |
| **Aggregate** | Không thiếu/thừa group theo định nghĩa | Kiểm tra tập khóa hai chiều |
| **Publish** | Version công bố khớp run đã kiểm tra | Chặn partial publish |
| **Monitoring** | Freshness, lag, rejected rows, p95/p99 job duration | Cảnh báo và xác định phạm vi ảnh hưởng |

Các kiểm tra phải có **chính sách khi lỗi xảy ra**. Ví dụ, 50 bản ghi thiếu mapping tiền tệ không thể được bỏ qua rồi vẫn gọi báo cáo “đầy đủ” nếu chúng chứa các giao dịch tài chính quan trọng. Có hệ thống cho phép công bố dữ liệu **partial** kèm cảnh báo, nhưng cách ấy phải được người dùng số liệu hiểu và chấp thuận.

### 14.2. Kiểm tra sự kiện vượt cutoff

~~~sql
SELECT
    e.run_id,
    e.source_dataset,
    e.source_event_id,
    e.source_ingested_at,
    r.source_cutoff_at
FROM run_financial_events AS e
JOIN etl_runs AS r ON r.run_id = e.run_id
WHERE e.source_ingested_at > r.source_cutoff_at;
~~~

Truy vấn phải rỗng nếu đúng chính sách cutoff đã mô tả. Nó **không** chứng minh các event trước cutoff đã được nạp đầy đủ hoặc mỗi raw event đều được chọn đúng revision; đây là kiểm tra riêng.

### 14.3. Kiểm tra bản chuẩn hóa còn tìm thấy nguồn

~~~sql
SELECT
    e.run_id,
    e.source_dataset,
    e.source_event_id,
    e.source_version
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE (e.source_dataset = 'raw_sales'
       AND s.source_event_id IS NULL)
   OR (e.source_dataset = 'raw_refunds'
       AND r.source_event_id IS NULL);
~~~

Nếu có kết quả, dữ liệu đã mất liên kết tới nguồn hoặc khóa lineage bị sai. Một tổ chức có thể chuyển raw sang kho lưu trữ lạnh; khi đó phải giữ **URI/checksum/manifest có quyền truy cập phù hợp** và thay quy trình đối soát chứ không nhất thiết giữ raw mãi trong bảng nóng.

### 14.4. Đối chiếu tổng toàn run

Trên dữ liệu mẫu run 9001:

~~~sql
SELECT
    COUNT(*) AS normalized_events,
    COUNT(*) FILTER (WHERE event_kind = 'SALE') AS sale_events,
    COUNT(*) FILTER (WHERE event_kind = 'REFUND') AS refund_events,
    SUM(CASE WHEN event_kind = 'SALE'
             THEN signed_amount_vnd ELSE 0 END) AS gross_vnd,
    SUM(CASE WHEN event_kind = 'REFUND'
             THEN -signed_amount_vnd ELSE 0 END) AS refund_vnd,
    SUM(signed_amount_vnd) AS net_vnd
FROM run_financial_events
WHERE run_id = 9001;
~~~

Kỳ vọng:

| normalized_events | sale_events | refund_events | gross_vnd | refund_vnd | net_vnd |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 5 | 2 | 1750000 | 150000 | 1600000 |

Tổng có thể khớp ngay cả khi **một dòng thiếu và một dòng khác được nhân đôi với số tiền bằng nhau**. Vì vậy cần đối soát **khóa sự kiện** và phiên bản, không chỉ so tổng tiền hoặc số hàng.

### 14.5. Kiểm tra nguồn thiếu/không khớp phải xét phạm vi

Một câu hỏi quan trọng là:

> Tất cả các source event **đủ điều kiện** trong manifest/cutoff đã được đưa vào run chưa?

Để trả lời, trước tiên chọn **tập revision hợp lệ mới nhất** trên raw và áp cùng điều kiện thời gian, trạng thái, currency và quy tắc lọc như ETL; sau đó dùng **anti-join theo (source_dataset, source_event_id)** để tìm event bị bỏ sót. Không thể đơn giản so **COUNT(*) raw** với **COUNT(*) normalized**, vì raw có thể chứa **nhiều revision cho cùng ID**, tombstone hoặc các event chưa đủ điều kiện.

Quy tắc chất lượng nguồn cần được định nghĩa và có thể kiểm thử độc lập. Trong một số luồng, một refund mới có thể chưa tìm thấy đơn gốc do order event đến trễ; lựa chọn phù hợp có thể là **defer/quarantine** và retry, chứ không mặc nhiên xóa refund.

### 14.6. Chỉ số vận hành nên gắn với phạm vi

Theo dõi **freshness** ở nhiều cấp:

~~~text
Last successful run: khi job hoàn tất?
Last source checkpoint: đã xử lý tới offset nào?
Event-time watermark: nguồn coi dữ liệu hoàn chỉnh đến lúc nào?
Last reported business date: báo cáo có thể công bố đến ngày nào?
Quarantine backlog: còn bao nhiêu nguồn bị từ chối?
Version published: dashboard đang xem run nào?
~~~

Một pipeline chạy thành công mỗi năm phút nhưng **nguồn Refund đã ngừng gửi từ sáng** vẫn có thể tạo số sai. Chỉ nhìn **job success rate** không phát hiện được nguồn thiếu.

## 15. Quản trị dữ liệu: quyền truy cập, bảo mật và vòng đời chứng cứ

Lineage hữu ích cho truy vết, nhưng chính metadata lineage cũng là **dữ liệu cần quản trị**. Một source ID, order ID hoặc đường dẫn đến raw object có thể giúp tìm ra giao dịch của khách hàng; nếu mọi người có thể xem đồ thị này, hệ thống có thể vô tình mở thêm một kênh lộ thông tin.

### 15.1. Quyền xem kết quả không đồng nghĩa quyền xem chứng cứ nguồn

Ví dụ:

- Quản lý kinh doanh được xem **tổng doanh số theo ngày** của tenant mình.
- Nhân viên đối soát được xem **những giao dịch nguồn góp vào tổng** của tenant mình.
- Quản trị pipeline được xem **job/run, schema và lỗi nạp** nhưng không nhất thiết cần tên, địa chỉ hoặc nội dung thanh toán.
- Kiểm toán viên có quyền truy cập dữ liệu nguồn trong phạm vi vụ việc, thời hạn và mục đích đã được phê duyệt.

Nếu một bảng tổng hợp là **ẩn danh hoặc tổng hợp nhiều tenant**, việc truy ngược tới source ID chi tiết có thể yêu cầu quyền cao hơn xem bảng tổng. Cần thực thi **authorization ở từng bước drill-down**, không chỉ ở dashboard ngoài cùng.

### 15.2. Nguyên tắc tối thiểu hóa thông tin trong metadata lineage

Ưu tiên lưu:

~~~text
dataset identifier
source record key có phạm vi và chính sách truy cập
source version / checkpoint
transform version / run ID
report row key / contribution
timestamp và trạng thái chất lượng
~~~

Hạn chế sao chép vào registry những payload không cần cho truy vết như **họ tên, email, số điện thoại, địa chỉ, token, thông tin thanh toán nhạy cảm**. Khi cần xem nội dung gốc, metadata có thể trỏ tới kho raw an toàn với kiểm tra quyền; không tạo một bản sao PII mới chỉ để tiện tra cứu.

Nếu hash hoặc token hóa source ID, phải xác định mục đích: **hash không mặc nhiên ẩn danh** khi miền ID nhỏ hoặc có thể liên kết ngược. Cũng cần cân nhắc khả năng đối soát khi rotate key/token và chính sách truy xuất của người được phép.

### 15.3. Quyền riêng tư và yêu cầu xóa dữ liệu

Giả sử một người dùng có quyền yêu cầu xóa thông tin cá nhân theo chính sách áp dụng. Dữ liệu có thể đã được sao chép sang:

~~~text
operational source
  -> event / outbox
  -> raw files
  -> normalized tables
  -> dimensions
  -> reports / materialized views
  -> exports / downstream consumers
  -> backups và lineage metadata
~~~

Đồ thị lineage hỗ trợ xác định **những vị trí có thể chứa dữ liệu hoặc thông tin dẫn xuất cần đánh giá**. Tuy nhiên, quy tắc xóa/giữ lại khác nhau theo loại dữ liệu, mục đích và nghĩa vụ lưu trữ. Không thể tuyên bố mọi dữ liệu dẫn xuất đều phải xóa ngay hoặc mọi audit log đều được giữ mãi: cần chính sách pháp lý và vận hành cụ thể.

Điều quan trọng là **khả năng đánh giá tác động và chứng minh hành động đã thực hiện**, không tự động gửi bản sao nhạy cảm đến mọi người dùng có quyền xem catalog.

### 15.4. Retention phải giữ được khả năng tái tạo trong thời hạn cần thiết

Nếu nguồn raw bị xóa sau 7 ngày nhưng báo cáo cần truy vết giao dịch trong 7 năm, chỉ lưu **source_event_id + run_id** sẽ không đủ khi chứng cứ đã biến mất. Cần đặt ra chính sách cho:

| Dữ liệu | Câu hỏi retention |
| --- | --- |
| Raw payload / CDC | Giữ đầy đủ bao lâu? Có archive hoặc immutable object snapshot không? |
| Source manifest | Có đủ file ID, checksum, offset, schema và version để tái lập không? |
| Pipeline run | Cần giữ metadata mọi run hay chỉ run đã publish? |
| Record/contribution lineage | Phải truy vết từng giao dịch trong bao lâu? |
| Báo cáo đã công bố | Cần giữ snapshot để giải thích số từng được người dùng xem không? |
| Audit truy cập | Ai được phép xem/sửa và trong thời hạn nào? |

Trường hợp không thể giữ raw lâu, có thể lưu **bằng chứng tối thiểu có thể kiểm toán**, checksum, bản snapshot được bảo vệ hoặc hệ thống archive tuân thủ chính sách. Nhưng checksum **chỉ hỗ trợ xác minh** khi có dữ liệu đối chiếu; nó **không tự dựng lại nội dung đã xóa**.

## 16. Chi phí lưu trữ và kỹ thuật triển khai lineage ở quy mô lớn

### 16.1. Chọn mức chi tiết theo rủi ro, không theo khẩu hiệu

| Bối cảnh | Lineage tối thiểu đáng cân nhắc | Khi cần bổ sung |
| --- | --- | --- |
| Sao chép bảng danh mục ít thay đổi | Dataset/source ID, đồng bộ phiên bản, thời điểm chạy | Record-level khi có điều tra sửa từng item |
| Đồng bộ trạng thái đơn nhiều lần/ngày | Source record ID, source version, ingestion/checkpoint, run | Bằng chứng transition và audit khi trạng thái ảnh hưởng giao dịch |
| Tổng hợp KPI vận hành không nhạy cảm | Dataset-level, column rule, run/version/cutoff, quality checks | Contribution-level nếu người dùng cần giải thích một group |
| Báo cáo tài chính cần đối soát từng khoản | Event ID/revision, contribution, rule version, báo cáo được công bố | Source snapshot/checksum và lịch sử correction |
| Mô hình dự đoán/feature store | Dataset/version, feature transformation, training window, model run | Record/feature lineage để điều tra sai lệch quyết định theo chính sách |

**Không phải mọi nguồn cần nhân số hàng gấp đôi** để có lineage. Nếu event chuẩn hóa đã giữ đầy đủ source identity và version, truy ngược từ group bằng JOIN có thể đủ. Khi một phép biến đổi làm mất khả năng suy ra record nguồn (ví dụ phân bổ nhiều–nhiều, dedup không ghi bản bị loại), cần tăng độ chi tiết hoặc lưu manifest chứng cứ.

### 16.2. Chỉ mục cho hai hướng truy vết

Truy vấn từ **report → event** trong mục 9 dùng:

~~~sql
CREATE INDEX idx_run_financial_report_lookup
ON run_financial_events (run_id, tenant_id, report_date);
~~~

Chỉ mục tương đương đã được tạo ở mục 6.5 với tên **idx_financial_events_run_day**, nên **không thực thi thêm chỉ mục trùng này trên ví dụ hiện có**. Đoạn trên chỉ nhắc lại hình dạng chỉ mục hữu ích cho hướng truy ngược.

Ngược lại, truy vấn từ **source → báo cáo bị ảnh hưởng** thường cần thứ tự khóa khác:

~~~sql
CREATE INDEX idx_run_financial_source_impact
ON run_financial_events (
    source_dataset,
    source_event_id,
    run_id
);
~~~

Lựa chọn chỉ mục phải dựa trên số hàng, mức chọn lọc, query plan và tần suất sử dụng. Với dữ liệu nhiều tỷ hàng, có thể phân vùng theo **run_id/ngày**, xây index cục bộ hoặc duy trì registry tra cứu riêng; cách partition cần tuân thủ những giới hạn UNIQUE/PK của engine. Không thêm mọi chỉ mục chỉ vì có thể viết một truy vấn.

### 16.3. Lưu raw bất biến và replay

Một số hệ thống giữ:

~~~text
raw source event / version (append-only, có archive)
    +
manifest của input snapshot
    +
transform code/config version
    +
run metadata
    =
khả năng replay có kiểm soát
~~~

Phương trình trên thể hiện **những điều kiện cần về chứng cứ**, không phải bảo đảm tự động replay ra byte giống nhau. Kết quả còn có thể phụ thuộc vào:

- Thư viện và phiên bản hệ thống chạy.
- Timezone, locale, lịch/ngày nghỉ và cách làm tròn.
- Tỷ giá, bảng tham chiếu và dimension tại thời điểm as-of.
- Thứ tự xử lý khi có phép toán không kết hợp hoặc không xác định.
- Hàm không xác định như random(), current_timestamp và dữ liệu API thời gian thực.
- Chính sách xử lý NULL, dữ liệu lỗi, late event và retry.

Muốn tái tạo **chính xác**, phải xác định và cố định các đầu vào không thuần túy dữ liệu nguồn. Thực hành tốt là coi transform như hàm của **input snapshot + rule/config version + reference snapshot**, tránh để một truy vấn “lấy trạng thái hiện tại” thay đổi kết quả lịch sử âm thầm.

### 16.4. Lineage tự động và lineage được đặc tả

Có thể trích lineage tự động từ **SQL parser**, query plan, orchestrator và metadata execution. Cách đó hữu ích để ghi dataset/column dependencies, nhưng có những giới hạn:

- Quy tắc trong UDF, Java/Python service, API call hoặc stored procedure có thể khó phân tích tĩnh.
- SQL có điều kiện động, schema thay đổi hoặc SELECT * khiến column lineage không đầy đủ.
- Câu lệnh JOIN cho thấy cột liên quan, chưa giải thích **ngữ nghĩa nghiệp vụ** của phép JOIN.
- Một job đọc bảng nhưng chỉ dùng một tập nhỏ dữ liệu theo predicate; dependency table-level có thể quá rộng cho impact analysis.
- Một record bị loại bởi filter vẫn có thể cần lý do loại để kiểm toán tính đầy đủ.

Vì vậy, nên kết hợp **metadata thu thập tự động** với **data contract và quy tắc nghiệp vụ được phê duyệt**, và kiểm tra định kỳ những cạnh lineage quan trọng chứ không chỉ tin một sơ đồ DAG.

### 16.5. Bảo vệ tenant boundary trong câu truy vấn lineage

Trong hệ đa tenant, một ID như **O1001** có thể xuất hiện ở hai tenant nếu nguồn chỉ cam kết duy nhất theo tenant. Khi drill-down:

~~~sql
SELECT e.*
FROM run_financial_events AS e
WHERE e.run_id = 9001
  AND e.tenant_id = 'T01'
  AND e.order_id = 'O1001';
~~~

Không nên tìm trên **order_id** một mình rồi trả mọi bản ghi từ mọi tenant. Nếu quy tắc source ID chỉ duy nhất **trong tenant**, schema lineage và phép JOIN tới raw phải mang **tenant_id** trong khóa định danh tương ứng. Bên cạnh điều kiện SQL, hệ thống có thể cần **row-level security hoặc chính sách phân quyền** ở tầng phục vụ; người dùng không được tin cậy chỉ vì đã truyền tenant_id trong request.

## 17. Quy trình thiết kế provenance từ yêu cầu đến vận hành

1. **Định nghĩa dữ kiện và người sở hữu:** một event là gì, nguồn nào là chuẩn, source ID duy nhất ở đâu và có revision hay không?
2. **Chốt grain từng lớp:** raw version, normalized event, fact, aggregate và dataset xuất bản; tránh đếm nhầm hàng sau JOIN.
3. **Phân biệt thời gian:** occurred/effective, committed, published, ingested, report as-of.
4. **Xác định hợp đồng nguồn:** event ID/version, loại sự kiện, schema, currency, tenant, deletion/correction, thứ tự và khả năng replay.
5. **Chọn mức lineage cần thiết:** dataset, column, run, record hay contribution; cân nhắc rủi ro và retention.
6. **Lưu run metadata và manifest:** code/config version, nguồn, snapshot/cutoff, checkpoint/watermark, trạng thái và người phê duyệt.
7. **Thiết kế biến đổi có thể giải thích:** filter, dedup, JOIN, quy đổi, phân bổ, timezone, rounding; kiểm thử logic thuần.
8. **Tách staging và dữ liệu đã công bố:** dữ liệu raw bất biến, bảng chuẩn hóa có provenance, bản tổng hợp có version và pointer publish.
9. **Kiểm tra hai chiều:** từ báo cáo về sự kiện/raw và từ sự kiện về những đích; đối soát số dòng, khóa và số đo.
10. **Xử lý late/correction/backfill:** giữ run cũ, tạo run mới, so delta và publish có kiểm soát.
11. **Đặt quyền và retention:** bảo vệ thông tin nhạy cảm trên cả payload và metadata, thực hiện chính sách xóa/archive.
12. **Giám sát và cải tiến:** quality, freshness theo nguồn, quarantine backlog, lineage completeness, chi phí truy vấn và thời gian tái tính.

### 17.1. Câu hỏi nghiệm thu có thể kiểm chứng

> Khi có người hỏi “Vì sao dashboard ngày 20/11 hiển thị 800.000 VND cho T01?”, nhóm dữ liệu có trả lời được trong phạm vi thời gian vận hành đã cam kết không?

Một câu trả lời đủ mạnh cần có:

~~~text
report row:
  dataset = daily_tenant_sales
  run_id = 9001
  tenant = T01
  report_date = 2026-11-20
  net_vnd = 800000

transformation:
  transform = daily_net_sales / v1.0
  source_cutoff = 2026-11-22 00:00 +07
  timezone = Asia/Ho_Chi_Minh
  formula = gross SALE - settled REFUND by occurred_at date

contributions:
  raw_sales/O1001-L1@v1 = +300000
  raw_sales/O1001-L2@v1 = +200000
  raw_sales/O1002-L1@v1 = +400000
  raw_refunds/RF1001@v1 = -100000

quality:
  source versions traceable
  totals reconciled
  published version and source completeness status available
~~~

Nếu chỉ biết “job chạy xong lúc 1 giờ sáng” hoặc “con số lấy từ bảng daily_sales” thì chưa đủ để giải thích nguồn gốc và phép tính.

## 18. Bài tập thực hành

### Bài 1. Truy nguồn một số tổng

Trong run 9001, tenant T01 ngày 20/11 có:

~~~text
SALE:   O1001-L1 = +300000
SALE:   O1001-L2 = +200000
SALE:   O1002-L1 = +400000
REFUND: RF1001   = -100000
~~~

**Yêu cầu:**

1. Tính gross_vnd, refund_vnd và net_vnd.
2. Cho biết **grain** của bảng tổng hợp và grain của bảng run_financial_events.
3. Muốn truy raw chính xác của sự kiện RF1001, cần ít nhất những trường nào?
4. Vì sao chỉ lưu **order_id = O1001** trên bảng tổng hợp không đủ để giải thích toàn bộ kết quả?

<details>
<summary>Gợi ý lời giải bài 1</summary>

- **gross_vnd = 900000**, **refund_vnd = 100000**, **net_vnd = 800000**.
- **daily_tenant_sales** có grain **(run_id, tenant_id, report_date)**; **run_financial_events** có grain **(run_id, source_dataset, source_event_id)**.
- Để tìm raw revision, cần **source_dataset = raw_refunds**, **source_event_id = RF1001**, **source_version = 1**, cùng thông tin nguồn/namespace trong môi trường thật. run_id giúp biết **báo cáo nào** đã chọn revision ấy.
- Một đơn có thể có nhiều dòng và refund; hơn nữa báo cáo ngày của T01 còn có **O1002-L1**, nên order_id O1001 không biểu diễn toàn bộ tập sự kiện đóng góp.

</details>

### Bài 2. Sửa nguồn và giữ lịch sử báo cáo

Run 9001 có cutoff 22/11 00:00 +07 và dùng refund **RF1001@v1 = 100000**. Ngày 23/11, nguồn gửi **RF1001@v2 = 120000**, với cùng occurred_at ngày 20/11. Không có nguồn nào khác thay đổi.

**Yêu cầu:**

1. Số net của run 9001 có được tự sửa thành 780000 không?
2. Nếu chạy run 9002 theo cùng công thức, cutoff sau khi nhận v2, kết quả net ngày 20/11 của T01 là bao nhiêu?
3. Nếu một job cộng cả RF1001@v1 và RF1001@v2, lỗi thuộc loại nào?
4. Metadata nào giải thích chênh lệch hai run?

<details>
<summary>Gợi ý lời giải bài 2</summary>

- **Không** tự sửa run 9001: nó là kết quả đã tính với snapshot/cutoff cũ và có giá trị kiểm toán.
- Run 9002 chọn **revision cao nhất đã nhận**, nên refund = 120000 và **net = 900000 - 120000 = 780000**.
- Cộng 100000 + 120000 là **double count các phiên bản của một source event**, vi phạm quy tắc chọn revision; không phải hai khoản refund độc lập.
- Cần **source_dataset, source_event_id, source_version**, cutoff, run ID, transform version và thời gian nhận revision mới để giải thích delta **-20000**.

</details>

### Bài 3. Event-time và ingestion-time

Một refund 50.000 VND xảy ra lúc **20/11 23:50 +07**, nhưng vì sự cố mạng chỉ được nhập kho lúc **23/11 08:00 +07**. Báo cáo run 9001 có cutoff ngày **22/11 00:00 +07**.

**Yêu cầu:**

1. Refund ấy có thuộc run 9001 không?
2. Khi tính lại với cutoff sau ngày 23/11, refund nên tác động vào **ngày 20/11 hay 23/11** theo quy tắc bài?
3. Nếu dashboard đã công bố ngày 20/11, cần thực hiện những bước nào để giải thích số thay đổi?
4. Vì sao chỉ ghi **updated_at** trong bảng tổng hợp là không đủ?

<details>
<summary>Gợi ý lời giải bài 3</summary>

Refund **không thuộc run 9001** do **ingested_at** sau cutoff. Theo quy tắc ngày xảy ra sự kiện, nó tác động vào **20/11** khi được nạp trong lần chạy mới, không phải ngày 23/11.

Cần ghi nguồn và event ID, run/cutoff mới, xác minh refund hợp lệ, tính lại group bị ảnh hưởng, đối soát delta, công bố phiên bản mới có ghi chú dữ liệu đến trễ và giữ lịch sử run cũ. **updated_at** chỉ nói khi hàng bị sửa; không nói **sự kiện nào, revision nào, công thức nào, cutoff nào** đã thay đổi kết quả.

</details>

### Bài 4. Đồ thị dataset có đủ để kiểm toán từng hàng?

Một nhóm lưu DAG:

~~~text
orders -> raw_orders -> normalized_sales -> daily_sales
refunds -> raw_refunds -> normalized_sales -> daily_sales
~~~

Nhóm khẳng định vì đã có sơ đồ nên có thể chứng minh mọi khoản tiền đóng góp vào một hàng **daily_sales**.

**Yêu cầu:**

1. Sơ đồ này thực sự cung cấp mức lineage nào?
2. Nó thiếu gì khi người dùng hỏi vì sao một hàng có số tiền 800000?
3. Nếu một refund cần phân bổ vào ba dòng đơn, cần ghi thêm thông tin gì?
4. Nêu một trường hợp chỉ cần lineage ở mức dataset/job là hợp lý.

<details>
<summary>Gợi ý lời giải bài 4</summary>

DAG cung cấp **dataset-level lineage**, giúp tìm bảng upstream và downstream. Để chứng minh số 800000 cần **run/version/cutoff**, nguồn record ID/revision, quy tắc lọc, dấu đóng góp, ngày và phép tổng. Nếu refund phân bổ vào ba dòng, cần **tỷ lệ/giá trị phân bổ, khóa hàng đích và phiên bản quy tắc làm tròn** để bảo đảm tổng đóng góp khớp refund gốc.

Lineage ở mức dataset/job có thể đủ cho một pipeline sao chép bảng tham chiếu nhỏ để phục vụ nội bộ, khi không có yêu cầu kiểm toán từng hàng và có thể rebuild từ snapshot đã lưu.

</details>

### Bài 5. SQL tìm sự kiện không tìm được bản raw

Bảng **run_financial_events** có source_dataset nhận **raw_sales** hoặc **raw_refunds**. Hãy viết truy vấn tìm các event của run 9001 mà **source_event_id + source_version** không khớp bản ghi nào trong đúng bảng raw.

**Yêu cầu bổ sung:** vì sao không JOIN vào hai bảng raw chỉ bằng **order_id**?

<details>
<summary>Gợi ý lời giải bài 5</summary>

Một cách dùng hai LEFT JOIN có điều kiện:

~~~sql
SELECT e.source_dataset, e.source_event_id, e.source_version
FROM run_financial_events AS e
LEFT JOIN raw_sale_versions AS s
  ON e.source_dataset = 'raw_sales'
 AND s.source_event_id = e.source_event_id
 AND s.source_version = e.source_version
LEFT JOIN raw_refund_versions AS r
  ON e.source_dataset = 'raw_refunds'
 AND r.source_event_id = e.source_event_id
 AND r.source_version = e.source_version
WHERE e.run_id = 9001
  AND (
      (e.source_dataset = 'raw_sales'
       AND s.source_event_id IS NULL)
      OR
      (e.source_dataset = 'raw_refunds'
       AND r.source_event_id IS NULL)
  );
~~~

**order_id không xác định duy nhất source event**: một đơn có thể có nhiều dòng, nhiều refund và các lần sửa. JOIN bằng order_id có thể tạo nhiều kết hợp giả, làm sai truy vết hoặc cộng trùng số tiền.

</details>

### Bài 6. Kiểm tra nguồn hoàn tất và số liệu bị trễ

Order Service đã chuyển đủ dữ liệu tới cuối ngày 21/11. Refund Service chỉ mới chuyển tới **12:00 ngày 21/11**. Job tính bảng daily_sales và báo **SUCCEEDED** lúc 00:30 ngày 22/11.

**Yêu cầu:**

1. Có thể gọi báo cáo ngày 21/11 là **hoàn chỉnh** chỉ vì job chạy thành công không?
2. Cần những metadata/checkpoint nào từ hai nguồn?
3. Nếu vẫn cho phép hiển thị, dashboard nên diễn đạt trạng thái dữ liệu thế nào?
4. Vì sao dùng source_cutoff_at trong database đích không thể thay thế watermark nguồn?

<details>
<summary>Gợi ý lời giải bài 6</summary>

Không. Job thành công chỉ nói bước xử lý hoàn tất với **những record đã nhìn thấy**. Cần checkpoint hoặc watermark của **cả nguồn Order và Refund**, chính sách độ trễ, số liệu đối soát hoặc trạng thái hoàn tất theo kỳ.

Nếu nghiệp vụ cho phép xem trước, dashboard nên hiển thị **preliminary/partial**, thời điểm dữ liệu gần nhất của từng nguồn và cảnh báo rằng số có thể cập nhật. **source_cutoff_at** chỉ giới hạn dữ liệu đã ingest; nó không bảo đảm các event nghiệp vụ của Refund Service đã được chuyển hết.

</details>

### Bài 7. Tác động và quyền riêng tư

Một bảng tổng hợp doanh số được chia sẻ rộng cho các quản lý. Một nhân viên phát hiện link drill-down có thể tải toàn bộ thông tin cá nhân của khách hàng trên raw record mà không cần xác thực bổ sung.

**Yêu cầu:** nêu ít nhất bốn thay đổi thiết kế hoặc vận hành để vẫn có lineage phục vụ kiểm toán nhưng giảm rủi ro lộ dữ liệu.

**Hướng giải:** tách quyền xem tổng hợp với quyền xem record/raw, kiểm tra **tenant scope và authorization** ở từng bước, tối thiểu hóa PII trong metadata, liên kết tới kho chứng cứ có quyền truy cập riêng, ghi audit cho truy cập nhạy cảm, áp retention/xóa theo chính sách, token hóa định danh khi thích hợp và kiểm thử việc người dùng tenant A không thể xem record tenant B. **Có lineage** không có nghĩa mọi người dùng đều được truy cập mọi tầng dữ liệu.

## 19. Những nhầm lẫn thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Biết bảng nguồn là đủ để truy vết mọi chỉ số.” | Dataset-level lineage không tự chỉ ra record/revision và số đóng góp. |
| “Có trace_id nên chắc chắn đã biết nguồn gốc bản ghi.” | Distributed tracing mô tả đường đi request; cần source ID và mapping dữ liệu. |
| “Job SUCCEEDED nghĩa là dữ liệu từ mọi hệ nguồn đã đủ.” | Phải kiểm tra checkpoint, watermark và chất lượng **theo từng nguồn**. |
| “ingested_at là ngày nghiệp vụ xảy ra.” | Event time và ingestion time có thể khác nhiều ngày. |
| “Source ID giống nhau ở hai dịch vụ là cùng một sự kiện.” | ID phải kèm **nguồn/namespace** và phạm vi duy nhất. |
| “Cứ SUM mọi revision trong raw sẽ có số chính xác.” | Revision có thể **thay thế** nhau; chọn latest hoặc áp chính sách event điều chỉnh. |
| “Chỉ cần giữ latest report, không cần run cũ.” | Mất khả năng giải thích số đã công bố trước correction hoặc đổi luật. |
| “Chạy cùng SQL luôn ra cùng kết quả.” | Input snapshot, cutoff, reference data, version và hàm không xác định có thể khác. |
| “Đếm số hàng và so tổng tiền là đủ đối soát.” | Hai lỗi bù trừ có thể làm tổng khớp; cần so ID/revision và tập khóa. |
| “Sửa một refund thì không cần tìm báo cáo bị ảnh hưởng.” | Có thể phải backfill nhiều ngày, nhóm, dashboard và data mart. |
| “Không có event trong kho tức là không có sự kiện ở nguồn.” | Có thể chưa ingest, bị reject, bị retention xóa hoặc trễ đồng bộ. |
| “Lineage phải lưu mọi payload trong catalog.” | Chỉ lưu metadata tối thiểu và dẫn tới nguồn an toàn khi cần. |
| “Đã hash ID thì dữ liệu lineage tự ẩn danh.” | ID hash còn có thể bị liên kết hoặc suy đoán; vẫn cần chính sách bảo mật. |
| “Lineage tự động từ SQL hiểu hết nghiệp vụ.” | Parser thấy phụ thuộc cột nhưng không tự hiểu nghĩa hoàn tiền, tỷ giá hay policy. |
| “Cập nhật hàng tổng hợp là đủ để sửa số.” | Phải biết nguyên nhân, run/version, dữ liệu nguồn và ảnh hưởng downstream. |

## 20. Checklist nghiệm thu lineage và provenance

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Một hàng nguồn được định danh bằng gì và duy nhất ở phạm vi nào? | Source namespace, record ID, revision/sequence, data contract |
| Nguồn sở hữu sự thật nào? | Danh sách source-of-truth và người chịu trách nhiệm |
| Grain của raw, normalized và aggregate có rõ không? | Đặc tả một hàng, khóa ứng viên, quan hệ |
| Event time, ingestion time và report as-of có tách biệt không? | Các timestamp và chính sách ngày/múi giờ |
| Job đã chạy bản logic nào? | Run ID, transform version, code/config digest |
| Bản đầu vào được chốt bằng cách nào? | Snapshot manifest, cutoff, checkpoint/watermark |
| Có tìm được chính xác revision nguồn cho một hàng đích? | Source dataset + ID + version và đường truy cập raw |
| Có truy được event đóng góp vào một số tổng không? | Contribution query/bridge, công thức dấu/rounding |
| Có xác định được downstream bị ảnh hưởng khi sửa nguồn không? | Dataset edges và published artefact versions |
| Event retry, revision, tombstone và late data được xử lý đúng chưa? | Idempotency, tests, quarantine và reprocessing policy |
| Có kiểm tra hàng thiếu/thừa, số tiền và schema không? | Kiểm thử tự động, reconciliation report |
| Có phân biệt job success với source completeness không? | Watermark từng nguồn, freshness và backlog |
| Có thể giữ/sửa lịch sử báo cáo mà không xóa chứng cứ? | Versioned runs, backfill, publish pointer, rollback |
| Ai được xem raw và thông tin truy nguồn? | Authorization, tenant isolation, audit, retention |
| Có thể tái tạo kết quả trong thời hạn cam kết không? | Raw/reference snapshots, code version và quy trình replay |
| Chi phí lưu metadata đã phù hợp quy mô chưa? | Chính sách chi tiết lineage, index/partition và archive |

## 21. Ghi nhớ

**Theo dõi nguồn gốc dữ liệu** không chỉ là vẽ mũi tên giữa hai bảng. Với dữ liệu sao chép qua ranh giới dịch vụ, phải biết **nguồn chuẩn, khóa và phiên bản nguồn, thời điểm nghiệp vụ, thời điểm nhận, trạng thái đồng bộ và lần chạy đã tạo bản sao**. Với dữ liệu tổng hợp, phải bổ sung **grain, quy tắc lọc/khử trùng/JOIN, công thức đóng góp, transform version và cách xác định tập đầu vào**.

Ví dụ doanh số ròng cho thấy một hàng báo cáo **800.000 VND** có thể được giải thích bằng **ba sự kiện sale** và **một sự kiện refund**, cùng **run 9001**, phiên bản phép tính và cutoff. Khi refund được sửa, tạo **run mới và so delta** thay vì âm thầm sửa kết quả cũ; khi nguồn đến trễ, đánh giá mức độ hoàn tất theo checkpoint/watermark chứ không chỉ dựa trên job thành công.

Một thiết kế đáng tin cậy cần hỗ trợ cả hai chiều: **từ báo cáo về đúng nguồn** để giải thích, kiểm toán và đối soát; **từ nguồn tới các đích phụ thuộc** để đánh giá tác động, sửa dữ liệu và backfill. Mọi bước phải tôn trọng **grain, khóa, tính nhất quán, lịch sử, phạm vi tenant và quyền riêng tư**. Thứ tự thực hành hữu ích là **định nghĩa sự thật → chốt grain/khóa/version → lưu dấu vết qua ranh giới → biến đổi có thể tái tạo → đối soát → công bố theo phiên bản → giám sát và quản trị vòng đời**.
