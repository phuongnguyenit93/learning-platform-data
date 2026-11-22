# Phân cấp phân tích và chiều dùng chung giữa nhiều bảng dữ kiện

## Mục tiêu học tập

Trong mô hình dữ liệu phân tích, **bảng dữ kiện (fact table)** trả lời “điều gì xảy ra và đo được bao nhiêu?”, còn **bảng chiều (dimension table)** trả lời “sự kiện đó diễn ra vào lúc nào, liên quan đến ai, sản phẩm nào, ở đâu và thuộc nhóm nào?”. Một dimension không chỉ lưu tên để hiển thị. Nó còn xác định **các cấp phân tích** giúp người dùng đi từ dữ liệu chi tiết lên mức tổng hợp hoặc ngược lại.

Chẳng hạn, từ doanh thu của từng **sản phẩm**, ta có thể cộng lên **nhóm sản phẩm**, **ngành hàng**, rồi toàn công ty. Nếu cả dữ liệu bán hàng và hoàn trả đều dùng cùng một khái niệm ngành hàng, hai fact có thể được so sánh trên cùng trục phân tích. Nhưng nếu hai hệ thống định nghĩa ngành hàng khác nhau hoặc JOIN hai fact ở mức chi tiết không tương thích, báo cáo có thể nhân bản số tiền dù tất cả khóa ngoại đều hợp lệ.

Bài thuộc chương **Bảng chiều**, module **DATABASE_DATA_MODELING**. Mục tiêu chung của module là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng từ thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục đến lược đồ vật lý; đồng thời so sánh mô hình quan hệ, document, đồ thị và phân tích nhằm chọn cấu trúc dễ tiến hóa và kiểm chứng. Bài này tập trung vào **ngữ nghĩa phân cấp trong dimension** và **tính nhất quán của chiều dùng chung giữa nhiều bảng fact**, không phải hướng dẫn xây toàn bộ luồng ETL/ELT.

Sau bài học, bạn có thể:

1. Mô tả phân cấp (**hierarchy**) của dimension và các thao tác **roll-up, drill-down, slice, dice** trên dữ liệu phân tích.
2. Phân biệt phân cấp **chặt/chồng lấn**, **đầy đủ/thiếu cấp**, **cân bằng/lệch cấp**, phân cấp thay thế và thay đổi theo thời gian.
3. Giải thích điều kiện để một phép tổng hợp **đúng và không đếm trùng** (*summarizability*), bao gồm tính đơn trị của đường phân cấp, tính đầy đủ và khả năng cộng của measure.
4. So sánh cách lưu phân cấp bằng **dimension phẳng**, **snowflake**, **quan hệ cha–con** hoặc **bảng cầu (bridge)**.
5. Định nghĩa một **conformed dimension** thật sự: thống nhất định danh, thuộc tính, miền giá trị, phân cấp, thời gian hiệu lực và phạm vi nghiệp vụ.
6. Thiết kế **bus matrix** cho các quy trình bán hàng, hoàn trả và tồn kho; phân biệt **dimension dùng chung** với **role-playing dimension**.
7. Truy vấn **drill-across** nhiều fact an toàn bằng cách tổng hợp **riêng từng fact về grain chung trước khi JOIN**.
8. Kiểm chứng bằng SQL PostgreSQL, nhận diện các bẫy về **fanout, SCD, nhiều–nhiều, dòng thiếu dimension, đơn vị đo và snapshot**.

> **Nguyên tắc xuyên suốt:** Hai fact dùng cùng tên cột không có nghĩa chúng dùng cùng định nghĩa chiều. Một phân cấp trông giống cây không có nghĩa SUM luôn đúng; phải kiểm tra cách gán thành viên vào từng cấp và tính chất của measure.

## 1. Phân cấp trong bảng chiều là gì?

### 1.1. Từ thành viên chi tiết đến cấp tổng hợp

Giả sử doanh nghiệp bán:

~~~~text
Ngành hàng: Văn phòng phẩm
  Nhóm: Giấy
    Sản phẩm: Sổ tay
    Sản phẩm: Giấy in
  Nhóm: Bút
    Sản phẩm: Bút bi
    Sản phẩm: Bút chì

Ngành hàng: Gia dụng
  Nhóm: Đồ uống
    Sản phẩm: Ly thủy tinh
~~~~

Đây là một phân cấp sản phẩm gồm ba cấp:

\[
\text{Sản phẩm}\longrightarrow\text{Nhóm}\longrightarrow\text{Ngành hàng}
\]

Mỗi mũi tên được hiểu là “thành viên ở cấp chi tiết thuộc một thành viên ở cấp cao hơn” theo **quy tắc phân loại đang áp dụng**. Nếu mỗi sản phẩm nằm trong đúng một nhóm và mỗi nhóm nằm trong đúng một ngành hàng, phân cấp này có đường đi **đơn trị**.

Với một dòng fact bán sản phẩm **Sổ tay**, người đọc có thể phân tích doanh thu:

- Ở cấp **sản phẩm**: riêng Sổ tay.
- Ở cấp **nhóm**: tổng các sản phẩm thuộc nhóm Giấy.
- Ở cấp **ngành hàng**: tổng các nhóm thuộc ngành hàng Văn phòng phẩm.
- Ở cấp **toàn hệ thống**: tổng các ngành hàng hợp lệ của tập dữ liệu.

### 1.2. Roll-up và drill-down

**Roll-up** là chuyển từ cấp chi tiết lên cấp tổng hợp, ví dụ:

\[
\text{Doanh thu theo sản phẩm}
\ \Rightarrow\
\text{Doanh thu theo nhóm}
\ \Rightarrow\
\text{Doanh thu theo ngành hàng}
\]

**Drill-down** làm điều ngược lại: từ ngành hàng xuống nhóm rồi đến sản phẩm để tìm nguồn gốc của một biến động.

**Slice** giữ một giá trị chiều, ví dụ chỉ ngành hàng “Văn phòng phẩm”. **Dice** lọc một tập giá trị của nhiều chiều, ví dụ “Văn phòng phẩm” trong quý IV và tại các cửa hàng miền Nam. **Drill-through** thường đi từ một ô tổng hợp về các dòng sự kiện hoặc bản ghi chi tiết nền tảng, nếu hệ thống có hỗ trợ đường dẫn dữ liệu.

Các thao tác này chỉ có nghĩa đúng khi **grain của fact**, **phân cấp của dimension** và **phép tổng hợp measure** đã rõ.

### 1.3. Phân cấp không chỉ có ở sản phẩm

| Dimension | Ví dụ phân cấp | Điểm cần xác định |
| --- | --- | --- |
| **Thời gian** | Ngày → Tháng → Quý → Năm | Lịch dương hay lịch tài chính, múi giờ, tuần thuộc năm nào |
| **Địa lý** | Điểm bán → Thành phố → Tỉnh/vùng → Quốc gia | Ranh giới vùng và thời gian hiệu lực |
| **Tổ chức** | Nhân viên → Nhóm → Phòng → Khối | Nhân viên có kiêm nhiệm không, có nhóm bỏ cấp không |
| **Sản phẩm** | SKU → Nhóm → Ngành hàng | Một SKU có nhiều ngành hàng cùng lúc không |
| **Khách hàng** | Khách → Phân khúc → Nhóm phân khúc | Phân khúc tại thời điểm giao dịch hay hiện tại |
| **Phân phối** | Cửa hàng → Khu vực → Miền | Cửa hàng chuyển khu vực khi nào |

Một dimension có thể có **nhiều phân cấp**. Ví dụ thời gian đồng thời có phân cấp **ngày → tháng dương lịch → năm dương lịch** và **ngày → kỳ tài chính → năm tài chính**. Chúng là hai đường roll-up khác nhau; không nên gộp “tháng” của hai lịch thành một chỉ vì tên cấp giống nhau.

### 1.4. Sơ đồ tổng quát

~~~~mermaid
flowchart BT
    P1["Sổ tay (P01)"] --> G1["Nhóm Giấy"]
    P2["Giấy in (P02)"] --> G1
    P3["Bút bi (P03)"] --> G2["Nhóm Bút"]
    G1 --> C1["Văn phòng phẩm"]
    G2 --> C1
    P4["Ly thủy tinh (P04)"] --> G3["Nhóm Đồ uống"]
    G3 --> C2["Gia dụng"]
~~~~

Sơ đồ trên giả định **mỗi thành viên cấp dưới có đúng một đường lên cấp trên tại thời điểm phân tích**. Đây là một giả định cần kiểm tra, không phải thuộc tính mặc định của mọi dimension.

## 2. Các tính chất phân cấp ảnh hưởng đến kết quả phân tích

### 2.1. Phân cấp chặt (strict) và không chặt (non-strict)

**Phân cấp chặt**: mỗi thành viên ở cấp dưới được gán vào **tối đa một** thành viên ở cấp trên kề nó trong cùng phân cấp và tại cùng thời điểm/ngữ cảnh.

Ví dụ sản phẩm P01 thuộc **duy nhất nhóm Giấy**; nhóm Giấy thuộc **duy nhất ngành hàng Văn phòng phẩm**. Một dòng doanh thu của P01 có một đường duy nhất khi roll-up lên ngành hàng.

**Phân cấp không chặt**: một thành viên cấp dưới **có thể thuộc nhiều thành viên cấp trên**. Ví dụ một sản phẩm được đưa vào hai bộ sưu tập marketing cùng lúc, hoặc một nhân viên có hai quản lý trong cơ cấu ma trận.

Giả sử P01 có doanh thu 100.000 VND, đồng thời thuộc hai bộ sưu tập “Tựu trường” và “Quà tặng”. Nếu JOIN quan hệ thành viên và SUM:

| Bộ sưu tập | Doanh thu P01 |
| --- | ---: |
| Tựu trường | 100.000 |
| Quà tặng | 100.000 |

Tổng của hai dòng là 200.000 VND dù doanh thu nguồn chỉ 100.000 VND. Có hai cách hiểu hợp lệ nhưng **khác nhau**:

- **Báo cáo gắn nhãn không phân bổ**: mỗi bộ sưu tập được xem toàn bộ doanh thu của sản phẩm; không cộng các bộ sưu tập với nhau để ra tổng công ty.
- **Báo cáo phân bổ**: dùng tỷ trọng, ví dụ 70% cho Tựu trường và 30% cho Quà tặng, để tổng phân bổ bằng 100% giá trị nguồn.

Không thể chữa bẫy này bằng SELECT DISTINCT đơn giản: hai nhóm có ý nghĩa khác nhau, còn cách phân bổ là **quyết định nghiệp vụ**.

### 2.2. Đầy đủ (complete) và không đầy đủ (incomplete)

Một phân cấp **đầy đủ** tại cấp đang phân tích khi mọi thành viên chi tiết cần đưa vào báo cáo đều có đường gán lên một thành viên cấp tổng hợp thích hợp.

Nếu sản phẩm P99 chưa có nhóm, phép INNER JOIN từ fact qua bảng nhóm có thể làm **biến mất** doanh thu P99 khỏi báo cáo. Phân cấp không đầy đủ khiến tổng theo ngành hàng có nguy cơ **nhỏ hơn tổng fact**.

Các chính sách có thể chọn:

1. **Không công bố các dòng chưa phân loại**, kèm quy tắc chờ sửa.
2. Đưa chúng vào thành viên **Chưa phân loại/Unknown** được định nghĩa rõ; doanh thu vẫn xuất hiện khi tổng hợp.
3. Bổ sung dữ liệu phân cấp từ nguồn đáng tin trước khi phân tích.

Việc chọn chính sách phải dựa vào nhu cầu **đủ tổng doanh thu** hay **chỉ báo cáo dữ liệu đã được phân loại**, và phải ghi rõ trong hợp đồng dữ liệu.

### 2.3. Cân bằng, không cân bằng và bỏ cấp (ragged)

Trong phân cấp **cân bằng**, các đường đi đến cấp tổng hợp có độ dài tương đương. Trong phân cấp **không cân bằng**, một số nhánh dài/ngắn khác nhau; phân cấp **ragged** có thể bỏ qua những cấp không áp dụng.

Ví dụ tổ chức:

~~~~text
Công ty
  Khối kinh doanh
    Phòng kinh doanh
      Nhóm bán lẻ
  Khối vận hành
    Phòng vận hành
  Văn phòng giám đốc
    (trực thuộc công ty, không có khối và phòng)
~~~~

Nếu bắt mọi đơn vị đều có Khối và Phòng, người thiết kế có thể phải:

- Dùng thành viên **“Không áp dụng”** có nghĩa rõ ràng.
- Dùng bảng quan hệ cha–con, hiển thị phân cấp linh hoạt thay vì ép vào số cột cố định.
- Xác định cách roll-up sao cho một đơn vị không bị rơi khỏi báo cáo hoặc đếm lặp.

Các giá trị **NULL**, **Unknown** và **Not applicable** khác nhau. NULL có thể mang nghĩa dữ liệu chưa biết; “không áp dụng” là trạng thái hợp lệ của một nhánh bỏ cấp. Không nên tùy ý gộp cả hai thành một nhóm mà không có quyết định.

### 2.4. Phân cấp thay thế và phân cấp song song

Một sản phẩm có thể được phân nhóm theo:

- **Danh mục vận hành:** SKU → Nhóm sản phẩm → Ngành hàng.
- **Chiến dịch marketing:** SKU → Bộ sưu tập → Chương trình.
- **Quy định quản lý:** SKU → Nhóm thuế → Loại thuế.

Đây có thể là **những phân cấp có mục đích khác nhau**. Phân cấp marketing thường nhiều–nhiều, trong khi danh mục vận hành có thể là một–nhiều chặt chẽ. Nếu sao chép mọi thuộc tính vào một cột category duy nhất, ta sẽ làm mất các ngữ nghĩa khác nhau.

### 2.5. Phân cấp thay đổi theo thời gian

Giả sử sản phẩm P01 chuyển từ ngành hàng **Văn phòng phẩm** sang **Quà tặng** từ ngày 01/11. Một báo cáo tháng 10 và tháng 11 có thể cần:

- **Phân loại hiện tại:** tính lại mọi lịch sử theo ngành hàng đang có hôm nay.
- **Phân loại lịch sử:** giao dịch tháng 10 được gắn ngành hàng cũ, tháng 11 ngành hàng mới.

Hai định nghĩa đều có thể hợp lệ cho những câu hỏi khác nhau. Chúng đòi hỏi chính sách dimension phù hợp, chẳng hạn **SCD Type 1** cho giá trị hiện hành hoặc **SCD Type 2** cho các phiên bản lịch sử. Chỉ thêm cột changed_at nhưng không lưu hoặc gắn phiên bản đúng **chưa đủ** để trả lời chính xác cả hai góc nhìn.

## 3. Điều kiện để roll-up cộng đúng: summarizability

**Summarizability** là khả năng tổng hợp measure từ một mức chi tiết lên mức cao hơn **mà không làm sai tổng, bỏ sót hoặc nhân bản đóng góp của các sự kiện gốc**. Nó không chỉ là chuyện dùng SUM đúng cú pháp.

### 3.1. Một sự kiện có bao nhiêu đường phân cấp?

Cho \(F\) là tập dòng fact có measure cộng được \(m(f)\), và \(H\) là tập thành viên ở cấp tổng hợp. Nếu mỗi fact thuộc **đúng một** thành viên \(h\in H\), ta có:

\[
M(h)=\sum_{\substack{f\in F\\group(f)=h}}m(f)
\]

Khi các nhóm tạo thành **một phân hoạch đầy đủ, không chồng lấn** của F:

\[
\sum_{h\in H}M(h)=\sum_{f\in F}m(f).
\]

Đẳng thức này dựa trên các giả định:

1. Mỗi dòng fact có **chính xác một nhóm** khi phân loại ở mức H, nếu báo cáo phải bao phủ toàn bộ F.
2. Không có dòng fact bị nhân bản bởi các JOIN hoặc quan hệ nhiều–nhiều không kiểm soát.
3. Measure được phép **cộng qua chiều đang xét**.
4. Dữ liệu và quy tắc phiên bản phân cấp được chọn nhất quán tại thời điểm phân tích.

Nếu một dòng fact thuộc hai nhóm thì nó có thể được cộng **hai lần**. Nếu không thuộc nhóm nào, nó có thể bị **bỏ qua**. Nếu measure là số dư cuối ngày, cộng qua nhiều ngày vẫn sai ý nghĩa dù các nhóm ngày không trùng nhau.

### 3.2. Ba yêu cầu của một đường roll-up an toàn

| Yêu cầu | Ý nghĩa | Hậu quả nếu không đạt |
| --- | --- | --- |
| **Đơn trị / disjoint membership** | Mỗi thành viên cấp dưới góp vào tối đa một nhóm cấp trên ở cùng phân cấp, thời điểm | Đếm trùng khi một thành viên xuất hiện nhiều nhóm |
| **Đầy đủ / complete coverage** | Mọi dòng cần báo cáo đều có nhóm ở cấp tổng hợp | Mất dòng, tổng nhóm nhỏ hơn tổng nguồn |
| **Tương thích measure** | Phép tổng hợp phù hợp với loại measure và đơn vị | Tổng số không có nghĩa, ví dụ cộng tồn kho qua ngày |

Một thiết kế phân cấp **strict nhưng incomplete** vẫn có thể mất doanh thu do nhóm chưa được gán. Một thiết kế **complete nhưng non-strict** vẫn có thể nhân doanh thu. Cần phân tích **cả ba điều kiện**, không chỉ kiểm tra UNIQUE trong bảng dimension.

### 3.3. Additive, semi-additive và non-additive

| Measure | Có thể SUM theo sản phẩm? | Có thể SUM qua nhiều ngày? | Ghi chú |
| --- | --- | --- | --- |
| **Doanh thu theo dòng bán** | Thường có, nếu cùng đơn vị tiền | Có, theo thời điểm ghi nhận nhất quán | Additive đối với các chiều phù hợp |
| **Số lượng bán** | Có điều kiện, nếu đơn vị đo tương thích | Thường có | Không cộng kg với chiếc nếu chưa quy đổi |
| **Tồn kho cuối ngày** | Có thể cộng theo sản phẩm/kho phù hợp | **Không** cộng như doanh thu | Semi-additive theo thời gian |
| **Giá bán trung bình** | **Không** SUM | **Không** SUM | Tính lại từ tổng tiền và tổng số lượng tương thích |
| **Tỷ lệ hoàn trả** | **Không** SUM | **Không** SUM | Tính từ tử số/mẫu số sau tổng hợp |
| **Số khách khác nhau** | Không cộng từ các nhóm chồng lấn | Không cộng số DISTINCT ngày thành số khách tháng | Non-additive; cần khử trùng theo phạm vi |

Ví dụ khách C01 mua sản phẩm trong hai nhóm A và B. Số khách DISTINCT của A = 1, của B = 1 nhưng toàn công ty vẫn chỉ có **một khách**. Ngay cả khi phân cấp sản phẩm là strict, **số khách khác nhau không additive theo nhóm sản phẩm**, bởi cùng một khách có thể xuất hiện ở nhiều nhóm qua nhiều dòng fact.

### 3.4. Phân cấp thời gian cũng có bẫy

Một ngày thuộc đúng một tháng theo **lịch dương**, nhưng một **tuần ISO** có thể nằm ở hai tháng dương lịch. Vì thế:

- **Ngày → Tháng → Năm** theo lịch dương có thể là đường phân cấp chặt.
- **Ngày → Tuần ISO → Tháng dương lịch** không tự tạo cây chặt: một tuần có thể đi qua ranh giới tháng.
- **Ngày → Tuần ISO → Năm ISO** có quy tắc riêng; tuần đầu/năm cuối có thể khác năm dương lịch.

Nếu báo cáo phải đi từ tuần lên tháng, cần định nghĩa cách gán tuần sang tháng: theo ngày bắt đầu, ngày kết thúc, đa số ngày, hoặc phân bổ theo từng ngày. Chọn cách nào là **quy tắc nghiệp vụ**, không phải thuộc tính tự nhiên của SQL DATE_TRUNC.

### 3.5. Tính đúng của phân cấp phụ thuộc phạm vi

Mã nhóm **VPP** có thể duy nhất trong một tenant, không duy nhất trên toàn hệ thống. Phân cấp strict trong mỗi tenant có thể trở thành non-strict hoặc mơ hồ nếu JOIN chỉ theo category_code mà bỏ tenant_id.

Tương tự, danh mục sản phẩm của mỗi thị trường có thể khác nhau. Phải ghi rõ các khóa, phiên bản và phạm vi:

~~~~text
tenant_id + product_id + effective_time
    → phiên bản phân loại thích hợp
    → nhóm thuộc tenant và thời điểm đó
    → ngành hàng thuộc tenant và thời điểm đó
~~~~

Không nên coi nhãn hiển thị “Văn phòng phẩm” là một khóa có thể dùng xuyên hệ thống; nhãn có thể đổi hoặc trùng. Các khóa ổn định và quy tắc mapping mới là cơ sở cho JOIN.

## 4. Các cách lưu phân cấp trong mô hình quan hệ

Phân cấp khái niệm **không buộc phải có một dạng bảng duy nhất**. Có thể dùng dimension phẳng, snowflake, bảng cha–con hoặc bridge tùy yêu cầu phân tích.

### 4.1. Dimension phẳng (denormalized / flattened)

Một dimension sản phẩm phẳng có thể lưu:

~~~~text
DIM_PRODUCT(
  product_key,
  product_id,
  product_name,
  subcategory_code,
  subcategory_name,
  category_code,
  category_name
)
~~~~

Ví dụ:

| product_key | product_id | product_name | subcategory | category |
| ---: | --- | --- | --- | --- |
| 101 | P01 | Sổ tay | Giấy | Văn phòng phẩm |
| 102 | P02 | Bút bi | Bút | Văn phòng phẩm |
| 103 | P03 | Ly thủy tinh | Ly | Gia dụng |

Ưu điểm:

- Truy vấn nhóm theo sản phẩm, nhóm và ngành hàng đơn giản; JOIN fact → dimension là đủ.
- Phù hợp nhiều mô hình hình sao và công cụ BI.
- Có thể giảm số JOIN ở truy vấn so với mô hình tách nhiều bảng chiều.

Đánh đổi:

- category_name lặp ở nhiều dòng sản phẩm; cập nhật tên ngành hàng có thể phải sửa nhiều dòng.
- Cần kiểm soát **subcategory_code → category_code** và **category_code → category_name** ở phạm vi nghiệp vụ đúng.
- Các thuộc tính lịch sử có thể khiến nhiều phiên bản sản phẩm cùng tồn tại; truy vấn phải dùng **product_key phiên bản phù hợp**, không JOIN tùy tiện bằng product_id.

Dimension phẳng **không tự có lỗi chuẩn hóa đến mức không thể dùng**: mô hình phân tích ưu tiên truy vấn và tính nhất quán được quản trị. Điều cần chứng minh là các thuộc tính lặp được **đồng bộ theo một nguồn định nghĩa** và phân cấp không sinh mâu thuẫn.

### 4.2. Snowflake: chuẩn hóa các cấp chiều thành bảng

Một phương án tách:

~~~~text
DIM_CATEGORY(category_key PK, category_code UNIQUE, category_name)
       ↑
DIM_SUBCATEGORY(
  subcategory_key PK,
  subcategory_code UNIQUE,
  category_key FK,
  subcategory_name
)
       ↑
DIM_PRODUCT(
  product_key PK,
  product_id,
  subcategory_key FK,
  product_name
)
       ↑
FACT_SALES(product_key FK, ...)
~~~~

Các FK từ sản phẩm đến nhóm và từ nhóm đến ngành giúp quản lý mối quan hệ **một–nhiều có xác định**. Nếu doanh nghiệp chuyển phân cấp theo lịch sử, khóa và cấu trúc phải được thiết kế cho các phiên bản, không chỉ gắn đè category_key hiện tại.

Ưu điểm:

- Quan hệ phân loại được kiểm soát ở một nơi; ngành hàng không lặp nguyên thông tin ở mọi sản phẩm.
- Giảm bất thường cập nhật tên hoặc quan hệ phân cấp khi có quy tắc tập trung.
- Có thể phù hợp với taxonomy phức tạp, nhiều nhóm dùng lại và quản trị cấp.

Đánh đổi:

- Truy vấn cần nhiều JOIN hơn; một số công cụ BI thích dimension phẳng.
- Các nhánh thiếu cấp có thể khó thể hiện nếu FK bắt buộc.
- Nếu hệ thống thực sự nhiều–nhiều, chỉ thêm FK đơn vào bảng con có thể mô tả sai nghiệp vụ.

**Snowflake và star schema không phải đối thủ tuyệt đối.** Có thể giữ fact ở trung tâm và chỉ chuẩn hóa một phần những dimension có phân cấp cần quản trị chặt.

### 4.3. Bảng cha–con cho phân cấp tổ chức không cân bằng

Với cấu trúc tổ chức có nhiều cấp không cố định, một bảng thành viên kèm khóa cha:

~~~~sql
CREATE TABLE org_unit_example (
    unit_id BIGINT PRIMARY KEY,
    unit_name VARCHAR(120) NOT NULL,
    parent_unit_id BIGINT
        REFERENCES org_unit_example(unit_id),
    CONSTRAINT ck_org_no_self_parent
        CHECK (parent_unit_id IS NULL OR parent_unit_id <> unit_id)
);
~~~~

Mô hình này cho phép cây có chiều sâu khác nhau. Tuy nhiên:

- CHECK trên chỉ chặn **một nút trỏ chính nó**, **không** chặn vòng dài như A → B → C → A.
- Nếu mỗi đơn vị cần nhiều cha tại cùng thời điểm, một cột parent_unit_id không đủ; cần mô hình quan hệ nhiều–nhiều và quy tắc phân bổ/đọc phù hợp.
- Khi phân tích lịch sử, quan hệ cha–con cần có thời gian hiệu lực hoặc phiên bản theo chính sách được chốt.

Truy vấn đệ quy PostgreSQL minh họa đi từ một đơn vị về các tổ tiên, với dữ liệu đã được kiểm soát không có chu kỳ:

~~~~sql
WITH RECURSIVE ancestors AS (
    SELECT unit_id, parent_unit_id, unit_name, 0 AS depth
    FROM org_unit_example
    WHERE unit_id = 10

    UNION ALL

    SELECT p.unit_id, p.parent_unit_id, p.unit_name, a.depth + 1
    FROM org_unit_example AS p
    JOIN ancestors AS a ON p.unit_id = a.parent_unit_id
)
SELECT unit_id, unit_name, depth
FROM ancestors
ORDER BY depth;
~~~~

Đây là **truy vấn minh họa trên cây hợp lệ**, không phải thuật toán xử lý mọi đồ thị hoặc chu kỳ. Trong hệ thống thực, cần thiết kế kiểm tra chu kỳ, giới hạn độ sâu hoặc sử dụng cơ chế đệ quy có phát hiện chu kỳ phù hợp nếu dữ liệu có thể sai.

### 4.4. Bảng cầu (bridge) cho quan hệ nhiều–nhiều

Giả sử P01 thuộc đồng thời hai bộ sưu tập và cần phân bổ doanh thu:

~~~~text
DIM_PRODUCT(product_key, ...)
DIM_COLLECTION(collection_key, collection_name, ...)
BRIDGE_PRODUCT_COLLECTION(
    product_key,
    collection_key,
    allocation_weight
)
~~~~

Ví dụ:

| product_key | collection | allocation_weight |
| ---: | --- | ---: |
| 101 | Tựu trường | 0,70 |
| 101 | Quà tặng | 0,30 |

Nếu doanh thu P01 là 100.000 VND, chỉ số **doanh thu phân bổ** là:

\[
100000\times 0{,}70=70000
\]

và

\[
100000\times 0{,}30=30000.
\]

Với mỗi sản phẩm và phạm vi/thời điểm áp dụng, nếu muốn bảo toàn tổng doanh thu sau phân bổ, cần bảo đảm:

\[
\sum_{\text{collection hợp lệ}}allocation\_weight=1.
\]

Ràng buộc CHECK từ 0 đến 1 trên từng hàng **chưa đủ** để bảo đảm **tổng trọng số bằng 1** cho cả nhóm; cần phép kiểm tra hoặc cơ chế liên hàng riêng. Nếu không cần phân bổ mà muốn xem **toàn bộ doanh thu liên quan đến mỗi bộ sưu tập**, có thể báo cáo có gắn nhãn nhưng phải ghi rõ **các tổng bộ sưu tập không cộng được với nhau**.

Đối với bridge có hiệu lực thời gian, khóa gán và trọng số phải được xét **tại thời điểm sự kiện** hoặc theo một quy tắc phân tích khác được phê duyệt. Không dùng trọng số hiện tại cho mọi sự kiện lịch sử một cách ngầm định.

## 5. Dimension dùng chung giữa nhiều bảng fact: conformed dimension

**Conformed dimension** là một dimension có **định nghĩa, khóa, thuộc tính và các cấp phân tích nhất quán đủ để được sử dụng tương thích giữa các quy trình kinh doanh hoặc bảng fact**. Đây là nền tảng để so sánh số liệu từ nhiều nguồn sự kiện trong cùng một hệ thống báo cáo.

Ví dụ một công ty có:

- **FACT_SALES_LINE:** mỗi hàng là một dòng bán hàng hợp lệ.
- **FACT_RETURN_LINE:** mỗi hàng là một lần hoàn trả ở mức dòng.
- **FACT_INVENTORY_DAILY:** mỗi hàng là tồn kho **cuối ngày**, theo sản phẩm và kho.

Cả ba quy trình có thể cần phân tích theo **sản phẩm**, **ngày** và **địa điểm**. Nhưng tính chất các measure và grain fact không giống nhau.

### 5.1. Cùng tên dimension chưa đủ để gọi là conformed

Giả sử bộ phận bán hàng có bảng **sales_product** và bộ phận hoàn trả có **returns_product**. Cả hai đều có cột category_name, nhưng:

- Sales gọi P01 là **Văn phòng phẩm**.
- Returns gọi P01 là **Quà tặng** theo taxonomy của bộ phận chăm sóc khách.
- Sales dùng category_code = VPP, Returns dùng category_code = OFFICE.
- Sales gán loại theo **ngày bán**, Returns gán loại theo **ngày nhận hàng hoàn**.

Nếu ghép báo cáo theo category_name hoặc category_code mà không có mapping được phê duyệt, số liệu có thể bị:

1. **Tách thành hai nhóm** dù người dùng tưởng chúng là cùng một ngành hàng.
2. **Gộp sai nhóm** chỉ vì nhãn hiển thị trùng nhau.
3. **Lệch lịch sử** vì hai fact dùng chính sách phân loại ở các thời điểm khác nhau.

Để có conformed dimension, phải xác nhận **cùng ngữ nghĩa hoặc khả năng ánh xạ chính xác sang một tập thuộc tính/cấp phân tích dùng chung**.

### 5.2. Các cấp độ nhất quán cần kiểm tra

| Khía cạnh | Câu hỏi thiết kế |
| --- | --- |
| **Business identity** | P01 có đại diện cùng sản phẩm ở cả hai quy trình không? Khóa có kèm tenant/source không? |
| **Surrogate key** | Hai fact có dùng cùng khóa tới một dimension được quản trị thống nhất không? |
| **Attribute definitions** | category, brand, size có cùng ý nghĩa và quy tắc làm sạch không? |
| **Domain values** | VPP, OFFICE, NULL, Unknown được dùng thống nhất hay có mapping công khai? |
| **Hierarchy paths** | P01 lên cùng nhóm và ngành hàng theo cùng phạm vi và thời điểm không? |
| **History policy** | Có dùng phân loại hiện tại, phân loại tại lúc bán hay phân loại tại lúc hoàn không? |
| **Granularity** | Có fact lưu SKU, fact khác chỉ lưu nhóm hàng? Có cấp chung nào không? |
| **Scope/security** | Khóa có phân biệt tenant, thị trường, đơn vị kinh doanh không? |
| **Ownership/versioning** | Ai được phép đổi taxonomy? Khi thay đổi, fact và báo cáo được chuyển đổi thế nào? |

Mô hình tốt thường có **một dimension được quản lý tập trung** để các fact tham chiếu chung khóa thay thế. Tuy nhiên, conformed dimension là **hợp đồng ngữ nghĩa**, không nhất thiết là một bảng vật lý duy nhất: các data mart độc lập cũng có thể dùng bản sao dimension thống nhất hoặc những thuộc tính chung đã được ánh xạ chính xác.

Nếu mỗi mart tự tạo **product_key = 101** nhưng thực ra tham chiếu sản phẩm khác nhau, không được JOIN hai fact qua 101. **Trùng số surrogate key không chứng minh sự đồng nhất danh tính.** Cần quản trị hoặc bảng ánh xạ định danh có kiểm chứng.

### 5.3. Conformed không bắt buộc mọi fact có cùng grain

FACT_SALES_LINE có grain **mỗi dòng bán**, FACT_RETURN_LINE có grain **mỗi sự kiện hoàn trả**, còn FACT_INVENTORY_DAILY có grain **sản phẩm–kho–ngày**.

Các fact vẫn có thể dùng chung DIM_PRODUCT và DIM_DATE. Điều kiện là:

- Khóa dimension có ngữ nghĩa thống nhất.
- Phân cấp trong dimension có thể cung cấp một **cấp nhóm chung** cho câu hỏi cần so sánh.
- Measure và thời điểm của từng fact được mô tả rõ.
- Báo cáo tổng hợp **mỗi fact riêng theo cấp chung trước khi so sánh**.

Không cần ép tất cả fact thành “một hàng trên mỗi đơn” chỉ để có cùng dimension. **Conformance của dimension** và **grain của fact** là hai quyết định khác nhau.

### 5.4. Bus matrix: bản đồ các quy trình và chiều phân tích

**Bus matrix** (ma trận bus) đặt các **quy trình/fact ở hàng** và **conformed dimensions ở cột**. Nó giúp nhận diện những chiều nào được dùng chung và nơi cần thống nhất định nghĩa.

| Quy trình / fact | Ngày | Sản phẩm | Cửa hàng | Khách hàng | Kho |
| --- | :---: | :---: | :---: | :---: | :---: |
| **Bán hàng — FACT_SALES_LINE** | ✓ | ✓ | ✓ | ✓ | — |
| **Hoàn trả — FACT_RETURN_LINE** | ✓ | ✓ | ✓ | ✓ nếu nguồn có | — |
| **Tồn kho cuối ngày — FACT_INVENTORY_DAILY** | ✓ | ✓ | — | — | ✓ |

Từ ma trận:

- **Ngày** và **Sản phẩm** là hai dimension conformed ứng viên cho cả ba quy trình.
- **Cửa hàng** dùng cho bán và hoàn trả; phải phân biệt cửa hàng bán với địa điểm nhận hoàn nếu nghiệp vụ khác.
- **Khách hàng** không thuộc grain tồn kho cuối ngày, vì tồn kho không “của một khách hàng”.
- **Kho** là chiều của tồn kho; không suy ra tự nhiên nó là cửa hàng nếu có quan hệ giao nhận riêng.

Ma trận không thay thế mô tả grain. Một dấu ✓ chỉ nói quy trình **có thể phân tích theo chiều đó**; không nói fact có cùng số hàng hay measure cộng được giữa các quy trình.

### 5.5. Conformed attributes và roll-up theo tập cột chung

Đôi khi hai dimension chi tiết khác nhau nhưng có các thuộc tính cấp cao nhất quán. Ví dụ:

~~~~text
DIM_PRODUCT_SALES:
  product_id, sales_sku_variant, category_code, category_name

DIM_PRODUCT_RETURNS:
  product_id, return_reason_group, category_code, category_name
~~~~

Nếu **category_code và category_name được quản trị cùng định nghĩa**, hai mart có thể phân tích theo **ngành hàng** ngay cả khi không có cùng toàn bộ cột chi tiết. Đây là một kiểu conformance **theo tập thuộc tính/cấp tổng hợp chung**.

Nhưng nếu một fact chỉ có category_code và fact kia có SKU, muốn so sánh theo SKU phải xác định có đủ mapping hay không. Conformed ở cấp **ngành hàng** không tự có nghĩa conformed ở cấp **SKU**.

### 5.6. Conformed dimension như hợp đồng giữa các nhóm

Để người viết báo cáo tin rằng số tiền bán và hoàn được nhóm theo cùng ngành hàng, tài liệu nên chỉ rõ:

> DIM_PRODUCT quản lý product_key và product_id ở phạm vi toàn hệ thống; category_code, category_name và quan hệ nhóm–ngành hàng được dùng chung giữa fact bán và fact hoàn theo cùng chính sách lịch sử. Mọi thay đổi taxonomy phải có chủ sở hữu, thời điểm hiệu lực và kiểm chứng các dòng fact bị ảnh hưởng.

Một định nghĩa như vậy giúp loại bỏ tình huống “hai dashboard đều đúng theo hệ thống của chúng nhưng không thể so sánh với nhau”.

## 6. Dimension dùng chung, role-playing và thời gian

### 6.1. Role-playing dimension: một bảng, nhiều vai trò

Một **DIM_DATE** có thể được dùng nhiều lần trong cùng một fact:

~~~~text
FACT_ORDER(
    order_date_key  FK → DIM_DATE.date_key,
    ship_date_key   FK → DIM_DATE.date_key,
    delivery_date_key FK → DIM_DATE.date_key
)
~~~~

Cùng một bảng ngày, nhưng ba vai trò khác nhau:

- **Ngày đặt đơn**.
- **Ngày giao hàng cho đơn vị vận chuyển**.
- **Ngày khách nhận hàng**.

Nếu người dùng hỏi “số đơn theo ngày đặt”, phải JOIN qua **order_date_key**. Nếu hỏi “số đơn đã giao theo ngày nhận”, phải JOIN qua **delivery_date_key**.

Ví dụ:

~~~~sql
-- Ví dụ cú pháp; giả định FACT_ORDER và DIM_DATE đã được khai báo
-- với các khóa và ràng buộc phù hợp.
SELECT d.full_date AS order_date, COUNT(*) AS orders
FROM fact_order AS f
JOIN dim_date AS d ON d.date_key = f.order_date_key
GROUP BY d.full_date
ORDER BY d.full_date;
~~~~

Không được thay order_date_key bằng delivery_date_key chỉ vì cả hai đều tham chiếu DIM_DATE. **Bảng chiều giống nhau nhưng vai trò khóa ngoại khác nhau**, nên ý nghĩa phân tích khác nhau.

### 6.2. Shared dimension không làm các ngày sự kiện tương đương

Trong mô hình bán và hoàn:

~~~~text
FACT_SALES_LINE.sale_date_key   → DIM_DATE.date_key
FACT_RETURN_LINE.return_date_key → DIM_DATE.date_key
~~~~

Một hàng hoàn trả ngày 03/11 có thể liên quan đến đơn bán ngày 01/10. Nếu so sánh **doanh thu bán tháng 10** với **tiền hoàn trả tháng 10**, ta đang dùng **hai ngày sự kiện khác nhau nhưng cùng trục lịch tháng**.

Nếu muốn chỉ số “tiền hoàn của các đơn bán trong tháng 10”, fact hoàn cần một khóa hoặc đường dẫn về **ngày bán gốc**, và mô hình phải gọi rõ vai trò:

~~~~text
return_date_key       = thời điểm hoàn trả xảy ra
original_sale_date_key = thời điểm bán của dòng được hoàn
~~~~

Tự ý dùng ngày bán gốc ở một báo cáo và ngày hoàn trả ở báo cáo khác sẽ cho hai số cùng nhãn “hoàn trả tháng 10” nhưng khác ngữ nghĩa.

### 6.3. Lịch dương và lịch tài chính

Một DIM_DATE có thể chứa:

~~~~text
date_key
full_date
calendar_month
calendar_year
fiscal_period
fiscal_year
iso_week
iso_week_year
~~~~

Các cột tạo ra **nhiều phân cấp** trên cùng tập ngày. Khi báo cáo:

- Nhóm theo **calendar_year + calendar_month** cho tháng dương lịch.
- Nhóm theo **fiscal_year + fiscal_period** cho kỳ tài chính.
- Nhóm theo **iso_week_year + iso_week** cho tuần ISO.

Không GROUP BY chỉ calendar_month mà bỏ calendar_year nếu dữ liệu có nhiều năm: tháng 10/2025 và tháng 10/2026 sẽ bị gộp. Cũng không nên dùng calendar_year với iso_week khi định nghĩa tuần ISO, vì ranh giới năm có thể khác.

### 6.4. SCD Type 2 và dimension dùng chung

Nếu DIM_PRODUCT dùng SCD2 để giữ lịch sử ngành hàng, P01 có thể có:

| product_key | product_id | category | effective_from | effective_to |
| ---: | --- | --- | --- | --- |
| 101 | P01 | Văn phòng phẩm | 2026-01-01 | 2026-11-01 |
| 104 | P01 | Quà tặng | 2026-11-01 | chưa kết thúc |

Fact bán ngày 01/10 trỏ product_key 101. Một fact hoàn ngày 03/11 **có thể** trỏ:

- **104**, nếu báo cáo dùng **phân loại tại thời điểm hoàn**.
- **101**, nếu báo cáo cần gắn hoàn trả với **phân loại tại thời điểm bán gốc**.

Hai cách đều có thể là quyết định hợp lệ, nhưng **không tương thích ngầm định** cho drill-across theo ngành hàng lịch sử. Phải ghi rõ câu hỏi của từng báo cáo, hoặc lưu thêm vai trò khóa phiên bản nếu có nhu cầu phân tích cả hai.

Khi cùng một dimension SCD2 được dùng xuyên nhiều fact, **định nghĩa thời điểm chọn phiên bản** là một phần của hợp đồng conformance, không chỉ là kỹ thuật lookup surrogate key.

## 7. Ví dụ thực hành: cùng DIM_PRODUCT và DIM_DATE cho bán hàng, hoàn trả

Phần này xây dựng **một bộ lược đồ PostgreSQL độc lập**, dùng các bảng DIM_DATE, DIM_PRODUCT, DIM_STORE và hai fact bán/hoàn. Mục tiêu là chứng minh cách **hai fact khác grain sử dụng dimension dùng chung**, rồi truy vấn so sánh doanh thu/hoàn trả không gây fanout.

### 7.1. Quy tắc nghiệp vụ của ví dụ

Đặt giả định:

1. **Mỗi dòng FACT_SALES_LINE là một dòng bán đã ghi nhận hợp lệ**; một đơn có thể có nhiều dòng.
2. **Mỗi dòng FACT_RETURN_LINE là một sự kiện hoàn trả dòng bán**; một dòng bán có thể có nhiều sự kiện hoàn trả theo từng đợt.
3. Tất cả measure tiền đều bằng **VND**, chưa xét thuế và phí; **net_amount = gross_amount - discount_amount** ở fact bán.
4. Mỗi bản ghi hoàn trả có **returned_amount** không âm. Tổng hoàn của các đợt theo cùng dòng bán cần quy tắc kiểm tra riêng.
5. **Ngày bán** và **ngày hoàn trả** là hai vai trò của **cùng DIM_DATE**; doanh thu và tiền hoàn được nhóm theo **ngày xảy ra sự kiện tương ứng**.
6. DIM_PRODUCT là **conformed dimension dùng chung**; mỗi sản phẩm có đúng một nhóm/ngành hàng hiện tại trong ví dụ. Đây là **Type 1**: không lưu lịch sử đổi phân loại.
7. Mỗi fact trỏ cùng **product_key**, **date_key** và **store_key** từ các dimension được quản trị thống nhất.
8. Quy tắc “doanh thu sau hoàn” ở ví dụ được định nghĩa là **doanh thu dòng bán sau chiết khấu trừ số tiền hoàn ghi nhận trong kỳ**, không mặc nhiên bằng chỉ số doanh thu kế toán.

### 7.2. Sơ đồ hai fact dùng chung dimension

~~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : sale_date
    DIM_DATE ||--o{ FACT_RETURN_LINE : return_date
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : sold_product
    DIM_PRODUCT ||--o{ FACT_RETURN_LINE : returned_product
    DIM_STORE ||--o{ FACT_SALES_LINE : selling_store
    DIM_STORE ||--o{ FACT_RETURN_LINE : return_store

    DIM_DATE {
        integer date_key PK
        date full_date UK
        smallint calendar_year
        smallint calendar_month
    }
    DIM_PRODUCT {
        bigint product_key PK
        varchar product_id UK
        varchar subcategory_code
        varchar category_code
        varchar category_name
    }
    DIM_STORE {
        bigint store_key PK
        varchar store_code UK
        varchar store_name
    }
    FACT_SALES_LINE {
        varchar sale_line_id PK
        varchar order_id
        integer sale_date_key FK
        bigint product_key FK
        bigint store_key FK
        integer quantity
        decimal net_amount
    }
    FACT_RETURN_LINE {
        varchar return_line_id PK
        varchar original_sale_line_id FK
        integer return_date_key FK
        bigint product_key FK
        bigint store_key FK
        integer returned_qty
        decimal returned_amount
    }
~~~~

Một DIM_DATE được tham chiếu **theo hai vai trò**. Một DIM_PRODUCT được dùng chung **theo cùng product_key và cùng phân cấp**. Điều này cho phép roll-up về cùng category_code để so sánh hai loại fact.

### 7.3. DDL dimension trong PostgreSQL

Chạy các lệnh trong một database/schema thử nghiệm trống:

~~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL,
    CONSTRAINT ck_dim_date_month CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_id VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    subcategory_code VARCHAR(30) NOT NULL,
    subcategory_name VARCHAR(100) NOT NULL,
    category_code VARCHAR(30) NOT NULL,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code VARCHAR(30) NOT NULL UNIQUE,
    store_name VARCHAR(150) NOT NULL
);
~~~~

Các cột phân cấp trong DIM_PRODUCT là dạng **flattened dimension**. DDL trên bảo đảm mỗi product_id duy nhất, nhưng chưa bắt **mọi dòng dùng cùng subcategory_code phải có một category_code giống nhau**. Phép kiểm tra tính nhất quán phân cấp sẽ được trình bày ở phần sau; trong hệ thống thực có thể quản trị taxonomy ở bảng riêng rồi phát hành dimension phẳng từ nguồn đó.

### 7.4. DDL hai fact với grain khác nhau

~~~~sql
CREATE TABLE fact_sales_line (
    sale_line_id VARCHAR(30) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    sale_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount NUMERIC(14, 2) NOT NULL
        CHECK (gross_amount >= 0),
    discount_amount NUMERIC(14, 2) NOT NULL
        CHECK (discount_amount >= 0 AND discount_amount <= gross_amount),
    net_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (gross_amount - discount_amount) STORED,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    -- Cho phép FK ghép của fact hoàn kiểm tra cả dòng bán lẫn sản phẩm.
    CONSTRAINT uq_sale_line_product UNIQUE (sale_line_id, product_key)
);

CREATE TABLE fact_return_line (
    return_line_id VARCHAR(30) PRIMARY KEY,
    original_sale_line_id VARCHAR(30) NOT NULL,
    return_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    returned_qty INTEGER NOT NULL CHECK (returned_qty > 0),
    returned_amount NUMERIC(14, 2) NOT NULL
        CHECK (returned_amount >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    CONSTRAINT fk_return_source_sale_product
        FOREIGN KEY (original_sale_line_id, product_key)
        REFERENCES fact_sales_line (sale_line_id, product_key)
);
~~~~

Ràng buộc UNIQUE(sale_line_id, product_key) ở fact bán có vẻ **dư thừa** về mặt định danh vì sale_line_id đã là PK. Tuy nhiên, nó được khai báo để PostgreSQL cho phép **FK ghép (original_sale_line_id, product_key)** từ fact hoàn, nhờ đó một sự kiện hoàn **không thể tham chiếu dòng bán của sản phẩm khác**.

Ràng buộc này **không** nói hai fact có cùng grain:

- sale_line_id là PK của dòng bán.
- return_line_id là PK của sự kiện hoàn.
- original_sale_line_id **không UNIQUE** ở fact hoàn vì một dòng bán có thể được hoàn nhiều đợt.

**Giới hạn của DDL:** Chưa có ràng buộc cộng dồn để ngăn tổng returned_qty hoặc returned_amount của mọi sự kiện hoàn vượt số lượng/giá trị của dòng bán ban đầu. Quy tắc này cần được định nghĩa và kiểm chứng qua phép tính liên hàng hoặc quy trình nghiệp vụ thích hợp. FK ghép chỉ bảo đảm **tham chiếu tồn tại và sản phẩm khớp**.

### 7.5. Nạp dữ liệu mẫu có kết quả dự kiến

Các INSERT sau là **fixture kiểm chứng mô hình**, không phải một chương trình ETL.

~~~~sql
INSERT INTO dim_date
    (date_key, full_date, calendar_year, calendar_month)
VALUES
    (20261001, DATE '2026-10-01', 2026, 10),
    (20261002, DATE '2026-10-02', 2026, 10),
    (20261103, DATE '2026-11-03', 2026, 11);

INSERT INTO dim_product
    (product_key, product_id, product_name,
     subcategory_code, subcategory_name,
     category_code, category_name)
VALUES
    (101, 'P01', 'Sổ tay',
     'GIAY', 'Giấy', 'VPP', 'Văn phòng phẩm'),
    (102, 'P02', 'Bút bi',
     'BUT', 'Bút', 'VPP', 'Văn phòng phẩm'),
    (103, 'P03', 'Ly thủy tinh',
     'LY', 'Ly', 'GD', 'Gia dụng');

INSERT INTO dim_store (store_key, store_code, store_name)
VALUES
    (11, 'HN', 'Cửa hàng Hà Nội'),
    (12, 'HCM', 'Cửa hàng TP.HCM');

INSERT INTO fact_sales_line
    (sale_line_id, order_id, sale_date_key,
     product_key, store_key, quantity,
     gross_amount, discount_amount)
VALUES
    ('S1', 'O100', 20261001, 101, 11, 2, 200000, 20000),
    ('S2', 'O101', 20261001, 101, 11, 1, 100000, 0),
    ('S3', 'O102', 20261002, 102, 11, 3, 90000, 0),
    ('S4', 'O103', 20261103, 103, 12, 1, 80000, 0);

INSERT INTO fact_return_line
    (return_line_id, original_sale_line_id,
     return_date_key, product_key, store_key,
     returned_qty, returned_amount)
VALUES
    ('R1', 'S1', 20261002, 101, 11, 1, 90000),
    ('R2', 'S1', 20261002, 101, 11, 1, 90000),
    ('R3', 'S3', 20261103, 102, 11, 1, 30000);
~~~~

Tóm tắt dữ liệu:

| Fact | Dòng | Ngày | Sản phẩm | Ngành hàng | Số lượng | Giá trị VND |
| --- | --- | --- | --- | --- | ---: | ---: |
| Bán | S1 | 01/10 | P01 | Văn phòng phẩm | 2 | 180.000 |
| Bán | S2 | 01/10 | P01 | Văn phòng phẩm | 1 | 100.000 |
| Bán | S3 | 02/10 | P02 | Văn phòng phẩm | 3 | 90.000 |
| Bán | S4 | 03/11 | P03 | Gia dụng | 1 | 80.000 |
| Hoàn | R1 | 02/10 | P01 | Văn phòng phẩm | 1 | 90.000 |
| Hoàn | R2 | 02/10 | P01 | Văn phòng phẩm | 1 | 90.000 |
| Hoàn | R3 | 03/11 | P02 | Văn phòng phẩm | 1 | 30.000 |

**Tổng bán** = 450.000 VND; **tổng hoàn** = 210.000 VND; chênh lệch bán trừ hoàn trên toàn bộ tập dữ liệu = **240.000 VND** theo định nghĩa của ví dụ.

### 7.6. Roll-up riêng fact bán theo ngành hàng và tháng

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name,
    SUM(s.quantity) AS units_sold,
    SUM(s.net_amount) AS sales_vnd
FROM fact_sales_line AS s
JOIN dim_date AS d ON d.date_key = s.sale_date_key
JOIN dim_product AS p ON p.product_key = s.product_key
GROUP BY
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name
ORDER BY d.calendar_year, d.calendar_month, p.category_code;
~~~~

| Năm | Tháng | Ngành hàng | Số lượng bán | Doanh thu bán VND |
| ---: | ---: | --- | ---: | ---: |
| 2026 | 10 | Văn phòng phẩm | 6 | 370.000 |
| 2026 | 11 | Gia dụng | 1 | 80.000 |

Kết quả từ ba dòng bán tháng 10 là 180.000 + 100.000 + 90.000 = **370.000**. Việc GROUP BY cả năm và tháng giúp không gộp hai tháng cùng số ở những năm khác nhau.

### 7.7. Roll-up riêng fact hoàn theo ngành hàng và tháng

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name,
    SUM(r.returned_qty) AS units_returned,
    SUM(r.returned_amount) AS returns_vnd
FROM fact_return_line AS r
JOIN dim_date AS d ON d.date_key = r.return_date_key
JOIN dim_product AS p ON p.product_key = r.product_key
GROUP BY
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name
ORDER BY d.calendar_year, d.calendar_month, p.category_code;
~~~~

| Năm | Tháng | Ngành hàng | Số lượng hoàn | Tiền hoàn VND |
| ---: | ---: | --- | ---: | ---: |
| 2026 | 10 | Văn phòng phẩm | 2 | 180.000 |
| 2026 | 11 | Văn phòng phẩm | 1 | 30.000 |

Fact hoàn có sự kiện R3 trong **tháng 11** cho dòng bán S3 diễn ra trong **tháng 10**. Báo cáo này dùng **ngày hoàn**, không phải ngày bán gốc. Việc dùng chung DIM_DATE không làm hai ngày sự kiện trở thành một.

### 7.8. Cách sai: JOIN hai fact chi tiết qua dimension chung

Một thiết kế báo cáo dễ mắc lỗi:

~~~~sql
-- CỐ Ý MINH HỌA JOIN SAI: không dùng kết quả làm báo cáo thật.
SELECT
    SUM(s.net_amount) AS sai_tong_ban,
    SUM(r.returned_amount) AS sai_tong_hoan
FROM fact_sales_line AS s
JOIN fact_return_line AS r
    ON r.product_key = s.product_key
JOIN dim_date AS ds ON ds.date_key = s.sale_date_key
JOIN dim_date AS dr ON dr.date_key = r.return_date_key
WHERE s.product_key = 101
  AND ds.calendar_year = 2026
  AND ds.calendar_month = 10
  AND dr.calendar_year = 2026
  AND dr.calendar_month = 10;
~~~~

Trong tháng 10, P01 có:

- **Hai dòng bán:** S1 = 180.000, S2 = 100.000.
- **Hai dòng hoàn:** R1 = 90.000, R2 = 90.000.

JOIN theo product_key cho **2 × 2 = 4 dòng kết quả**:

| Dòng bán | net_amount | Dòng hoàn | returned_amount |
| --- | ---: | --- | ---: |
| S1 | 180.000 | R1 | 90.000 |
| S1 | 180.000 | R2 | 90.000 |
| S2 | 100.000 | R1 | 90.000 |
| S2 | 100.000 | R2 | 90.000 |

Nếu SUM trực tiếp sau JOIN:

\[
\text{sai\_tong\_ban}=2\times(180000+100000)=560000
\]

\[
\text{sai\_tong\_hoan}=2\times(90000+90000)=360000
\]

Trong khi số đúng cho P01 là **280.000 bán** và **180.000 hoàn**. Đây là lỗi **fanout** do JOIN hai fact có nhiều dòng trên cùng một thành viên dimension.

Một FK hợp lệ không ngăn fanout. Cả hai fact cùng tham chiếu sản phẩm P01 **không** có nghĩa một dòng bán khớp một–một với một dòng hoàn ở cấp product_key. Nếu JOIN theo original_sale_line_id, quan hệ còn có thể là **1:N** vì một dòng bán có nhiều đợt hoàn; SUM số bán sau JOIN vẫn có thể bị lặp nếu không xử lý grain.

Không nên dùng **SUM(DISTINCT net_amount)** để “vá” lỗi. Hai dòng bán hợp lệ có thể có cùng giá trị tiền và SUM(DISTINCT) sẽ loại bỏ một khoản đúng. Cách sửa là thiết kế phép tổng hợp theo grain, không khử trùng giá trị measure.

### 7.9. Cách đúng: drill-across bằng truy vấn đa lượt (multipass SQL)

**Drill-across** là so sánh measure của nhiều fact theo **một tập chiều conformed chung**. Quy tắc an toàn:

1. Quyết định **grain kết quả**: ở ví dụ là một hàng trên **năm + tháng + ngành hàng**.
2. Tổng hợp **mỗi fact độc lập** về đúng grain kết quả ấy.
3. JOIN **hai tập kết quả đã tổng hợp** theo **khóa thành viên các chiều chung**, không theo từng dòng fact.
4. Giữ cả nhóm chỉ xuất hiện ở một phía bằng FULL OUTER JOIN hoặc giải pháp tương đương.
5. Thay NULL của measure thiếu bằng 0 **chỉ khi ý nghĩa đúng là không có sự kiện trong nhóm**, không thay NULL thiếu dữ liệu nguồn tùy tiện.

SQL:

~~~~sql
WITH sales_by_month_category AS (
    SELECT
        d.calendar_year AS yr,
        d.calendar_month AS mo,
        p.category_code,
        p.category_name,
        SUM(s.net_amount) AS sales_vnd
    FROM fact_sales_line AS s
    JOIN dim_date AS d ON d.date_key = s.sale_date_key
    JOIN dim_product AS p ON p.product_key = s.product_key
    GROUP BY
        d.calendar_year,
        d.calendar_month,
        p.category_code,
        p.category_name
),
returns_by_month_category AS (
    SELECT
        d.calendar_year AS yr,
        d.calendar_month AS mo,
        p.category_code,
        p.category_name,
        SUM(r.returned_amount) AS returns_vnd
    FROM fact_return_line AS r
    JOIN dim_date AS d ON d.date_key = r.return_date_key
    JOIN dim_product AS p ON p.product_key = r.product_key
    GROUP BY
        d.calendar_year,
        d.calendar_month,
        p.category_code,
        p.category_name
)
SELECT
    COALESCE(s.yr, r.yr) AS calendar_year,
    COALESCE(s.mo, r.mo) AS calendar_month,
    COALESCE(s.category_code, r.category_code) AS category_code,
    COALESCE(s.category_name, r.category_name) AS category_name,
    COALESCE(s.sales_vnd, 0) AS sales_vnd,
    COALESCE(r.returns_vnd, 0) AS returns_vnd,
    COALESCE(s.sales_vnd, 0)
        - COALESCE(r.returns_vnd, 0) AS sales_after_returns_vnd
FROM sales_by_month_category AS s
FULL OUTER JOIN returns_by_month_category AS r
    ON s.yr = r.yr
   AND s.mo = r.mo
   AND s.category_code = r.category_code
ORDER BY
    calendar_year,
    calendar_month,
    category_code;
~~~~

Kết quả:

| Năm | Tháng | Ngành hàng | Bán VND | Hoàn VND | Bán sau hoàn VND |
| ---: | ---: | --- | ---: | ---: | ---: |
| 2026 | 10 | Văn phòng phẩm | 370.000 | 180.000 | 190.000 |
| 2026 | 11 | Gia dụng | 80.000 | 0 | 80.000 |
| 2026 | 11 | Văn phòng phẩm | 0 | 30.000 | -30.000 |

**Dòng âm trong tháng 11 có ý nghĩa:** số tiền hoàn của ngành Văn phòng phẩm phát sinh tháng 11 dù trong tập dữ liệu không có giao dịch bán ngành đó trong tháng 11. Đó là kết quả đúng **theo định nghĩa ngày sự kiện và phép tính trong ví dụ**, không phải lỗi phải ép về 0. Nếu cần “hoàn của các giao dịch bán trong tháng 10”, phải dùng **ngày bán gốc** làm khóa nhóm thay vì ngày hoàn.

Trong truy vấn này, **category_code** là khóa cấp ngành hàng đã được conformed; category_name là nhãn dùng chung theo chính sách Type 1 của ví dụ. Nếu cùng category_code có nhiều category_name trong dimension, một CTE có thể tạo **nhiều hàng** trên cùng khóa JOIN và lại phát sinh fanout. Vì vậy phần **kiểm tra tính duy nhất của quan hệ code–name** là điều kiện trước khi đưa truy vấn vào sản xuất.

### 7.10. Có thể thêm số lượng vào phép drill-across không?

Có thể bổ sung SUM(quantity) và SUM(returned_qty) vào hai CTE, nhưng phải ghi rõ:

- Cùng tên “quantity” không chứng minh cùng đơn vị đo.
- Số lượng bán và hoàn có thể đo bằng **đơn vị bán, kiện, chiếc, kg** tùy nghiệp vụ.
- Nếu các sản phẩm khác đơn vị, tổng theo ngành hàng có thể **không có ý nghĩa vật lý**.
- Tỷ lệ hoàn theo số lượng phải dùng **tử số/mẫu số trên cùng đơn vị và cùng tập giao dịch định nghĩa**.

Một tỷ lệ “số lượng hoàn trong tháng / số lượng bán trong tháng” có thể vượt 100% khi hoàn trả của các tháng trước đến muộn. Nếu mục tiêu là tỷ lệ hoàn của các lô bán, cần định nghĩa **cohort theo ngày bán**, không chỉ hai measure theo lịch sự kiện.

## 8. Chứng minh dimension conformed và phân cấp đúng bằng kiểm tra dữ liệu

Một sơ đồ đẹp chưa chứng minh dữ liệu phân loại thống nhất. Cần kiểm tra các **bất biến logic**, đồng thời phân biệt những gì đã được PK/FK/UNIQUE bảo vệ với những gì cần kiểm tra nhiều dòng.

### 8.1. Một mã nhóm không được trỏ nhiều ngành trong phân cấp strict

Với ví dụ DIM_PRODUCT phẳng, kiểm tra:

~~~~sql
SELECT
    subcategory_code,
    COUNT(DISTINCT category_code) AS category_count
FROM dim_product
GROUP BY subcategory_code
HAVING COUNT(DISTINCT category_code) > 1;
~~~~

Kỳ vọng **0 dòng** nếu subcategory_code có nghĩa duy nhất toàn hệ thống theo chính sách Type 1. Nếu mã nhóm chỉ duy nhất trong tenant, phép kiểm tra phải bổ sung **tenant_id** vào GROUP BY và khóa phân loại; nếu phân cấp thay đổi theo thời gian, cần xét **khoảng thời gian/phiên bản** thay vì cấm mọi biến đổi lịch sử.

**Kiểm tra nhãn ngành hàng nhất quán với category_code:**

~~~~sql
SELECT
    category_code,
    COUNT(DISTINCT category_name) AS name_count
FROM dim_product
GROUP BY category_code
HAVING COUNT(DISTINCT category_name) > 1;
~~~~

Kỳ vọng **0 dòng** cho bộ dữ liệu mẫu. Nếu một code có nhiều nhãn do bản dịch hoặc lịch sử, mô hình cần quy định chiều ngôn ngữ/phiên bản thay vì chỉ gắn nhãn có vẻ giống nhau.

### 8.2. Tổng theo ngành hàng phải đối soát tổng fact

~~~~sql
WITH totals AS (
    SELECT SUM(net_amount) AS fact_total
    FROM fact_sales_line
),
rolled AS (
    SELECT SUM(s.net_amount) AS category_total
    FROM fact_sales_line AS s
    JOIN dim_product AS p ON p.product_key = s.product_key
)
SELECT
    totals.fact_total,
    rolled.category_total,
    totals.fact_total - rolled.category_total AS difference
FROM totals CROSS JOIN rolled;
-- Kỳ vọng: 450000, 450000, 0.
~~~~

Ở đây JOIN qua **product_key duy nhất trong dim_product**, nên một dòng fact khớp tối đa một sản phẩm. Ràng buộc FK không NULL bảo đảm tồn tại một sản phẩm nếu các constraint được thực thi và dữ liệu không bị làm sai ngoài luồng. Nếu thay DIM_PRODUCT bằng một **bridge nhiều–nhiều**, đối soát phải xét phân bổ/trọng số; chỉ SUM sau JOIN không còn an toàn.

### 8.3. Kiểm tra dòng hoàn không vượt số lượng dòng bán

FK từ fact hoàn đến fact bán không tự biết tổng số lượng hoàn của nhiều sự kiện:

~~~~sql
SELECT
    s.sale_line_id,
    s.quantity AS sold_qty,
    SUM(r.returned_qty) AS total_returned_qty
FROM fact_sales_line AS s
JOIN fact_return_line AS r
    ON r.original_sale_line_id = s.sale_line_id
GROUP BY s.sale_line_id, s.quantity
HAVING SUM(r.returned_qty) > s.quantity;
~~~~

Kỳ vọng **0 dòng** trong bộ dữ liệu mẫu: S1 bán 2 và được hoàn hai lần, mỗi lần 1; S3 bán 3, được hoàn 1.

Truy vấn này chỉ **phát hiện** vi phạm đã có; để **ngăn** hai giao dịch hoàn đồng thời cùng vượt số lượng, hệ thống cần cơ chế nghiệp vụ hoặc giao dịch tại database được thiết kế an toàn. Đây cũng là ví dụ cho thấy conformed dimension không thay thế ràng buộc giữa các sự kiện.

### 8.4. Kiểm tra hai fact dùng cùng chiều nhưng không có nghĩa cùng sự kiện

Nếu đối soát tiền hoàn theo **tháng hoàn**, tổng theo DIM_DATE phải khớp lịch sự kiện hoàn; nếu đối soát tiền hoàn theo **tháng bán gốc**, cần JOIN đường gốc qua original_sale_line_id và sale_date_key để xác định lịch bán:

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    SUM(r.returned_amount) AS returns_by_original_sale_month
FROM fact_return_line AS r
JOIN fact_sales_line AS s
    ON s.sale_line_id = r.original_sale_line_id
JOIN dim_date AS d ON d.date_key = s.sale_date_key
GROUP BY d.calendar_year, d.calendar_month
ORDER BY d.calendar_year, d.calendar_month;
-- Với dữ liệu mẫu: toàn bộ 210000 gắn về tháng bán 10/2026.
~~~~

Ở truy vấn này, mỗi sự kiện hoàn trỏ đến **đúng một** sale_line_id, nên JOIN về fact bán được dùng để **đọc thuộc tính ngày bán gốc của mỗi sự kiện hoàn**. Chúng ta chỉ SUM **returned_amount** (measure của bên nhiều), **không SUM net_amount của bên bán** trên kết quả JOIN 1:N. Đây là khác biệt quan trọng giữa một JOIN có mục đích truy vấn ngữ cảnh và một JOIN hai fact để cộng tùy tiện mọi measure.

### 8.5. Đánh giá kiểm thử trước khi công bố

| Điều cần bảo đảm | Kiểm tra khả thi | Lưu ý |
| --- | --- | --- |
| Một fact có đúng grain | UNIQUE sale_line_id / return_line_id | Khóa cần ổn định trong phạm vi nguồn/tenant |
| Không có product_key mồ côi | FK đến DIM_PRODUCT | Không chứng minh category gán đúng nghiệp vụ |
| Subcategory chỉ có một category trong phân cấp strict | GROUP BY subcategory_code và COUNT DISTINCT category_code | Theo đúng tenant/phiên bản |
| category_code có tên nhất quán | GROUP BY category_code | Theo quy tắc ngôn ngữ và lịch sử |
| Roll-up không mất/nhân dòng | Đối soát tổng fact với tổng sau dimension JOIN | Chọn measure additive |
| Bridge phân bổ bảo toàn tổng | Kiểm tra tổng trọng số và tổng sau phân bổ | Theo nhóm và thời điểm hiệu lực |
| Fact hoàn có sản phẩm khớp dòng bán | FK ghép dòng bán + product_key | Không bảo đảm không hoàn quá số lượng |
| Nhiều fact cùng định nghĩa chiều | Kiểm tra mapping danh tính, taxonomy, thời gian | Không thể chỉ so tên cột |
| Truy vấn drill-across không fanout | Tổng hợp riêng từng fact đến khóa chung rồi JOIN | Mỗi CTE phải có tối đa một hàng/khóa JOIN |

## 9. Những tình huống nâng cao trong dimension dùng chung

### 9.1. Thay đổi phân cấp nhưng vẫn cần đối chiếu lịch sử

Giả sử P01 được phân loại như sau:

~~~~text
Trước 2026-11-01:
    product_id=P01, product_key=101, category=VPP

Từ 2026-11-01:
    product_id=P01, product_key=104, category=QUATANG
~~~~

Trong dimension **SCD Type 2**, mỗi phiên bản có **surrogate key riêng**. Một báo cáo lịch sử theo ngành hàng tại thời điểm bán có thể giữ fact tháng 10 ở product_key 101, tháng 11 ở 104.

Nếu một fact khác chỉ trỏ product_id = P01 rồi JOIN DIM_PRODUCT qua product_id, nó có thể khớp **cả hai phiên bản** và nhân đôi dòng. Vì vậy:

- Khi dùng SCD2, fact phải trỏ **phiên bản dimension thích hợp** hoặc có quy tắc tra cứu “as of” được kiểm chứng.
- Nếu muốn phân loại **theo trạng thái hiện tại**, có thể dùng đường mapping ra phiên bản hiện hành hoặc một thuộc tính/hệ thống chiều hiện tại riêng; không vô tình JOIN mọi phiên bản rồi cộng.
- Hai fact phải đồng thuận về **khoảng thời gian và sự kiện nào chọn phiên bản** nếu muốn drill-across theo lịch sử.

Với cùng nguồn thời gian, một phân cấp có thể **strict ở mỗi thời điểm** nhưng thay đổi giữa các thời điểm. Nếu kiểm tra toàn bộ phiên bản bằng cách GROUP BY product_id HAVING COUNT(DISTINCT category_code) > 1, ta sẽ báo động cả những thay đổi lịch sử **hợp lệ**. Kiểm tra đúng phải phân biệt **lịch sử hợp lệ** với **hai phân loại mâu thuẫn đang cùng hiệu lực**.

### 9.2. Một dimension đang được dùng chung không nên tự ý sửa định nghĩa

Khi nhóm marketing muốn chuyển ngành hàng của một số SKU, thay đổi taxonomy có thể ảnh hưởng:

- Báo cáo doanh thu theo ngành hàng.
- Báo cáo hoàn trả theo ngành hàng.
- Dashboard tồn kho và vòng quay hàng.
- Chỉ số xu hướng theo kỳ đã công bố.

Cần quyết định **phiên bản taxonomy** và cách xử lý số liệu lịch sử, công bố thay đổi schema/hợp đồng và kiểm thử tác động xuyên các fact. Nếu một nhóm cập nhật DIM_PRODUCT nhưng nhóm còn lại giữ bản sao dimension cũ, chúng không còn conformed ở phần thuộc tính bị ảnh hưởng.

**Conformed dimension là một cam kết quản trị và tiến hóa dữ liệu**, không chỉ là bảng được dùng nhiều lần trong một truy vấn.

### 9.3. Trường hợp dữ liệu thiếu mã sản phẩm

Với sales_line chứa một sản phẩm chưa tồn tại trong DIM_PRODUCT, có thể:

- Giữ dòng lại đến khi có dimension tương ứng.
- Gán một **unknown product member** có product_key riêng, category_code = UNKNOWN, rồi sửa lại khi có dữ liệu tin cậy.
- Tạm hiển thị nhóm “Chưa phân loại” có nghĩa rõ ràng.

Nếu bắt buộc báo cáo **doanh thu công ty phải đủ** trước khi có sản phẩm, dùng unknown member có thể là lựa chọn thực tế. Nhưng từ góc nhìn phân cấp, nhóm “Unknown” **không phải ngành hàng kinh doanh thật**. Khi tính cơ cấu ngành hàng hoặc KPI chất lượng taxonomy, phải tách rõ doanh thu chưa phân loại.

Không nên dùng một nhãn rỗng cho cả hai trạng thái:

- **Không biết** sản phẩm thuộc ngành nào.
- Sản phẩm **không áp dụng** phân loại ngành hàng.

Chúng có thể dẫn đến hành động nghiệp vụ và quy tắc báo cáo khác nhau.

### 9.4. Cùng một category_code nhưng khác tenant hoặc thị trường

Trong một hệ thống nhiều tenant, mã ngành hàng **GD** ở tenant A có thể mang ý nghĩa khác tenant B. Cần quyết định dimension conformed trên phạm vi:

~~~~text
product_business_key = (tenant_id, product_id)
category_business_key = (tenant_id, category_code)
~~~~

Một mô hình có thể dùng surrogate key toàn hệ thống cho các thành viên này, nhưng mapping từ business key vẫn phải bao gồm tenant. Nếu bỏ tenant trong JOIN, báo cáo có thể gán doanh thu cho ngành hàng của khách hàng hoặc công ty khác.

Ngoài ra, phép roll-up doanh thu xuyên tenant chỉ có nghĩa nếu đã thống nhất **đồng tiền, định nghĩa doanh thu, chính sách hoàn và khoảng thời gian**. “Đều có cột amount” không có nghĩa hai measure additive với nhau.

### 9.5. Dữ liệu đa tiền tệ

Giả sử một fact bán bằng VND, fact hoàn bằng USD. Dù hai fact cùng DIM_PRODUCT và DIM_DATE, không được trực tiếp tính:

\[
SUM(\text{sales\_amount})-SUM(\text{return\_amount})
\]

nếu các giá trị chưa được quy đổi về cùng một đơn vị tiền theo chính sách được phê duyệt.

Một mô hình có thể:

- Lưu currency_code cùng amount gốc, nhóm theo tiền tệ.
- Lưu thêm amount quy đổi và cột tỷ giá/thời điểm/nguồn tỷ giá.
- Dùng dimension tiền tệ và một mô hình tỷ giá theo thời gian.

Đây là **ràng buộc ngữ nghĩa của measure**, không phải vấn đề chỉ cần thêm FK. Dimension conformed mới giải quyết **các trục phân tích**; còn phép tính giữa các fact vẫn cần **measure tương thích**.

### 9.6. Nhiều bộ phân loại khác nhau nhưng cùng sản phẩm

Nếu marketing muốn phân loại sản phẩm theo hai chiến dịch, có thể xây:

~~~~text
DIM_PRODUCT
DIM_CATEGORY
DIM_MARKETING_COLLECTION
BRIDGE_PRODUCT_COLLECTION
~~~~

Đừng gộp **category_code** và **collection_code** thành một “nhóm” duy nhất, vì category có thể tạo cây strict, còn collection thường nhiều–nhiều. Khi drill-across doanh thu và hoàn trả theo collection:

1. Chọn cùng **phiên bản quan hệ product–collection** cho cả hai fact.
2. Quy định có **phân bổ trọng số** hay không.
3. Nếu có phân bổ, phải áp trọng số ở mức phù hợp trước khi tổng hợp.
4. Không cộng chồng các tổng nhóm được gắn nhãn toàn phần.

### 9.7. Phân cấp có vòng và chu kỳ

Với dimension tổ chức dạng bảng cha–con, một vòng A → B → C → A sẽ khiến roll-up đệ quy không có đường về cấp gốc đúng nghĩa. Tương tự, nếu một đơn vị có hai đường lên cùng một cấp, truy vấn đệ quy có thể đếm hai lần.

Cần kiểm soát:

- **Không có chu kỳ** theo cấu trúc cây/DAG được chấp nhận.
- **Đúng số cha** theo quy tắc strict hoặc non-strict.
- **Tính hợp lệ theo thời gian**, không để hai quan hệ cha cùng hiệu lực nếu mô hình strict.
- **Phạm vi đơn vị/tenant** nếu cùng mã đơn vị xuất hiện ở nhiều hệ thống.

Không nên cho rằng một FK(parent_id) tự chứng minh phân cấp là cây không chu kỳ; FK chỉ bảo đảm **cha tồn tại** nếu parent_id có giá trị.

## 10. Thêm fact snapshot: dimension dùng chung không làm measure cộng được qua thời gian

Giả sử đội kho muốn báo cáo **tồn kho cuối ngày theo sản phẩm và kho**. Đây là một fact thứ ba có grain khác hai fact bán và hoàn:

> Mỗi hàng FACT_INVENTORY_DAILY biểu diễn tồn kho cuối ngày của một sản phẩm tại một kho, được xác định bởi **(date_key, product_key, warehouse_key)**.

### 10.1. Ví dụ schema và dữ liệu tồn kho

Đoạn SQL tiếp tục trên cơ sở dữ liệu thử đã tạo ở mục 7:

~~~~sql
CREATE TABLE dim_warehouse (
    warehouse_key BIGINT PRIMARY KEY,
    warehouse_code VARCHAR(30) NOT NULL UNIQUE,
    warehouse_name VARCHAR(150) NOT NULL
);

CREATE TABLE fact_inventory_daily (
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dim_warehouse(warehouse_key),
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    PRIMARY KEY (date_key, product_key, warehouse_key)
);

INSERT INTO dim_warehouse
    (warehouse_key, warehouse_code, warehouse_name)
VALUES (21, 'WH-HN', 'Kho Hà Nội');

INSERT INTO fact_inventory_daily
    (date_key, product_key, warehouse_key, on_hand_qty)
VALUES
    (20261001, 101, 21, 200),
    (20261002, 101, 21, 180);
~~~~

FACT_INVENTORY_DAILY dùng lại **DIM_DATE và DIM_PRODUCT**, nhưng bổ sung **DIM_WAREHOUSE**; không ép warehouse_key thành store_key. Một kho và một cửa hàng có thể liên quan về logistics mà **không phải cùng một loại địa điểm phân tích**.

### 10.2. Tại sao SUM(200 + 180) sai?

Kho có:

- 200 đơn vị sản phẩm P01 **cuối ngày 01/10**.
- 180 đơn vị sản phẩm P01 **cuối ngày 02/10**.

Hai con số là **hai ảnh chụp tại hai thời điểm** của cùng tồn kho. SUM bằng 380 không phải tồn kho cuối kỳ. Tùy câu hỏi:

- **Tồn kho cuối kỳ** ở 02/10 là **180**.
- **Trung bình số dư của hai snapshot** là **190**, nếu chỉ số trung bình trên hai snapshot có ý nghĩa và được chấp thuận.
- **Chênh lệch cuối kỳ so với đầu kỳ** là -20.

Tồn kho là measure **semi-additive theo thời gian**. Nó có thể được cộng **theo kho** hoặc **theo sản phẩm** tại **cùng một thời điểm**, nếu đơn vị đo và cách tránh trùng tồn kho phù hợp, nhưng không được cộng mọi ngày như doanh thu bán.

SQL báo cáo tồn cuối ngày 02/10:

~~~~sql
SELECT
    d.full_date,
    p.product_id,
    SUM(i.on_hand_qty) AS on_hand_end_of_day
FROM fact_inventory_daily AS i
JOIN dim_date AS d ON d.date_key = i.date_key
JOIN dim_product AS p ON p.product_key = i.product_key
WHERE d.full_date = DATE '2026-10-02'
GROUP BY d.full_date, p.product_id
ORDER BY p.product_id;
-- P01: 180 đơn vị tại kho WH-HN.
~~~~

### 10.3. So sánh tốc độ bán và tồn kho

Nếu muốn tính “tỷ lệ bán trên tồn kho” hoặc “ngày tồn kho”, không thể chỉ JOIN ba fact qua product_key và SUM mọi measure:

- Bán hàng là **dòng sự kiện** trong một khoảng thời gian.
- Hoàn trả là **dòng sự kiện** trong một khoảng thời gian.
- Tồn kho là **ảnh chụp** tại một mốc thời gian.

Phải thống nhất:

1. **Khoảng đo doanh số**, ví dụ cả tháng 10.
2. **Mốc tồn kho** (cuối tháng, đầu tháng hoặc bình quân các snapshot).
3. **Đơn vị đo** có tương thích và đã được chuyển đổi nếu cần chưa.
4. **Cấp phân tích chung**: SKU, nhóm hay ngành hàng; có cần phân biệt kho với cửa hàng không?
5. **Công thức tỷ lệ và điều kiện mẫu số bằng 0**.

Sau đó tổng hợp từng fact về cấp thích hợp trước khi tính tỷ lệ. **Cùng DIM_PRODUCT** giúp nhóm đúng theo sản phẩm/ngành hàng, nhưng không thay thế quy tắc đo lường.

## 11. Checklist thiết kế phân cấp và conformed dimension

Trước khi công bố một dimension dùng chung cho nhiều fact, thực hiện:

1. **Chốt câu hỏi nghiệp vụ.** Doanh thu, hoàn trả và tồn kho cần phân tích theo cấp nào? Các báo cáo có cùng thời gian và phạm vi không?
2. **Định nghĩa grain của từng fact.** Bán dòng, hoàn sự kiện, tồn kho snapshot; không mặc định các fact cùng cấp chi tiết.
3. **Liệt kê các dimension conformed ứng viên.** Ngày, sản phẩm, khách, địa điểm; xác định chiều nào thật sự dùng chung và chiều nào chỉ trùng tên.
4. **Định nghĩa business key và surrogate key.** Bao gồm tenant/source/phiên bản khi cần; tránh JOIN bằng nhãn hiển thị.
5. **Vẽ từng đường phân cấp.** SKU → nhóm → ngành; ngày → tháng → năm; phân biệt các phân cấp thay thế.
6. **Đánh giá strict/completeness/ragged.** Mỗi thành viên có bao nhiêu cha? Có được thiếu nhóm? Có bỏ cấp không?
7. **Đánh giá measure.** SUM, DISTINCT, tồn kho cuối kỳ và tỷ lệ có được tính lại từ đúng thành phần không?
8. **Chọn biểu diễn quan hệ.** Flat dimension, snowflake, parent–child hoặc bridge với trọng số theo đúng nghiệp vụ.
9. **Chốt chính sách lịch sử.** Dùng phân loại hiện tại hay tại thời điểm sự kiện? Các fact gắn phiên bản dimension bằng quy tắc nào?
10. **Lập bus matrix.** Ghi rõ vai trò của cùng DIM_DATE và sự khác nhau giữa DIM_STORE, DIM_WAREHOUSE.
11. **Thiết kế truy vấn drill-across.** Chọn cấp kết quả chung; tổng hợp từng fact trước khi JOIN; giữ những nhóm chỉ xuất hiện ở một phía.
12. **Kiểm tra chất lượng.** Không mồ côi, không phân cấp mâu thuẫn, không chồng lấn phiên bản sai, đối soát tổng và kiểm tra trọng số bridge.
13. **Thử phản ví dụ.** Hai fact cùng sản phẩm có nhiều dòng; một SKU thuộc hai bộ sưu tập; sản phẩm chưa phân loại; SCD có nhiều phiên bản; tuần băng qua tháng.
14. **Phân công chủ sở hữu dimension.** Ai duyệt thay đổi taxonomy, làm mới bản sao conformed và cảnh báo báo cáo bị ảnh hưởng?
15. **Chỉ sau đó tối ưu vật lý.** Xem chỉ mục, partition, pre-aggregation và cache theo truy vấn thực tế; không đổi ngữ nghĩa để né một JOIN.

### Tài liệu bàn giao tối thiểu

| Đầu ra | Tối thiểu phải có |
| --- | --- |
| **Dimension specification** | Thành viên, khóa, các thuộc tính, phạm vi, cách xử lý Unknown, lịch sử |
| **Hierarchy specification** | Tên/cấp, strict/completeness, quy tắc bỏ cấp/nhiều cha, thời gian |
| **Bus matrix** | Danh sách quy trình/fact và chiều dùng chung |
| **Metric contract** | Công thức, đơn vị, thời gian, điều kiện cộng và đối soát |
| **Drill-across contract** | Cấp kết quả chung, khóa JOIN kết quả, chính sách xử lý nhóm thiếu |
| **Quality tests** | Quy tắc duy nhất, conformance, chồng lấn, bridge weights, roll-up |
| **Versioning/governance** | Chủ sở hữu taxonomy, thời điểm đổi, chính sách báo cáo lịch sử |

Tài liệu như vậy đủ làm **hợp đồng thiết kế** cho các nhóm ETL/ELT, BI, data governance và vận hành. Việc hiện thực job đồng bộ dimension, nạp fact, backfill SCD hoặc tự động chạy kiểm tra là phạm vi triển khai tiếp theo; các việc ấy không làm thay đổi định nghĩa đúng của mô hình.

## 12. Bài tập thực hành có đáp án

### Bài 1 — Roll-up theo nhóm và ngành hàng

Trong tháng 10, P01 có doanh thu 280.000 VND và thuộc nhóm Giấy, P02 có doanh thu 90.000 VND và thuộc nhóm Bút. Cả Giấy và Bút đều thuộc ngành hàng Văn phòng phẩm. Phân cấp strict và complete; doanh thu additive.

**Câu hỏi:** Doanh thu theo hai nhóm và theo ngành hàng là bao nhiêu?

**Đáp án:** Nhóm Giấy = **280.000**, nhóm Bút = **90.000**; ngành hàng Văn phòng phẩm = **370.000 VND**. Hai nhóm không chồng lấn và bao phủ các dòng đang xét, nên tổng ngành bằng tổng của hai nhóm. Nếu một sản phẩm thuộc cả hai nhóm, kết luận cộng thẳng sẽ không còn an toàn.

### Bài 2 — Phân cấp strict nhưng thiếu bao phủ

Một fact có tổng doanh thu 380.000 VND. Trong đó 370.000 VND đã phân loại được theo ngành, còn 10.000 VND đến từ sản phẩm P99 chưa có ngành hàng.

**Câu hỏi:** Nếu chỉ dùng INNER JOIN vào danh mục đã có ngành, báo cáo có sai không? Có những phương án nào?

**Đáp án:** Báo cáo theo ngành chỉ cộng được **370.000**, bỏ mất 10.000; nếu được công bố như **tổng toàn bộ công ty** thì sai. Có thể dùng nhóm **Chưa phân loại**, hoặc tạm giữ dòng tới khi taxonomy được bổ sung, hoặc áp một quy tắc xử lý đã chốt. Không được im lặng đổi mục tiêu thành “doanh thu đã phân loại” mà vẫn gắn nhãn tổng công ty.

### Bài 3 — Phân cấp nhiều–nhiều và phân bổ

Sản phẩm P01 bán được 100.000 VND, xuất hiện trong hai bộ sưu tập A và B. Quy tắc phân bổ là A = 0,7 và B = 0,3.

**Câu hỏi:** Nếu gắn toàn bộ tiền cho cả hai bộ sưu tập, tổng bao nhiêu? Nếu phân bổ, kết quả thế nào?

**Đáp án:** Gắn nhãn toàn bộ sẽ có A = 100.000 và B = 100.000, tổng **200.000**, không thể xem là doanh thu toàn công ty. Phân bổ theo trọng số cho A = **70.000**, B = **30.000**, tổng **100.000**. Phải kiểm tra tổng trọng số theo đúng sản phẩm, phạm vi và thời gian bằng 1.

### Bài 4 — Bus matrix của ba fact

Có FACT_SALES_LINE, FACT_RETURN_LINE và FACT_INVENTORY_DAILY. Ngày và sản phẩm có mặt ở cả ba fact. Bán và hoàn trả có cửa hàng; tồn kho có kho.

**Câu hỏi:** Dimension nào nên là ứng viên dùng chung? Có nên coi cửa hàng và kho là một chiều chỉ vì đều là địa điểm?

**Đáp án:** DIM_DATE và DIM_PRODUCT là **conformed dimension ứng viên** cho cả ba. DIM_STORE có thể dùng chung giữa bán/hoàn nếu vai trò và định nghĩa tương thích; DIM_WAREHOUSE riêng cho tồn kho. Không tự đồng nhất store_key và warehouse_key: một cửa hàng có thể nhận hàng từ nhiều kho và một kho phục vụ nhiều cửa hàng.

### Bài 5 — Cùng tên nhưng chưa conformed

Sales có P01 → category_code VPP; Returns có P01 → category_code GIFT, vì Returns dùng phân loại marketing. Hai bảng đều có cột category_code.

**Câu hỏi:** Có thể GROUP BY category_code rồi FULL JOIN hai báo cáo không?

**Đáp án:** Chưa thể coi hai cột là cùng dimension ở cấp ngành hàng. Phải thống nhất taxonomy hoặc xác định **mapping công khai sang cấp chung** có nghĩa nghiệp vụ phù hợp. JOIN trực tiếp theo category_code có thể tách hoặc gộp sai số liệu. **Trùng tên thuộc tính không đồng nghĩa conformed**.

### Bài 6 — Drill-across doanh thu và hoàn trả

Dữ liệu mẫu:

- Tháng 10, Văn phòng phẩm: bán 370.000 VND, hoàn 180.000 VND.
- Tháng 11, Văn phòng phẩm: không có bán mới, hoàn 30.000 VND.
- Tháng 11, Gia dụng: bán 80.000 VND, không có hoàn.

**Câu hỏi:** Tính bán trừ hoàn theo từng tháng/ngành và tổng cả tập. Tại sao tháng 11 có số âm?

**Đáp án:** Tháng 10 VPP = **190.000**; tháng 11 VPP = **-30.000**; tháng 11 Gia dụng = **80.000**. Tổng = **240.000 VND**. Dòng âm xuất hiện vì báo cáo dùng **ngày phát sinh hoàn**, nên tháng 11 có hoàn của các giao dịch bán từ trước. Nó không chứng minh dữ liệu sai.

### Bài 7 — JOIN hai fact chi tiết làm sai số

Trong tháng 10, P01 có hai dòng bán 180.000 và 100.000, hai dòng hoàn 90.000 và 90.000. Người lập trình JOIN trực tiếp hai fact theo product_key rồi SUM cả hai measure.

**Câu hỏi:** Có bao nhiêu dòng sau JOIN? SUM bị sai thế nào?

**Đáp án:** Có **4 dòng** (2 × 2). Tổng bán bị thành **560.000** thay vì 280.000; tổng hoàn bị thành **360.000** thay vì 180.000. Phải tổng hợp riêng sales và returns đến cấp **P01 + tháng** (hoặc cấp chung cần báo cáo), sau đó JOIN hai kết quả.

### Bài 8 — SUM(DISTINCT) có chữa fanout được không?

Hai dòng bán khác nhau của một sản phẩm đều có net_amount = 90.000 VND.

**Câu hỏi:** Nếu dùng SUM(DISTINCT net_amount), kết quả là bao nhiêu? Có đúng không?

**Đáp án:** SUM(DISTINCT) trả **90.000**, trong khi tổng bán hợp lệ là **180.000**. DISTINCT loại **giá trị measure trùng**, không phân biệt **hai sự kiện hợp lệ**. Sửa fanout bằng grain và phép JOIN đúng, không bằng DISTINCT trên tiền.

### Bài 9 — Role-playing DIM_DATE

Một đơn đặt ngày 01/10, giao cho vận chuyển ngày 02/10, khách nhận ngày 05/10. Ba cột order_date_key, ship_date_key, delivery_date_key đều trỏ DIM_DATE.

**Câu hỏi:** Báo cáo “đơn theo ngày đặt” phải dùng khóa nào? Vì sao không thay bằng delivery_date_key?

**Đáp án:** Dùng **order_date_key**. DIM_DATE là một bảng dùng lại, nhưng mỗi FK có **vai trò nghiệp vụ riêng**. Thay sang delivery_date_key sẽ tạo báo cáo theo **ngày nhận**, không phải ngày đặt, dù kỹ thuật JOIN đều hợp lệ.

### Bài 10 — Thời gian của dimension SCD2

P01 thuộc ngành VPP đến hết 31/10; từ 01/11 thuộc ngành Quà tặng. Dòng bán P01 ngày 01/10 sau đó được hoàn vào 03/11.

**Câu hỏi:** Fact hoàn nên trỏ phiên bản VPP hay Quà tặng?

**Đáp án:** **Phụ thuộc định nghĩa báo cáo**. Nếu hỏi “hoàn trả được phát sinh trong ngành hàng tại thời điểm hoàn”, có thể dùng phiên bản Quà tặng. Nếu hỏi “hoàn trả gắn với ngành hàng của giao dịch bán gốc”, cần dùng phiên bản VPP của ngày bán. Hai cách có thể đều hợp lệ; phải ghi rõ chính sách role/time conformance để tránh so sánh sai.

### Bài 11 — Type 2 và JOIN theo business key

DIM_PRODUCT có hai hàng cho product_id P01 với product_key 101 và 104 do SCD2. FACT_SALES_LINE lưu product_id P01 nhưng người lập trình JOIN DIM_PRODUCT chỉ bằng product_id.

**Câu hỏi:** Điều gì xảy ra? Cách sửa?

**Đáp án:** Một dòng bán P01 có thể JOIN thành **hai dòng**, khiến measure bị nhân đôi. Fact nên lưu **surrogate key phiên bản được chọn đúng thời điểm**, hoặc áp tra cứu khoảng hiệu lực có quy tắc rõ. Không JOIN tất cả phiên bản theo business key mà không lọc thời gian/phiên bản.

### Bài 12 — Tồn kho không additive theo thời gian

P01 tại kho W1 có tồn kho cuối ngày 01/10 = 200 và cuối ngày 02/10 = 180.

**Câu hỏi:** Tồn kho cuối ngày 02/10 là bao nhiêu? Có thể báo cáo tồn kho “hai ngày” bằng SUM = 380 không?

**Đáp án:** Tồn kho cuối ngày 02/10 là **180**. SUM = 380 không phải một số dư tồn kho có ý nghĩa. Có thể tính trung bình snapshot = **190** nếu KPI thực sự là tồn kho bình quân hai snapshot; phải phân biệt **measure semi-additive** với doanh thu cộng được qua thời gian.

### Bài 13 — Tuần ISO và tháng dương lịch

Một tuần ISO bắt đầu cuối tháng 9 và kết thúc đầu tháng 10. Người thiết kế đề xuất đường Ngày → Tuần ISO → Tháng dương lịch.

**Câu hỏi:** Đây có phải đường phân cấp strict tự nhiên không?

**Đáp án:** Không. Một tuần ISO có thể **giao với hai tháng**, nên Tuần → Tháng không tự là quan hệ nhiều–một duy nhất. Cần một quy tắc gán tuần về tháng (theo ngày bắt đầu/cuối/đa số ngày), hoặc thực hiện tổng hợp từ **ngày** lên tháng và lên tuần theo **hai phân cấp riêng**.

### Bài 14 — Mã ngành hàng có phạm vi tenant

Tenant A và tenant B đều dùng category_code = GD nhưng ý nghĩa và nhãn khác nhau.

**Câu hỏi:** Có thể JOIN hai mart chỉ theo GD không? Thiết kế khóa nào phù hợp?

**Đáp án:** Không. Cần định nghĩa khóa ngành hàng theo phạm vi **(tenant_id, category_code)** hoặc một surrogate key toàn hệ thống có mapping rõ ràng. Nếu muốn phân tích xuyên tenant, còn cần chính sách harmonization: hai nhóm có thực sự cùng nghĩa để gộp không?

### Bài 15 — SUM sau bảng cầu

Một sản phẩm được phân bổ vào ba nhóm với trọng số 0,4; 0,4; 0,3.

**Câu hỏi:** Dù mỗi trọng số đều nằm trong [0,1], phép phân bổ có bảo toàn tổng không?

**Đáp án:** **Không.** Tổng trọng số bằng **1,1** nên doanh thu 100.000 sẽ thành **110.000 VND** sau phân bổ. CHECK từng trọng số từ 0 tới 1 không đủ; cần kiểm tra tổng trọng số **bằng 1 cho từng sản phẩm và phạm vi thời gian áp dụng**.

### Bài 16 — DISTINCT khách hàng có cộng được qua nhóm sản phẩm?

Một khách C01 mua một sản phẩm ngành VPP và một sản phẩm ngành GD. Mỗi ngành có một khách DISTINCT.

**Câu hỏi:** Tổng số khách toàn công ty có phải 1 + 1 = 2 không?

**Đáp án:** Không, tổng khách DISTINCT là **1**. Cùng một khách xuất hiện ở hai ngành nên số khách phân biệt là measure **không additive qua ngành hàng**. Phải tính COUNT(DISTINCT customer_id) trên tập giao dịch ở cấp toàn công ty hoặc dùng cơ chế distinct phù hợp với grain báo cáo.

### Bài 17 — Kiểm tra conformance ở cấp danh mục

Hai data mart độc lập có các nhóm ngành giống nhau. Mart A và B đều báo VPP, GD, nhưng product_key ở A = 101 là P01, còn product_key ở B = 101 là P99.

**Câu hỏi:** Có thể JOIN trực tiếp product_key không? Nếu muốn so sánh ở cấp ngành, cần gì?

**Đáp án:** Không thể JOIN product_key của hai mart nếu các surrogate key được cấp độc lập. Có thể so sánh ở cấp **category_code** sau khi chứng minh nó có cùng nghĩa/phạm vi/phiên bản giữa hai mart. Nếu muốn so sánh cấp sản phẩm, cần mapping danh tính sản phẩm đáng tin và kiểm chứng.

### Bài 18 — Thiết kế kiểm thử cho một dimension dùng chung

Một dự án đã tạo DIM_PRODUCT, FACT_SALES_LINE và FACT_RETURN_LINE. Người phụ trách nói “vì cả hai fact cùng có product_key nên đã bảo đảm so sánh đúng”.

**Câu hỏi:** Nêu ít nhất bốn điều phải kiểm tra trước khi chấp nhận kết luận.

**Đáp án tham khảo:**

1. Hai FK có thật sự trỏ **cùng bộ định danh của DIM_PRODUCT** hoặc có mapping conformed được kiểm chứng không?
2. Mỗi product_key có đúng một **đường phân cấp** ở cấp báo cáo và phạm vi/thời điểm đang xét không?
3. Cả hai fact có dùng **chính sách phân loại lịch sử** tương thích với KPI cần so sánh không?
4. Đã kiểm tra **measure và tiền tệ** tương thích chưa?
5. Truy vấn có **tổng hợp riêng mỗi fact** trước khi JOIN, tránh fanout không?
6. Có thử **missing dimension, nhiều phiên bản, nhiều–nhiều và đối soát tổng** chưa?

Chỉ có cùng tên khóa là điều kiện kỹ thuật ban đầu, không đủ để bảo đảm ngữ nghĩa phân tích.

## 13. Tổng kết

| Chủ đề | Quy tắc trọng tâm |
| --- | --- |
| **Phân cấp** | Đường từ thành viên chi tiết đến cấp tổng hợp; cần xác định quy tắc thành viên thuộc cấp nào |
| **Roll-up / drill-down** | Đổi cấp tổng hợp; phải tôn trọng grain và tính chất measure |
| **Strict hierarchy** | Thành viên cấp dưới có tối đa một cha trong cùng phạm vi/thời điểm |
| **Complete hierarchy** | Mọi thành viên cần báo cáo có đường lên cấp phù hợp |
| **Non-strict hierarchy** | Nhiều cha; muốn bảo toàn tổng có thể phải phân bổ bằng bridge weights |
| **Ragged hierarchy** | Đường phân cấp có cấp bị bỏ qua/không cân bằng; cần quy tắc hiển thị và tổng hợp |
| **Summarizability** | Đơn trị, đầy đủ, measure tương thích và JOIN không fanout |
| **Flat dimension** | Nhiều cấp phân cấp trong một bảng để truy vấn tiện; cần kiểm soát phụ thuộc và tính nhất quán |
| **Snowflake** | Tách các cấp thành bảng có FK; thuận quản trị phân cấp nhưng thêm JOIN |
| **Parent–child** | Linh hoạt cho cây không cân bằng; phải kiểm soát chu kỳ, thời gian và số cha |
| **Conformed dimension** | Cùng định nghĩa danh tính, giá trị, phân cấp, lịch sử và phạm vi dùng được xuyên fact |
| **Bus matrix** | Ma trận quy trình/fact × dimension giúp nhận diện chiều dùng chung và vai trò khác nhau |
| **Role-playing dimension** | Một dimension được dùng nhiều lần theo các vai trò FK khác nhau, ví dụ ngày bán/ngày hoàn |
| **SCD2** | Fact cần gắn đúng phiên bản dimension và đúng ý nghĩa thời điểm |
| **Drill-across** | Tổng hợp riêng mỗi fact về cùng cấp conformed rồi JOIN kết quả |
| **Fact-to-fact fanout** | JOIN fact chi tiết qua khóa chiều có thể nhân số dòng và đo lường sai |
| **Semi-additive** | Tồn kho cuối ngày không được SUM qua thời gian như doanh thu |
| **Kiểm chứng** | Soát nhất quán taxonomy, khóa, phiên bản, weight, đối soát tổng và phản ví dụ fanout |

**Kết luận:** Phân cấp trong bảng chiều biến những danh mục, thời gian và tổ chức thành các trục **roll-up/drill-down có ý nghĩa**, nhưng chỉ có thể tổng hợp chính xác khi quan hệ thành viên phù hợp, bao phủ dữ liệu và measure được phép cộng. **Conformed dimension** cho phép nhiều fact chia sẻ cùng ngữ nghĩa phân tích dù grain và thời điểm sự kiện của chúng khác nhau. Muốn so sánh bán hàng, hoàn trả và tồn kho, hãy xác định **khóa, phân cấp, vai trò thời gian, chính sách lịch sử và cấp kết quả chung**, rồi **tổng hợp từng fact trước khi nối**. Đây là nền tảng để mô hình phân tích có số liệu nhất quán, dễ giải thích và có thể kiểm chứng khi doanh nghiệp thay đổi.
