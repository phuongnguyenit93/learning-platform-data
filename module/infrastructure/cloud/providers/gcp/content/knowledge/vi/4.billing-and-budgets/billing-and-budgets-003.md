# Đọc bảng giá, SKU và đơn vị tính phí của GCP

## 1. Vì sao phải biết đọc bảng giá Google Cloud?

Một kiến trúc chạy được trên Google Cloud chưa chắc đã có chi phí dự đoán được. Chẳng hạn, một ứng dụng bán hàng dùng **Cloud Run**, **Cloud SQL**, **Cloud Storage** và **VPC** có thể trả tiền cho thời gian xử lý, bộ nhớ, dung lượng lưu trữ, số thao tác và lưu lượng mạng dưới những **SKU** khác nhau. Nếu chỉ nhìn giá của một dịch vụ, nhóm phát triển dễ bỏ sót khoản phí quan trọng.

Trong module **CLOUD_PROVIDERS_GCP**, người học tìm hiểu từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, phát hành và vận hành. Phần **Thanh toán và ngân sách** bổ sung một kỹ năng xuyên suốt: **đọc đúng một dòng giá, hiểu đơn vị đo, tính chi phí dự kiến và kiểm chứng khoản phí thực tế**.

Sau bài học, bạn có thể:

1. Phân biệt **Cloud Billing account**, **service**, **SKU**, **consumption model** và **pricing tier**.
2. Đọc các cột quan trọng trong **Pricing table**: mã SKU, phạm vi địa lý, đơn vị tính phí, lượng tính theo một mức giá và mốc bắt đầu của từng bậc.
3. Quy đổi giữa đơn vị sử dụng và đơn vị tính giá; tính thử giá một hoặc nhiều bậc bằng công thức minh bạch.
4. Tìm nguyên nhân chênh lệch giữa bảng giá công khai, dự toán, Billing reports, **Cost table** và hóa đơn.
5. Áp dụng kỹ năng này khi chọn dịch vụ hoặc đánh giá kiến trúc Google Cloud về hiệu năng, độ tin cậy và chi phí.

> **Quy ước:** Mọi con số đơn giá trong các bài tính bên dưới đều là **số liệu giả định để học cách tính**, không phải giá bán hiện tại của Google Cloud. Khi ra quyết định triển khai, hãy tra cứu giá tại **ngày kiểm tra**, trong **đúng billing account, vùng, tiền tệ, SKU và consumption model** của mình.

## 2. Bức tranh tổng thể: từ tài nguyên đến khoản phí

Một **Cloud Billing account** là tài khoản thanh toán dùng để chi trả cho một hoặc nhiều Google Cloud project được liên kết. Project dùng để tổ chức và kiểm soát tài nguyên; billing account dùng để quản lý cách thanh toán và tập hợp nhiều khoản chi. Một project không tự đồng nghĩa một hóa đơn riêng.

Khi workload hoạt động, dịch vụ ghi nhận **usage** (mức tiêu thụ). Usage được gắn với **service** (ví dụ Compute Engine), **SKU** (một loại tài nguyên hoặc hoạt động có cách định giá cụ thể) và các thông tin như vị trí, khoảng thời gian, mức giá áp dụng. Cloud Billing dùng những thông tin này để xác định chi phí.

```mermaid
flowchart LR
    A[Project và workload] --> B[Phát sinh mức sử dụng]
    B --> C[Service và SKU]
    C --> D[Đơn vị, vùng, bậc giá, consumption model]
    D --> E[Chi phí sử dụng]
    E --> F[Giảm giá, credits, điều chỉnh, thuế nếu áp dụng]
    F --> G[Phân tích chi phí và đối chiếu hóa đơn]
```

Sơ đồ chỉ mô tả mối quan hệ logic. Một workload có thể phát sinh **nhiều dòng SKU** ở nhiều dịch vụ, project hoặc vùng khác nhau; các loại ưu đãi và phụ phí không nhất thiết được hiển thị như một mức giảm trên cùng dòng giá.

### Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa trong Cloud Billing | Câu hỏi cần hỏi |
| --- | --- | --- |
| **Service** | Dịch vụ báo cáo lượng dùng, ví dụ Compute Engine, Cloud Storage, Cloud SQL | Chi phí thuộc sản phẩm nào? |
| **Service ID** | Mã định danh dịch vụ, dùng liên kết dữ liệu kỹ thuật | Có đang xem đúng dịch vụ không? |
| **SKU (Stock Keeping Unit)** | Định danh loại tài nguyên/hoạt động được tính giá | Mình đang trả tiền **cho cái gì**? |
| **SKU ID** | Mã nhận diện SKU, ổn định hơn mô tả để phân tích và đối soát | Có thể đối chiếu dòng sử dụng với dòng bảng giá nào? |
| **Usage** | Lượng sử dụng được đo trong một khoảng thời gian | Đã tiêu thụ bao nhiêu? |
| **Pricing unit** | Đơn vị dùng để biểu diễn mức giá | Đơn giá tính theo GiB, GiB-tháng, giờ, giây hay triệu yêu cầu? |
| **Per unit quantity** | Giá niêm yết ứng với **bao nhiêu** đơn vị tính giá | Mức giá có phải dành cho 1 hay 1.000.000 đơn vị? |
| **Pricing tier** | Một bậc giá tương ứng với ngưỡng mức sử dụng | Khối lượng tăng có làm đổi đơn giá không? |
| **Consumption model** | Mô hình định giá được áp dụng cho một lượng SKU usage trong ngữ cảnh cụ thể | Đang tính theo mức mặc định hay giá của hình thức cam kết? |
| **List price** | Giá niêm yết công khai hoặc trên bảng giá tại thời điểm xem | Đây có phải giá thực tế theo hợp đồng của mình? |
| **Contract price** | Giá theo thỏa thuận của billing account, nếu có | Có được phép xem và sử dụng mức giá riêng không? |
| **Credits** | Khoản ghi giảm giá trị thanh toán theo điều kiện chương trình | Khoản ghi giảm nằm ở dòng nào trong báo cáo? |

**SKU không phải tên máy ảo hay tên project.** Chẳng hạn, một VM Compute Engine có thể dẫn tới nhiều khoản phí tính riêng cho năng lực tính toán, ổ đĩa, snapshot và mạng. Một database Cloud SQL cũng có thể có phần chi phí instance, storage, backup và lưu lượng mạng. Chi tiết SKU cụ thể phụ thuộc dịch vụ, cấu hình và bảng giá hiện hành.

## 3. Mở đúng bảng giá và chọn đúng ngữ cảnh

Google Cloud có nhiều trang và công cụ có tên gần giống nhau. Mỗi công cụ trả lời một câu hỏi khác:

| Nơi tra cứu | Dùng để làm gì? | Điểm cần chú ý |
| --- | --- | --- |
| **Trang Pricing của từng sản phẩm** | Hiểu mô hình tính phí, ngoại lệ, ví dụ, Free Tier và các tính năng phát sinh phí | Diễn giải của dịch vụ là nền tảng trước khi tính giá |
| **Cloud Billing → Pricing** (**Pricing table**) | Tra **giá theo SKU** và bậc giá của các dịch vụ | Giá đang hiển thị tại thời điểm xem; quyền truy cập quyết định có thấy giá hợp đồng không |
| **Google Cloud Pricing Calculator** | Ước lượng chi phí trước khi triển khai theo cấu hình và usage dự kiến | Kết quả dự toán không phải cam kết hóa đơn |
| **Cloud Billing → Reports** | Phân tích xu hướng tiền đã phát sinh, lọc theo project, service, SKU, nhãn và thời gian | Phải kiểm tra bộ lọc và khoảng thời gian |
| **Cloud Billing → Cost table** | Đối chiếu chi phí và credits của **tháng hóa đơn** theo project/service/SKU | Phù hợp truy nguyên khoản phí trên invoice/statement |
| **Cloud Billing export → BigQuery** | Phân tích lịch sử usage/cost hoặc giá ở mức chi tiết bằng SQL | Phải chủ động bật export; chi tiết và dữ liệu quá khứ phụ thuộc loại export |
| **Cloud Billing Catalog API / Pricing API** | Lấy metadata và giá bằng chương trình | Catalog API cho giá công khai; Pricing API phục vụ giá gắn với billing account theo quyền tương ứng |

### Cách đọc Pricing table

1. Vào **Google Cloud Console → Billing**, chọn **Cloud Billing account** cần phân tích.
2. Trong trang Billing, mở **Pricing**. Người dùng chỉ có quyền giới hạn có thể thấy bảng **giá công khai**, còn người có quyền `billing.accounts.getPricing` có thể xem **giá hợp đồng** khi billing account có thỏa thuận tương ứng.
3. Chọn **View all SKUs** nếu muốn tra toàn bộ danh mục, hoặc **SKUs with historical usage** nếu cần khoanh vùng những SKU đã tiêu thụ, khi quyền truy cập cho phép.
4. Lọc **Service description** (ví dụ Cloud Storage), rồi quan sát **SKU ID**, **SKU description**, **Consumption model**, **Geo taxonomy**, **Unit**, **Per unit quantity**, **Tiered usage start** và **List price**.
5. Nếu một SKU có nhiều hàng, kiểm tra xem đó là **các bậc giá** hay các **consumption model** khác nhau trước khi cộng hoặc so sánh.
6. Kiểm tra **đơn vị tiền tệ** của billing account. Bảng giá của một billing account có thể hiển thị bằng đồng tiền khác USD.

**Điểm dễ nhầm:** Bảng Pricing thể hiện **giá hiện tại**, còn Cost table và hóa đơn phản ánh giá/điều kiện tính phí cho khoảng usage hoặc invoice cụ thể. Giá của SKU có thể thay đổi theo thời gian. Bảng Pricing **không tự bao gồm các credits** như khuyến mại hoặc những khoản hỗ trợ được hạch toán riêng.

## 4. Giải mã một dòng SKU

Một dòng giả định trong bảng giá có thể được diễn đạt:

| Trường | Giá trị minh họa | Cách đọc |
| --- | --- | --- |
| Service | Cloud Storage | Dịch vụ phát sinh phí |
| SKU description | Standard Storage – một vị trí minh họa | Loại usage đang được định giá; cần xem đúng vùng và storage class |
| SKU ID | `SKU_ID_GIA_DINH` | Mã để liên kết bảng giá và báo cáo; **không phải mã SKU thực** |
| Geo taxonomy | Region / vùng tương ứng | Giá hoặc phạm vi áp dụng theo vị trí |
| Unit | GiBy.mo | Dung lượng lưu trung bình nhân thời gian lưu, thường đọc là GiB-tháng |
| Per unit quantity | 1 | Giá áp dụng cho một đơn vị của cột Unit |
| Tiered usage start | 0 | Bậc đầu tiên bắt đầu từ lượng dùng 0 |
| List price | **0,02 USD** | Đơn giá giả định cho một GiB-tháng |

Từ bảng này, có thể đọc: “Dịch vụ đang tính phí lưu trữ theo **GiB-tháng**, giá giả định **0,02 USD cho mỗi GiB-tháng**, ở vị trí và bậc giá đã chọn”.

Điều **chưa được kết luận**: tổng chi phí bucket. Bucket có thể phát sinh thêm phí thao tác, truy xuất, di chuyển dữ liệu, chính sách lưu trữ tối thiểu hoặc những khoản khác theo storage class và cấu hình. Cần đọc trang giá Cloud Storage và kiểm tra toàn bộ SKU thực tế.

### SKU ID, SKU description và vị trí

Hai SKU có mô tả khá giống nhau vẫn có thể khác giá do **region, loại máy, storage class, hướng truyền dữ liệu hoặc tính năng**. Khi phân tích nhiều kỳ:

- Ưu tiên liên kết theo **`sku.id`**, sau đó đối chiếu **service, consumption model, vị trí, đơn vị và thời điểm giá**.
- Dùng `sku.description` để người đọc hiểu ý nghĩa, nhưng không coi mô tả là khóa duy nhất.
- Không suy ra vị trí từ một phần tên SKU nếu trường **geo taxonomy** hoặc tài liệu sản phẩm cung cấp phạm vi chính thức.

## 5. Hiểu chính xác các đơn vị tính phí

### 5.1. Phân biệt dung lượng và dung lượng theo thời gian

| Đơn vị thường gặp | Đọc như thế nào? | Khi nào có thể gặp? |
| --- | --- | --- |
| **B**, **GB**, **GiB** | Dung lượng dữ liệu | Truyền dữ liệu, xử lý dữ liệu, dung lượng |
| **GiB-month / GiBy.mo** | GiB nhân phần thời gian của tháng | Lưu trữ dữ liệu hoặc cấp phát storage |
| **GiB-hour**, **GiB-second** | Dung lượng bộ nhớ nhân thời gian | Một số dịch vụ compute/serverless |
| **vCPU-hour**, **vCPU-second** | Số vCPU nhân thời gian | Tài nguyên tính toán tính theo công suất và thời gian |
| **instance-hour** | Số instance nhân số giờ sử dụng | Một số mô hình tính phí theo phiên bản instance |
| **request / operation / event** | Số lượt yêu cầu hoặc thao tác | API, serverless, message, truy xuất đối tượng |
| **1.000 / 1.000.000 operations** | Giá ứng với một lượng thao tác quy định | Khi cột giá không tính theo một request duy nhất |
| **GB processed / TiB scanned** | Dữ liệu được đọc hoặc xử lý | Một số kiểu truy vấn, phân tích dữ liệu |
| **data transfer (egress)** | Lượng dữ liệu truyền theo hướng và đích được định nghĩa | Lưu lượng từ Cloud ra internet hoặc qua ranh giới mạng cụ thể |

**GB** thường dùng hệ thập phân: **1 GB = 10⁹ byte**. **GiB** dùng hệ nhị phân: **1 GiB = 2³⁰ byte**. Tương tự, 1 TiB = 1.024 GiB. Do đó **100 GB ≠ 100 GiB**. Khi chuyển đơn vị, phải dựa trên ký hiệu thực trong bảng giá và báo cáo, không tự đổi tùy tiện.

**GiB-month** không có nghĩa “mỗi lần ghi 1 GiB phải trả một tháng”. Đây là đại lượng kết hợp **lượng dung lượng** và **thời gian**: ví dụ giữ trung bình 50 GiB trong cả tháng tương đương khoảng 50 GiB-tháng theo quy ước đo của dịch vụ. Quy tắc tính thời gian, lưu trữ tối thiểu và làm tròn cụ thể cần xem tài liệu sản phẩm.

### 5.2. Đơn vị đo usage và đơn vị dùng để định giá có thể khác nhau

Trong Billing export, bạn có thể gặp:

- `usage.amount` và `usage.unit`: lượng và đơn vị dùng để báo cáo usage.
- `usage.amount_in_pricing_units` và `usage.pricing_unit`: lượng được quy đổi sang đơn vị phục vụ tính giá.

Ví dụ, dịch vụ có thể báo thời gian bằng **giây**, trong khi trang giới thiệu diễn giải giá theo **giờ**; hoặc bảng giá ghi giá **mỗi 1 triệu yêu cầu**. Không thể lấy một số lượng “request” nhân trực tiếp với một giá “per million requests” mà không chia đúng hệ số.

### 5.3. Công thức tính thử một bậc giá

Với một SKU chỉ có **một bậc**, không có ưu đãi khác, một phép ước lượng cơ bản là:

```text
Chi phí = Lượng sử dụng (đã quy đổi sang pricing unit)
          ÷ Per unit quantity
          × Đơn giá niêm yết cho Per unit quantity
```

Ví dụ **giả định**: giá là **0,40 USD cho mỗi 1.000.000 request**, workload có **2.400.000 request tính phí** trong kỳ.

```text
2.400.000 / 1.000.000 × 0,40 USD = 0,96 USD
```

Nếu nhầm 0,40 USD là giá cho **một request**, dự toán sẽ sai đến một triệu lần. Dòng `Per unit quantity` vì thế quan trọng không kém con số đơn giá.

### 5.4. Dung lượng trung bình theo thời gian

Ví dụ **giả định**: dữ liệu chiếm **150 GiB trong 20 ngày** của một tháng 30 ngày, và giả sử SKU tính theo **GiB-tháng với cách quy đổi tỉ lệ thuận theo ngày**:

```text
Usage quy đổi = 150 GiB × (20 / 30) = 100 GiB-tháng
Nếu đơn giá giả định = 0,02 USD/GiB-tháng:
Chi phí dự toán = 100 × 0,02 = 2,00 USD
```

Đây là mô hình để hiểu đơn vị. Chi phí thực tế có thể khác do quy tắc tính thời gian của sản phẩm, minimum storage duration, class, tier, phí thao tác hoặc dữ liệu phát sinh trong kỳ.

## 6. Đọc bậc giá (tiered pricing)

Một SKU có thể có **một bậc giá** hoặc **nhiều bậc**. Trong Pricing table, mỗi bậc của SKU được biểu diễn bằng một hàng; cột **Tiered usage start** chỉ **ngưỡng bắt đầu** của bậc đó theo pricing unit.

Giả sử một SKU truyền dữ liệu có bảng giá hoàn toàn **giả định**:

| Bậc | Tiered usage start | Phạm vi sử dụng trong kỳ | Đơn giá giả định |
| --- | ---: | --- | ---: |
| 1 | 0 GiB | 0 đến dưới 100 GiB | 0,00 USD/GiB |
| 2 | 100 GiB | 100 đến dưới 1.000 GiB | 0,08 USD/GiB |
| 3 | 1.000 GiB | Từ 1.000 GiB trở lên | 0,06 USD/GiB |

Với tổng usage **1.350 GiB**, tính riêng từng phần:

```text
Bậc 1: 100 GiB × 0,00 USD =  0,00 USD
Bậc 2: 900 GiB × 0,08 USD = 72,00 USD
Bậc 3: 350 GiB × 0,06 USD = 21,00 USD
                                  ----------
Tổng chi phí giả định            93,00 USD
```

Không lấy toàn bộ **1.350 × 0,06 USD**; việc chia bậc là một phần của phép tính. Cũng không mặc định bậc miễn phí áp dụng cho mọi SKU mạng.

### Bậc giá được cộng dồn ở phạm vi nào?

Tùy SKU, tier có thể tính trên usage **theo project** hoặc **theo billing account**; khoảng cộng dồn cũng có thể là **mỗi ngày** hoặc **mỗi tháng**. Khi tra bảng Pricing, kiểm tra các trường:

- **Aggregation level:** ví dụ `PROJECT` hoặc `ACCOUNT` nếu áp dụng.
- **Aggregation interval:** ví dụ `ONE_DAY` hoặc `ONE_MONTH` nếu áp dụng.
- **Tiered usage start:** mốc bắt đầu của mỗi bậc.

Một bậc được cộng dồn theo billing account **không có nghĩa** usage của các billing account khác nhau trong cùng Organization được gộp chung. Đồng thời, mỗi SKU có bộ bậc riêng: usage của SKU này thông thường không giúp chuyển bậc của SKU khác.

**Ví dụ đọc sai:** Hai project cùng dùng 600 GiB. Nếu bậc áp dụng **theo project**, mỗi project có thể bắt đầu lại từ mốc 0; nếu bậc áp dụng **theo account**, tổng 1.200 GiB có thể vượt ngưỡng kế tiếp. Chi phí không nhất thiết giống nhau, dù tổng dữ liệu bằng nhau.

## 7. Một dịch vụ có thể gồm nhiều dòng chi phí

Khi lập dự toán, hãy chia workload thành các thành phần tiêu thụ thay vì chỉ chọn một con số “giá Compute Engine” hoặc “giá Cloud SQL”.

| Dịch vụ | Những đại lượng cần kiểm tra trên bảng giá hiện hành | Chi phí thường dễ bỏ sót |
| --- | --- | --- |
| **Compute Engine** | Loại VM, vCPU, RAM, thời gian chạy, disk, địa chỉ IP liên quan | Persistent Disk, snapshot, đường truyền, tải cân bằng, license |
| **GKE** | Tài nguyên node/cluster theo chế độ vận hành, pod/compute, disk | Hạ tầng node, mạng, load balancer, monitoring/logging |
| **Cloud Run** | Request, CPU, memory, thời gian instance được tính phí và mô hình billing | Min instances, kết nối ra ngoài, Cloud Logging, dịch vụ phụ thuộc |
| **Cloud SQL** | Instance/compute, storage, backup, tính sẵn sàng cao, mạng | Dự phòng, disk tăng, backup/PITR, truyền dữ liệu |
| **Cloud Storage** | Dung lượng × thời gian, storage class, thao tác, retrieval | Thời gian lưu tối thiểu, egress và thao tác đọc/ghi |
| **VPC / networking** | Hướng truyền dữ liệu, nguồn/đích, vùng, dịch vụ mạng | Internet egress, truyền giữa vùng, NAT, load balancer |
| **BigQuery** | Mô hình xử lý truy vấn/slot, dữ liệu lưu trữ, tính năng | Dung lượng quét, metadata, network, streaming theo cấu hình |

Đây là **bản đồ câu hỏi**, không phải danh sách SKU cố định. Một số thành phần có thể miễn phí trong phạm vi điều kiện, được gộp vào giá sản phẩm hoặc có cách định giá khác tùy phiên bản dịch vụ.

### 7.1. Phân biệt ingress, egress và transfer nội bộ

Nhiều người mới thấy “dữ liệu truyền đi 100 GiB” rồi chọn ngay giá **internet egress**. Cách này thiếu thông tin. Trước khi tìm SKU, cần biết:

1. **Từ đâu đến đâu?** VM → database cùng zone, VM → region khác, Cloud Storage → internet, hay client → dịch vụ?
2. **Theo hướng nào?** Ingress vào nền tảng hay egress rời nền tảng?
3. **Qua sản phẩm nào?** VPC, Cloud NAT, load balancer, CDN và các dịch vụ trung gian có thể có khoản phí riêng.
4. **Vùng nào?** Nguồn và đích có thể làm thay đổi SKU và đơn giá.

Phí truyền dữ liệu, nếu có, cần tính đúng số byte **thuộc phạm vi tính phí**. Truyền dữ liệu miễn phí ở một tình huống không có nghĩa mọi đường truyền giữa các dịch vụ đều miễn phí.

### 7.2. Compute được cấp phát hay compute thật sự được sử dụng?

Một hệ thống có CPU chỉ chạy ở mức 10% **không tự động** trả 10% giá máy ảo. Với cấu hình được tính phí theo thời gian **tài nguyên đã cấp phát**, cần xét loại máy và thời gian tồn tại/chạy theo quy tắc của dịch vụ. Ngược lại, mô hình serverless có thể căn cứ vào request và thời gian compute được tính phí, nhưng cũng cần xem min instances, concurrency và billing settings.

Vì vậy, **utilization** là dữ liệu để tối ưu cấu hình và chi phí về sau; nó không luôn là đầu vào trực tiếp của mọi SKU.

## 8. Bài toán tổng hợp: dự toán một workload nhỏ

Giả sử một ứng dụng chạy hai instance, có ổ đĩa và truyền dữ liệu ra ngoài. Để luyện tính toán, **giả định** tháng gồm 30 ngày, tương đương 720 giờ; các đơn giá và mục cấu thành bên dưới đều được tạo riêng cho bài tập.

| Thành phần tính phí giả định | Lượng sử dụng | Đơn giá giả định | Dự toán |
| --- | ---: | ---: | ---: |
| vCPU | 2 instance × 2 vCPU × 720 giờ = 2.880 vCPU-giờ | 0,025 USD/vCPU-giờ | **72,00 USD** |
| RAM | 2 instance × 8 GiB × 720 giờ = 11.520 GiB-giờ | 0,003 USD/GiB-giờ | **34,56 USD** |
| Ổ đĩa | 2 × 100 GiB × 1 tháng = 200 GiB-tháng | 0,05 USD/GiB-tháng | **10,00 USD** |
| Internet egress | 80 GiB thuộc phạm vi tính phí giả định | 0,12 USD/GiB | **9,60 USD** |
| **Tổng trước ưu đãi và khoản khác** | | | **126,16 USD** |

Kiểm tra phép cộng: **72,00 + 34,56 + 10,00 + 9,60 = 126,16 USD**.

Ở kiến trúc thật, cần xác định Compute Engine sử dụng loại máy và SKU nào (có trường hợp cách tính giá không tách giống bảng ví dụ), thời lượng sử dụng được tính như thế nào, disk class, network route, giảm giá theo cam kết/usage và các dịch vụ đi kèm.

Tổng **126,16 USD không phải dự toán cho một cấu hình Compute Engine hoặc Cloud Run thực tế**. Giá bán, điều kiện ưu đãi và tất cả khoản phí liên quan phải được kiểm tra ở bảng giá hiện hành hoặc Pricing Calculator.

### Từ dự toán đến câu hỏi kiến trúc

Nếu ứng dụng chỉ đông khách trong hai giờ mỗi ngày, cần đo usage trước khi quyết định:

- Chạy VM thường trực hay chuyển một phần sang Cloud Run?
- Chọn Cloud SQL cấu hình cao, tự mở rộng ở tầng ứng dụng hay tối ưu truy vấn trước?
- Đặt workload ở một region hay đa region để đạt RTO/RPO đã xác định?
- Lưu dữ liệu lâu ở lớp Storage nào, có phí truy xuất hoặc lưu tối thiểu không?

**Tối ưu chi phí phải đi cùng bảo mật, độ tin cậy và hiệu năng.** Một cấu hình rẻ hơn nhưng thường xuyên mất kết nối, không đạt SLO hoặc vi phạm yêu cầu lưu giữ dữ liệu chưa phải kiến trúc tối ưu.

## 9. Vì sao giá niêm yết khác số tiền thực trả?

Chi phí ghi nhận trong Cloud Billing có thể chịu ảnh hưởng của **thời gian sử dụng, vùng, bậc giá, consumption model, giá hợp đồng, credits, thuế và điều chỉnh**.

| Khái niệm | Cách hiểu đúng |
| --- | --- |
| **List price** | Giá niêm yết cho SKU và bậc giá tại thời điểm tra cứu |
| **Contract price** | Giá riêng theo hợp đồng, nếu billing account có và người xem được cấp quyền |
| **Consumption model** | Ngữ cảnh giá áp dụng cho usage, ví dụ mô hình mặc định hoặc một mô hình liên quan cam kết |
| **Sustained use discounts / committed use discounts** | Chương trình giảm giá theo điều kiện sản phẩm và hình thức cam kết; cách thể hiện có thể khác nhau giữa loại giảm giá và thời điểm |
| **Free Tier / free usage tier** | Miễn phí trong một giới hạn hoặc điều kiện; không đồng nghĩa mọi dự án đều có một hạn mức độc lập |
| **Promotional credits** | Khoản credits có thể giảm số tiền phải thanh toán, theo điều kiện sử dụng |
| **Taxes / adjustments / support** | Các khoản ngoài usage chính có thể xuất hiện trong tổng thanh toán |

Đặc biệt, từ các thay đổi gần đây của **spend-based committed use discounts**, một số mức giá cam kết được thể hiện qua **consumption model** thay vì chỉ như dòng credit. Khi so sánh cùng SKU qua nhiều kỳ, cần đối chiếu cả **consumption model ID** và tài liệu chương trình đang áp dụng; không được giả định mọi chiết khấu đều xuất hiện ở một cột `credits`.

Trong một phép tính đơn giản, ta có thể diễn đạt:

```text
Chi phí sử dụng theo các SKU, tier và mô hình giá áp dụng
  ± những điều chỉnh/giảm giá được hạch toán theo cơ chế của chương trình
  - credits hợp lệ
  + thuế/phụ phí/hỗ trợ nếu phát sinh
  = số tiền cần đối chiếu với báo cáo/hóa đơn
```

Đây là **sơ đồ kế toán khái niệm**, không phải công thức chuẩn áp dụng cho mọi trường dữ liệu và mọi loại contract. Một số ưu đãi đã được thể hiện ngay trong **đơn giá hiệu lực**, nên nếu tiếp tục trừ cùng khoản giảm giá lần nữa sẽ bị **đếm hai lần**.

### Chênh lệch theo tháng sử dụng và tháng hóa đơn

**Usage month** là thời điểm tài nguyên được sử dụng; **invoice month** là kỳ ghi nhận trên invoice/statement. Hai kỳ có thể lệch do độ trễ báo cáo, điều chỉnh và cơ chế chốt hóa đơn. Vì vậy không nên kỳ vọng mọi truy vấn nhóm theo `usage_start_time` phải khớp hoàn toàn với một hóa đơn chọn theo `Invoice month`.

Để giải thích số tiền trên hóa đơn, hãy dùng **Cost table** theo invoice month và bộ lọc mặc định trước khi đi sâu vào từng SKU. Bảng này cung cấp các khoản usage, credits, thuế, điều chỉnh và các dòng có thể đối soát với tổng hóa đơn.

## 10. Phân tích chi phí bằng báo cáo và BigQuery

### 10.1. Tìm một SKU đang tạo chi phí

Khi quan sát một khoản phí bất thường:

1. Vào **Cloud Billing → Reports** để xác định **billing account**, project và khoảng thời gian phát sinh chi phí.
2. Nhóm hoặc lọc tiếp theo **Service** và **SKU**.
3. Nếu mục tiêu là đối soát hóa đơn, mở **Cost table**, chọn **Invoice month** và xem dòng theo **Project → Service → SKU → Consumption model**.
4. Ghi nhận **SKU ID**, mô tả, usage, pricing unit, cost, credits, consumption model và vị trí.
5. Mở **Pricing table** để tra đơn giá áp dụng khi xem, rồi xác minh với thông tin lịch sử hoặc dữ liệu xuất giá nếu cần tính cho kỳ cũ.
6. Kiểm tra việc tăng usage đến từ **tăng thời gian chạy, dung lượng, số request, egress** hay chuyển qua bậc giá; xác minh có thay đổi cấu hình, workload hoặc mức ưu đãi.

**Không lấy** đơn giản tổng tiền chia số request của cả project để kết luận “SKU request tăng giá”: trong tổng tiền có thể có database, logging, network, credits và nhiều SKU khác.

### 10.2. Các kiểu export và khi nên dùng

Nếu cần phân tích lặp lại bằng SQL, có thể bật **Cloud Billing export to BigQuery** từ tài khoản thanh toán với quyền và cấu hình phù hợp:

| Loại export | Thông tin điển hình | Mục đích |
| --- | --- | --- |
| **Standard usage cost data** | Billing account, project, service/SKU, usage, cost, credits, currency | Báo cáo chi phí theo dịch vụ và kỳ |
| **Detailed usage cost data** | Trường standard và một phần thông tin cấp tài nguyên | Truy nguyên tài nguyên cụ thể gây chi phí khi được hỗ trợ |
| **Pricing data** | SKU, mô hình giá, bậc giá, đơn vị, tiền tệ, metadata địa lý và thời điểm giá | Đối chiếu đơn giá theo billing account |

Detailed export tự động có thông tin cấp tài nguyên cho một số trường hợp như Compute Engine; với **GKE cost allocation**, cần bật tính năng liên quan để thấy phân bổ chi phí cluster đầy đủ hơn. Bật export **không có nghĩa mọi lịch sử quá khứ sẽ được tự động tải lại**; hãy xem chính sách backfill, độ trễ và cách đặt dataset của từng loại export.

### 10.3. Ví dụ SQL nhóm theo SKU

Ví dụ đọc dữ liệu **standard usage cost export**. Thay tên bảng đúng theo dữ liệu được tạo trong project của bạn. Truy vấn minh họa dùng khoảng **01–30/11/2026** theo `usage_start_time`, chỉ xét dòng usage thông thường; truy vấn này **không nhằm đối chiếu tổng hóa đơn**:

```sql
SELECT
  project.id AS project_id,
  service.description AS service_name,
  sku.id AS sku_id,
  sku.description AS sku_name,
  usage.pricing_unit AS pricing_unit,
  SUM(usage.amount_in_pricing_units) AS usage_in_pricing_units,
  SUM(cost) AS cost_before_credits,
  SUM(
    IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0
    )
  ) AS credits_total,
  SUM(
    cost + IFNULL(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c),
      0
    )
  ) AS cost_plus_credits
FROM `BILLING_PROJECT.DATASET.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX`
WHERE usage_start_time >= TIMESTAMP('2026-11-01')
  AND usage_start_time < TIMESTAMP('2026-12-01')
  AND cost_type = 'regular'
GROUP BY project_id, service_name, sku_id, sku_name, pricing_unit
ORDER BY cost_plus_credits DESC;
```

Trong export này, `credits.amount` thường mang dấu âm khi là khoản ghi giảm. Trường `cost_plus_credits` là một cách nhìn **net usage theo các dòng được lọc**, chưa bao gồm thuế, một số khoản hóa đơn và các cơ chế giá ngoài phạm vi truy vấn. Kết quả nhóm nhiều thời điểm cũng không phải bằng chứng rằng **một SKU chỉ có một giá duy nhất**, vì có thể khác tier, consumption model hoặc thời điểm.

Để xem giá **theo billing account** bằng BigQuery, dùng **pricing data export** với bảng có tên theo loại `cloud_pricing_export`; tra các trường `sku.id`, `pricing_as_of_time`, unit, tier, consumption model và currency theo schema hiện hành. Không giả định chỉ nối theo `sku.id` là đủ để xác định một giá cho mọi thời điểm.

**Lưu ý vận hành:** truy vấn BigQuery có thể phát sinh chi phí phân tích dữ liệu. Nên kiểm tra dung lượng dữ liệu quét và quyền trước khi chạy trên tập dữ liệu thực.

## 11. Các nhầm lẫn phổ biến

| Nhận định sai | Cách hiểu và hành động đúng |
| --- | --- |
| “Giá một VM là toàn bộ chi phí hệ thống.” | Đọc thêm các SKU storage, network, load balancer, backup, logging và dịch vụ phụ thuộc. |
| “Giá niêm yết hiện tại chính là giá đã trả tháng trước.” | Tra theo thời điểm và điều kiện giá lịch sử; dùng Cost table và export khi đối soát. |
| “0,40 USD cho 1 triệu request nghĩa là 0,40 USD/request.” | Đọc `Per unit quantity` và chuyển usage sang đơn vị tính giá. |
| “100 GB = 100 GiB.” | Đối chiếu đơn vị thập phân và nhị phân trước khi nhân giá. |
| “GiB-tháng là số GiB đã upload trong tháng.” | GiB-tháng gắn với mức dung lượng được lưu và thời gian lưu. |
| “Cùng tên dịch vụ thì giá giống nhau ở mọi region.” | Kiểm tra SKU/geo taxonomy và bảng giá riêng của sản phẩm. |
| “Mọi usage vượt một ngưỡng đều có cùng đơn giá mới.” | Kiểm tra từng bậc tính phí và phạm vi cộng dồn của tier. |
| “Có Free Tier thì chắc chắn hóa đơn bằng 0.” | Xem điều kiện Free Tier, usage ngoài phạm vi, phí mạng và dịch vụ khác. |
| “Có budget sẽ tự động ngắt dịch vụ khi chạm ngưỡng.” | Cloud Billing budget thường dùng để **theo dõi và gửi cảnh báo**, không phải trần chi tiêu cứng tự động cho toàn bộ workload. |
| “Cost Table, Pricing Table và Reports hiển thị cùng một loại tiền.” | Pricing Table cho **đơn giá SKU**; Reports cho **xu hướng chi phí**; Cost Table dùng để **đối chiếu hóa đơn**. |
| “Gán label rồi toàn bộ chi phí sẽ thuộc đúng label đó.” | Không phải mọi khoản phí hoặc tài nguyên đều hỗ trợ nhãn/phân bổ chi phí theo cùng cách; cần kiểm tra phần không gắn nhãn. |

## 12. Bài tập thực hành và câu hỏi kiểm tra

### Bài 1: Đọc bảng giá, không tạo tài nguyên

Trong Google Cloud Console hoặc tài liệu giá chính thức:

1. Chọn một **service** bất kỳ trong phạm vi đang học, ví dụ Cloud Storage hoặc Compute Engine.
2. Tìm **một SKU** và ghi lại: SKU ID, SKU description, region/geo taxonomy, unit, per unit quantity và list price.
3. Kiểm tra SKU có bao nhiêu pricing tier và có consumption model nào.
4. Ghi lại **ngày tra cứu**, **đồng tiền** và bạn đang xem **giá công khai** hay **giá billing account**.
5. Giải thích bằng một câu: “SKU này tính tiền cho đại lượng nào và theo đơn vị gì?”.

### Bài 2: Tính tiền từ một dòng giá giả định

Một dịch vụ giả định tính **0,25 USD cho mỗi 10.000 thao tác**. Workload có **380.000 thao tác tính phí** trong kỳ, không có miễn phí, bậc giá hoặc giảm giá. Kết quả:

```text
380.000 / 10.000 × 0,25 USD = 9,50 USD
```

Hãy thử thay usage bằng **1.200.000 thao tác**, sau đó kiểm tra kết quả (**30,00 USD**) và giải thích vì sao phải chia cho `Per unit quantity = 10.000`.

### Bài 3: Tính bậc giá theo phạm vi

Một SKU giả định có hai bậc: 0–500 GiB giá **0,10 USD/GiB**, phần trên 500 GiB giá **0,07 USD/GiB**. Tổng usage 800 GiB. Kết quả:

```text
500 × 0,10 + 300 × 0,07 = 50 + 21 = 71,00 USD
```

Giả sử bậc tính **theo project**, hãy tự tính lại khi usage nằm ở **hai project, mỗi project 400 GiB**. Tổng tiền giả định lúc này là **80,00 USD**, nếu mỗi project được tính lại từ bậc đầu. Đổi giả định sang phạm vi cộng dồn **theo billing account** và giải thích vì sao kết quả có thể trở về **71,00 USD**.

### Bài 4: Giải thích chênh lệch chi phí thực tế

Giả sử dự toán 120 USD, Reports cho thấy 150 USD, nhưng hóa đơn tháng được chọn là 142 USD. Hãy viết một danh sách các kiểm tra theo thứ tự:

1. Cùng billing account, kỳ usage và invoice month chưa?
2. SKU nào có usage tăng, xuất hiện thêm hoặc chuyển bậc?
3. Có thay đổi region, máy ảo, storage class hoặc egress không?
4. Có consumption model, hợp đồng, credits hay điều chỉnh nào không?
5. Có thuế, phí hỗ trợ hoặc độ trễ ghi nhận khác biệt không?

Không kết luận một lỗi tính giá chỉ từ ba con số. Cần đối chiếu **dữ liệu theo SKU và kỳ kế toán**.

## 13. Checklist đọc giá trước khi triển khai

- [ ] Xác định project và Cloud Billing account đúng.
- [ ] Mô tả workload, vùng triển khai và những thành phần có thể phát sinh phí.
- [ ] Tra **service + SKU** chính xác, gồm SKU ID và geo taxonomy.
- [ ] Ghi lại **pricing unit**, **per unit quantity**, tier và phạm vi/chu kỳ cộng dồn.
- [ ] Chọn đúng **consumption model**, loại giá và đồng tiền; ghi ngày đối chiếu.
- [ ] Ước lượng usage từ lưu lượng, thời gian chạy, dung lượng, request và dữ liệu truyền.
- [ ] Tính đủ thành phần liên quan: compute, database, storage, network, logging và backup.
- [ ] Tách **giá niêm yết**, **giá hợp đồng**, **discount** và **credits**, tránh đếm hai lần.
- [ ] So sánh bằng Pricing Calculator và dự phòng cho tăng trưởng/lỗi cấu hình.
- [ ] Thiết lập Billing reports, ngân sách và cảnh báo; kiểm tra chi phí thực tế sau triển khai.

## 14. Tài liệu Google Cloud chính thức

Đơn giá, chương trình giảm giá và cột thông tin có thể thay đổi. Ưu tiên tài liệu chính thức khi cần dữ liệu hiện hành:

1. [View and download prices for Google Cloud services – Pricing table](https://cloud.google.com/billing/docs/how-to/pricing-table)
2. [Get publicly available Google Cloud pricing information – Cloud Billing Catalog API](https://cloud.google.com/billing/v1/how-tos/catalog-api)
3. [Get started with the Cloud Billing API](https://cloud.google.com/billing/v1/getting-started)
4. [Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
5. [View and download cost details – Cost table](https://cloud.google.com/billing/docs/how-to/cost-table)
6. [Set up Cloud Billing export to BigQuery](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)
7. [Structure of Standard usage cost export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage)
8. [Structure of pricing data export](https://cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data)

**Ghi nhớ khi đọc bảng giá:** luôn trả lời đủ năm câu hỏi: **đang mua loại usage nào (SKU), tại đâu (location), bao nhiêu (usage), tính theo đơn vị/bậc nào (pricing unit và tier), và dưới điều kiện giá nào (consumption model, hợp đồng, credits)?** Khi trả lời rõ năm câu hỏi này, bạn có cơ sở để dự toán, tìm lỗi chi phí và cải tiến kiến trúc trên Google Cloud.
