# Tần suất thay đổi, lịch sử lỗi và vùng cần ưu tiên

Trong một hệ thống đã tồn tại nhiều năm, không phải mọi phần mã đều có cùng mức rủi ro. Có những lớp gần như không đổi, có những module được sửa trong hầu hết các đợt phát hành, và có những vùng liên tục xuất hiện lỗi hồi quy. Khi nguồn lực review, viết test và refactor có hạn, nhóm cần biết **nên ưu tiên xem xét phần nào trước**.

Tuy nhiên, **tần suất thay đổi cao không tự chứng minh mã kém chất lượng**, cũng như **nhiều lỗi được ghi nhận không tự chứng minh lỗi của từng người hoặc của riêng một file**. Những con số này chỉ hữu ích khi đặt cạnh mức độ quan trọng của nghiệp vụ, loại thay đổi, chất lượng kiểm thử và tác động nếu lỗi xảy ra.

Bài học thuộc chương **Chỉ số chất lượng** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu của module, việc sử dụng chỉ số cần giúp xây dựng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Trọng tâm ở đây là dùng **lịch sử thay đổi**, **lịch sử lỗi** và **bối cảnh rủi ro** để nhận diện các *hotspot* — vùng mã đáng được đầu tư kiểm tra và cải thiện — mà không biến số liệu thành một bảng xếp hạng thiếu căn cứ.

## 1. Tại sao cần tìm vùng cần ưu tiên?

Giả sử một repository có hàng nghìn tệp Java. Nhóm có thể chọn nhiều cách phân bổ nguồn lực:

- Đọc và refactor các lớp dài nhất.
- Viết thêm test cho tất cả lớp có coverage thấp.
- Sửa module vừa gây sự cố sản xuất.
- Tập trung vào mã được sửa thường xuyên và có nhiều lỗi hồi quy.
- Ưu tiên các luồng quản lý tiền, quyền hoặc dữ liệu nhạy cảm dù số lần sửa không nhiều.

Không có cách nào luôn đúng. Một lớp dài nhưng ổn định, ít tác động có thể chưa cấp bách bằng một lớp nhỏ, thay đổi mỗi tuần, ảnh hưởng trực tiếp đến tính tiền và thường xuất hiện lỗi.

Câu hỏi có ích hơn là:

> **Vùng mã nào có khả năng khiến nhóm tốn nhiều chi phí hoặc gặp hậu quả nghiêm trọng nếu tiếp tục thay đổi mà không bổ sung kiểm soát?**

Cần phối hợp ít nhất ba chiều:

1. **Mức phơi lộ trước thay đổi:** vùng mã có được sửa hoặc chạm tới thường xuyên không?
2. **Bằng chứng về vấn đề trong quá khứ:** đã có lỗi, hồi quy, sự cố hoặc khó khăn lặp lại chưa?
3. **Hậu quả và khả năng kiểm soát:** vùng mã phục vụ nghiệp vụ nào, có test và ranh giới trách nhiệm phù hợp chưa?

Ba chiều này không phải công thức bảo đảm dự đoán lỗi tương lai; chúng giúp **xếp thứ tự câu hỏi cần điều tra**.

## 2. Tần suất thay đổi là gì?

**Tần suất thay đổi (change frequency)** mô tả mức độ thường xuyên một đơn vị mã được sửa trong một khoảng thời gian xác định. Đơn vị có thể là tệp, class, package, module hoặc thành phần triển khai.

Ví dụ: “Trong **90 ngày**, package `com.example.checkout` xuất hiện trong **12 thay đổi đã merge**.” Đây là một quan sát cụ thể hơn câu “checkout thường xuyên thay đổi”.

Có nhiều phép đo liên quan nhưng không đồng nghĩa:

| Chỉ số | Diễn đạt điều gì? | Hạn chế thường gặp |
| --- | --- | --- |
| **Số commit chạm vào tệp** | Bao nhiêu commit sửa tệp trong thời gian xét | Một tính năng có thể trải qua nhiều commit nhỏ; merge và revert gây nhiễu |
| **Số PR/change set độc lập** | Bao nhiêu đơn vị thay đổi được review và merge | Cần quy ước gộp commit và xác định PR liên quan |
| **Số ngày/tuần có thay đổi** | Sự thay đổi phân bố liên tục hay tập trung một đợt | Không cho biết kích thước hay rủi ro thay đổi |
| **Code churn** | Số dòng thêm, xóa hoặc sửa theo quy ước đo | Format, di chuyển mã, sinh mã tự động có thể làm phồng số |
| **Số lần đổi hợp đồng public** | Tần suất thay đổi giao diện có người sử dụng | Khó suy hoàn toàn từ diff tệp, cần biết hợp đồng |
| **Co-change** | Những tệp nào thường phải sửa cùng nhau | Sửa cùng không nhất thiết là phụ thuộc xấu; có thể cùng một tính năng |
| **Độ mới của thay đổi** | Vùng mã vừa được sửa gần đây tới mức nào | Không tự chứng minh đang có lỗi |

### 2.1. Đặt cửa sổ thời gian trước khi đếm

Các ví dụ về cửa sổ đo:

- **30 ngày:** phù hợp để xem thay đổi rất gần đây nhưng dễ nhiễu theo sprint.
- **90 ngày:** có thể phản ánh một vài chu kỳ phát triển, vẫn cần xem mùa vụ.
- **180 hoặc 365 ngày:** thấy xu hướng dài hơn nhưng có thể trộn nhiều phiên bản và thay đổi cấu trúc.

Không có một cửa sổ chuẩn cho mọi dự án. Nhóm bảo trì theo tuần, dự án có phát hành theo quý và sản phẩm có mùa cao điểm cần các lựa chọn khác nhau.

Khi so sánh hai module, phải dùng **cùng cửa sổ, cùng đơn vị và cùng quy tắc đếm**. Nếu một module mới xuất hiện tháng trước còn module khác đã tồn tại hai năm, đếm tổng cả năm có thể làm sai ý nghĩa mức thay đổi.

### 2.2. Thay đổi không phải lúc nào cũng là dấu hiệu xấu

Một vùng mã có nhiều thay đổi vì:

- Sản phẩm đang mở rộng đúng kế hoạch.
- Đội ngũ đang chủ động trả nợ kỹ thuật, thêm test hoặc làm rõ tên.
- API ngoài thay đổi, buộc adapter được cập nhật thường xuyên.
- Một dự án đổi tên package hoặc chuẩn hóa formatter hàng loạt.
- Thường xuyên có bug fix hoặc điều chỉnh gấp sau phát hành.
- Quy tắc nghiệp vụ thay đổi nhiều nhưng thiết kế vẫn đáp ứng tốt.

Các nguyên nhân khác nhau đòi hỏi hành động khác nhau. **Đếm thay đổi là điểm bắt đầu để hỏi “vì sao?”, không phải kết luận một đoạn mã đã sai.**

## 3. Code churn và sự khác biệt với số commit

**Code churn** thường dùng để chỉ lượng mã bị thêm/xóa/sửa trong một giai đoạn. Một cách đếm thực dụng là tổng số dòng thêm và xóa trong các diff được chọn; một dòng sửa có thể được công cụ xem như một dòng xóa và một dòng thêm.

Ví dụ minh họa:

| Vùng mã | PR thay đổi / 90 ngày | Dòng thêm + xóa | Bối cảnh |
| --- | ---: | ---: | --- |
| `checkout/PricingPolicy.java` | 10 | 180 | Nhiều thay đổi quy tắc giá |
| `reports/Template.java` | 2 | 2.000 | Đổi định dạng hàng loạt một lần |
| `security/Authorization.java` | 3 | 45 | Sửa ba quy tắc quyền quan trọng |
| `generated/ApiModels.java` | 12 | 7.000 | Sinh mã theo schema mỗi đợt phát hành |

Không thể xếp mức rủi ro chỉ bằng cột “dòng thêm + xóa”:

- 2.000 dòng của mẫu báo cáo có thể chủ yếu là định dạng.
- 45 dòng ở mã phân quyền có thể là thay đổi rủi ro cao.
- Tệp sinh tự động thường không nên được đánh giá như mã viết tay; cần xem schema và generator.

**Quy tắc đếm phải được công bố.** Có tính commit merge? Revert? File rename? Dòng comment? Code sinh tự động? Cùng một pull request sửa tệp ba lần được tính là một hay ba thay đổi?

Nếu không ghi các quy tắc ấy, số liệu qua hai lần đo có thể thay đổi vì cách thu thập chứ không vì chất lượng mã.

## 4. Lịch sử lỗi cung cấp tín hiệu gì?

**Lịch sử lỗi (defect history)** có thể gồm bug được xác nhận, regression, incident sản xuất, lần rollback hoặc thay đổi khắc phục nguyên nhân gốc.

Ví dụ: “Trong 180 ngày qua, luồng checkout có **ba lỗi nghiệp vụ đã xác nhận**, gồm một lần áp sai điều kiện giảm giá và hai lần hồi quy tính phí.” Thông tin này hữu ích hơn “checkout có ba issue”.

### 4.1. Nên phân loại lỗi theo ảnh hưởng

Các chiều có thể ghi:

- **Loại lỗi:** tính sai, mất dữ liệu, lộ thông tin, phân quyền, lỗi tích hợp, hiệu năng, trải nghiệm.
- **Mức ảnh hưởng:** số người dùng, dữ liệu liên quan, gián đoạn, khả năng khôi phục.
- **Nguồn phát hiện:** unit test, CI, staging, production, khách hàng, monitoring.
- **Tính chất lặp lại:** một nguyên nhân tái phát, lỗi mới hay trường hợp chưa được test.
- **Thời điểm:** lỗi còn gần đây hay thuộc kiến trúc/phiên bản đã thay thế.
- **Nguyên nhân gốc:** quy tắc sai, thiếu test, phụ thuộc ngoài đổi hợp đồng, cấu hình, dữ liệu hoặc vận hành.

**Đừng xem mọi issue gắn nhãn bug là lỗi có cùng sức nặng.** Một lỗi giao diện nhỏ không tự tương đương lỗi phân quyền hoặc mất dữ liệu.

### 4.2. Lỗi thuộc về vùng mã nào?

Một sự cố thanh toán có thể liên quan:

1. Chính sách tính tổng.
2. Adapter cổng thanh toán.
3. Quy tắc retry.
4. Định dạng sự kiện.
5. Cấu hình timeout ở hạ tầng.

Nếu một PR sửa cả năm nơi, đếm sự cố đó thành “năm lỗi độc lập” sẽ phóng đại số lỗi. Ngược lại, gán toàn bộ lỗi cho tệp cuối cùng trong commit sửa có thể che các nguyên nhân khác.

Có thể lưu **một incident ID duy nhất** cùng danh sách vùng mã liên quan, rồi phân biệt:

- **Vùng nguyên nhân gốc đã xác minh.**
- **Vùng góp phần tạo hậu quả hoặc lan truyền.**
- **Vùng chỉ được sửa để giảm tác động.**
- **Vùng chưa đủ bằng chứng liên quan.**

Với phân tích hotspot, không nhất thiết phải đạt quy trách nhiệm hoàn hảo ở cấp dòng. Nhưng cần tránh biến **số lần sửa lỗi** thành **số lỗi do tệp gây ra** nếu không có bằng chứng tương ứng.

### 4.3. Commit có chữ “fix” không tự chứng minh đã sửa bug

Không nên coi mọi commit chứa từ `fix`, `hotfix` hoặc `repair` là một lỗi riêng biệt. “Fix typo”, “fix build script” và “fix security incident” rất khác nhau.

Nguồn dữ liệu nên liên kết **ticket, PR, kết quả review, incident report và regression test** khi có thể. Quy tắc gắn nhãn thủ công cũng cần được hiểu là có nhiễu. Một bug có thể cần nhiều commit; một commit có thể sửa nhiều bug.

### 4.4. Lịch sử sạch chưa chắc là chất lượng cao

Một module không có bug được ghi nhận có thể vì:

- Ít người dùng hoặc gần như không chạy.
- Thiếu logging, monitoring hoặc test để phát hiện lỗi.
- Người dùng báo lỗi qua kênh khác không được ghi lại.
- Đội ngũ sửa trực tiếp nhưng không liên kết issue.
- Module vừa được tạo, chưa trải qua đủ tải và thời gian.

Đó là **thiếu bằng chứng lỗi**, không phải bằng chứng chắc chắn rằng module không có lỗi. Khi so sánh, nên xem mức độ sử dụng và khả năng quan sát của từng phần.

## 5. Hotspot: nơi thay đổi và khó khăn có thể giao nhau

Trong phân tích mã nguồn, **hotspot** thường là vùng mã có nhiều thay đổi và có dấu hiệu khó bảo trì hoặc nhiều vấn đề đáng quan tâm. Một số phương pháp kết hợp **change frequency** với **độ phức tạp**; những phương pháp khác bổ sung **lịch sử lỗi**, **chất lượng test** hoặc **mức quan trọng nghiệp vụ**.

Không có định nghĩa công thức duy nhất. Trong bài này, ta dùng nghĩa vận hành:

> **Hotspot là vùng cần điều tra ưu tiên vì có bằng chứng về sự thay đổi lặp lại và/hoặc hậu quả đáng kể, kết hợp các dấu hiệu dễ sai hoặc khó sửa.**

~~~mermaid
flowchart TD
    A[Tần suất thay đổi / churn] --> H[Ứng viên hotspot]
    B[Lịch sử lỗi đã xác nhận] --> H
    C[Độ phức tạp và phụ thuộc] --> H
    D[Chất lượng kiểm thử và quan sát] --> H
    E[Mức quan trọng nghiệp vụ] --> H
    H --> F[Review bối cảnh và nguyên nhân]
    F --> G{Có rủi ro hoặc chi phí đáng xử lý?}
    G -- Có --> I[Đầu tư test, thiết kế, kiểm soát]
    G -- Chưa rõ --> J[Thu thập thêm bằng chứng]
    G -- Không --> K[Ghi lý do, tiếp tục theo dõi]
~~~

Sơ đồ thể hiện **quy trình ra quyết định**, không phải phép tính cộng chính xác năm con số.

### 5.1. Mã phức tạp nhưng hiếm đổi

Một lớp có Cyclomatic Complexity cao, ít test và chưa được sửa trong ba năm có thể khó hiểu, nhưng chi phí bảo trì hằng ngày hiện thấp. Nếu không nằm trên luồng quan trọng, nó chưa chắc là ứng viên refactor cấp bách.

Tuy nhiên, nếu lớp đó xử lý **phân quyền, giao dịch hoặc dữ liệu nguy hiểm** và hiện không có bằng chứng kiểm chứng, rủi ro vẫn có thể cao **ngay cả khi tần suất thay đổi thấp**. Vì thế không nên dùng change frequency làm điều kiện bắt buộc duy nhất.

### 5.2. Mã thay đổi nhiều nhưng dễ sửa

Một adapter có cấu trúc đơn giản, test hợp đồng tốt và thay đổi định dạng thường xuyên theo yêu cầu sản phẩm có thể có churn cao mà ít lỗi. Giải pháp không nhất thiết là viết lại; có thể chỉ cần theo dõi phiên bản hợp đồng và duy trì test.

### 5.3. Mã thay đổi nhiều, lỗi lặp lại và test yếu

Đây là ứng viên rõ ràng để điều tra. Nhóm nên hỏi:

- Quy tắc nghiệp vụ có bị trải ra nhiều lớp không?
- Các thay đổi có liên tục chạm cùng một nhánh điều kiện không?
- Có test biên hoặc test lỗi từng xuất hiện chưa?
- Có phụ thuộc ngoài hoặc trạng thái dùng chung làm thay đổi lan rộng?
- Nếu sửa một chỗ, những chỗ nào phải được cập nhật cùng?

Hotspot không đồng nghĩa **phải refactor lớn ngay**. Có thể bắt đầu bằng **regression test** cho lỗi cũ, thêm test hợp đồng, làm rõ trạng thái hoặc tách một phụ thuộc khó kiểm soát.

## 6. Ví dụ bảng ưu tiên với dữ liệu minh họa

Giả sử nhóm có nguồn lực cải thiện hai vùng mã trong sprint tiếp theo. Bảng dưới là **dữ liệu giả định để luyện lập luận**, không phải kết quả từ một repository thật.

| Vùng mã | PR / 90 ngày | Lỗi xác nhận / 180 ngày | Test và ranh giới | Hậu quả khi sai |
| --- | ---: | ---: | --- | --- |
| **Checkout/Pricing** | 14 | 4, gồm 1 regression nghiêm trọng | Thiếu test đúng ngưỡng giảm giá | Tính sai tiền người dùng |
| **Catalog/Import** | 11 | 1 | Test parsing khá tốt, phần retry còn thiếu | Dữ liệu nhập chậm hoặc trùng |
| **Report/Template** | 2 | 0 | Đơn giản, ít thay đổi | Sai định dạng báo cáo thông thường |
| **Authorization/AccessPolicy** | 3 | 1 | Thiếu test đa tenant | Có thể lộ dữ liệu trái quyền |
| **Generated/ClientModel** | 18 | 0 | Mã sinh từ schema, có contract test | Sai tương thích nếu schema đổi |

Nếu chỉ xếp theo số PR, `Generated/ClientModel` đứng đầu. Nếu chỉ đếm lỗi, `Checkout/Pricing` đứng đầu, trong khi `Authorization/AccessPolicy` có thể bị đánh giá quá thấp dù hậu quả nghiêm trọng.

Một quyết định có căn cứ có thể là:

1. **Ưu tiên kiểm tra ngay `Checkout/Pricing`** vì vừa thay đổi nhiều, vừa có lỗi được xác nhận và thiếu test biên ở luồng tiền.
2. **Kiểm tra `Authorization/AccessPolicy` sớm** vì rủi ro lộ dữ liệu có tác động cao và thiếu test cách ly tenant, dù số thay đổi thấp.
3. **Xem `Catalog/Import` ở lần cải thiện kế tiếp** nếu retry gây trùng dữ liệu; cần thêm bằng chứng về hậu quả và tần suất.
4. **Không vội refactor mã sinh tự động**, mà kiểm tra schema, generator và contract test.
5. **Tiếp tục theo dõi template báo cáo**, trừ khi có yêu cầu mới làm thay đổi mức quan trọng.

Đây là **thứ tự điều tra đề xuất**, không phải xếp hạng “chất lượng cá nhân” hay kết luận toàn bộ mã của module nào tốt/xấu.

## 7. Tránh biến điểm tổng hợp thành sự thật tuyệt đối

Một nhóm có thể tạo công thức thử nghiệm:

`priorityScore = w1 × changeFrequency + w2 × defectHistory + w3 × criticality`

Vấn đề là các thành phần khác **đơn vị và thang đo**. Số PR trong 90 ngày không cùng ý nghĩa với số incident trong 180 ngày, còn mức criticality thường là phân loại định tính. Nếu cộng thẳng, giá trị số cao có thể chỉ phản ánh phương pháp chuẩn hóa hoặc trọng số chọn tùy ý.

Các điểm cần cân nhắc:

- **Chuẩn hóa:** dùng cùng khoảng thời gian hoặc mô tả rõ khác biệt; xác định thang của từng chỉ số.
- **Trọng số:** giải thích vì sao một mức hậu quả được xem trọng hơn số lần sửa mã.
- **Ngưỡng:** xuất phát từ dữ liệu, SLO, yêu cầu bảo mật và khả năng xử lý, không từ con số đẹp.
- **Độ tin cậy dữ liệu:** thông tin incident chưa đầy đủ có thể làm score sai.
- **Độ nhạy:** thay đổi trọng số một chút có làm thứ tự đảo hoàn toàn không?
- **Kiểm tra của con người:** score gợi ý review, không thay đánh giá mã và nghiệp vụ.

Với một nhóm nhỏ hoặc giai đoạn đầu, **phân loại theo tiêu chí rõ ràng** có thể dễ kiểm tra và giải thích hơn một chỉ số tổng hợp có hai chữ số thập phân.

## 8. Ví dụ Java 17: biến tiêu chí ưu tiên thành quy tắc có thể đọc

Giả sử nhóm muốn tạo một báo cáo **triage ban đầu** theo ba nhóm `HIGH`, `MEDIUM`, `LOW`. Quy tắc chỉ dùng dữ liệu đã có và **không tự kết luận mã có bug**.

**Chính sách minh họa:**

- `HIGH` nếu vùng nằm trong luồng nghiệp vụ quan trọng và đã có lỗi được xác nhận gần đây.
- `HIGH` nếu thay đổi nhiều (**ít nhất 8 PR / 90 ngày**) và có ít nhất **2 lỗi / 180 ngày**.
- `MEDIUM` nếu thay đổi khá thường (**ít nhất 5 PR / 90 ngày**) và thiếu test có ý nghĩa.
- `MEDIUM` nếu đã có lỗi được xác nhận nhưng chưa đạt tiêu chí `HIGH`.
- Các trường hợp khác tạm `LOW`, nhưng vẫn được phép nâng ưu tiên sau review.

Các mốc **8, 2, 5** chỉ là số liệu giả định cho ví dụ lập trình. Chúng **không phải ngưỡng chất lượng chuẩn** và không dùng trực tiếp ở hệ thống khác nếu chưa hiệu chỉnh.

### 8.1. Dữ liệu đầu vào có hợp đồng rõ ràng

~~~java
import java.util.Objects;

record CodeAreaSignals(
        String area,
        int mergedChanges90d,
        int confirmedDefects180d,
        boolean criticalBusinessFlow,
        boolean insufficientTests) {

    CodeAreaSignals {
        Objects.requireNonNull(area, "area");
        if (area.isBlank()) {
            throw new IllegalArgumentException(
                    "area must not be blank");
        }
        if (mergedChanges90d < 0 || confirmedDefects180d < 0) {
            throw new IllegalArgumentException(
                    "counts must not be negative");
        }
    }
}
~~~

Tên trường giữ **đơn vị và cửa sổ thời gian**: người đọc biết đây là số thay đổi đã merge trong 90 ngày và số lỗi đã xác nhận trong 180 ngày.

Biến `criticalBusinessFlow` là kết quả đánh giá tác động đã được nhóm xác nhận, không phải suy từ tên package. Biến `insufficientTests` cũng là **nhận định có căn cứ** từ test và hợp đồng cụ thể, không đơn giản bằng `coverage < 80%`.

### 8.2. Quy tắc triage tường minh

~~~java
enum Priority {
    HIGH,
    MEDIUM,
    LOW
}

final class HotspotTriage {
    static Priority classify(CodeAreaSignals signals) {
        if (signals == null) {
            throw new IllegalArgumentException(
                    "signals are required");
        }

        if (signals.criticalBusinessFlow()
                && signals.confirmedDefects180d() > 0) {
            return Priority.HIGH;
        }

        if (signals.mergedChanges90d() >= 8
                && signals.confirmedDefects180d() >= 2) {
            return Priority.HIGH;
        }

        if (signals.mergedChanges90d() >= 5
                && signals.insufficientTests()) {
            return Priority.MEDIUM;
        }

        if (signals.confirmedDefects180d() > 0) {
            return Priority.MEDIUM;
        }

        return Priority.LOW;
    }
}
~~~

Điều này có một ưu điểm: mọi người có thể đọc **vì sao** một vùng được đánh dấu cần review. Một số điểm cần hiểu đúng:

- Kết quả là **ưu tiên thu thập bằng chứng**, không phải phán quyết lỗi chắc chắn.
- `LOW` không chứng minh an toàn, nhất là khi lịch sử lỗi chưa được ghi đầy đủ.
- Nếu có incident nghiêm trọng mà dữ liệu nhập không phản ánh, cần xử lý theo quy trình sự cố, không đợi bộ phân loại.
- Một vùng có thể được nâng mức ưu tiên bằng review bảo mật hoặc thay đổi nghiệp vụ dù hai đếm lịch sử thấp.
- Quy tắc cần được xem lại khi kích thước codebase, nhịp thay đổi hoặc cách ghi nhận lỗi đổi.

### 8.3. Kiểm thử chính sách triage

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class HotspotTriageTest {
    @Test
    void prioritizesCriticalAreaWithConfirmedDefect() {
        CodeAreaSignals signals =
                new CodeAreaSignals(
                        "authorization", 3, 1, true, true);

        assertEquals(
                Priority.HIGH,
                HotspotTriage.classify(signals));
    }

    @Test
    void prioritizesRepeatedChangeAndDefects() {
        CodeAreaSignals signals =
                new CodeAreaSignals(
                        "pricing", 8, 2, false, false);

        assertEquals(
                Priority.HIGH,
                HotspotTriage.classify(signals));
    }

    @Test
    void marksFrequentlyChangedWeaklyTestedAreaMedium() {
        CodeAreaSignals signals =
                new CodeAreaSignals(
                        "catalog", 5, 0, false, true);

        assertEquals(
                Priority.MEDIUM,
                HotspotTriage.classify(signals));
    }

    @Test
    void doesNotTreatNoRecordedBugsAsProofOfQuality() {
        CodeAreaSignals signals =
                new CodeAreaSignals(
                        "reports", 2, 0, false, false);

        // LOW là mức ưu tiên theo quy tắc, không phải "an toàn tuyệt đối".
        assertEquals(
                Priority.LOW,
                HotspotTriage.classify(signals));
    }

    @Test
    void rejectsInvalidCounts() {
        assertThrows(IllegalArgumentException.class,
                () -> new CodeAreaSignals(
                        "checkout", -1, 0, false, true));
    }
}
~~~

Test đảm bảo **quy tắc phân loại được thực thi đúng như chính sách đã viết**, không chứng minh chính sách đó là phương pháp dự báo lỗi tối ưu. Muốn chọn ngưỡng và đo hiệu quả thực tế, phải đánh giá trên dữ liệu lịch sử và kết quả review của dự án.

### 8.4. Tránh giấu giả thiết trong mã phân tích

Nếu sau này team thay cửa sổ 90 ngày thành 180 ngày nhưng giữ tên `mergedChanges90d`, kết quả có thể bị hiểu sai. Nếu thay cách tính lỗi mà không ghi rõ “confirmed defects”, cùng một con số có thể mang ý nghĩa khác.

Đối với code thu thập số liệu, nên giữ riêng:

- **Định nghĩa dữ liệu và thời gian lấy mẫu.**
- **Bước lọc bỏ thay đổi gây nhiễu.**
- **Các quy tắc đánh giá ưu tiên.**
- **Kết quả review và quyết định hành động.**

Tách các trách nhiệm này giúp thay nguồn dữ liệu hoặc chính sách mà không phải viết lại toàn bộ công cụ.

## 9. Thu thập dữ liệu thay đổi mà không tự gây nhiễu

Nhóm có thể lấy tín hiệu từ hệ thống quản lý phiên bản và hệ thống quản lý công việc. Với Git, dữ liệu gốc gồm commit, diff, đường dẫn tệp, ngày và thông tin merge; còn PR/ticket chứa ý định và phạm vi thay đổi.

Một hướng xử lý thường có các bước:

~~~mermaid
flowchart LR
    A[Lịch sử Git và PR] --> B[Chuẩn hóa change set]
    B --> C[Lọc generated/format-only]
    C --> D[Nhóm theo file, package hoặc module]
    E[Issue và incident đã xác nhận] --> F[Liên kết nguyên nhân và phạm vi]
    D --> G[Bảng tín hiệu theo cửa sổ]
    F --> G
    G --> H[Đánh giá rủi ro và review]
~~~

### 9.1. Chuẩn hóa đơn vị thay đổi

Một pull request có thể gồm 20 commit, nhưng chỉ đại diện **một yêu cầu nghiệp vụ**. Nếu nhóm dùng “số lần thay đổi” để đo mức chạm code, cần quyết định đếm theo PR hay commit và giữ nhất quán.

Một pull request cũng có thể chứa nhiều thay đổi độc lập; không có phép đếm đơn giản nào luôn mô tả đúng tất cả. Vì thế, **cần giữ liên kết đến dữ liệu gốc** để người review đọc chi tiết khi một vùng nổi bật.

### 9.2. Xử lý rename, move và code sinh tự động

Tệp di chuyển từ package A sang B có thể bị nhìn như xóa một tệp và thêm tệp mới nếu công cụ không theo dõi rename. Các dự án chuyển package lớn sẽ tạo churn rất cao mà chưa chắc logic đã đổi.

Mã sinh tự động cần được phân tích ở **nguồn tạo ra nó**: schema, template và phiên bản generator. Có thể báo riêng mã sinh thay vì xếp cùng mã viết tay.

Nếu thay một formatter trên toàn repository, nên đánh dấu đợt đó như **thay đổi định dạng hàng loạt**, để không kết luận mọi package đồng loạt trở thành hotspot nghiệp vụ.

### 9.3. Phân biệt cùng sửa với phụ thuộc bắt buộc

Hai tệp thường xuất hiện cùng PR có thể vì chúng:

- Cùng thuộc một use case và cần thay đổi đồng thời.
- Là code và test tương ứng — điều này có thể tốt.
- Là adapter và hợp đồng cùng đổi phiên bản.
- Bị gộp trong một refactor/đợt format lớn.
- Thật sự có sự kết dính không hợp lý giữa những module cần độc lập.

Phân tích **co-change** có thể gợi ý nơi cần đọc thêm, nhưng không tự xác nhận thiết kế sai. Hãy kiểm tra chiều phụ thuộc, ranh giới nghiệp vụ và tính chất mỗi thay đổi.

## 10. Ưu tiên sửa gì trong một hotspot?

Phát hiện một vùng cần ưu tiên là **bắt đầu của công việc**, không phải kết thúc. Cần tìm nguyên nhân khiến thay đổi ở vùng đó rủi ro hoặc tốn chi phí.

| Dấu hiệu quan sát | Việc đầu tiên nên xem | Hành động có thể hữu ích |
| --- | --- | --- |
| Lỗi biên lặp lại ở phép tính | Đặc tả, giá trị biên, oracle của test | Thêm regression test và làm rõ điều kiện |
| Nhiều PR sửa cùng một luồng nghiệp vụ | Trách nhiệm có đang bị phân tán? | Tách policy, đặt hợp đồng rõ, giảm phụ thuộc không cần thiết |
| Thay đổi nhỏ làm nhiều module cùng lỗi | Cấu trúc phụ thuộc và khả năng tương thích | Củng cố contract test, giảm coupling |
| Bug xuất hiện khi concurrency tăng | Mutable state, vòng đời object, transaction | Cô lập state, xác nhận đồng bộ và retry |
| Vùng mã lâu không đổi nhưng rất quan trọng | Bất biến an toàn và bằng chứng test | Review rủi ro, thêm test đặc thù, kiểm tra cấu hình |
| Churn do schema và mã sinh | Nguồn schema, migration và hợp đồng | Kiểm tra generator, versioning, test tương thích |
| Thay đổi thường xuyên nhưng ít lỗi | Độ rõ của code, quy trình review và test | Giữ quy trình tốt, chỉ cải thiện nếu có chi phí thực |

### 10.1. Test hồi quy trước refactor lớn

Nếu vùng mã vừa gây lỗi sản xuất, ưu tiên viết một test **tái hiện hành vi sai trên bản lỗi** và **xác nhận bản sửa**. Test cần có dữ liệu, điều kiện và kết quả mong đợi từ đặc tả.

Không nên viết lại toàn bộ module ngay khi vừa có incident. Refactor lớn trong trạng thái thông tin chưa đầy đủ có thể thêm rủi ro mới. Tách cải thiện thành những bước có thể kiểm chứng và triển khai an toàn.

### 10.2. Chọn ranh giới refactor dựa trên lý do thay đổi

Nếu quy tắc giảm giá đổi mỗi tháng còn adapter database ít đổi, tách quy tắc vào một thành phần có đầu vào/đầu ra rõ có thể giúp giảm phạm vi sửa.

Nếu API ngoài đổi thường xuyên, một adapter có hợp đồng ổn định có thể ngăn thay đổi lan tới miền bài toán. Nhưng **thêm interface không tự động tốt**: hãy chỉ tách khi nó làm luồng phụ thuộc và trách nhiệm rõ hơn.

### 10.3. Đừng xem “giảm churn” là mục tiêu riêng

Có lúc thay đổi là dấu hiệu **tốt**: sửa lỗi đã biết, nâng phiên bản bảo mật, cải thiện quan sát hoặc xóa nợ kỹ thuật. Nếu nhóm bị đánh giá theo số lần chạm tệp, họ có thể ngại sửa phần cần sửa.

Mục tiêu là **giảm chi phí và rủi ro của thay đổi cần thiết**, không phải làm biểu đồ số thay đổi thấp bất kể yêu cầu kinh doanh.

## 11. Kết hợp chất lượng kiểm thử vào ưu tiên

Một vùng mã thay đổi thường xuyên và có test phù hợp có thể an toàn hơn vùng có cùng tần suất nhưng chỉ có test “không ném ngoại lệ”.

Cần phân biệt:

- **Coverage:** mã đã chạy qua những dòng/nhánh nào.
- **Test oracle:** kết quả mong đợi có bắt nguồn từ quy tắc đúng không.
- **Regression test:** lỗi thật đã gặp có được bảo vệ không.
- **Integration/contract test:** phụ thuộc ngoài có được kiểm tra theo hợp đồng không.
- **Tính ổn định của test:** test có flaky hoặc phụ thuộc dữ liệu môi trường không.
- **Đường lỗi:** timeout, dữ liệu thiếu, quyền bị từ chối, retry hoặc trạng thái chưa xác định đã được xét chưa.

### 11.1. Coverage thấp có phải ưu tiên ngay không?

Tùy mục tiêu và rủi ro. Một file mapper đơn giản có coverage thấp nhưng ít tác động có thể được xử lý sau một API phân quyền có test chỉ chạy bằng tài khoản quản trị.

Ngược lại, coverage thấp ở một nhánh mới được sửa nhiều và liên tục hồi quy có thể là tín hiệu rất mạnh để viết thêm test.

### 11.2. Lịch sử lỗi nên tạo ra test cụ thể

Ví dụ hệ thống đã từng sai mức phí ở **đúng ngưỡng**. Khi đánh giá hotspot, một trong những hành động tốt là xác định xem đã có test khẳng định **đúng ngưỡng, dưới ngưỡng, trên ngưỡng** hay chưa, không chỉ thêm một test gọi phương thức.

Bằng chứng kiểm thử phải được nối tới **cách lỗi xuất hiện**; tăng số lượng test không phải mục tiêu độc lập.

## 12. Mức quan trọng nghiệp vụ có thể đảo thứ tự ưu tiên

Một thành phần có ít thay đổi nhưng nắm giữ các khả năng sau có thể cần review trước một hotspot chỉ có nhiều PR:

- Quyết định quyền truy cập dữ liệu người dùng hoặc tenant.
- Tính toán số tiền thanh toán, hoàn tiền, hạn mức.
- Ghi hoặc xóa dữ liệu không thể khôi phục dễ dàng.
- Quản lý khóa, token, xác thực hoặc quyền dịch vụ.
- Điều phối giao dịch qua nhiều hệ thống có tác dụng phụ.
- Thao tác trong hệ thống có yêu cầu độ sẵn sàng nghiêm ngặt.

Có thể dùng ma trận đánh giá định tính:

| Tần suất chạm | Hậu quả nếu sai thấp | Hậu quả nếu sai cao |
| --- | --- | --- |
| **Thấp** | Theo dõi, cải thiện khi có yêu cầu | Review bất biến và kiểm soát theo rủi ro |
| **Cao** | Làm rõ cấu trúc và giảm chi phí thay đổi | Ưu tiên test, review và cải thiện theo từng bước |

Ma trận này **không ước lượng xác suất lỗi**. Nó chỉ nhắc rằng “ít thay đổi” không xóa bỏ hậu quả nếu phần mã đang bảo vệ tài sản quan trọng.

Trong đánh giá bảo mật, cần hiểu **rủi ro thực tế theo bối cảnh** chứ không chỉ tên class hoặc điểm static analyzer. Trong đánh giá độ tin cậy, cần thêm quan sát về tải, sự cố, khả năng khôi phục và sự thay đổi của hệ thống ngoài.

## 13. Điều chỉnh để tránh thiên lệch khi dùng dữ liệu lịch sử

### 13.1. Thay đổi theo mùa hoặc theo đợt

Một module thuế chỉ thay đổi nhiều vào đầu năm hoặc một module báo cáo chỉ hoạt động cuối tháng sẽ có tính chu kỳ. Dùng cửa sổ ngắn không đúng mùa có thể khiến ưu tiên bị sai.

**Giải pháp:** giữ cả xu hướng ngắn và dài hạn, ghi nhận thời điểm các đợt thay đổi có ý nghĩa.

### 13.2. Tệp lớn tự nhiên bị chạm nhiều hơn

Tệp hoặc module lớn hơn có nhiều cơ hội xuất hiện trong diff. Nhiều tác giả cùng làm việc cũng có thể khiến số thay đổi tăng, nhưng đó chưa phải bằng chứng thiết kế tệ.

Có thể xem **số thay đổi trên một vùng chức năng** hoặc kết hợp độ lớn, nhưng việc chuẩn hóa theo LOC cũng không đơn giản: 100 dòng điều phối có thể ảnh hưởng rộng hơn 1.000 dòng mã mẫu. Khi xếp hạng, cần review kết quả thay vì dựa hoàn toàn vào tỷ lệ.

### 13.3. Lịch sử lỗi phụ thuộc văn hóa ghi nhận

Một nhóm ghi đầy đủ lỗi vào issue tracker có thể có số bug cao hơn nhóm âm thầm sửa lỗi. Coi số bug là KPI đánh giá đội ngũ có thể tạo động cơ **không ghi nhận lỗi**, làm dữ liệu kém trung thực.

Chỉ số nên phục vụ **học hỏi và phân bổ hỗ trợ**, không dùng để suy luận năng lực cá nhân từ tệp mà họ thường sửa. Vùng mã nhiều người sửa không có nghĩa người sửa nhiều đã tạo ra nhiều lỗi.

### 13.4. Sai lệch do thay đổi cấu trúc

Khi một package bị tách thành ba module, lịch sử trước và sau có thể không so sánh trực tiếp. Một số công cụ theo dõi rename tốt hơn những công cụ khác, nhưng vẫn phải ghi lại mốc thay đổi kiến trúc.

Một biểu đồ “churn của module A giảm” có thể chỉ phản ánh công việc đã được chuyển sang module B.

### 13.5. Dữ liệu không quan sát đủ

Một dịch vụ ít người dùng, ít logging hoặc thiếu monitoring có thể có ít incident hơn dịch vụ được theo dõi kỹ. Số lỗi ghi nhận cần được hiểu cùng **mức sử dụng và năng lực phát hiện**.

Nếu không có dữ liệu đại diện, hãy ghi **độ tin cậy thấp** thay vì tự điền số 0 như bằng chứng không có vấn đề.

## 14. Phân biệt chỉ số hệ quả, chỉ số dự báo và hành động

**Chỉ số hệ quả (lagging indicator)** phản ánh điều đã xảy ra: sự cố sản xuất, hồi quy, thời gian sửa lỗi, rollback. Chúng quan trọng nhưng thường xuất hiện **sau khi** người dùng bị ảnh hưởng.

**Tín hiệu có thể giúp dự báo/ưu tiên (leading signal)** gồm vùng mã vừa đổi nhiều, sự thay đổi ở hợp đồng quan trọng, test yếu hoặc phụ thuộc chéo. Chúng có thể giúp nhóm hành động sớm, nhưng **không phải lời tiên tri về lỗi tương lai**.

Một cách sử dụng hiệu quả:

1. Dùng **lịch sử lỗi** để biết vùng đang gây tổn thất thật.
2. Dùng **tần suất và kiểu thay đổi** để biết nơi sắp phải sửa hoặc chịu tác động thường xuyên.
3. Dùng **bằng chứng test và cấu trúc** để xác định rủi ro có thể kiểm soát.
4. Dùng **mức hậu quả** để quyết định nên đầu tư ở đâu trước.
5. Sau khi cải thiện, xem **lỗi có ít tái phát hơn, thay đổi có dễ hơn** không — thay vì chỉ xem số dòng code giảm.

Ví dụ, giảm Cyclomatic Complexity bằng cách chia một hàm thành mười hàm tên mơ hồ có thể làm điểm tĩnh đẹp hơn nhưng không giảm thời gian sửa lỗi. **Mục tiêu là thay đổi an toàn và hiểu rõ**, không phải một chỉ số đứng riêng.

## 15. Quy trình thực tế để chọn vùng cải thiện

### Bước 1 — Chốt quyết định cần hỗ trợ

Nhóm muốn ưu tiên **viết test**, **review bảo mật**, **giảm coupling** hay **refactor**? Nếu chưa biết việc muốn quyết định, thu thập nhiều số liệu cũng không tạo giá trị.

Ví dụ: “Trong sprint tới, chúng ta có khả năng bổ sung regression test cho hai vùng mã, nên chọn vùng nào?”

### Bước 2 — Xác định phạm vi và cửa sổ

Chọn repository/module, commit, cửa sổ **90 ngày thay đổi** và **180 ngày lỗi**, cách tính PR, cách nhận diện file rename. Các mốc này là ví dụ minh họa; nhóm phải chọn theo lịch làm việc thật.

### Bước 3 — Làm sạch và kiểm tra nguồn dữ liệu

Đánh dấu generated code, format-only, migration và đợt refactor đặc biệt. Liên kết issue/incident với vùng mã và ghi mức chắc chắn của liên kết.

Nếu dữ liệu thiếu, **không giả định bằng 0**; đánh dấu “chưa có dữ liệu đáng tin” để không xếp nhầm vùng vào nhóm rủi ro thấp.

### Bước 4 — Lập danh sách ứng viên

Kết hợp số thay đổi, bug được xác nhận, tác động nghiệp vụ, test yếu và độ phức tạp/coupling. Có thể dùng bảng hoặc quy tắc phân loại tường minh giống ví dụ Java phần 8.

Chỉ coi đây là **danh sách cần xem xét**, không tự động sinh yêu cầu viết lại toàn bộ những phần có điểm cao.

### Bước 5 — Review mã cùng người hiểu miền nghiệp vụ

Hỏi vì sao thay đổi thường xuyên, lỗi đến từ đâu, ranh giới có bị lẫn trách nhiệm không và test đang bảo vệ điều gì. Nếu một hotspot chủ yếu do tính năng phát triển nhanh và test tốt, có thể không cần refactor.

### Bước 6 — Chọn một cải thiện nhỏ, có mục tiêu

Ví dụ:

- Thêm regression test cho ngưỡng sai trước đây.
- Củng cố contract test khi adapter thay đổi phiên bản thường xuyên.
- Tách một quy tắc giá khỏi luồng I/O để kiểm thử độc lập.
- Thêm kiểm tra quyền theo đối tượng trên một endpoint có rủi ro.
- Làm rõ retry/idempotency cho một workflow từng ghi trùng.
- Ghi quyết định kiến trúc và ranh giới phụ thuộc tránh sửa lan rộng.

### Bước 7 — Đặt tiêu chí hoàn thành đúng bản chất

Không chỉ đặt “giảm số finding”. Có thể dùng:

- Lỗi cũ được tái hiện bởi test và không còn xảy ra sau sửa.
- Cập nhật chính sách giá chỉ cần thay tại một nơi được kiểm thử.
- Không còn phụ thuộc vòng giữa hai package đã thống nhất.
- Contract test phát hiện thay đổi schema gây lỗi trước triển khai.
- Incident cùng nguyên nhân không tái diễn trong giai đoạn theo dõi, dù vẫn cần xét mức tải và số thay đổi thực tế.

### Bước 8 — Đo lại và xem xét rủi ro chuyển chỗ

Sau refactor, một phần mã có thể đổi đường dẫn hoặc chuyển trách nhiệm sang class mới. Cần quan sát **toàn luồng**, không chỉ số liệu của tệp cũ. Nếu bug history biến mất khỏi báo cáo chỉ vì đổi tên file, kết luận “đã cải thiện” là không có căn cứ.

## 16. Mẫu ghi nhận một quyết định ưu tiên

Một mẫu ngắn cho phép người bảo trì sau này hiểu **vì sao vùng mã đã được chọn**, và **dữ liệu nào chỉ là giả thiết**.

~~~markdown
### QUALITY-HOTSPOT-007 — <vùng mã và mục tiêu>

Quyết định cần hỗ trợ:
- Ví dụ: ưu tiên regression test/refactor trong sprint tiếp theo.

Phạm vi và nguồn:
- Repository, commit, module:
- Cửa sổ thay đổi và quy tắc đếm PR/commit:
- Cửa sổ lỗi và cách xác nhận incident:
- Generated code, rename, format-only được xử lý thế nào:

Tín hiệu:
- Tần suất thay đổi:
- Code churn / co-change nếu phù hợp:
- Các lỗi đã xác nhận (đường dẫn ticket/incident):
- Rủi ro nghiệp vụ và mức độ sử dụng:
- Bằng chứng test, phụ thuộc và khả năng quan sát:
- Độ tin cậy và dữ liệu còn thiếu:

Giả thuyết:
- Nguyên nhân khiến thay đổi dễ sai hoặc khó sửa:
- Nếu giả thuyết đúng, cải thiện nào có ích?

Quyết định:
- Ưu tiên điều tra hoặc cải thiện nào? Vì sao?
- Vùng chưa chọn và lý do trì hoãn:
- Người phụ trách và phạm vi thay đổi nhỏ nhất:

Bằng chứng hoàn thành:
- Test/contract/review/measurement:
- Hành vi nghiệp vụ phải được giữ:
- Rủi ro mới hoặc đánh đổi phát sinh:

Điều kiện xem lại:
- Khi số lỗi, cách sử dụng, cơ cấu module hoặc dữ liệu đo thay đổi:
- Mốc và người chịu trách nhiệm rà soát:
~~~

Mẫu này không yêu cầu mỗi thay đổi nhỏ phải tạo một biên bản dài. Nó hữu ích với **quyết định có thể gây tranh luận hoặc ảnh hưởng đến nhiều sprint**, khi lịch sử và giả thiết cần được bàn giao.

## 17. Bài tập vận dụng

### Tình huống A — Module đổi nhiều nhưng chưa thấy lỗi

`CatalogAdapter` có 20 PR trong 90 ngày do đối tác cập nhật API. Không ghi nhận lỗi sản xuất, hợp đồng được kiểm thử và phần lớn PR chỉ thêm field không bắt buộc.

**Câu hỏi:** có nên lập tức viết lại toàn bộ adapter vì churn cao?

**Gợi ý:** chưa có đủ căn cứ. Thay đổi cao có thể phản ánh nhịp API ngoài; nên xem contract test, khả năng tương thích và mức công sức mỗi lần nâng phiên bản. Nếu những điều đó tốt, ưu tiên có thể thấp hơn các vùng có lỗi hoặc hậu quả lớn.

### Tình huống B — Chỉ một lỗi nhưng hậu quả rất nghiêm trọng

`AccessPolicy` chỉ sửa hai lần trong nửa năm. Tuy nhiên, một lỗi đã được xác nhận cho phép tài khoản thuộc tenant A đọc dữ liệu tenant B. Test hiện chỉ dùng một tenant.

**Câu hỏi:** số lần sửa thấp có đủ để hạ ưu tiên không?

**Gợi ý:** không. Tác động bảo mật và khoảng trống test làm khu vực này cần ưu tiên cao. Cần kiểm tra mọi đường đọc tương tự và thêm test nhiều tenant, tài khoản được phép/bị từ chối.

### Tình huống C — Churn tăng vì formatter

Sau khi bật một formatter mới, gần như mọi file Java đều có hàng nghìn dòng thay đổi. Báo cáo hotspot tuần đó đột nhiên đánh dấu toàn bộ repository rủi ro cao.

**Câu hỏi:** làm sao sửa cách diễn giải dữ liệu?

**Gợi ý:** xác định đợt thay đổi định dạng, ghi rõ phương pháp lọc hoặc báo riêng. Không dùng churn do formatting như bằng chứng các quy tắc nghiệp vụ đột nhiên khó bảo trì hơn.

### Tình huống D — Một incident sửa nhiều file

Một sự cố tính giá khiến đội ngũ sửa `PricingPolicy`, `CheckoutService`, `OrderController` và test. Công cụ đếm bốn commit/tệp rồi báo “bốn bug”.

**Câu hỏi:** lỗi nằm ở cách đếm nào?

**Gợi ý:** số file sửa và số incident không cùng đơn vị. Cần giữ incident ID, phân biệt nguyên nhân gốc và nơi cần thay đổi để khắc phục, không nhân số lỗi theo file/commit.

### Tình huống E — Coverage cao, hồi quy vẫn lặp lại

Một package tính phí có branch coverage cao nhưng hai lần sai ở ngưỡng miễn phí vận chuyển vì test chỉ dùng số thấp hơn và cao hơn ngưỡng.

**Câu hỏi:** nên đầu tư ở đâu trước khi refactor lớn?

**Gợi ý:** bổ sung test dựa trên đặc tả ở đúng ngưỡng, dưới ngưỡng và trên ngưỡng; xem oracle của test. Coverage cao không chứng minh dữ liệu biên đã được kiểm tra.

### Tình huống F — Số bug ít vì thiếu monitoring

Một worker mới xử lý hàng đợi không có dashboard lỗi, không theo dõi dead-letter và chưa liên kết retry thất bại với ticket. Báo cáo hiển thị `confirmedDefects = 0`.

**Câu hỏi:** có nên gán ưu tiên `LOW` không?

**Gợi ý:** không nên suy ra an toàn từ dữ liệu thiếu. Ghi mức tin cậy thấp, xác định khả năng quan sát và các tình huống lỗi quan trọng trước khi quyết định. Có thể cần bổ sung monitoring và integration test làm bước đầu.

### Tình huống G — Hai người chạm nhiều mã bị đánh giá cá nhân

Một module đang đổi kiến trúc có nhiều PR và lỗi hồi quy. Quản lý muốn dùng bảng hotspot để xếp hạng lập trình viên sửa nhiều file nhất là người làm việc kém.

**Câu hỏi:** điều gì sai trong cách sử dụng chỉ số?

**Gợi ý:** số lần chạm file và số lỗi được báo cáo phản ánh công việc, phạm vi, quy trình và bối cảnh, không trực tiếp đo năng lực cá nhân. Dùng dữ liệu để nhận diện hệ thống cần cải thiện và phân bổ hỗ trợ, tránh tạo động cơ che giấu lỗi hoặc ngại sửa phần khó.

## 18. Những ngộ nhận thường gặp

**“File thay đổi nhiều chắc là code xấu.”** Không. Nó có thể là vùng phát triển nhanh, có test tốt và trách nhiệm rõ. Cần xem nguyên nhân thay đổi và tác động thật.

**“Không có bug được báo nghĩa là không có bug.”** Không. Thiếu sử dụng, thiếu quan sát hoặc thiếu văn hóa ghi nhận có thể che nhiều lỗi.

**“Cứ cộng số commit và số bug là có risk score.”** Không đủ. Thang đo, thời gian, độ tin cậy và hậu quả rất khác nhau. Một điểm tổng hợp cần được giải thích và kiểm chứng.

**“Cùng xuất hiện trong PR là phụ thuộc kiến trúc xấu.”** Chưa chắc. Code và test thường phải thay cùng nhau; một use case hợp lý cũng có nhiều lớp liên quan.

**“File có nhiều bug fix tức là tác giả tệp đó gây nhiều bug.”** Không. Bug fix có thể khắc phục lỗi từ dữ liệu, hệ thống ngoài hoặc quyết định kiến trúc cũ. Không suy năng lực cá nhân từ số đếm này.

**“Coverage cao thì vùng được ưu tiên đã an toàn.”** Không. Test có thể chạy qua mã nhưng thiếu oracle, dữ liệu biên hoặc kiểm tra tích hợp.

**“Thứ hạng hotspot là thứ tự refactor bắt buộc.”** Không. Nó là thứ tự điều tra; có vùng chỉ cần thêm test, có vùng chưa cần thay đổi.

**“Giảm LOC, churn hoặc Cyclomatic Complexity chứng minh cải thiện.”** Không riêng lẻ. Phải giữ hành vi và quan sát xem thay đổi có thực sự dễ và ít lỗi hơn không.

**“Mã cũ ít sửa luôn nên bỏ qua.”** Không nếu nó giữ dữ liệu quan trọng hoặc có rủi ro cao; hậu quả có thể quan trọng hơn tần suất sửa.

**“Số liệu từ các tool luôn so sánh trực tiếp được.”** Không. Phải hiểu định nghĩa, phiên bản, phạm vi và cách gắn lỗi của từng nguồn.

**“Có thể dùng một bảng metric để thay review nghiệp vụ.”** Không. Người hiểu hệ thống phải xác định tài sản, hợp đồng và hậu quả khi sai, những điều nhiều công cụ không tự suy ra.

**“Sau khi chia module, hotspot cũ biến mất thì vấn đề đã được giải quyết.”** Không chắc. Có thể chỉ đổi nơi đặt mã; phải theo dõi toàn bộ trách nhiệm qua chuyển đổi.

## 19. Checklist khi dùng lịch sử thay đổi và lỗi để ưu tiên

- **Quyết định:** bảng số liệu dùng để chọn review, test, refactor hay xử lý bảo mật?
- **Phạm vi:** đo file, class, package, module hay luồng nghiệp vụ?
- **Thời gian:** có cùng cửa sổ và định nghĩa đếm rõ cho mỗi phép đo?
- **Nguồn Git:** có xử lý merge, rename, revert, generated code và format-only?
- **Nguồn lỗi:** bug đã xác nhận, incident và PR có được liên kết đúng, không đếm trùng?
- **Độ tin cậy:** số 0 là thật sự không ghi nhận lỗi hay thiếu dữ liệu?
- **Bối cảnh:** có xem mức sử dụng, loại thay đổi, yêu cầu nghiệp vụ và hậu quả khi sai?
- **Kiểm thử:** coverage có đi kèm oracle, trường hợp biên và test tích hợp thích hợp?
- **Cấu trúc:** churn hoặc co-change có phản ánh coupling và trách nhiệm bị trộn thật không?
- **Ưu tiên:** tiêu chí có giải thích được, tránh trọng số tùy ý và kết luận tuyệt đối?
- **Hành động:** đã chọn một cải thiện có mục tiêu và bảo vệ hành vi bằng test?
- **Đánh giá lại:** có theo dõi lỗi tái phát, chi phí thay đổi và các rủi ro chuyển sang nơi khác?
- **Đạo đức sử dụng:** chỉ số có được dùng để cải thiện hệ thống, không làm méo hành vi ghi nhận lỗi hoặc đánh giá phiến diện cá nhân?

**Tần suất thay đổi và lịch sử lỗi là những tín hiệu giúp tìm vùng đáng đầu tư, không phải thước đo đầy đủ của chất lượng mã.** Khi đặt chúng bên cạnh mức quan trọng nghiệp vụ, ranh giới trách nhiệm và bằng chứng kiểm thử, nhóm có thể chọn đúng nơi cần cải thiện, với thay đổi nhỏ và kết quả có thể kiểm chứng. Đó là cách dùng **chỉ số chất lượng** để giúp mã trong **CODE_QUALITY_FUNDAMENTALS** ngày càng **đáng tin cậy, dễ hiểu và dễ thay đổi**, thay vì chỉ làm một biểu đồ trông đẹp hơn.
