# Độ phức tạp và phân bố các điểm khó hiểu

Một dự án Java có hàng trăm phương thức. Công cụ phân tích báo độ phức tạp trung bình khá thấp, nhưng mỗi lần sửa chức năng hoàn tiền, nhóm vẫn mất nhiều ngày để hiểu các nhánh điều kiện và xử lý hồi quy. Trong khi đó, một phương thức parser rất dài ở thư viện nội bộ gần như không thay đổi trong nhiều năm lại thường đứng đầu bảng xếp hạng độ phức tạp. Nếu chỉ nhìn một điểm số trung bình hoặc chọn phương thức có điểm lớn nhất để refactor, nhóm có thể đầu tư sai chỗ.

Vấn đề không chỉ là **mã phức tạp đến mức nào**, mà còn là **độ phức tạp tập trung ở đâu, có thường xuyên bị tác động không và ảnh hưởng thế nào tới công việc thực tế**.

Trong chương **Chỉ số chất lượng** của module `CODE_QUALITY_FUNDAMENTALS`, việc đo lường được sử dụng để hiểu những yếu tố khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Các chỉ số như cyclomatic complexity, độ sâu lồng nhau, kích thước phương thức hoặc tần suất sửa đổi có thể cung cấp dấu hiệu về điểm khó hiểu. Nhưng chúng chỉ là **tín hiệu để điều tra**, không phải một phép đo duy nhất cho chất lượng phần mềm.

Sau bài học, bạn có thể:

- Phân biệt độ phức tạp điều khiển, độ phức tạp nhận thức, độ phức tạp cấu trúc và độ phức tạp nghiệp vụ.
- Hiểu các chỉ số phổ biến và giới hạn của chúng trong Java.
- Đọc **phân bố** chỉ số theo phương thức, lớp, package thay vì chỉ nhìn trung bình của toàn dự án.
- Nhận diện **hotspot** bằng cách kết hợp mức khó hiểu với tần suất thay đổi, lỗi và mức độ quan trọng của chức năng.
- Phân tích một đoạn Java nhiều nhánh, refactor có kiểm soát và kiểm tra hành vi vẫn tương đương.
- Thiết kế một bảng theo dõi chất lượng có thể dùng cho quyết định bảo trì, tránh “làm đẹp điểm số” mà không cải thiện thực tế.

## 1. Độ phức tạp có nhiều chiều

Không có một con số duy nhất mô tả đầy đủ việc đọc, hiểu và thay đổi mã.

| Chiều phức tạp | Câu hỏi chính | Dấu hiệu thường quan sát |
| --- | --- | --- |
| **Luồng điều khiển** | Có bao nhiêu lựa chọn và nhánh cần xét? | `if`, `switch`, vòng lặp, đường thoát, điều kiện kết hợp |
| **Nhận thức** | Người đọc phải ghi nhớ bao nhiêu trạng thái và ngữ cảnh cùng lúc? | Lồng nhiều tầng, tên thiếu nghĩa, điều kiện phủ định, luồng khó theo |
| **Dữ liệu và trạng thái** | Có bao nhiêu tổ hợp trạng thái hoặc bất biến liên quan? | Cờ boolean, nullable state, mutable state, chuyển trạng thái |
| **Cấu trúc** | Muốn hiểu một hành vi phải qua bao nhiêu thành phần? | Gọi nhiều tầng, phụ thuộc vòng, coupling, fan-out lớn |
| **Nghiệp vụ** | Bản thân bài toán có bao nhiêu quy tắc thực sự? | Thuế, phân quyền, chính sách giá, ngoại lệ theo quốc gia |
| **Vận hành** | Hành vi phụ thuộc bao nhiêu hệ thống hoặc điều kiện bên ngoài? | Database, mạng, concurrency, retry, transaction |

Độ phức tạp **vốn có** của nghiệp vụ không thể biến mất chỉ bằng cách chia phương thức. Ví dụ tính thuế đa quốc gia đòi hỏi nhiều quy tắc thực; tách chúng thành các thành phần có tên rõ có thể giúp hiểu tốt hơn, nhưng không làm mất các quy tắc ấy.

Ngược lại, độ phức tạp **do thiết kế tạo thêm** có thể giảm: cờ truyền qua nhiều tầng, các nhánh kiểm tra lặp lại, tên `process()` khó hiểu hoặc một máy thực thi quy tắc tổng quát cho bài toán nhỏ.

Đây là lý do một chỉ số có thể hữu ích nhưng không đủ: mã ít nhánh vẫn có thể khó hiểu vì phụ thuộc ẩn, còn mã nhiều nhánh có thể là một bảng chuyển trạng thái được tổ chức tốt.

## 2. Cyclomatic complexity: dấu hiệu về số đường đi điều khiển

**Cyclomatic complexity** thường được dùng để ước lượng độ phức tạp của luồng điều khiển. Ở mức khái niệm, với đồ thị luồng điều khiển liên thông phù hợp, có thể biểu diễn:

\[
V(G) = E - N + 2
\]

Trong đó `E` là số cạnh và `N` là số nút của đồ thị. Với một số dạng chương trình có cấu trúc, cách đếm trực quan là bắt đầu từ 1 rồi cộng những điểm quyết định làm tăng số đường đi độc lập.

Xét phương thức Java:

```java
boolean shouldNotify(Order order) {
    if (order.cancelled()) {
        return false;
    }

    if (order.totalVnd() >= 500_000L) {
        return true;
    }

    return order.vip();
}
```

Theo cách đếm minh họa **1 điểm cơ sở + 2 câu lệnh `if`**, cyclomatic complexity là **3**. Người đọc có thể cần xem các nhánh “đã hủy”, “đạt ngưỡng” và “không đạt ngưỡng nhưng VIP” khi kiểm thử.

Điểm quan trọng:

- Cyclomatic complexity liên quan đến **cấu trúc đường đi**, không nói một nhánh có khó hiểu về nghiệp vụ hay không.
- Điểm cao có thể gợi ý nơi cần kiểm tra nhiều tình huống hơn, nhưng **không có quy tắc “điểm là N thì chỉ cần N test”**. Các điều kiện kết hợp, ngoại lệ, dữ liệu và bất biến có thể đòi hỏi test khác.
- Công cụ có thể khác nhau ở cách đếm toán tử `&&`/`||`, `switch`, biểu thức điều kiện, ngoại lệ hoặc cú pháp ngôn ngữ. Phải đọc định nghĩa chỉ số của công cụ trước khi so sánh.
- Cộng điểm giữa các phương thức hoặc phiên bản chỉ có nghĩa khi cùng định nghĩa, cùng phạm vi đo và điều kiện tương đương.

### Một ví dụ có nhiều nhánh hơn

```java
long deliveryFee(Order order) {
    if (order.digitalOnly()) {
        return 0L;
    }
    if (order.remoteArea()) {
        return 60_000L;
    }
    if (order.vip()) {
        return 0L;
    }
    if (order.totalVnd() >= 500_000L) {
        return 0L;
    }
    return 25_000L;
}
```

Theo quy ước đếm đơn giản trên: cơ sở 1 + bốn `if` = **5**. Đếm này hữu ích để mô tả cấu trúc, nhưng điều quan trọng hơn là **thứ tự ưu tiên**: đơn hàng vùng xa trả 60.000 VND trước khi xét VIP và ngưỡng miễn phí. Đảo thứ tự hai nhánh có thể đổi hành vi mà điểm cyclomatic vẫn bằng 5.

Vì vậy, một thay đổi giữ nguyên điểm complexity chưa chắc giữ nguyên logic.

## 3. Cognitive complexity: mức khó theo dõi luồng khi đọc

Cyclomatic complexity chủ yếu quan sát đồ thị điều khiển. **Cognitive complexity** cố gắng phản ánh khó khăn khi người đọc phải theo nhiều nhánh và mức lồng nhau. Các công cụ có thể áp dụng quy tắc tính điểm riêng; không nên tự khẳng định một con số chính xác nếu chưa dùng định nghĩa của công cụ cụ thể.

Xem phương thức sau:

```java
String refundStatus(RefundRequest request) {
    if (request.paymentCaptured()) {
        if (!request.alreadyRefunded()) {
            if (request.withinRefundWindow()) {
                if (request.amountVnd() <= 1_000_000L
                        || request.managerApproved()) {
                    return "APPROVED";
                }
                return "NEEDS_APPROVAL";
            }
            return "EXPIRED";
        }
        return "ALREADY_REFUNDED";
    }
    return "NOT_CAPTURED";
}
```

Người đọc phải giữ ngữ cảnh của nhiều `if` lồng nhau để hiểu nhánh ở mức sâu nhất. Mỗi lần xuống sâu là thêm điều kiện ngầm: “đã thu tiền, chưa hoàn, còn hạn…”.

Một phiên bản sử dụng **guard clauses** diễn đạt thứ tự kiểm tra bằng các điều kiện loại trừ sớm:

```java
String refundStatus(RefundRequest request) {
    if (!request.paymentCaptured()) {
        return "NOT_CAPTURED";
    }
    if (request.alreadyRefunded()) {
        return "ALREADY_REFUNDED";
    }
    if (!request.withinRefundWindow()) {
        return "EXPIRED";
    }
    if (request.amountVnd() > 1_000_000L
            && !request.managerApproved()) {
        return "NEEDS_APPROVAL";
    }
    return "APPROVED";
}
```

Hai phiên bản có **cùng bốn câu lệnh `if`** theo cách đếm đơn giản, nhưng phiên bản sau không yêu cầu theo dõi nhiều mức lồng nhau. Đây là ví dụ vì sao một chỉ số nhận thức có thể bổ sung thông tin mà cyclomatic complexity bỏ sót.

Lưu ý:

- Các đoạn mã là minh họa; kiểu `RefundRequest` và hợp đồng sẽ được định nghĩa đầy đủ ở phần thực hành.
- Không phải mọi `if` lồng nhau đều xấu. Có trường hợp cấu trúc phân cấp phản ánh chính xác mối quan hệ nghiệp vụ và dễ đọc hơn guard clauses.
- Giảm mức lồng nhau chỉ có giá trị khi **thứ tự kiểm tra, tác dụng phụ và ngoại lệ được giữ đúng**.

## 4. Độ sâu lồng nhau, kích thước và số lượng phụ thuộc

Ngoài hai loại complexity trên, các số đo khác giúp nêu câu hỏi về khả năng bảo trì:

| Chỉ số | Có thể gợi ý điều gì? | Điều nó không chứng minh |
| --- | --- | --- |
| **Độ sâu lồng nhau lớn nhất** | Người đọc phải giữ nhiều điều kiện cùng lúc | Không chứng minh mọi lồng nhau đều khó hiểu |
| **Độ dài phương thức / số dòng** | Nhiều trách nhiệm hoặc nhiều chi tiết trong một chỗ | Mã dài chưa chắc phức tạp; bảng dữ liệu có thể dài mà rõ |
| **Số tham số** | API đòi hỏi nhiều đầu vào, có thể thiếu mô hình | Hàm có nhiều tham số không tự động sai |
| **Fan-out / số phụ thuộc** | Một thành phần phải biết nhiều dịch vụ/lớp khác | Các phụ thuộc có thể là ranh giới nghiệp vụ hợp lý |
| **Fan-in / số nơi gọi** | Thay đổi một thành phần có thể ảnh hưởng rộng | Nhiều nơi dùng có thể là tái sử dụng tốt |
| **Duplication** | Một quy tắc bị sao chép dễ lệch khi sửa | Những đoạn giống cú pháp chưa chắc có cùng lý do thay đổi |
| **Churn / tần suất thay đổi** | Vùng mã bị chỉnh sửa thường xuyên | Churn cao có thể do phát triển chủ động, không phải lỗi |
| **Bug history / sự cố** | Vùng mã có lỗi đã quan sát | Ít lỗi được báo có thể do ít người sử dụng hoặc thiếu giám sát |

Các chỉ số khác nhau có thể xung đột. Một phương thức 80 dòng chứa tên rõ và nhiều trường hợp nhỏ có thể dễ hiểu hơn một pipeline 10 dòng chuyển qua tám lớp tổng quát với `Object` và `Map`.

Đừng chỉ đếm dòng, tên lớp hoặc số lệnh `if` rồi kết luận mã tốt/xấu. Hãy luôn hỏi **thao tác bảo trì nào đang bị cản trở** và chỉ số nào có thể giúp điều tra nguyên nhân.

## 5. Phân bố quan trọng hơn một giá trị trung bình

Giả sử hai module đều có cyclomatic complexity **trung bình bằng 3** trên sáu phương thức:

```text
Module A: 3, 3, 3, 3, 3, 3
Module B: 1, 1, 1, 1, 1, 13

Trung bình A = (3+3+3+3+3+3)/6 = 3
Trung bình B = (1+1+1+1+1+13)/6 = 3
```

Nếu chỉ xem trung bình, hai module giống nhau. Nhưng module B chứa một phương thức có nhiều nhánh, có thể là điểm cần xem kỹ. Module A trải độ phức tạp đều qua các phương thức nhỏ.

Một ví dụ tám phương thức khác:

```text
Điểm cyclomatic đã đo (giả định):
2, 2, 3, 3, 4, 4, 5, 25

Tổng điểm = 48
Trung bình = 6
Trung vị = (3 + 4) / 2 = 3,5
Phương thức lớn nhất = 25 điểm
Tỷ phần của phương thức lớn nhất = 25 / 48 ≈ 52,1%
```

Chỉ một phương thức đóng góp hơn một nửa tổng điểm trong ví dụ này. Đây là dấu hiệu **phân bố lệch**: phần khó có thể tập trung vào rất ít vị trí.

Tuy nhiên, `25/48` là **tỷ phần của tổng điểm số đo** theo quy ước, **không phải** “52,1% độ khó hiểu của hệ thống” hay xác suất gây lỗi. Tổng điểm cyclomatic không có đơn vị vật lý tương ứng với mức đau đầu của người đọc.

### Những phép tóm tắt hữu ích khi đọc phân bố

- **Trung vị:** giá trị điển hình, ít bị một vài điểm cực lớn kéo lên so với trung bình.
- **Phân vị p90/p95:** cho biết mức điểm ở vùng đuôi phân bố; cần thống nhất phương pháp nội suy nếu các công cụ khác nhau.
- **Giá trị lớn nhất / top-N:** nêu vị trí cần đọc thủ công.
- **Số và tỷ lệ phương thức vượt ngưỡng:** hỗ trợ theo dõi sự xuất hiện của vùng rủi ro theo quy ước đã thống nhất.
- **Tỷ phần điểm nằm trong top 10% phương thức:** giúp quan sát mức tập trung; phải so sánh với chính nó theo thời gian và giữ cùng định nghĩa.
- **Đường phân bố/histogram:** cho biết có nhiều phương thức phức tạp vừa hay chỉ một vài ngoại lệ.

Phân vị ở mẫu rất nhỏ dễ bị tác động bởi một phương thức. Vì vậy, ở module chỉ có 6–8 phương thức, danh sách từng điểm có thể có ích hơn biểu đồ p95 trông “chính xác” nhưng thiếu thông tin.

## 6. Vẽ bản đồ các điểm khó hiểu thay vì một điểm số toàn dự án

Một dashboard tốt giúp người bảo trì đi từ **số đo → vị trí → nguyên nhân → quyết định**.

Ví dụ báo cáo giả định:

| Vị trí | Cyclomatic | Độ sâu lồng tối đa | Thay đổi trong 90 ngày | Lỗi đã ghi nhận | Nhận xét cần xác minh |
| --- | ---: | ---: | ---: | ---: | --- |
| `RefundPolicy.decide` | 18 | 5 | 14 | 3 | Có nhiều nhánh và thay đổi liên tục |
| `LegacyCsvParser.parse` | 31 | 4 | 0 | 0 | Điểm cao nhưng ổn định, có thể là logic định dạng khó tránh |
| `PromotionService.apply` | 12 | 3 | 21 | 2 | Quy tắc biến động, nguy cơ hồi quy |
| `HealthController.ping` | 1 | 0 | 8 | 0 | Thay đổi nhiều nhưng logic rất đơn giản |
| `OrderRepository.findPage` | 4 | 1 | 17 | 1 | Điểm nhánh thấp; cần xem SQL, I/O và quyền truy cập |

**Mọi số liệu trong bảng đều là ví dụ giả định để luyện đọc chỉ số**, không phải báo cáo của repository thực.

Một thứ tự điều tra hợp lý có thể là:

1. Xem `RefundPolicy.decide` và `PromotionService.apply` vì vừa có độ phức tạp đáng kể vừa thường xuyên thay đổi và đã có lỗi.
2. Chưa vội refactor `LegacyCsvParser.parse` chỉ vì điểm cao; cần xem yêu cầu thay đổi, test và rủi ro trong tương lai.
3. Với `OrderRepository.findPage`, điểm cyclomatic thấp không loại trừ truy vấn chậm, SQL phức tạp hoặc rủi ro phân quyền.

**Hotspot** không nhất thiết là phương thức đứng đầu mỗi bảng. Đó thường là vị trí mà **độ khó kỹ thuật trùng với áp lực thay đổi hoặc tác động nghiệp vụ**, khiến nhóm thường xuyên trả chi phí bảo trì.

### Quan sát ở nhiều cấp

```text
Repository
    |
    +-- Module/package: khu vực nào có đuôi phức tạp rõ?
    |       |
    |       +-- Class: nhiều phương thức phức tạp tập trung không?
    |               |
    |               +-- Method: những nhánh và trạng thái nào khó hiểu?
    |
    +-- Lịch sử thay đổi: file/class nào bị sửa thường xuyên?
    |
    +-- Nghiệp vụ: luồng nào nhạy với lỗi, tiền hoặc quyền?
```

Không cần đặt mọi số liệu thành một “điểm chất lượng tổng hợp” thiếu giải thích. Bản đồ thường hữu ích hơn khi cho phép drill-down và giữ thông tin từng chỉ số.

## 7. Kết hợp độ phức tạp với tần suất thay đổi

Một phương pháp thực dụng là xem hai trục:

- **Mức phức tạp hoặc khó hiểu:** số liệu tĩnh, kết hợp đánh giá của người đọc.
- **Tần suất thay đổi (*churn*):** số lần sửa, phạm vi thay đổi hoặc lịch sử chỉnh sửa trong một khoảng thời gian xác định.

Ma trận ưu tiên mang tính định hướng:

| | Ít thay đổi | Thay đổi thường xuyên |
| --- | --- | --- |
| **Độ phức tạp thấp** | Theo dõi thông thường | Giữ test và hợp đồng rõ khi thay đổi |
| **Độ phức tạp cao** | Xem rủi ro khi phải sửa; chưa chắc ưu tiên ngay | Ứng viên tốt để điều tra, tăng kiểm thử và cải thiện thiết kế |

Mã phức tạp nhưng ổn định có thể gây ít chi phí hằng ngày hơn mã phức tạp mà mỗi tuần đều phải sửa. Ngược lại, một bộ giải mã định dạng bảo mật hiếm thay đổi vẫn có thể cần ưu tiên kiểm tra nếu một lỗi ở đó gây hậu quả nghiêm trọng.

### Dùng lịch sử Git có giới hạn

Lịch sử version control có thể chỉ ra file nào thay đổi thường xuyên, nhưng có những cạm bẫy:

- Một commit format toàn dự án có thể làm churn tăng mạnh mà không có thay đổi logic.
- Rename/move có thể làm lịch sử file đứt đoạn nếu phương pháp truy xuất không theo dõi đổi tên.
- Git ghi thay đổi chủ yếu theo file/diff; quy kết chính xác churn cho **một phương thức** thường cần phân tích bổ sung, không thể suy ra chỉ từ `git log --stat`.
- File lớn dễ bị chạm hơn file nhỏ; có thể cần xem tỷ lệ, phạm vi và mục đích thay đổi.
- Số commit phụ thuộc cách nhóm squash/merge và chia công việc; không phải thước đo phổ quát.
- “Không có commit” không đồng nghĩa “không rủi ro”, đặc biệt ở mã quan trọng nhưng ít được thử thách.

Giả sử đo trên 90 ngày, cần ghi rõ cửa sổ thời gian, phạm vi file, có loại commit định dạng và mã sinh tự động hay không. Đừng đem con số “20 lần sửa” từ hai nhóm có cách commit khác hẳn so trực tiếp rồi kết luận nhóm nào viết mã kém.

## 8. Tác động nghiệp vụ, test và lịch sử lỗi thay đổi cách ưu tiên

Độ phức tạp là một yếu tố; rủi ro thực tế còn phụ thuộc hậu quả khi lỗi xảy ra và khả năng phát hiện lỗi.

Ví dụ:

- Một phương thức xử lý quyền truy cập có cyclomatic complexity 8 nhưng chỉ một lỗi có thể làm lộ dữ liệu.
- Một bộ định dạng chuỗi có điểm 25, chỉ dùng nội bộ và có test bao phủ tốt.
- Một hàm tính chiết khấu điểm 12, thay đổi mỗi tuần và thường bị regression.
- Một pipeline có ít nhánh nhưng cập nhật nhiều bảng không có transaction.

Nếu chỉ chọn **điểm complexity lớn nhất**, ta có thể bỏ qua điểm rủi ro thực sự.

Một bảng điều tra hữu ích có thể giữ những trường sau:

| Thuộc tính | Câu hỏi |
| --- | --- |
| Complexity | Có nhiều quyết định, lồng nhau hoặc phụ thuộc khó theo không? |
| Churn | Có bị chỉnh sửa thường xuyên ở giai đoạn gần đây không? |
| Lỗi | Có sự cố hoặc lỗi hồi quy đã quan sát không? |
| Tác động | Sai sót ảnh hưởng tiền, dữ liệu, quyền hay chỉ hiển thị? |
| Test | Có bài test mô tả những nhánh và bất biến quan trọng không? |
| Ownership | Có người hiểu và duy trì rõ ràng không? |
| Kế hoạch | Chức năng có sắp thay đổi lớn không? |

Không nhất thiết nhân các cột thành một điểm rủi ro. Nếu nhóm có một công thức xếp hạng nội bộ, cần công khai trọng số và kiểm chứng bằng các trường hợp thực. Một phép nhân `complexity × churn` có thể giúp tạo danh sách ban đầu nhưng không thể thay thế đánh giá tác động nghiệp vụ.

## 9. Ví dụ thực hành Java: từ lồng nhau sang luồng quyết định rõ

Giả sử hệ thống có quy tắc hoàn tiền đơn giản:

- Chỉ xét hoàn tiền cho giao dịch đã thu tiền.
- Không hoàn hai lần.
- Chỉ hoàn trong thời hạn quy định.
- Khoản hoàn **lớn hơn** 1.000.000 VND cần quản lý phê duyệt.
- Khoản hoàn bằng đúng 1.000.000 VND **không** cần bước phê duyệt bổ sung.

Mô hình dữ liệu và kết quả:

```java
record RefundRequest(
        long amountVnd,
        boolean paymentCaptured,
        boolean alreadyRefunded,
        boolean withinRefundWindow,
        boolean managerApproved
) {
    RefundRequest {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("Refund amount must be positive");
        }
    }
}

enum RefundDecision {
    NOT_CAPTURED,
    ALREADY_REFUNDED,
    EXPIRED,
    NEEDS_APPROVAL,
    APPROVED
}
```

Một bản đầu với nhiều tầng lồng nhau:

```java
final class LegacyRefundPolicy {
    RefundDecision decide(RefundRequest request) {
        if (request.paymentCaptured()) {
            if (!request.alreadyRefunded()) {
                if (request.withinRefundWindow()) {
                    if (request.amountVnd() <= 1_000_000L
                            || request.managerApproved()) {
                        return RefundDecision.APPROVED;
                    }
                    return RefundDecision.NEEDS_APPROVAL;
                }
                return RefundDecision.EXPIRED;
            }
            return RefundDecision.ALREADY_REFUNDED;
        }
        return RefundDecision.NOT_CAPTURED;
    }
}
```

Ta có thể viết lại theo những điều kiện loại trừ sớm:

```java
final class RefundPolicy {
    private static final long APPROVAL_THRESHOLD_VND = 1_000_000L;

    RefundDecision decide(RefundRequest request) {
        if (!request.paymentCaptured()) {
            return RefundDecision.NOT_CAPTURED;
        }
        if (request.alreadyRefunded()) {
            return RefundDecision.ALREADY_REFUNDED;
        }
        if (!request.withinRefundWindow()) {
            return RefundDecision.EXPIRED;
        }
        if (request.amountVnd() > APPROVAL_THRESHOLD_VND
                && !request.managerApproved()) {
            return RefundDecision.NEEDS_APPROVAL;
        }
        return RefundDecision.APPROVED;
    }
}
```

Bản sau có những ưu điểm có thể quan sát:

- Các **lý do từ chối** xuất hiện theo thứ tự ưu tiên; người đọc không phải giữ bốn tầng điều kiện.
- Ngưỡng có tên và đơn vị `VND`.
- Mỗi nhánh trả một giá trị `RefundDecision` rõ ý nghĩa, không dùng chuỗi tự do.
- Có thể thêm test ngay tại ranh giới `1_000_000L` và `1_000_001L`.

Cả hai vẫn có **bốn `if`**; do đó, theo cách tính cyclomatic đơn giản ở phần đầu, điểm **không nhất thiết giảm**. Tuy nhiên, độ sâu lồng giảm và cách đọc luồng nghiệp vụ có thể rõ hơn.

Đây là một bài học quan trọng: **refactor thành công không bắt buộc mọi chỉ số cùng giảm**.

### Refactor có thể làm đổi hành vi nếu không kiểm tra biên

Nếu viết `amountVnd() >= APPROVAL_THRESHOLD_VND` thay vì `>`, khoản hoàn bằng đúng 1.000.000 VND sẽ phải xin phê duyệt, trái với yêu cầu đã nêu. Điểm complexity có thể vẫn y nguyên.

Tương tự, đổi thứ tự kiểm tra `alreadyRefunded` và `withinRefundWindow` có thể thay lý do từ chối mà API trả ra. Khi lý do là một phần hợp đồng, không được coi đó là thay đổi thuần cấu trúc.

## 10. Kiểm chứng tính tương đương và bao phủ các nhánh

Một bộ test theo hành vi nên xác nhận các trường hợp quan trọng:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Giao dịch chưa thu tiền | `NOT_CAPTURED` |
| Đã thu tiền nhưng đã hoàn | `ALREADY_REFUNDED` |
| Chưa hoàn nhưng hết hạn | `EXPIRED` |
| Hợp lệ, số tiền 1.000.000 VND, chưa được duyệt | `APPROVED` |
| Hợp lệ, số tiền 1.000.001 VND, chưa được duyệt | `NEEDS_APPROVAL` |
| Hợp lệ, số tiền lớn, đã được duyệt | `APPROVED` |

Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RefundPolicyTest {
    private final RefundPolicy policy = new RefundPolicy();

    @Test
    void checksPriorityAndApprovalBoundary() {
        assertEquals(RefundDecision.NOT_CAPTURED,
                policy.decide(new RefundRequest(100L, false, false, true, true)));
        assertEquals(RefundDecision.ALREADY_REFUNDED,
                policy.decide(new RefundRequest(100L, true, true, true, true)));
        assertEquals(RefundDecision.EXPIRED,
                policy.decide(new RefundRequest(100L, true, false, false, true)));
        assertEquals(RefundDecision.APPROVED,
                policy.decide(new RefundRequest(1_000_000L, true, false, true, false)));
        assertEquals(RefundDecision.NEEDS_APPROVAL,
                policy.decide(new RefundRequest(1_000_001L, true, false, true, false)));
        assertEquals(RefundDecision.APPROVED,
                policy.decide(new RefundRequest(1_000_001L, true, false, true, true)));
    }

    @Test
    void newImplementationMatchesOldOnSelectedDomain() {
        LegacyRefundPolicy oldPolicy = new LegacyRefundPolicy();

        for (boolean captured : new boolean[] {false, true}) {
            for (boolean refunded : new boolean[] {false, true}) {
                for (boolean withinWindow : new boolean[] {false, true}) {
                    for (boolean managerApproved : new boolean[] {false, true}) {
                        for (long amount : new long[] {1L, 1_000_000L, 1_000_001L}) {
                            RefundRequest request = new RefundRequest(
                                    amount, captured, refunded, withinWindow,
                                    managerApproved);
                            assertEquals(
                                    oldPolicy.decide(request),
                                    policy.decide(request));
                        }
                    }
                }
            }
        }
    }
}
```

Vòng lặp cuối kiểm tra **48 tổ hợp** của bốn cờ boolean và ba mức tiền được chọn (2 × 2 × 2 × 2 × 3). Nó tạo bằng chứng về tính tương đương **trên tập đã thử**, không phải chứng minh mọi giá trị `long` và mọi tình huống ngoài phạm vi đều tương đương.

Sự có mặt của test này **không tự làm điểm complexity trong production giảm**. Đừng “tối ưu điểm” bằng cách bỏ đi những trường hợp test thiết yếu. Mục tiêu là giảm rủi ro khi sửa mã, không giảm số điều kiện trong bộ kiểm thử.

### Nhận thức về coverage

- **Line coverage:** dòng nào được thực thi trong test.
- **Branch coverage:** những nhánh quyết định nào được đi qua.
- **Mutation testing:** thay đổi có chủ đích một phần logic để xem test có phát hiện hay không.
- **Kiểm thử theo bất biến nghiệp vụ:** xác nhận các điều kiện mà hệ thống phải luôn giữ đúng.

Coverage cao không tự bảo đảm đúng. Test có thể đi qua mọi nhánh mà không assert kết quả quan trọng. Với một đoạn code phức tạp, cần dựa trên quy tắc nghiệp vụ, các giá trị biên và rủi ro để thiết kế ca kiểm thử.

## 11. Đo lại sau refactor: đừng chỉ tìm một con số thấp hơn

Sau khi sửa `RefundPolicy`, một bảng đối chiếu có thể trông như sau:

| Chỉ số/quan sát | Trước | Sau | Cách diễn giải |
| --- | --- | --- | --- |
| Số `if` trực tiếp | 4 | 4 | Điểm cyclomatic theo quy tắc minh họa không đổi |
| Độ sâu lồng tối đa của `if` | 4 | 1 | Giảm ngữ cảnh lồng nhau |
| Tên ngưỡng tiền | Literal ở điều kiện | `APPROVAL_THRESHOLD_VND` | Quy tắc và đơn vị dễ tìm hơn |
| Kết quả | `RefundDecision` | `RefundDecision` | Hợp đồng giữ nguyên |
| Test các trường hợp chính | Cần xác nhận baseline | Có test ranh giới và tương đương | Bằng chứng về hành vi tốt hơn |
| Độ dễ hiểu | Cần review thực tế | Cần review thực tế | Không suy ra từ các con số trên |

Bảng phản ánh **cấu trúc của ví dụ**, không phải kết quả một công cụ phân tích cụ thể. Nếu công cụ tính cognitive complexity, hãy đo bằng cùng công cụ/phiên bản và ghi nhận kết quả thực, không tự điền điểm ước đoán.

Đánh giá đúng sau refactor gồm:

1. Các hành vi quan trọng và thứ tự ưu tiên có được giữ không?
2. Người đọc mới có hiểu nhanh vì sao hoàn tiền bị từ chối không?
3. Khi thêm một quy tắc mới, có nơi sửa rõ ràng không?
4. Số điểm nóng ở phạm vi module có giảm, giữ nguyên hay chỉ chuyển sang file khác?
5. Test và hợp đồng lỗi có trở nên dễ duy trì hơn không?

Không nên chia một phương thức thành mười helper chỉ để hạ điểm mỗi helper nếu người đọc giờ phải nhảy qua mười file mới hiểu được một quyết định.

## 12. Cảnh giác với việc “dịch chuyển” độ phức tạp

Một phép refactor có thể biến:

```text
OrderService.calculate()
    - nhiều if
    - hiểu ngay trong một file
```

thành:

```text
OrderService.calculate()
    -> PolicyFactory
       -> PolicyRegistry
          -> RuleDispatcher
             -> RuleEvaluator
                -> các điều kiện nghiệp vụ
```

Điểm complexity của `OrderService.calculate()` giảm nhưng **độ gián tiếp** và tổng số khái niệm cần đọc có thể tăng.

Do đó, khi theo dõi cải tiến nên nhìn:

- Chỉ số ở **phương thức đã sửa**.
- Phân bố ở **class, package hoặc luồng nghiệp vụ liên quan**.
- Số đường đi qua các lớp, dependency và cấu hình để tìm một quy tắc.
- Việc thay đổi yêu cầu mới có phải sửa nhiều nơi hơn không.
- Cảm nhận có kiểm chứng qua review hoặc một bài tập bảo trì thực tế.

Đây là lý do không thể chỉ treo ngưỡng “mọi phương thức phải dưới 10” rồi coi đạt ngưỡng là đủ. Ngưỡng có thể giúp báo động, nhưng **việc tối ưu riêng điểm số** dễ khuyến khích chia nhỏ hình thức mà không giải quyết độ phức tạp ở cấp hệ thống.

### Complexity “thấp” có thể che giấu rủi ro lớn

Một repository method chỉ có một câu gọi SQL có thể chứa truy vấn nhiều join và nhánh nghiệp vụ ở database. Một lời gọi HTTP chỉ một dòng có thể kết nối dịch vụ không ổn định và cần xử lý trạng thái không chắc chắn.

Chỉ số dựa trên cú pháp Java không nhìn hết độ phức tạp của query plan, schema, retry, timeout hay sự phụ thuộc giữa các dịch vụ. Cần kết hợp công cụ đo ở đúng tầng.

## 13. Dùng chỉ số để ưu tiên công việc, không để xếp hạng con người

Một cách dùng chỉ số có ích:

1. Chọn top các phương thức có đuôi complexity cao.
2. Kết hợp với churn, lỗi đã ghi nhận và dự kiến thay đổi.
3. Đọc một số ví dụ tiêu biểu với người hiểu nghiệp vụ.
4. Xác định loại rủi ro: nhiều nhánh, nhiều trạng thái, coupling hoặc dữ liệu thiếu hợp đồng.
5. Quyết định hành động nhỏ nhất: thêm test, đổi tên, tách trách nhiệm, đơn giản hóa điều kiện hoặc giữ nguyên vì hợp lý.
6. Đo và đánh giá lại khi có thay đổi thực.

Không nên dùng cyclomatic complexity hoặc số dòng làm **KPI năng suất cá nhân**. Những con số này chịu ảnh hưởng loại công việc, phân chia trách nhiệm, framework và lịch sử mã. Người nhận xử lý hệ thống cũ phức tạp có thể làm chất lượng tốt hơn mà điểm complexity của module vẫn cao trong một thời gian.

Khi đặt mục tiêu “điểm càng thấp càng tốt”, người viết có thể né khai báo logic cần thiết hoặc tách nhỏ để làm đẹp số. Mục tiêu chất lượng đúng hơn là **giảm nguy cơ lỗi và chi phí thay đổi ở những nơi quan trọng**.

### Ngưỡng cảnh báo nên là chính sách địa phương

Một nhóm có thể chọn ngưỡng cảnh báo của công cụ khi code mới vượt mức đã thống nhất. Nhưng ngưỡng phải được:

- Hiểu theo **định nghĩa và phiên bản công cụ**.
- Áp dụng đúng phạm vi (mã sản xuất, bỏ generated code nếu phù hợp).
- Xem như tín hiệu cần review, không tự kết luận sai.
- Điều chỉnh khi nhận thấy quá nhiều báo động giả hoặc bỏ sót vùng rủi ro.
- Xem xét trường hợp đặc biệt có lý do nghiệp vụ rõ.

Không có một ngưỡng cyclomatic/cognitive duy nhất đúng cho mọi dự án Java.

## 14. Thu thập và trình bày dữ liệu để theo dõi xu hướng

Một báo cáo định kỳ có thể nhóm theo module:

| Module | Số phương thức được đo | Trung vị | p90 | Số phương thức vượt ngưỡng | Hotspot cần xem |
| --- | ---: | ---: | ---: | ---: | --- |
| Checkout | 120 | 2 | 9 | 7 | Chính sách miễn phí và giao hàng |
| Payments | 90 | 3 | 11 | 9 | Chuyển trạng thái thanh toán |
| Reports | 150 | 2 | 7 | 5 | Bộ lọc dữ liệu báo cáo |

Bảng là **minh họa**, không phải số đo của repository. Nếu nhóm muốn so sánh xu hướng theo tuần, cần giữ cùng phạm vi và cách đếm, hoặc ghi chú rõ khi đổi phiên bản công cụ.

Ngoài ảnh chụp tĩnh, có thể theo dõi:

- **Số hotspot mới phát sinh** trong mã đang thay đổi.
- **Số hotspot đã cải thiện** nhưng còn được kiểm thử và review.
- **Phân bố complexity của mã mới** so với mã cũ, tránh chỉ đếm tổng.
- **Mối liên hệ giữa hotspot và lỗi hồi quy** trong một khoảng thời gian.
- **Phần mã bị thay đổi thường xuyên nhưng thiếu test hành vi**.

Cần phân biệt **thay đổi do mã** với **thay đổi do phép đo**. Khi nâng phiên bản analyzer, một số loại cú pháp có thể được chấm điểm khác; hãy ghi dấu mốc thay đổi công cụ để biểu đồ không tạo ra kết luận sai.

### Gợi ý biểu đồ phân bố

```text
Số phương thức theo khoảng cyclomatic (ví dụ giả định)

1–3      ############################  56
4–6      ##########                    20
7–10     ######                        12
11–20    ####                           8
>20      ##                             4

Tổng: 100 phương thức
```

Biểu đồ cho thấy phần lớn phương thức ở mức thấp, một đuôi nhỏ có điểm cao. Từ đây có thể mở danh sách 12 phương thức trên 10 điểm và kết hợp với churn, phạm vi nghiệp vụ.

Đừng xem biểu đồ như một bảng xếp hạng lỗi; nó là cách tìm **điểm nên đọc kỹ trước**.

## 15. Quy trình kiểm tra và cải thiện một hotspot

Giả sử `RefundPolicy.decide` có điểm cao, thay đổi liên tục và thường phát sinh lỗi. Có thể thực hiện quy trình:

### Bước 1: Xác nhận dữ liệu đo

Đảm bảo tên phương thức, phạm vi đo, phiên bản analyzer và lịch sử thay đổi đều đúng. Không bắt đầu refactor từ một kết quả chỉ có tên file và con số.

### Bước 2: Đọc luồng và mô tả quy tắc

Vẽ hoặc liệt kê các quyết định: giao dịch có thu tiền chưa, đã hoàn chưa, còn hạn không, vượt ngưỡng phê duyệt không. Xác định **thứ tự ưu tiên và đầu vào bất hợp lệ**.

### Bước 3: Chọn hành động theo nguyên nhân

- Nếu chỉ khó đọc do lồng nhau: cân nhắc guard clauses.
- Nếu điều kiện lặp lại ở nhiều nơi: đặt tên và gom quy tắc chung.
- Nếu nhiều trạng thái có thể kết hợp vô nghĩa: cân nhắc enum/kiểu miền.
- Nếu một phương thức vừa quyết định vừa làm I/O: tách ranh giới cho kiểm thử.
- Nếu có nhiều thuật toán thay đổi độc lập: xem chiến lược/tách trách nhiệm phù hợp.

### Bước 4: Cố định hành vi trước khi sửa

Viết test ở nhánh quan trọng, giá trị biên, trường hợp lỗi và tác dụng phụ. Khi cần, ghi nhận hành vi hiện tại để phân biệt refactor với thay đổi nghiệp vụ có chủ đích.

### Bước 5: Refactor nhỏ và đo lại

Dùng cùng analyzer; kiểm tra điểm phương thức và phân bố vùng liên quan. Nếu một điểm giảm nhưng tổng coupling tăng, chưa chắc là cải tiến.

### Bước 6: Đánh giá kết quả bảo trì

Nhờ một người khác đọc đoạn mới, thử mô phỏng một yêu cầu sắp tới hoặc xem số nơi phải sửa. Test pass và complexity giảm là bằng chứng hữu ích nhưng không thay thế đánh giá khả năng hiểu.

### Bước 7: Ghi quyết định

Có thể giữ nguyên một phương thức phức tạp nếu đó là mô tả rõ ràng nhất của bảng chuyển trạng thái và có test đủ tốt. Việc **cố ý giữ lại** sau khi đánh giá là quyết định hợp lệ, không phải thất bại.

## 16. Những cách diễn giải chỉ số sai thường gặp

**“Độ phức tạp trung bình thấp nên mã dễ bảo trì.”** Trung bình che một vài hotspot ở đuôi phân bố.

**“Phương thức có điểm cao nhất chắc chắn nên sửa trước.”** Cần xét churn, mức độ quan trọng, test và lịch thay đổi; có khi nó ổn định và ít rủi ro.

**“Cyclomatic complexity cao nghĩa là có chính xác bấy nhiêu trường hợp test.”** Chỉ số mô tả đồ thị, không bao trùm dữ liệu, bất biến và điều kiện kết hợp.

**“Mọi công cụ tính cyclomatic/cognitive giống nhau.”** Cách đếm phụ thuộc định nghĩa và phiên bản; so sánh phải có điều kiện.

**“Càng ít `if` càng tốt.”** Một `switch` rõ nghĩa hoặc guard clauses có thể là biểu đạt đúng. Thay nhiều `if` bằng ánh xạ chuỗi/registry chưa chắc giảm khó hiểu.

**“Chia phương thức đủ nhỏ thì hệ thống hết phức tạp.”** Logic có thể chỉ chuyển từ một nơi sang nhiều lớp trung gian.

**“Coverage cao chứng minh mã không còn rủi ro.”** Coverage là tín hiệu về phần mã được thực thi; tính đúng còn phụ thuộc assertion, dữ liệu và bất biến được kiểm thử.

**“File thay đổi nhiều là code kém.”** Một vùng mã thay đổi vì chức năng đang phát triển cũng có churn cao; cần phân biệt mục đích sửa và ảnh hưởng thực tế.

**“Số liệu tăng sau khi nâng công cụ nghĩa là chất lượng giảm.”** Trước tiên kiểm tra xem định nghĩa đo có đổi không.

**“Có thể dùng metrics để đánh giá từng lập trình viên.”** Các chỉ số mã không phản ánh trực tiếp kỹ năng, mức độ khó của nhiệm vụ hay tác động của người đó.

**“Đạt ngưỡng chất lượng là hoàn thành.”** Ngưỡng chỉ là hàng rào hỗ trợ; các luồng có rủi ro nghiệp vụ vẫn cần test, review và thiết kế đúng.

## 17. Bài tập tình huống

### Tình huống A: cùng điểm trung bình, phân bố rất khác

Module A có điểm theo phương thức: `3, 3, 3, 3, 3, 3`. Module B có `1, 1, 1, 1, 1, 13`.

Hãy tính trung bình, trung vị và điểm lớn nhất của hai module. Vì sao việc chỉ dùng trung bình có thể khiến nhóm bỏ qua một điểm cần xem? Bạn sẽ hỏi thêm điều gì trước khi ưu tiên module B?

### Tình huống B: parser phức tạp nhưng ổn định

Một parser có cyclomatic 28, ít thay đổi trong hai năm, có bộ test tốt và chưa có sự cố được ghi nhận. Một policy khác chỉ có điểm 12 nhưng thay hàng tuần và liên tục có lỗi hồi quy.

Hãy chọn nơi điều tra trước theo **tác động, áp lực thay đổi và bằng chứng**, không chỉ điểm lớn nhất. Trong điều kiện nào parser vẫn cần ưu tiên kiểm tra?

### Tình huống C: giảm điểm nhưng tăng phụ thuộc

Một phương thức 150 dòng có điểm 20 được tách thành 15 helper qua nhiều lớp. Mỗi helper có điểm dưới 5, nhưng một thay đổi nghiệp vụ bây giờ cần sửa 8 file và cấu hình registry.

Hãy phân tích điểm số ở cấp phương thức có đang che độ phức tạp cấu trúc hay không. Đề xuất những chỉ số và bài tập review để kiểm tra khả năng bảo trì thật.

### Tình huống D: refactor quy tắc hoàn tiền

Từ `LegacyRefundPolicy`, hãy viết lại bằng guard clauses, giữ nguyên thứ tự từ chối và ranh giới 1.000.000 VND. Viết test cho giao dịch chưa thu tiền, đã hoàn, hết hạn, chưa duyệt khoản lớn và khoản đúng ngưỡng. Chỉ ra chỉ số nào có thể giảm và chỉ số nào có thể giữ nguyên.

### Tình huống E: chương trình có coverage cao nhưng vẫn lỗi

Một hàm tính giá có 100% line coverage và 90% branch coverage. Khi chương trình chạy, đơn đúng 500.000 VND bị tính phí sai vì điều kiện dùng `>` thay vì `>=`.

Hãy giải thích vì sao coverage không chứng minh đúng và bổ sung test biên thế nào. Cyclomatic complexity của hàm có cần thay đổi để sửa lỗi không?

### Tình huống F: bảng xếp hạng phức tạp của nhiều nhóm

Một dashboard so số commit, complexity và số bug của ba nhóm, rồi định xếp hạng năng suất từng người. Một nhóm bảo trì hệ thống thanh toán cũ, một nhóm phát triển giao diện mới và một nhóm làm mã sinh tự động.

Hãy nêu những yếu tố gây sai lệch trong phép so sánh. Thiết kế lại mục tiêu dashboard theo hướng giúp tìm **hotspot bảo trì** và hỗ trợ quyết định cải tiến, thay vì chấm điểm con người.

Với mỗi tình huống, hãy diễn giải theo chuỗi: **số đo → phân bố → bối cảnh thay đổi → rủi ro nghiệp vụ → kiểm tra thủ công → hành động và cách xác minh**.

## 18. Ghi nhớ

**Độ phức tạp và phân bố các điểm khó hiểu** nên được dùng để tạo bản đồ hỗ trợ bảo trì, không phải bảng thành tích dựa trên một con số.

- Cyclomatic complexity phản ánh cấu trúc luồng điều khiển; cognitive complexity cố phản ánh chi phí đọc, đặc biệt khi có lồng nhau.
- Kích thước, độ sâu, coupling, churn, lỗi và test bổ sung những chiều mà một chỉ số đơn lẻ không thấy.
- Trung bình có thể che một số ít phương thức rất phức tạp. Hãy xem trung vị, đuôi phân bố, top-N và vị trí cụ thể.
- Ưu tiên điều tra những nơi vừa khó hiểu vừa **thường xuyên thay đổi hoặc có tác động lớn**, thay vì chạy theo điểm cao nhất.
- Giữ định nghĩa công cụ, phạm vi và thời gian đo nhất quán; mọi số liệu phải có nguồn và bối cảnh.
- Refactor để làm quy tắc dễ hiểu và ít rủi ro hơn, không chỉ để kéo điểm xuống. Bảo vệ hành vi bằng test và xem tác động ở cấp luồng nghiệp vụ.
- Dùng metrics như tín hiệu trao đổi trong nhóm; không suy trực tiếp chất lượng cá nhân hay xác suất lỗi từ điểm số.

Mục tiêu cuối cùng là biết **đoạn mã nào đang làm việc thay đổi trở nên khó khăn, vì sao nó khó và hành động nào thực sự cải thiện được tình hình**. Một tập chỉ số có giới hạn được hiểu đúng sẽ giúp nhóm tìm được những điểm đó sớm hơn.
