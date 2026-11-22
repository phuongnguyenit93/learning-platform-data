# Chuẩn hóa phạm vi trước khi so sánh các thành phần

Hai module đều có báo cáo “độ phức tạp trung bình 12”, nhưng một báo cáo chỉ tính mã Java production viết tay, còn báo cáo kia gồm cả test và code được sinh. Một service có 20 lỗi, service khác có 5 lỗi, nhưng số request mà chúng phục vụ chênh nhau hàng trăm lần. Nếu xếp hạng ngay từ các con số đó, nhóm phát triển có thể ưu tiên sai nơi cần cải thiện.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chỉ số chất lượng là một phần bằng chứng giúp xem mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Chỉ số chất lượng**, trước khi so sánh hai thành phần, cần bảo đảm chúng được đo **cùng định nghĩa, phạm vi, đơn vị, khoảng thời gian và điều kiện liên quan**.

Đó là mục tiêu của **chuẩn hóa phạm vi (scope normalization)**: làm rõ và căn chỉnh những gì được đưa vào phép đo, thay vì lấy mọi con số sẵn có đặt cạnh nhau. Chuẩn hóa đúng giúp kết quả có ý nghĩa; chuẩn hóa sai có thể làm một bảng số liệu trông chuyên nghiệp nhưng dẫn tới kết luận thiếu căn cứ.

## 1. Chuẩn hóa phạm vi không đơn giản là chia cho số dòng

Khi nói “chuẩn hóa metric”, người ta có thể đang đề cập nhiều việc khác nhau:

| Hoạt động | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Chuẩn hóa phạm vi** | Chính xác những gì được đo và những gì bị loại ra? | Chỉ mã Java production viết tay, không gồm test và generated code. |
| **Chuẩn hóa định nghĩa** | Công cụ tính “dòng mã”, “nhánh” hoặc “lỗi” theo cùng quy tắc không? | Cả hai dùng NCLOC cùng công cụ và cấu hình. |
| **Chuẩn hóa đơn vị/mẫu số** | Chỉ số là tổng, tỷ lệ, số trên mỗi KLOC hay số trên mỗi request? | Lỗi trên 1.000 NCLOC hoặc lỗi trên 10.000 request. |
| **Chuẩn hóa thời gian** | Hai thành phần được đo ở cùng kỳ và trạng thái triển khai tương ứng không? | Cùng 90 ngày, cùng chính sách ghi nhận lỗi. |
| **Phân nhóm đối tượng so sánh** | Chúng có nhiệm vụ và đặc tính đủ gần để đặt cạnh nhau không? | So sánh các API cùng loại thay vì thư viện parser với service thanh toán. |
| **Điều chỉnh theo bối cảnh** | Có khác biệt tải, môi trường, độ mới, độ rủi ro cần diễn giải riêng không? | Service xử lý ít request nhưng mỗi request có giá trị tài chính cao. |

Ví dụ **chia số lỗi cho LOC** chỉ xử lý một phần của vấn đề mẫu số. Nó không làm biến mất sự khác biệt về thời gian vận hành, mức tải, cách phân loại lỗi hoặc mức độ nghiêm trọng.

**Quy tắc nền tảng:** Trước khi tính tỷ lệ, phải biết **tử số và mẫu số có cùng phạm vi hay không**.

## 2. Mỗi chỉ số cần có hợp đồng đo lường

Một phép đo đáng tin nên được mô tả như một **hợp đồng đo lường (measurement contract)**. Hợp đồng này chỉ rõ cách người khác có thể tái tạo cùng kết quả.

Các trường tối thiểu:

1. **Tên metric:** Ví dụ NCLOC Java production viết tay, branch coverage hoặc tỷ lệ request lỗi.
2. **Định nghĩa chính xác:** “Dòng” hay “lỗi” được nhận diện theo quy tắc nào?
3. **Đơn vị quan sát:** File, method, class, module, service, request, giao dịch hay phiên triển khai?
4. **Phạm vi bao gồm:** Đường dẫn, ngôn ngữ, source set, runtime hoặc thành phần được tính.
5. **Phạm vi loại trừ:** Test, generated code, dependency bên thứ ba, migration, dữ liệu fixture hay đoạn mã không thuộc trách nhiệm cần đánh giá.
6. **Khoảng thời gian hoặc revision:** Commit, bản phát hành và thời gian quan sát.
7. **Công cụ và cấu hình:** Công cụ đếm, phiên bản, filter, profile kiểm thử, cách tổng hợp.
8. **Mẫu số và quy tắc xử lý thiếu dữ liệu:** Chia cho bao nhiêu? Nếu mẫu số bằng 0 thì ghi **N/A**, không tự ghi 0%.
9. **Người chịu trách nhiệm và mục đích sử dụng:** Ai xác nhận dữ liệu và kết luận nào được phép rút ra?

Chỉ khi hai phép đo có hợp đồng tương thích, chúng ta mới có cơ sở so sánh trực tiếp.

### Ví dụ một định nghĩa có thể kiểm chứng

~~~yaml
metric: java_handwritten_production_ncloc
unit: lines
scope:
  include:
    - Java source thuộc production do nhóm duy trì
  exclude:
    - Java test source
    - generated Java source
    - vendored/dependency source
definition: dòng không trống và không chỉ chứa comment, theo công cụ đã chọn
revision: commit được ghi nhận trong báo cáo
tool: tên công cụ và phiên bản thực tế
ownership: nhóm sở hữu thành phần
~~~

Đây là **ví dụ mô tả hợp đồng**, không phải cấu hình thực thi sẵn cho một công cụ cụ thể. Khi áp dụng, cần thay các trường bằng đường dẫn, filter và phiên bản thật, tránh ghi các giá trị ước lượng như thể đã đo.

## 3. Xác định ranh giới thành phần trước khi đếm

“Module A” và “Module B” có thể được định nghĩa khác nhau:

- Một module build có thể chứa cả production, test, resource và code sinh.
- Một service triển khai có thể gồm nhiều module build.
- Một bounded context nghiệp vụ có thể trải qua nhiều repository.
- Một library có thể được dùng bởi nhiều service nhưng chỉ có một nhóm sở hữu.
- Một file lớn có thể được chuyển sang module khác mà hành vi sản phẩm không đổi.

Vì vậy, cần chọn **đơn vị sở hữu và đơn vị đo** phù hợp với câu hỏi.

| Câu hỏi | Phạm vi gợi ý | Không nên vô tình trộn |
| --- | --- | --- |
| “Module nào cần review về cấu trúc?” | Mã production viết tay thuộc trách nhiệm module. | Test fixture, generated client và thư viện vendor. |
| “Thành phần nào có nhiều lỗi vận hành?” | Service hoặc ca sử dụng trong cùng kỳ vận hành. | Lỗi phát hiện ở môi trường khác hoặc sự cố không thuộc thành phần. |
| “Coverage của mã sản phẩm là bao nhiêu?” | Branch/line được công cụ nhận diện trong production target. | Tập code sinh hoặc class ngoài phạm vi test được thay đổi tùy ý. |
| “PR nào khó review hơn?” | Diff có ý nghĩa theo từng loại thay đổi. | Dòng format-only trộn với sửa logic mà không phân loại. |
| “Bản phát hành có chậm hơn không?” | Cùng endpoint/workload, môi trường và cách đo latency. | Benchmark trên máy/traffic khác mà không chú thích. |

**Phạm vi không đồng nghĩa với đường dẫn thư mục duy nhất.** Cần xem đường dẫn có thực sự trùng với ranh giới trách nhiệm và vận hành hay không.

## 4. Ví dụ: hai module và cái bẫy của tổng LOC

Giả sử ta quan sát hai module cùng nhóm sản phẩm trong **một kỳ báo cáo giả định**. Các giá trị sau chỉ dùng để học cách phân tích, không phải đo từ một hệ thống đang chạy.

| Loại mã | Module A | Module B |
| --- | ---: | ---: |
| Java production viết tay, NCLOC | 2.400 | 1.800 |
| Java test, NCLOC | 1.100 | 650 |
| Java generated, NCLOC | 800 | 2.300 |
| **Tổng ba nhóm** | **4.300** | **4.750** |

Nếu chỉ nhìn tổng, B có **4.750 dòng**, nhiều hơn A có **4.300 dòng**. Nhưng nếu câu hỏi là “Đâu là khối lượng Java production viết tay cần review và bảo trì?”, A lại lớn hơn B: **2.400 so với 1.800 NCLOC**.

Sự đảo chiều này không phải phép toán phức tạp. Nó xảy ra vì **phạm vi so sánh đã thay đổi**:

- Tổng ba nhóm là một thước đo quy mô nội dung đã chọn.
- Java production viết tay là một phạm vi khác, gắn với trách nhiệm khác.
- Generated code có thể lớn nhưng chủ yếu được thay đổi qua generator hoặc schema.
- Test code có giá trị riêng và không nên bị coi là mã “thừa” vì làm tổng LOC tăng.

**Không phải cứ bỏ test và generated code thì mọi metric đều trở nên đúng.** Nếu mục tiêu là đánh giá công sức bảo trì test hoặc tác động khi nâng generator, hai nhóm đó phải được đo riêng. Quy tắc là **chọn phạm vi theo câu hỏi**, không phải loại trừ cố định để được con số nhỏ.

## 5. Cùng là LOC cũng có thể khác định nghĩa

Một công cụ đếm **physical lines**, công cụ khác đếm **non-comment lines of code (NCLOC)**. Một formatter đổi cách xuống dòng; một tool lại phân loại comment cạnh code theo quy tắc riêng.

Ví dụ Java:

~~~java
// Cùng logic trong hai cách trình bày.
if (accountActive && balance > 0) { process(); }
~~~

~~~java
if (accountActive && balance > 0) {
    process();
}
~~~

Số dòng vật lý khác nhau, nhưng không thể từ đó kết luận đoạn thứ hai có nhiều quy tắc nghiệp vụ hơn.

Đối với so sánh công bằng:

- Chọn **một định nghĩa**: physical LOC, NCLOC, logical statements hoặc metric khác.
- Cố định **công cụ và phiên bản** nếu phép đếm phụ thuộc parser/rule.
- Cố định **cấu hình include/exclude** và cách nhận diện generated source.
- Ghi nhận **formatter migration** vì nó có thể tạo biến động dòng lớn.
- Không gộp số liệu từ hai phép đếm khác nhau chỉ vì cùng dùng chữ “LOC”.

Một biểu đồ LOC trước/sau chỉ có ý nghĩa khi cả hai điểm được tính **cùng tiêu chuẩn** hoặc có chú thích rõ về việc tiêu chuẩn đã đổi.

## 6. Cùng phạm vi mã nhưng khác thời gian vẫn không so sánh được

Giả sử báo cáo defect count của A lấy **90 ngày gần nhất**, của B lấy **12 tháng**. Nếu A có 9 lỗi và B có 7 lỗi, không thể xếp hạng bằng cách đối chiếu trực tiếp.

Cần xác định:

- **Cửa sổ thời gian:** cùng 30, 90 ngày hay cùng chu kỳ phát hành?
- **Điều kiện đưa lỗi vào:** lỗi được phát hiện, xác nhận, tái hiện hoặc đóng trong kỳ?
- **Ngày ghi nhận:** theo thời điểm báo cáo hay thời điểm lỗi được đưa vào production?
- **Thời gian vận hành:** cả hai service có hoạt động cùng kỳ hay một service mới ra mắt?
- **Tải và mức tiếp xúc:** số request, số người dùng hoặc giao dịch khác nhau bao nhiêu?
- **Thay đổi quy trình:** có lúc nhóm bắt đầu ghi nhận thêm lỗi mức độ thấp không?

**Đồng nhất kỳ báo cáo chỉ là điều kiện cần.** Lỗi được tìm thấy trong cùng 90 ngày nhưng ở các thành phần có lượng người dùng, kiểu dữ liệu và mức độ kiểm thử rất khác nhau vẫn không tự động phản ánh “chất lượng tốt hơn”.

### Snapshot và window là hai dạng thời gian khác nhau

**NCLOC tại commit X** là ảnh chụp một trạng thái. **Lỗi trong 90 ngày** là biến cố trong một khoảng thời gian. Khi tạo tỷ lệ lỗi/KLOC, phải chỉ rõ LOC lấy ở **đầu kỳ, cuối kỳ hay trung bình kỳ**, và đánh giá xem kích thước có thay đổi mạnh không.

Nếu giữa kỳ có migration chuyển một nửa mã sang module khác, lấy số lỗi cả kỳ chia cho NCLOC cuối kỳ có thể dẫn tới kết quả gây hiểu nhầm. Khi ấy, báo cáo cần mô tả thay đổi ranh giới và cân nhắc phân tách giai đoạn.

## 7. Chuẩn hóa mẫu số: mật độ lỗi trên KLOC

Tiếp tục dùng dữ liệu minh họa. Giả sử cùng kỳ 90 ngày và cùng cách phân loại **lỗi production được xác nhận và quy cho thành phần**:

| Metric | Module A | Module B |
| --- | ---: | ---: |
| Java production viết tay, NCLOC | 2.400 | 1.800 |
| Lỗi production được xác nhận trong kỳ | 9 | 7 |

Một tỷ lệ thường gặp:

\[
\text{Defects per KLOC}
= \frac{\text{Số lỗi được tính}}{\text{NCLOC sản phẩm}/1000}
\]

Kết quả:

- A: **9 / 2,4 = 3,75 lỗi/KNCLOC**.
- B: **7 / 1,8 ≈ 3,89 lỗi/KNCLOC**.

Tổng lỗi của B ít hơn A (7 so với 9), nhưng mật độ tính theo mẫu số đã chọn hơi cao hơn. Điều này **không chứng minh** B có chất lượng kém hơn: số mẫu ít, khác biệt nhỏ, công sức tìm lỗi, độ phức tạp nghiệp vụ và cách quy lỗi có thể khác nhau.

### Khi nào tỷ lệ này có ích?

Có thể dùng nó như **tín hiệu khám phá** giữa các nhóm mã có vai trò gần nhau, được đo nhất quán, để đặt câu hỏi: “Có module nào có mật độ lỗi cao bất thường và cần xem thêm không?”

### Khi nào tỷ lệ dễ gây sai lệch?

- Mã generated bị loại khỏi mẫu số nhưng lỗi của generated code lại tính vào tử số.
- Lỗi ở một phụ thuộc dùng chung bị tính toàn bộ cho hai module.
- Service B có ít LOC nhưng chịu trách nhiệm nghiệp vụ rủi ro cao.
- Module A có tuổi đời 8 năm và B mới ra mắt, mức tiếp xúc khác nhau.
- LOC giảm do chuyển logic sang thư viện nhưng lỗi vẫn gắn ở module gọi.
- Một thành phần có nhiều lỗi được tìm ra vì được test kỹ hơn, không nhất thiết vì nó tệ hơn.

**Tỷ lệ có mẫu số không tự giải quyết vấn đề chất lượng dữ liệu và khả năng so sánh.**

## 8. Lỗi trên LOC khác lỗi trên lượng sử dụng

Cùng là “error rate” nhưng có thể có nhiều mẫu số:

~~~text
9 lỗi được xác nhận / 2.400 NCLOC
    -> mật độ lỗi theo kích thước mã

25 request lỗi / 5.000 request
    -> 0,5% request lỗi

50 request lỗi / 50.000 request
    -> 0,1% request lỗi
~~~

Hai ví dụ request cho thấy **số lỗi tuyệt đối 50 lớn hơn 25**, nhưng tỷ lệ request lỗi lại thấp hơn khi lượng request khác nhau.

Lưu ý:

- “Lỗi được xác nhận” là **sự cố/defect** được ghi nhận và phân loại.
- “Request lỗi” là **lượt thực thi** không đạt hợp đồng theo định nghĩa metric.
- Một defect có thể gây hàng nghìn request lỗi.
- Một request thất bại có thể là hành vi hợp lệ, ví dụ 403 do thiếu quyền; không nhất thiết là lỗi chất lượng code.

Vì vậy, **không thể thay mẫu số NCLOC bằng request và vẫn giữ nguyên ý nghĩa của metric**. Mỗi metric trả lời một câu hỏi khác.

## 9. Khi tổng hợp tỷ lệ, cần trọng số đúng

Giả sử hai module có số nhánh được công cụ coverage nhận diện:

| Module | Nhánh được bao phủ | Tổng nhánh được tính | Branch coverage |
| --- | ---: | ---: | ---: |
| A | 72 | 90 | **80,00%** |
| B | 35 | 40 | **87,50%** |

Nếu lấy trung bình cộng đơn giản hai phần trăm, ta được:

\[
(80 + 87,5)/2 = 83,75\%
\]

Nhưng nếu câu hỏi là **“bao nhiêu nhánh trong toàn bộ phạm vi A+B được bao phủ?”**, phải dùng tỷ lệ từ **tổng tử số và tổng mẫu số**:

\[
\frac{72+35}{90+40}\times100
=\frac{107}{130}\times100
\approx82,31\%
\]

Số **82,31%** mô tả coverage gộp theo số nhánh. Số **83,75%** là trung bình hai tỷ lệ với giả định mỗi module có trọng số bằng nhau. Hai phép tính trả lời **hai câu hỏi khác nhau**.

**Không được chọn phép tổng hợp chỉ vì nó tạo ra con số đẹp hơn.** Hãy xác định trước bạn muốn biết tỷ lệ của toàn bộ nhánh hay tỷ lệ trung bình giữa các module.

### Đừng cộng tùy ý các metric khác đơn vị

Không có ý nghĩa trực tiếp khi cộng:

~~~text
80% branch coverage
+ 3,75 lỗi/KLOC
+ 25 điểm cognitive complexity
= 108,75 “điểm chất lượng”
~~~

Các chỉ số này có **đơn vị, hướng diễn giải và giới hạn khác nhau**. Nếu tổ chức xây dựng một điểm tổng hợp, phải thiết kế rõ việc chuẩn hóa, trọng số, độ nhạy và mục tiêu sử dụng; không nên coi phép cộng tùy tiện là bằng chứng khách quan.

## 10. Các thành phần khác loại phải được phân nhóm

Ngay cả khi cùng metric và cùng công cụ, **đối tượng không cùng loại** có thể không nên được xếp trực tiếp.

Ví dụ:

| Thành phần | Đặc điểm chính | Vì sao không nên so sánh máy móc? |
| --- | --- | --- |
| **Library xử lý định dạng** | Nhiều phép parse, trường hợp biên và lỗi dữ liệu. | Có thể nhiều nhánh và test phức tạp nhưng không chạy như HTTP service. |
| **REST Controller** | Chủ yếu chuyển HTTP request/response. | Ít logic có thể là do trách nhiệm được tách, không tự chứng minh thiết kế tốt. |
| **Payment Service** | Quy tắc giao dịch, bảo mật và độ tin cậy cao. | Một lỗi nhỏ có thể nghiêm trọng hơn nhiều lỗi giao diện. |
| **Batch Worker** | Xử lý dữ liệu lớn, có retry và checkpoint. | Thông lượng và độ trễ cần đánh giá theo batch, không theo request tương tác. |
| **Generated API Client** | Nhiều dòng do generator quyết định. | LOC cao có thể phản ánh schema lớn, không phải quyết định của lập trình viên. |
| **Test Utility** | Nhiều fixture, assertion và dữ liệu thử. | Loại mã khác production; metric kích thước và chất lượng nên giải thích riêng. |

**Chuẩn hóa phạm vi không biến những thành phần khác bản chất thành tương đương.** Một cách phân tích tốt hơn là chia thành các **cohort** (nhóm so sánh có đặc điểm gần nhau), hoặc báo cáo từng nhóm và nêu bối cảnh.

Ví dụ, có thể so sánh xu hướng NCLOC của hai thư viện Java production viết tay cùng mục đích, sau đó dùng yêu cầu và test để giải thích chênh lệch. Không nên xếp hạng quality của một thư viện parse và một service thanh toán chỉ dựa trên NCLOC hoặc coverage.

## 11. Cần xem phân bố thay vì một trung bình

Giả sử hai module đều có **độ phức tạp trung bình 8 trên mỗi method** theo cùng công cụ. Điều đó chưa cho biết:

- A có nhiều method độ phức tạp 7–9 tương đối đồng đều.
- B có phần lớn method đơn giản và một method rất phức tạp, ảnh hưởng nhiều đường nghiệp vụ.

Một trung bình có thể **che khuất điểm nóng (hotspot)**. Do đó, báo cáo nên kết hợp:

1. Số đối tượng được đo, ví dụ **bao nhiêu method**.
2. Phân bố (median, percentiles, max) khi đủ dữ liệu và cách tổng hợp có ý nghĩa.
3. Danh sách trường hợp ngoại lệ cần xem.
4. Tần suất thay đổi và lỗi thực tế tại những trường hợp đó.
5. Trách nhiệm nghiệp vụ, không chỉ vị trí của chúng trong bảng xếp hạng.

**Một method phức tạp chưa chắc xấu.** Nó có thể thực hiện một thuật toán intrinsically phức tạp, có test và diễn giải rõ. Mục đích của metric là chỉ nơi cần đọc và hỏi thêm, không thay người review kết luận chất lượng.

### Thận trọng với percentiles và tập dữ liệu nhỏ

Nếu module có 4 method, p95 độ phức tạp có thể không hữu ích theo cách diễn giải thống kê thông thường. Nếu module có hàng nghìn method, xem phân bố có thể giúp nhiều hơn chỉ nhìn trung bình.

Khi so sánh p95 latency của hai service, không được **lấy trung bình các p95** rồi gọi đó là p95 của toàn hệ thống. Muốn tính percentile chung, cần phân phối/số liệu thô hoặc cách tổng hợp hỗ trợ phân phối, cùng định nghĩa về request được tính.

## 12. Chuẩn hóa coverage: bộ test và vùng mã phải tương ứng

Coverage nghe có vẻ đơn giản: bao nhiêu dòng hoặc nhánh được test chạy tới? Nhưng để so sánh đúng cần xác định:

- Instrumentation đã áp dụng cho **những class nào**?
- Có tính **generated code** và lớp hỗ trợ không?
- Chỉ chạy **unit test** hay gồm integration test?
- Có chạy cùng build profile và cấu hình feature flag không?
- Các test có cùng phạm vi platform/version không?
- Có method không thể chạy bằng test hiện tại do phụ thuộc ngoài hay không?
- Metric là **line coverage, branch coverage hay instruction coverage**?

Ví dụ, A có 80% branch coverage từ unit+integration test, B có 90% từ unit test nhưng chỉ instrument các package nhỏ nhất. Hai giá trị không so sánh trực tiếp nếu **tập class và cách chạy khác nhau**.

Ngược lại, ép hai nhóm chạy cùng mọi test không phải lúc nào phù hợp. Quan trọng là định nghĩa **hợp đồng đo lường** và trình bày khác biệt; có thể cần báo riêng “unit coverage” và “combined coverage”.

**Coverage cao không chứng minh test oracle đúng.** Test chỉ đi qua nhánh mà không kiểm tra kết quả có thể đạt coverage cao nhưng vẫn bỏ lọt lỗi logic.

## 13. Chuẩn hóa churn và phạm vi thay đổi

**Churn** thường liên quan số dòng thêm/xóa hoặc số lần sửa trong một kỳ. Để so sánh cần biết:

- Có tính dòng di chuyển hoặc đổi tên file không?
- Có tính formatter migration không?
- Có tách test và generated không?
- “Một lần sửa” tính theo commit, PR hay thay đổi thực tế?
- Cửa sổ thời gian có giống nhau không?
- Có bao nhiêu tính năng hoặc yêu cầu được giao trong kỳ?
- Một module có nhiều release hơn module kia không?

Ví dụ giả định:

| Đơn vị | Java production NCLOC | Tổng dòng thêm/xóa được tính trong kỳ |
| --- | ---: | ---: |
| A | 2.400 | 800 |
| B | 1.800 | 300 |

Một tỷ lệ thô:

- A: **800/2.400 ≈ 0,33**.
- B: **300/1.800 ≈ 0,17**.

Đây **không phải tỷ lệ mã khác nhau duy nhất đã thay đổi**, vì một dòng có thể bị sửa nhiều lần và diff có thể đếm thêm/xóa cho cùng một dòng. Nó chỉ là thước đo churn theo định nghĩa đã chốt, cần diễn giải cùng dữ liệu công việc, file di chuyển và giai đoạn phát triển.

A có churn cao hơn có thể do thêm tính năng đúng kế hoạch. Nếu xem churn cao đồng nghĩa “mã kém”, nhóm có thể cố giảm số commit hoặc tránh sửa code cần thiết, làm metric mất giá trị.

## 14. Một ví dụ Java 17 để bảo vệ hợp đồng so sánh

Khi xây dựng báo cáo tự động, nên để dữ liệu kèm **định nghĩa phạm vi**. Ví dụ Java 17 dưới đây minh họa việc từ chối so sánh hai snapshot dùng **kỳ báo cáo hoặc protocol khác nhau**, đồng thời không âm thầm coi mẫu số bằng 0 là tỷ lệ 0%.

Đây là lớp minh họa cho **việc tính toán sau khi đã thu thập dữ liệu**. Nó không tự quét repository, đo coverage hay xác minh chất lượng dữ liệu đầu vào.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class MetricEvidence {
    private MetricEvidence() {
    }

    public record Scope(
            String sourceKind,
            String protocolId,
            String period) {

        public Scope {
            requireNonBlank(sourceKind, "sourceKind");
            requireNonBlank(protocolId, "protocolId");
            requireNonBlank(period, "period");
        }
    }

    public record Snapshot(
            String component,
            Scope scope,
            long productionNcloc,
            long confirmedProductionDefects,
            long coveredBranches,
            long totalBranches) {

        public Snapshot {
            requireNonBlank(component, "component");
            Objects.requireNonNull(scope, "scope");
            if (productionNcloc < 0 || confirmedProductionDefects < 0
                    || coveredBranches < 0 || totalBranches < 0
                    || coveredBranches > totalBranches) {
                throw new IllegalArgumentException(
                        "Invalid metric counts");
            }
        }
    }

    public record Comparison(
            BigDecimal leftDefectsPerKloc,
            BigDecimal rightDefectsPerKloc,
            BigDecimal leftBranchCoveragePercent,
            BigDecimal rightBranchCoveragePercent) {
    }

    public static Comparison compare(Snapshot left, Snapshot right) {
        requireComparable(left, right);

        return new Comparison(
                defectDensity(left),
                defectDensity(right),
                percent(left.coveredBranches(), left.totalBranches()),
                percent(right.coveredBranches(), right.totalBranches()));
    }

    public static BigDecimal combinedBranchCoverage(
            Snapshot left, Snapshot right) {
        requireComparable(left, right);

        long covered = Math.addExact(
                left.coveredBranches(), right.coveredBranches());
        long total = Math.addExact(
                left.totalBranches(), right.totalBranches());
        return percent(covered, total);
    }

    private static void requireComparable(
            Snapshot left, Snapshot right) {
        Objects.requireNonNull(left, "left");
        Objects.requireNonNull(right, "right");

        if (!left.scope().equals(right.scope())) {
            throw new IllegalArgumentException(
                    "Measurement scopes are different");
        }
    }

    private static BigDecimal defectDensity(Snapshot snapshot) {
        if (snapshot.productionNcloc() == 0) {
            throw new IllegalArgumentException(
                    "Defect density denominator is zero");
        }

        return BigDecimal.valueOf(
                snapshot.confirmedProductionDefects())
                .multiply(BigDecimal.valueOf(1_000L))
                .divide(BigDecimal.valueOf(
                        snapshot.productionNcloc()),
                        2, RoundingMode.HALF_UP);
    }

    private static BigDecimal percent(long part, long total) {
        if (total == 0) {
            throw new IllegalArgumentException(
                    "Coverage denominator is zero");
        }

        return BigDecimal.valueOf(part)
                .multiply(BigDecimal.valueOf(100L))
                .divide(BigDecimal.valueOf(total),
                        2, RoundingMode.HALF_UP);
    }

    private static void requireNonBlank(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " must not be blank");
        }
    }
}
~~~

### Vì sao ví dụ cố tình kiểm tra phạm vi?

- **Scope** gắn loại nguồn, phiên bản hợp đồng đo lường và kỳ quan sát với dữ liệu.
- **compare** từ chối khi hai Scope không trùng, thay vì đặt số liệu khác protocol vào cùng bảng kết luận.
- **productionNcloc** là mẫu số của mật độ lỗi; không dùng tổng tất cả file.
- **coveredBranches/totalBranches** là một cặp của metric coverage; không lấy hai phần trăm gộp bằng trung bình cộng.
- **Mẫu số bằng 0** không được ngầm trả 0 vì “không có đối tượng cần đo” khác “0% được bao phủ”.
- **BigDecimal** tránh lỗi biểu diễn thập phân không cần thiết trong kết quả báo cáo, đồng thời xác định cách làm tròn.

**Giới hạn quan trọng:** So sánh chuỗi Scope bằng nhau chỉ kiểm tra metadata được cung cấp. Nó **không chứng minh** hai pipeline thực sự đã tuân thủ cùng protocol. Trong hệ thống thật, protocolId nên tham chiếu tới cấu hình đo có kiểm soát và được lưu kèm bằng chứng thu thập. Một Snapshot có thể được ghi sai phạm vi dù tên trường vẫn đúng.

Các thành phần cần được xác định **đủ tương đồng về nhiệm vụ** ngoài những trường mà lớp ví dụ có thể kiểm tra tự động.

## 15. Kiểm thử JUnit 5 cho phép so sánh và tổng hợp

JUnit 5 có thể kiểm tra những tính toán quan trọng từ bộ số liệu đã nêu:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MetricEvidenceTest {
    private static final MetricEvidence.Scope SCOPE =
            new MetricEvidence.Scope(
                    "JAVA_PRODUCTION_HANDWRITTEN",
                    "METRIC_PROTOCOL_V1",
                    "2026-Q3");

    private static MetricEvidence.Snapshot moduleA() {
        return new MetricEvidence.Snapshot(
                "A", SCOPE, 2_400L, 9L, 72L, 90L);
    }

    private static MetricEvidence.Snapshot moduleB() {
        return new MetricEvidence.Snapshot(
                "B", SCOPE, 1_800L, 7L, 35L, 40L);
    }

    @Test
    void computesDensityAndBranchCoverage() {
        var comparison = MetricEvidence.compare(moduleA(), moduleB());

        assertEquals(new BigDecimal("3.75"),
                comparison.leftDefectsPerKloc());
        assertEquals(new BigDecimal("3.89"),
                comparison.rightDefectsPerKloc());

        assertEquals(new BigDecimal("80.00"),
                comparison.leftBranchCoveragePercent());
        assertEquals(new BigDecimal("87.50"),
                comparison.rightBranchCoveragePercent());
    }

    @Test
    void aggregatesCoveredAndTotalBranchesBeforeDividing() {
        assertEquals(new BigDecimal("82.31"),
                MetricEvidence.combinedBranchCoverage(
                        moduleA(), moduleB()));
    }

    @Test
    void rejectsDifferentReportingPeriods() {
        var otherScope = new MetricEvidence.Scope(
                "JAVA_PRODUCTION_HANDWRITTEN",
                "METRIC_PROTOCOL_V1",
                "2026-Q2");

        var other = new MetricEvidence.Snapshot(
                "C", otherScope, 100L, 1L, 1L, 2L);

        assertThrows(IllegalArgumentException.class,
                () -> MetricEvidence.compare(moduleA(), other));
    }

    @Test
    void rejectsDifferentMeasurementProtocols() {
        var otherScope = new MetricEvidence.Scope(
                "JAVA_PRODUCTION_HANDWRITTEN",
                "METRIC_PROTOCOL_V2",
                "2026-Q3");

        var other = new MetricEvidence.Snapshot(
                "C", otherScope, 100L, 1L, 1L, 2L);

        assertThrows(IllegalArgumentException.class,
                () -> MetricEvidence.compare(moduleA(), other));
    }

    @Test
    void doesNotInventRatioWhenDenominatorIsZero() {
        var empty = new MetricEvidence.Snapshot(
                "Empty", SCOPE, 0L, 0L, 0L, 0L);

        assertThrows(IllegalArgumentException.class,
                () -> MetricEvidence.compare(empty, moduleA()));
    }
}
~~~

Ví dụ này minh họa **kiểm tra phép tính và từ chối dữ liệu không so sánh được**. Để dùng thực tế cần thêm quy tắc xử lý trường hợp không có coverage, kiểm tra nguồn số liệu, audit cấu hình và các ngoại lệ nghiệp vụ; không xem test của lớp tính toán là chứng minh toàn bộ metric pipeline đã chính xác.

## 16. Khi nào phải ghi “không thể so sánh” thay vì cố ra tỷ lệ?

Một báo cáo chất lượng có thể gặp các tình huống:

| Tình huống | Cách trình bày có trách nhiệm |
| --- | --- |
| Module không có dòng production trong phạm vi đã chọn | Ghi **N/A** hoặc không tính mật độ lỗi/KLOC; giải thích mẫu số 0. |
| Một module chỉ có 4 method | Có thể báo số liệu thô và từng method; hạn chế diễn giải percentile phức tạp. |
| Một service mới triển khai được 7 ngày | Ghi thời gian tiếp xúc; không tự so trực tiếp với service đã hoạt động 90 ngày. |
| Hai tool coverage dùng rule khác nhau | Báo riêng hoặc đo lại theo một quy trình thống nhất. |
| Lỗi chưa được phân loại theo component | Ghi dữ liệu thiếu; không phân bổ tùy ý chỉ để có tỷ lệ. |
| Không biết generated code đã được loại trừ hay chưa | Đánh dấu chưa xác minh phạm vi; chưa đưa vào xếp hạng. |
| Hai service có traffic hoặc nghiệp vụ rất khác | Trình bày theo nhóm và bối cảnh; không gắn nhãn tốt/xấu từ một metric. |

**N/A không phải 0.** Một tỷ lệ không thể tính do thiếu mẫu số là trạng thái dữ liệu khác với tỷ lệ thật bằng 0%. Biến N/A thành 0 có thể khiến dashboard báo “không có rủi ro” cho thành phần chưa được đo.

## 17. Xử lý sự kiện đổi cấu trúc hoặc chuyển ownership

Một thành phần có thể bị chia đôi, đổi tên hoặc chuyển một phần mã sang module chung. Nếu không xử lý lịch sử, dashboard có thể báo:

- LOC của A giảm mạnh.
- Churn của module mới tăng bất thường.
- Lỗi của A giảm do cách quy lỗi đổi.
- Coverage tăng vì phần khó kiểm thử đã chuyển ra ngoài phạm vi.

Những thay đổi đó **có thể là biến động của ranh giới đo**, không phải cải thiện thực chất.

Cần ghi chú các mốc như:

1. **Đổi cấu trúc module:** phần mã nào được chuyển và còn thuộc nhóm nào?
2. **Đổi ownership:** ai chịu trách nhiệm đo và xử lý lỗi sau chuyển giao?
3. **Đổi định nghĩa metric:** có cần tính lại chuỗi lịch sử không?
4. **Đổi công cụ hoặc rule:** kết quả trước/sau có còn tương thích không?
5. **Tách service/runtime:** lưu lượng và lỗi có phân chia lại không?

Nếu muốn tạo chuỗi xu hướng liên tục, chỉ so sánh những kỳ có **phạm vi tương thích** hoặc tái tính theo một định nghĩa chung khi có dữ liệu. Không nối hai chuỗi khác phạm vi mà không đánh dấu giai đoạn chuyển đổi.

## 18. Đừng dùng chuẩn hóa để tạo một bảng xếp hạng tuyệt đối

Chuẩn hóa cần thiết, nhưng nó không biến chỉ số thành phán quyết về chất lượng:

- **Ít LOC/KLOC** không có nghĩa logic đúng hơn.
- **Ít lỗi được báo** không chắc ít lỗi tồn tại; có thể ít người dùng hoặc ít test hơn.
- **Coverage cao** không chứng minh test có expected đúng.
- **Độ phức tạp thấp** có thể đạt được bằng cách chuyển logic sang các lớp gián tiếp khó lần theo.
- **Churn thấp** có thể do module ổn định, cũng có thể do ít được bảo trì.
- **Latency thấp** có thể đi cùng kiểm tra quyền bị bỏ qua hoặc công việc bị xử lý thiếu.

Một tổ chức dùng metric để thưởng/phạt hoặc xếp hạng cá nhân có thể khiến người thực hiện **tối ưu con số thay vì chất lượng thật**. Chỉ số nên giúp nhận diện rủi ro và điều tra, không thay thế việc đọc yêu cầu, test, code và tác động đến người dùng.

### Một cách ra quyết định có trách nhiệm

Thay vì kết luận:

> “B có 3,89 lỗi/KLOC, A chỉ 3,75, vậy B kém chất lượng hơn.”

Nên nói:

> “Theo phạm vi Java production viết tay và cùng quy trình đo trong kỳ này, mật độ lỗi của B cao hơn A một chút. Số lượng còn nhỏ và chưa kiểm soát khác biệt về nhiệm vụ, mức tải và cách phát hiện lỗi. Cần xem nhóm lỗi, mức nghiêm trọng và nơi phát sinh trước khi quyết định ưu tiên.”

Phép so sánh lúc này **không bị che giấu**, nhưng cũng không bị diễn giải vượt quá bằng chứng.

## 19. Quy trình chuẩn hóa phạm vi trước khi so sánh

Một quy trình có thể áp dụng trong code review hoặc báo cáo chất lượng:

~~~mermaid
flowchart TD
    A["Nêu câu hỏi quyết định"] --> B["Chọn đơn vị quan sát và cohort"]
    B --> C["Chốt định nghĩa, nguồn và phạm vi"]
    C --> D["Cố định kỳ đo / revision / công cụ"]
    D --> E{"Các dữ liệu có tương thích?"}
    E -- "Không" --> F["Đo lại, phân nhóm hoặc báo N/A"]
    E -- "Có" --> G["Tính số liệu gốc và mẫu số"]
    G --> H["Tổng hợp đúng trọng số / đơn vị"]
    H --> I["Xem phân bố, chất lượng dữ liệu và bối cảnh"]
    I --> J["Rút ra câu hỏi điều tra / hành động phù hợp"]
~~~

Chi tiết từng bước:

1. **Bắt đầu từ câu hỏi:** Có muốn tìm nơi review, đo mức lỗi vận hành, hay đánh giá hiệu quả một thay đổi?
2. **Xác định đối tượng:** Module, service, method, API, request hay bản phát hành?
3. **Chọn nhóm tương đồng:** Tránh so library parser với endpoint giao diện chỉ vì cùng dùng Java.
4. **Chốt hợp đồng metric:** Định nghĩa, cách đếm, tử số, mẫu số, include/exclude và nguồn số liệu.
5. **Cố định điều kiện:** Revision, thời gian, công cụ, test profile, traffic/workload khi có liên quan.
6. **Kiểm tra độ đầy đủ:** Missing data, zero denominator, phần mã chuyển owner và nguồn lỗi chưa được phân loại.
7. **Tính và tổng hợp đúng:** Không lấy trung bình các tỷ lệ hoặc percentile khi công thức không phù hợp.
8. **Đọc kết quả cùng bối cảnh:** Độ rủi ro, quy tắc nghiệp vụ, lịch sử thay đổi, phân bố và mức quan trọng.
9. **Đưa ra hành động kiểm chứng được:** Chọn vùng đọc code/test sâu hơn, không xếp hạng người dựa vào một con số.
10. **Lưu protocol và kết quả:** Để người khác có thể tái lập và so sánh trong kỳ tiếp theo.

### Checklist nhanh cho reviewer

- **Hai bảng số có cùng định nghĩa metric không?**
- **Phạm vi include/exclude có giống và có được kiểm tra không?**
- **Có trộn production, test, generated hoặc dependency không?**
- **Tử số và mẫu số có thuộc cùng thành phần và kỳ đo không?**
- **Độ tuổi, workload và mục đích của các thành phần có khác đáng kể không?**
- **Dữ liệu thiếu và mẫu số 0 đã được xử lý đúng chưa?**
- **Tỷ lệ gộp có được tính từ số liệu gốc thay vì trung bình tùy ý không?**
- **Có thay đổi tool, formatter, CI profile hoặc ownership trong kỳ không?**
- **Kết luận có vượt quá điều metric thật sự đo không?**
- **Có thể chỉ ra bước điều tra hoặc kiểm thử tiếp theo không?**

## 20. Bài tập tự luyện

### Bài 1 — Tổng LOC gây nhầm lẫn

Module X có 1.500 dòng production, 300 dòng test và 5.000 dòng generated. Module Y có 2.000 dòng production, 1.000 dòng test và 0 dòng generated.

**Câu hỏi:** Module nào lớn hơn nếu xét tổng tệp? Module nào có nhiều mã production viết tay hơn?

**Gợi ý:** X có tổng **6.800 dòng**, Y có **3.000 dòng**. Nhưng nếu production đều viết tay và được đo cùng cách, Y có nhiều hơn **500 dòng production**. Hai kết quả đúng với hai phạm vi khác nhau.

### Bài 2 — Đếm lỗi khác kỳ

Module A có 12 defect được xác nhận trong 30 ngày; module B có 20 defect trong 180 ngày. Hai nhóm dùng cùng cách phân loại nhưng chưa có dữ liệu traffic.

**Câu hỏi:** Có thể kết luận A tốt hơn vì 12 ít hơn 20 không?

**Gợi ý:** Không. Ít nhất phải căn chỉnh thời gian và mức tiếp xúc; sau đó vẫn cần xem severity, nhiệm vụ và nguồn phát hiện lỗi.

### Bài 3 — Coverage gộp sai

Module A có 9/10 nhánh được bao phủ; module B có 10/100 nhánh. Một báo cáo lấy trung bình hai tỷ lệ: (90% + 10%)/2 = 50%.

**Câu hỏi:** Coverage gộp của toàn bộ nhánh A+B là bao nhiêu?

**Gợi ý:** **(9+10)/(10+100) = 19/110 ≈ 17,27%**. 50% là trung bình **theo module**, không phải tỷ lệ nhánh được bao phủ trong tập gộp.

### Bài 4 — Mẫu số bằng 0

Một module chỉ chứa generated code. Theo hợp đồng metric, số NCLOC production viết tay của nó bằng 0. Trong kỳ có một lỗi được phát hiện ở client sinh tự động.

**Câu hỏi:** Có thể ghi mật độ lỗi 0/KLOC vì “không có mã viết tay” không?

**Gợi ý:** Không. Phép chia theo mẫu số này **không xác định**, và tử số lại thuộc loại mã bị loại khỏi phạm vi. Cần ghi N/A, chuyển lỗi sang nhóm phân tích thích hợp hoặc dùng một hợp đồng metric khác.

### Bài 5 — Hai service khác đặc tính

Service A là API đọc public catalog, có hàng triệu request mỗi ngày. Service B thực hiện thanh toán, chỉ hàng nghìn giao dịch nhưng có ràng buộc tài chính và phân quyền nghiêm ngặt.

**Câu hỏi:** Cùng tỷ lệ request lỗi 0,1% có nghĩa mức rủi ro ngang nhau không?

**Gợi ý:** Không. Cần xét mức nghiêm trọng, loại lỗi, tác dụng phụ, khả năng khôi phục, khối lượng request và yêu cầu nghiệp vụ. Tỷ lệ bằng nhau chưa phải bằng chứng về rủi ro ngang nhau.

### Bài 6 — Formatter làm LOC tăng

Một nhóm nâng formatter rồi physical LOC tăng 18%, trong khi số statement logic không đổi đáng kể và không thêm tính năng.

**Câu hỏi:** Có nên báo “độ phức tạp tăng 18%” không?

**Gợi ý:** Không. Đây là biến động do cách trình bày. Muốn theo dõi xu hướng, cần giữ cùng phép đo, chú thích mốc formatter và sử dụng metric phù hợp cho độ phức tạp.

### Bài 7 — Một bảng xếp hạng đẹp nhưng thiếu định nghĩa

Dashboard xếp module theo “quality score” tạo từ LOC, độ bao phủ test, số lỗi và churn, nhưng không công bố công thức, thời kỳ hoặc cách loại generated code.

**Câu hỏi:** Tại sao không nên dùng để quyết định tái cấu trúc ngay?

**Gợi ý:** Không thể xác minh khả năng so sánh, trọng số hoặc nguồn dữ liệu. Hãy yêu cầu hợp đồng đo lường, các giá trị gốc, giới hạn và mục đích; dùng kết quả làm tín hiệu điều tra, không làm phán quyết tự động.

---

**Ghi nhớ:** Trước khi so sánh chỉ số chất lượng của hai thành phần, hãy **chuẩn hóa ranh giới, định nghĩa, nguồn dữ liệu, mẫu số, thời gian và nhóm đối tượng**. Phép chia cho LOC hay việc hiển thị phần trăm không tự biến dữ liệu khác phạm vi thành so sánh công bằng. Một kết luận tốt phải nói rõ **đang đo điều gì, điều gì chưa đo được và bước kiểm chứng tiếp theo**, để metric hỗ trợ cải thiện mã nguồn thay vì dẫn dắt quyết định sai.
