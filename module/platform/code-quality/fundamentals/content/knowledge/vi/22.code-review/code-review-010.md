# Giữ thay đổi đủ tập trung để người khác đánh giá được

Một pull request được mở để sửa quy tắc miễn phí giao hàng. Khi reviewer mở diff, họ thấy cùng lúc: hàng nghìn dòng được formatter viết lại, một lớp được tách thành nhiều service, điều kiện ngưỡng giá thay đổi, migration thêm cột database, thư viện được nâng phiên bản và một phần logging bị xóa. Mỗi thay đổi có thể có lý do riêng, nhưng reviewer phải tự tìm xem phần nào thực sự sửa lỗi, phần nào chỉ đổi cấu trúc và phần nào có thể ảnh hưởng dữ liệu đang chạy.

Khi phạm vi bị trộn, việc đánh giá trở nên khó hơn: reviewer khó xác định ý định, khó nhận ra lỗi trong diff lớn và khó biết test nào bảo vệ hành vi nào. Nếu phát hiện vấn đề, việc tìm nguyên nhân và hoàn tác cũng tốn công hơn.

**Giữ thay đổi đủ tập trung để người khác đánh giá được** là thiết kế một change set có mục đích rõ, các phần liên quan chặt chẽ với nhau và phạm vi vừa đủ để reviewer hiểu được tác động. Điều đó không có nghĩa mọi pull request phải cực nhỏ. Một thay đổi cần nhiều file để giữ hợp đồng nhất quán vẫn có thể là một đơn vị review tốt; ngược lại, một PR chỉ có vài dòng nhưng che giấu nhiều tác động ngoài phạm vi vẫn khó đánh giá.

Trong chương **Rà soát mã** thuộc module `CODE_QUALITY_FUNDAMENTALS`, cách tổ chức thay đổi ảnh hưởng trực tiếp tới khả năng xây dựng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Review hiệu quả cần giúp người khác kiểm tra được vấn đề, lý do sửa, hành vi mới, rủi ro và bằng chứng xác minh.

Sau bài học, bạn có thể:

- Nhận diện diff đang trộn nhiều mục tiêu độc lập và giải thích vì sao điều đó làm tăng chi phí review.
- Chọn ranh giới thay đổi dựa trên một mục đích có thể mô tả, không dựa máy móc vào số dòng.
- Phân biệt refactor bảo toàn hành vi với thay đổi chức năng, sửa lỗi và thay đổi hạ tầng.
- Chia công việc thành commit hoặc pull request có thứ tự mà vẫn giữ các trạng thái trung gian an toàn.
- Nhận biết khi nào migration, API, cấu hình, test và mã sản xuất phải được review cùng nhau.
- Viết mô tả PR, cung cấp bằng chứng và hướng dẫn reviewer đi qua diff.
- Giảm nhiễu do formatter, mã sinh tự động, file lock và thay đổi không liên quan.
- Đánh giá phạm vi theo rủi ro, tính gắn kết và khả năng kiểm chứng.

## 1. Reviewable change là gì?

Một thay đổi dễ review giúp reviewer trả lời được các câu hỏi cốt lõi mà không phải tái dựng toàn bộ lịch sử phát triển:

1. **Vấn đề nào đang được giải quyết?**
2. **Thay đổi này có chủ đích gì?**
3. **Những phần nào của hệ thống bị ảnh hưởng?**
4. **Hành vi trước và sau khác nhau ở đâu?**
5. **Bằng chứng nào cho thấy thay đổi đúng và không phá phần liên quan?**
6. **Rủi ro hoặc điều chưa được kiểm tra là gì?**

Một change set tốt có thể gồm nhiều file, thậm chí nhiều module, nếu chúng cùng thực hiện một thay đổi nhất quán. Ví dụ, đổi tên một trường API có thể cần cập nhật DTO, mapper, controller, tài liệu, contract test và client nội bộ. Chia các file này thành những PR không thể tích hợp độc lập có thể khiến reviewer mất bối cảnh hoặc tạo trạng thái nửa vời.

Ngược lại, một PR có ít dòng nhưng đồng thời thay đổi ngưỡng giá, chính sách hoàn tiền và cách xử lý timeout có thể chứa ba quyết định nghiệp vụ riêng. **Kích thước diff là tín hiệu về chi phí đọc; tính gắn kết của mục tiêu mới quyết định phạm vi có hợp lý hay không.**

### Ba thuộc tính của một thay đổi tập trung

- **Mục đích đơn nghĩa:** có thể mô tả bằng một câu cụ thể, như “từ chối checkout khi phí vận chuyển âm”.
- **Các phần phụ thuộc có lý do:** file và commit trong diff cùng góp phần hoàn tất mục tiêu đó.
- **Có thể kiểm chứng:** reviewer biết test, kiểm tra hoặc bằng chứng nào xác nhận hành vi.

“Refactor toàn bộ checkout” có thể là một mục tiêu quá rộng nếu nó bao gồm đồng thời thay đổi API, chính sách giá, transaction và hệ thống thông báo. Nhưng nếu một thay đổi cần chuyển nhiều thành phần để giữ một bất biến, gom chúng trong một PR có thể là lựa chọn đúng.

## 2. Phân biệt phạm vi theo mục tiêu, không theo số file

Hãy xem một yêu cầu: “Đơn hàng có tổng tiền từ 500.000 VND trở lên được miễn phí giao hàng.”

Các công việc liên quan có thể là:

| Công việc | Mục đích | Có thể độc lập không? |
| --- | --- | --- |
| Thêm test cho ngưỡng hiện tại | Ghi nhận hành vi và điều kiện biên | Có thể là bước chuẩn bị riêng |
| Đổi cấu trúc lớp tính phí | Làm rõ trách nhiệm, giữ hành vi | Có thể tách nếu test bảo vệ đủ |
| Đổi điều kiện từ `>` sang `>=` | Sửa hành vi tại đúng ngưỡng | Có thể là thay đổi chức năng riêng |
| Thêm chính sách theo vùng | Mở rộng quy tắc nghiệp vụ | Thường là mục tiêu riêng |
| Định dạng toàn bộ repository | Chuẩn hóa trình bày | Nên có kế hoạch riêng |
| Nâng phiên bản database driver | Thay đổi phụ thuộc hạ tầng | Cần lý do và xác minh riêng |

Không phải mọi dòng trong bảng đều bắt buộc thành PR riêng. Đây là cách bóc tách để nhóm nhận ra những quyết định khác nhau đang bị gộp.

### Một câu mô tả phạm vi hữu ích

Thử hoàn thành câu:

> PR này thay đổi ______ để ______; các hành vi ______ được giữ nguyên và được kiểm tra bằng ______.

Ví dụ:

> PR này tách chính sách phí giao hàng khỏi `CheckoutManager` để quy tắc giá có thể được kiểm thử độc lập; ngưỡng và kết quả hiện tại được giữ nguyên, được kiểm tra bằng các test ở dưới ngưỡng, đúng ngưỡng và trên ngưỡng.

Nếu không thể mô tả phạm vi theo cách đó, có thể mục tiêu đang quá rộng hoặc chưa được làm rõ.

## 3. Vì sao diff lớn làm tăng chi phí nhận thức?

Reviewer không chỉ đọc từng dòng. Họ phải xây dựng mô hình về luồng dữ liệu, các quyết định và tác động của thay đổi. Một diff rộng có thể làm tăng nhiều loại chi phí:

- **Chi phí tìm tín hiệu:** phải phân biệt thay đổi thực chất với dòng chỉ đổi khoảng trắng.
- **Chi phí chuyển ngữ cảnh:** đang đọc logic giá phải chuyển sang migration, cấu hình hoặc logging không liên quan.
- **Chi phí kiểm tra quan hệ:** phải hiểu nhiều mục tiêu để biết chúng có tương tác hay không.
- **Chi phí xác minh:** khó ánh xạ từng yêu cầu sang test tương ứng.
- **Chi phí phát hiện hồi quy:** thay đổi ở một phần có thể bị che bởi nhiều phần khác.
- **Chi phí phản hồi:** reviewer mất lâu mới đưa ra nhận xét, tác giả khó biết phần nào cần sửa.
- **Chi phí hoàn tác:** khi một mục tiêu có vấn đề, có thể không thể revert riêng mà không ảnh hưởng phần còn lại.

Đây là lý do một diff lớn thường cần nhiều lượt review hơn. Nhưng không thể kết luận “diff càng nhỏ luôn càng tốt”: chia một thay đổi nguyên tử thành nhiều PR khiến trạng thái trung gian không chạy được cũng làm tăng rủi ro.

### Signal và noise trong diff

```text
Một diff dễ đọc:
  - mục tiêu được nêu rõ
  - thay đổi liên quan được nhóm gần nhau
  - test cho hành vi mới hiện diện
  - phần không liên quan được giữ ngoài phạm vi

Một diff nhiều nhiễu:
  - format hàng loạt trộn với logic
  - rename hàng loạt không có kế hoạch
  - file generated thay đổi khó giải thích
  - dependency update không liên quan
  - sửa thêm các cảnh báo cũ không thuộc mục tiêu
```

“Noise” ở đây không có nghĩa các dòng ấy vô giá trị. Một migration hoặc file lock có thể rất quan trọng, nhưng nếu không giải thích mối liên hệ, reviewer khó phân biệt chúng với phần thêm vào ngoài ý muốn.

## 4. Ví dụ Java: một PR đang trộn refactor và thay đổi hành vi

Giả sử phiên bản hiện tại:

```java
final class ShippingFeePolicy {
    long fee(long subtotalVnd, boolean vip) {
        if (vip || subtotalVnd > 500_000L) {
            return 0L;
        }
        return 25_000L;
    }
}
```

Yêu cầu mới là **đơn hàng đúng 500.000 VND cũng được miễn phí giao hàng**. Thay đổi chức năng cần thiết chỉ là `>` thành `>=` cùng test biên.

Nhưng tác giả đưa vào cùng PR một loạt việc:

- Đổi `ShippingFeePolicy` thành `DeliveryPricingEngine`.
- Chuyển sang một package khác.
- Tạo interface và factory mới.
- Đổi tên tham số và mọi biến trong nhiều file.
- Format toàn bộ module.
- Thay đổi điều kiện ngưỡng.
- Thêm một cấu hình vùng giao hàng chưa được yêu cầu.

Reviewer phải tự phân biệt **sửa lỗi ngưỡng** với **thay đổi kiến trúc** và **chính sách mới**. Nếu test chỉ kiểm tra đơn 400.000 và 600.000 VND, lỗi ở đúng 500.000 VND còn có thể lọt qua.

Một cách tổ chức tập trung hơn có thể là:

1. Thêm test xác nhận hành vi cũ và biên hiện tại.
2. Tách phương thức hoặc lớp với cùng hành vi, nếu refactor thực sự cần thiết.
3. Trong một thay đổi riêng, đổi `>` thành `>=` và thêm test đúng ngưỡng.
4. Đưa chính sách theo vùng vào công việc riêng khi yêu cầu và hợp đồng đã rõ.

Các bước này chỉ nên thành PR độc lập nếu mỗi trạng thái sau merge vẫn build, test và có thể triển khai an toàn. Nếu việc tách lớp và sửa ngưỡng phải diễn ra đồng thời để mã không có trạng thái trung gian sai, có thể giữ chung nhưng cần trình bày rõ hai phần trong diff và test.

## 5. Tách refactor khỏi thay đổi chức năng

**Refactor** thay đổi cấu trúc bên trong mà chủ đích là giữ hành vi quan sát được. **Thay đổi chức năng** làm kết quả hoặc hợp đồng thay đổi. Trộn hai loại khiến reviewer khó xác định một khác biệt là chủ đích hay lỗi ngoài ý muốn.

Ví dụ, refactor:

```java
final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 25_000L;

    long fee(long subtotalVnd, boolean vip) {
        return isFreeShipping(subtotalVnd, vip)
                ? 0L
                : STANDARD_FEE_VND;
    }

    private boolean isFreeShipping(long subtotalVnd, boolean vip) {
        return vip || subtotalVnd > FREE_THRESHOLD_VND;
    }
}
```

Trong bước này, điều kiện vẫn là `>`. Nếu yêu cầu ban đầu là giữ nguyên hành vi, đổi sang `>=` trong cùng thay đổi sẽ khiến refactor không còn thuần túy.

Thay đổi chức năng tiếp theo:

```java
private boolean isFreeShipping(long subtotalVnd, boolean vip) {
    return vip || subtotalVnd >= FREE_THRESHOLD_VND;
}
```

Và test biên:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void exactThresholdIsFreeAfterPolicyChange() {
        assertEquals(0L, policy.fee(500_000L, false));
    }

    @Test
    void amountBelowThresholdPaysStandardFee() {
        assertEquals(25_000L, policy.fee(499_999L, false));
    }

    @Test
    void vipReceivesFreeShipping() {
        assertEquals(0L, policy.fee(100_000L, true));
    }
}
```

Khi tách theo cách này, reviewer có thể đánh giá cấu trúc trước rồi đánh giá thay đổi nghiệp vụ ở bước sau. Tuy nhiên, **không được ép mọi refactor và bugfix thành hai PR nếu PR refactor không thể merge an toàn hoặc không thể xác định hành vi cần giữ**. Có thể giữ trong một PR và tách thành hai commit có mô tả rõ nếu sự phụ thuộc kỹ thuật khiến hai phần cần đi cùng nhau.

## 6. Chọn kích thước PR theo khả năng hiểu và kiểm chứng

Không có một giới hạn dòng phổ quát cho mọi repository. Một PR 500 dòng thay đổi dữ liệu sinh tự động có thể dễ kiểm tra nếu có nguồn generator và diff được giải thích. Một PR 80 dòng thay đổi thuật toán phân quyền có thể cần review sâu hơn nhiều.

Có thể dùng các tín hiệu sau:

| Tín hiệu | Câu hỏi |
| --- | --- |
| Số file và dòng thay đổi | Reviewer có thể đọc hết trong thời gian hợp lý không? |
| Số mục tiêu độc lập | Có thể chia một phần mà vẫn giữ trạng thái hợp lệ không? |
| Số tầng hệ thống | Có thay đổi đồng thời API, DB, queue, UI và vận hành không? |
| Độ phức tạp nghiệp vụ | Có nhiều quy tắc hoặc điều kiện biên mới không? |
| Rủi ro | Thay đổi có liên quan tiền, quyền, dữ liệu, concurrency không? |
| Khả năng test | Có thể chỉ ra test tương ứng cho từng hành vi không? |
| Mức độ phụ thuộc | Reviewer có cần đọc nhiều thành phần không liên quan mới hiểu được không? |

Một số nhóm chọn mục tiêu thời gian review hoặc giới hạn diff để cảnh báo. Những con số đó nên là **tín hiệu cần trao đổi**, không phải luật cứng. Nếu PR vượt mục tiêu, hãy xem nguyên nhân: thay đổi có thật sự lớn, hay có nhiễu format, generated files hoặc nhiều mục tiêu bị trộn?

### Dấu hiệu PR đã quá rộng

- Mô tả PR chứa nhiều câu “ngoài ra còn…”.
- Tiêu đề dùng những từ mơ hồ như “cleanup”, “misc fixes”, “improve everything”.
- Test thay đổi cho nhiều hành vi không được mô tả trong mục tiêu.
- Có nhiều file chỉ đổi format hoặc tên nhưng không có lý do.
- Reviewer phải hỏi “phần này liên quan gì tới yêu cầu?” ở nhiều nơi.
- Tác giả không thể giải thích vì sao các phần phải merge cùng nhau.

Một PR rộng vẫn có thể hợp lý nếu thay đổi là một migration xuyên hệ thống hoặc một thay đổi contract không thể chia. Khi đó, cần tăng chất lượng mô tả, thứ tự đọc, test và bằng chứng tương ứng.

## 7. Khi nào nên chia thành nhiều commit hoặc nhiều PR?

Hai công cụ này giải quyết vấn đề khác nhau.

- **Nhiều commit trong một PR:** giữ một mục tiêu merge nhưng cho reviewer xem quá trình thay đổi theo từng bước logic.
- **Nhiều PR:** tách những mục tiêu có thể được phát triển, review và tích hợp độc lập.

Ví dụ refactor một lớp checkout có thể có commit:

```text
1. Add characterization tests for current checkout behavior
2. Extract shipping fee calculation without changing behavior
3. Inject clock and receipt ID source
4. Update service wiring and remove obsolete fields
5. Add tests for the new shipping threshold behavior
```

Nếu các commit đầu đều build và test được, reviewer có thể đọc tuần tự. Nếu commit 2 chỉ build sau commit 4 vì thiếu class, vẫn có thể dùng commit sequence nhưng phải giải thích; không nên giả vờ từng commit là trạng thái hoàn chỉnh.

### Một PR hay nhiều PR?

| Điều kiện | Cách tổ chức có thể phù hợp |
| --- | --- |
| Một mục tiêu, nhiều file phụ thuộc chặt | Một PR, chia commit theo bước |
| Refactor bảo toàn hành vi có thể merge độc lập | PR refactor trước, PR chức năng sau |
| Cần cập nhật contract và mọi consumer cùng lúc | Một PR phối hợp hoặc rollout tương thích theo nhiều giai đoạn |
| Nâng dependency không liên quan tính năng | PR riêng để kiểm tra tác động |
| Format toàn bộ repository | Commit/PR riêng, có kế hoạch cho nhánh đang mở |
| Migration và code mới phải triển khai cùng nhau | Một PR nếu có thể; hoặc quy trình expand–migrate–contract |

Không chia chỉ để giảm số dòng. Hãy chia khi mỗi phần có **giá trị review độc lập và trạng thái tích hợp an toàn**.

## 8. Giữ trạng thái trung gian an toàn khi chia thay đổi

Một chuỗi PR có thể tạo trạng thái không tương thích. Ví dụ đổi tên cột database:

- PR A đổi code để chỉ đọc cột mới.
- PR B mới thêm cột mới vào database.

Nếu PR A được triển khai trước, ứng dụng có thể lỗi. Cần thiết kế trình tự triển khai tương thích.

Một chiến lược thường dùng là **expand–migrate–contract**:

```text
Giai đoạn 1 — Expand
  Thêm cấu trúc mới, giữ cấu trúc cũ hoạt động.

Giai đoạn 2 — Migrate
  Ứng dụng hỗ trợ đọc/ghi tương thích trong giai đoạn chuyển đổi.
  Di chuyển dữ liệu và xác minh.

Giai đoạn 3 — Switch
  Chuyển consumer sang cấu trúc mới, theo dõi kết quả.

Giai đoạn 4 — Contract
  Chỉ xóa cấu trúc cũ khi không còn consumer phụ thuộc.
```

Không phải mọi thay đổi schema đều cần bốn giai đoạn; đây là cách tổ chức cho thay đổi có consumer đang hoạt động và yêu cầu tương thích. Cần xác định chính sách rollback, dữ liệu mới/cũ và khả năng chạy song song trước khi chia PR.

**Một change set tập trung vẫn phải bao gồm đủ phần để bảo đảm tính nhất quán của giai đoạn mà nó thay đổi.** Chia code và migration thành hai PR có thể hợp lý nếu mỗi PR đều giữ hệ thống chạy được; nếu không, cần giữ cùng một đơn vị triển khai hoặc dùng quy trình tương thích rõ ràng.

## 9. Quản lý các file dễ tạo nhiễu

Một diff có thể chứa nhiều file mà reviewer khó đánh giá bằng cách đọc thông thường.

### File lock và dependency

Khi nâng thư viện, file build và lockfile thường phải thay đổi cùng nhau. Reviewer cần biết:

- Dependency nào được nâng và vì sao?
- Có thay đổi major version hoặc hành vi mặc định không?
- Lockfile có được sinh bởi đúng package/build tool không?
- Có CVE, lỗi tương thích hoặc thay đổi license liên quan không?
- Test nào xác minh đường dùng thư viện trong ứng dụng?

Không xóa lockfile khỏi diff chỉ vì nó dài; nó có thể là phần đảm bảo build tái lập. Thay vào đó, hướng reviewer đến phần thay đổi dependency thực chất và báo cáo công cụ.

### Mã sinh tự động

Generated code có thể chiếm phần lớn diff. Cần cung cấp nguồn tạo, phiên bản generator và lệnh tái tạo. Reviewer tập trung vào schema/template hoặc thay đổi đầu vào, sau đó kiểm tra output có được sinh nhất quán không.

Không chỉnh trực tiếp file generated nếu lần chạy generator tiếp theo sẽ ghi đè thay đổi, trừ khi quy trình dự án xác định rõ đó là nguồn sở hữu.

### Snapshot, fixture và dữ liệu mẫu

Các snapshot lớn nên có lý do thay đổi và cách kiểm tra. Nếu hàng trăm dòng JSON thay đổi vì một trường mới, hãy chỉ ra schema hoặc hành vi tạo ra thay đổi. Reviewer có thể dùng công cụ so sánh cấu trúc phù hợp, nhưng cũng không nên che dữ liệu nhạy cảm trong fixture.

### File format và rename

Nếu thay đổi format hàng loạt, dùng commit format-only riêng hoặc thông báo rõ cách bỏ qua phần format để xem logic. Với rename hàng loạt, giữ mapping cũ–mới hoặc công cụ nhận diện rename để reviewer biết file nào chỉ đổi tên.

## 10. Một thay đổi tập trung vẫn phải có đủ test và tài liệu liên quan

Không nên hiểu “PR nhỏ” là “chỉ sửa file production, không sửa test”. Một thay đổi nghiệp vụ tốt thường cần cập nhật các bằng chứng đi cùng:

- Unit test cho quy tắc và giá trị biên.
- Integration test khi thay đổi query, transaction, serialization hoặc adapter.
- Contract/API test nếu consumer phụ thuộc.
- Migration test hoặc kiểm tra tương thích schema khi có thay đổi dữ liệu.
- Tài liệu/README/API spec nếu hợp đồng công khai thay đổi.
- Metric/log/alert nếu thay đổi cách vận hành hoặc xử lý lỗi.

Ví dụ sửa điều kiện phí vận chuyển ở ngưỡng 500.000 VND mà không thêm test đúng ngưỡng có thể tạo diff rất nhỏ nhưng khó review tính đúng. **Độ tập trung không phải cắt bỏ bằng chứng; nó là gom đúng bằng chứng vào cùng mục tiêu.**

### Ánh xạ yêu cầu sang bằng chứng

| Mục tiêu | Bằng chứng nên có |
| --- | --- |
| Đơn đúng ngưỡng được miễn phí | Test 499.999, 500.000 và 500.001 |
| Không lưu đơn khi tính tiền tràn | Test overflow và xác nhận store không nhận lệnh lưu |
| API mới tương thích consumer | Contract test hoặc kiểm tra consumer liên quan |
| Cột mới được migrate | Migration test, kiểm tra dữ liệu cũ và rollback |
| Thay đổi retry | Test số lần thử, deadline và idempotency |
| Đổi formatter | Format check với đúng phiên bản công cụ |

Test cần chứng minh hành vi được mô tả, không chỉ làm build xanh.

## 11. Trình bày diff theo thứ tự giúp reviewer hiểu

Một PR có thể rất tập trung nhưng vẫn khó đọc nếu các thay đổi được sắp xếp lộn xộn. Tác giả có thể chủ động:

1. Đặt phần thay đổi cốt lõi trước, như mô hình hoặc chính sách.
2. Tiếp theo là phần tích hợp/call site.
3. Sau đó là test cho hành vi và trường hợp lỗi.
4. Để file generated/lockfile ở cuối hoặc tách commit nếu công cụ hỗ trợ.
5. Nêu các file quan trọng trong mô tả PR.

Thứ tự commit có thể giúp người review xem từng bước. Tuy nhiên, không phải nền tảng review nào cũng hiển thị commit theo cách giống nhau; mô tả PR nên cung cấp **đường dẫn đọc** rõ ràng.

### Dùng diff để kiểm tra phạm vi trước khi gửi

Tác giả nên tự đọc diff như một reviewer lần đầu:

```text
git status --short
git diff --stat
git diff --check
git diff --name-only
git diff
```

Các lệnh trên chỉ minh họa cho Git:

- `git status --short` giúp nhận ra file ngoài ý muốn.
- `git diff --stat` cho biết quy mô thay đổi.
- `git diff --check` phát hiện whitespace error theo quy tắc Git.
- `git diff --name-only` giúp kiểm tra phạm vi file.
- `git diff` cho phép đọc nội dung thực.

Nếu đang dùng commit đã stage, cần xem cả `git diff --cached`; nếu PR so với nhánh base, cần kiểm tra đúng phạm vi so sánh. Đừng chỉ nhìn diff của working tree rồi nghĩ đó là toàn bộ PR.

## 12. Mô tả PR là một phần của khả năng review

Reviewer không nên phải suy ra toàn bộ bối cảnh từ tên branch hoặc chat cũ. Một mô tả PR hữu ích có thể theo mẫu:

```markdown
## Vấn đề
Mô tả hành vi hiện tại và ảnh hưởng quan sát được.

## Mục tiêu thay đổi
Nêu chính xác hành vi hoặc cấu trúc cần thay đổi.

## Phạm vi
- Các thành phần được sửa và lý do.
- Những phần liên quan được giữ nguyên.
- Điều không thuộc phạm vi.

## Cách triển khai
Tóm tắt các quyết định kỹ thuật quan trọng.

## Kiểm thử
- Lệnh đã chạy.
- Test/điều kiện biên được bổ sung.
- Kết quả thực tế.

## Rủi ro và rollout
Migration, tương thích, feature flag, rollback hoặc điều chưa xác minh.

## Hướng dẫn review
Các file/commit nên đọc trước và câu hỏi cần tập trung.
```

Không cần giữ đủ mọi heading cho một PR rất nhỏ. Một sửa lỗi đơn giản có thể chỉ cần vấn đề, thay đổi và test. Mục tiêu là cung cấp đủ thông tin để người khác đánh giá độc lập.

### Nêu rõ điều không thuộc phạm vi

Nếu PR tách chính sách giá nhưng chưa thay đổi cách gửi email, hãy nói rõ. Điều này giúp reviewer không hiểu nhầm rằng việc gửi email đã được xử lý. Tương tự, nếu test chỉ chạy unit test chứ chưa chạy integration test với database thật, hãy ghi rõ giới hạn đó.

Đừng ghi “đã test đầy đủ” nếu chỉ chạy một lệnh. Hãy nêu lệnh và kết quả thực tế.

## 13. Reviewer nên đọc theo mục tiêu và rủi ro

Reviewer có thể dùng trình tự sau:

1. **Đọc vấn đề và mục tiêu:** hiểu hành vi nào cần thay đổi.
2. **Xem test:** xác định tác giả đã diễn đạt kỳ vọng nào thành kiểm thử.
3. **Đọc đường đi chính:** theo dõi dữ liệu từ đầu vào tới kết quả/tác dụng phụ.
4. **Kiểm tra các biên:** null, giá trị ngưỡng, lỗi, concurrency, quyền truy cập và dữ liệu cũ khi có liên quan.
5. **Xem migration/cấu hình/dependency:** bảo đảm rollout và vận hành an toàn.
6. **Đối chiếu phần ngoài phạm vi:** hỏi vì sao chúng xuất hiện trong diff.
7. **Đưa phản hồi cụ thể:** nêu vị trí, vấn đề, tác động và hướng giải quyết khi cần.

Review không phải cuộc thi tìm thật nhiều comment. Một nhận xét về điều kiện có thể làm sai tiền quan trọng hơn mười nhận xét về tên biến. Khi vấn đề không ảnh hưởng tính đúng, bảo mật, khả năng bảo trì hoặc quy ước đã thống nhất, có thể để lại như gợi ý thay vì blocker.

### Phân biệt blocker và đề xuất

- **Blocker:** lỗi có thể gây sai hành vi, mất dữ liệu, lộ quyền, vi phạm contract hoặc làm hệ thống không triển khai được.
- **Cần làm rõ:** thiếu thông tin để xác nhận an toàn, ví dụ migration chưa có chiến lược rollback.
- **Đề xuất:** cải thiện có ích nhưng không bắt buộc để thay đổi hiện tại đúng.
- **Vấn đề ngoài phạm vi:** nên tạo công việc riêng nếu không cần xử lý ngay để PR an toàn.

Cách phân loại rõ giúp tác giả biết cần sửa gì và tránh mở rộng PR vì những đề xuất không liên quan.

## 14. Khi nào không nên tách?

Có những thay đổi phải được đánh giá như một đơn vị vì các phần phụ thuộc chặt:

- Đổi chữ ký phương thức và tất cả call site cần cập nhật để code biên dịch.
- Thay schema và mapper cần cùng nhau để dữ liệu được đọc đúng.
- Thêm validation và cập nhật test cho contract mới.
- Sửa thứ tự transaction và side effect để bảo vệ bất biến.
- Đổi định dạng lưu trữ cùng code đọc/ghi tương thích.
- Một thay đổi bảo mật cần cập nhật policy, enforcement và test cùng lúc.

Nếu tách, mỗi bước phải có trạng thái **build/test được và triển khai an toàn**, hoặc phải có kế hoạch rollout tương thích cụ thể. Nếu không, việc chia chỉ chuyển độ khó từ reviewer sang người tích hợp.

### Một ví dụ về thay đổi API

Giả sử API đổi trường `customerId` thành `customerRef`. Nếu server bỏ trường cũ trước khi mọi consumer được cập nhật, ứng dụng client cũ sẽ lỗi. Có thể cần một giai đoạn server chấp nhận cả hai, cập nhật consumer, theo dõi usage rồi mới loại bỏ trường cũ. Đây là nhiều bước có thể review riêng nếu mỗi bước giữ tương thích; nếu không, chúng phải được điều phối như một thay đổi phát hành có thứ tự.

**Tập trung không đồng nghĩa độc lập giả tạo.** Ranh giới tốt phản ánh sự phụ thuộc thật.

## 15. Dùng stacked PR khi một thay đổi lớn có các bước phụ thuộc

Một chuỗi PR phụ thuộc (*stacked changes*) có thể giúp chia công việc lớn thành các đơn vị reviewable:

```text
PR 1: Thêm mô hình/policy mới, chưa chuyển consumer
             |
             v
PR 2: Chuyển một nhóm consumer sang policy mới
             |
             v
PR 3: Chuyển consumer còn lại và xóa đường cũ
             |
             v
PR 4: Dọn cấu hình/compatibility không còn cần
```

Cách này phù hợp khi mỗi bước có thể được tích hợp an toàn và reviewer có thể xem phạm vi nhỏ. Cần ghi rõ PR sau phụ thuộc PR trước, nhánh base và cách cập nhật khi PR nền thay đổi.

Các rủi ro:

- PR con có diff chứa cả thay đổi của PR cha nếu chọn sai base.
- PR cha bị sửa có thể khiến các PR sau cần rebase.
- Merge một phần không theo thứ tự có thể làm mất tương thích.
- Reviewer mất bối cảnh nếu mô tả không liên kết các phần.

Nếu nhóm không có quy trình hỗ trợ stacked PR, có thể dùng một PR với nhiều commit có thứ tự. Hãy chọn cách phù hợp với năng lực tích hợp của repository.

## 16. Phân chia theo rủi ro, không chỉ theo cấu trúc thư mục

Một thay đổi có thể chạm nhiều package nhưng chỉ một rủi ro xuyên suốt. Ví dụ thêm idempotency key cho thao tác tạo đơn có thể cần cập nhật controller, service, schema, repository và test. Tách theo package thành năm PR sẽ không phản ánh mục tiêu.

Ngược lại, một PR chỉ sửa một package có thể chứa hai hành vi nghiệp vụ không liên quan.

Một cách xác định ranh giới:

| Trục phân chia | Câu hỏi |
| --- | --- |
| Hành vi | Có bao nhiêu hành vi mới hoặc thay đổi? |
| Bất biến | Các phần có cùng bảo vệ một bất biến không? |
| Rủi ro | Có cùng kiểu lỗi và cùng cách kiểm chứng không? |
| Triển khai | Có thể phát hành từng phần an toàn không? |
| Sở hữu | Có cần phối hợp nhiều nhóm hoặc chủ sở hữu khác nhau không? |
| Phản hồi | Reviewer có thể xác nhận phần này mà không phải hiểu toàn bộ phần khác không? |

Nếu các phần cùng thay đổi một contract hoặc bất biến, chúng thường nên được review cùng. Nếu chúng chỉ tình cờ xuất hiện trong cùng một buổi làm việc, hãy cân nhắc tách.

## 17. Ví dụ phân rã một công việc checkout thành các PR

Yêu cầu lớn: “Cải thiện checkout để dễ thay đổi chính sách phí, hỗ trợ phí theo vùng và bảo đảm không tạo đơn trùng khi client retry.”

Có ít nhất ba mục tiêu khác nhau:

1. Tách chính sách phí khỏi điều phối checkout.
2. Bổ sung quy tắc tính phí theo vùng.
3. Bảo vệ idempotency cho thao tác tạo đơn.

Một kế hoạch có thể là:

| PR | Phạm vi | Điều kiện để review/merge |
| --- | --- | --- |
| PR A | Thêm test đặc tả và tách `ShippingFeePolicy`, giữ nguyên hành vi | Test xác nhận kết quả cũ và ngưỡng hiện tại |
| PR B | Thêm chính sách theo vùng và test các vùng/giá trị biên | Hợp đồng vùng và cấu hình đã rõ |
| PR C | Thêm idempotency key, ràng buộc lưu trữ và xử lý retry | Migration, transaction và test concurrency được kiểm tra cùng |
| PR D nếu cần | Xóa code cũ hoặc cấu hình tương thích sau rollout | Không còn consumer dùng đường cũ |

PR C có thể cần bao gồm cả schema, repository, service và integration test trong cùng một PR vì chúng cùng bảo vệ một bất biến. PR A và B có thể độc lập nếu mỗi bước đều giữ contract hợp lệ.

Đây là **một cách phân rã minh họa**, không phải thứ tự bắt buộc. Nếu chính sách vùng cần thay đổi cùng API contract, hoặc idempotency phải triển khai trước khi mở traffic mới, thứ tự cần điều chỉnh.

## 18. Những dấu hiệu cho thấy PR cần được tổ chức lại

| Triệu chứng | Câu hỏi chẩn đoán | Hướng xử lý |
| --- | --- | --- |
| Diff hàng nghìn dòng chỉ cho một bugfix | Có format/rename hàng loạt không? | Tách format-only hoặc giới hạn phạm vi |
| Một PR có nhiều tiêu đề tính năng | Các mục tiêu có thể merge độc lập không? | Tạo PR riêng hoặc chia commit |
| Reviewer không biết bắt đầu ở đâu | Có đường đọc và file cốt lõi không? | Thêm hướng dẫn review và thứ tự commit |
| Test thay đổi ở nhiều vùng không liên quan | Có mục tiêu ẩn thứ hai không? | Phân loại test theo hành vi và tách phần độc lập |
| Migration không khớp code | Trạng thái triển khai trung gian có an toàn không? | Thiết kế expand–migrate–contract hoặc giữ cùng đơn vị |
| PR con chứa toàn bộ diff của PR cha | Base branch có đúng không? | Sửa quan hệ stacked PR và mô tả dependency |
| Reviewer liên tục phát hiện file ngoài phạm vi | Tác giả đã tự kiểm tra diff chưa? | Kiểm tra `git status`, `git diff --stat`, `git diff --name-only` |
| PR nhỏ nhưng không có test cho hành vi mới | Đã cắt mất bằng chứng cần thiết? | Bổ sung test liên quan vào cùng mục tiêu |
| Một PR phải chờ nhiều nhóm không liên quan | Phạm vi có thể tách theo contract không? | Xác định ranh giới phối hợp và chủ sở hữu |
| Không thể rollback riêng một phần | Các mục tiêu có bị ghép vào một release không? | Xem lại feature flag, migration và trình tự rollout |

Bảng là công cụ điều tra, không phải quy tắc tự động. Một PR có 1.000 dòng không nhất thiết cần chia nếu đó là thay đổi sinh mã được kiểm soát; một PR 20 dòng liên quan quyền truy cập vẫn có thể cần review chuyên sâu.

## 19. Bài tập tình huống

### Tình huống A: một bugfix, năm mục tiêu

PR sửa lỗi ngưỡng phí giao hàng đồng thời format toàn module, đổi tên package, nâng database driver và thêm chính sách VIP mới.

Hãy liệt kê các mục tiêu độc lập, xác định phần nào phải đi cùng nhau để build và triển khai an toàn, rồi đề xuất commit/PR sequence. Test nào chứng minh bug ngưỡng đã được sửa?

### Tình huống B: migration và code không tương thích

Một PR đổi tên cột `customer_id` thành `customer_ref`, nhưng ứng dụng cũ vẫn đang chạy trong quá trình rollout. Nhóm muốn tách migration và code thành hai PR nhỏ.

Hãy mô tả các trạng thái trung gian có thể xảy ra, xác định thứ tự expand–migrate–contract phù hợp và giải thích khi nào cần review chúng như một kế hoạch phát hành thống nhất.

### Tình huống C: PR 30 dòng thay đổi quyền truy cập

Một thay đổi chỉ sửa 30 dòng trong service phân quyền nhưng có thể làm lộ dữ liệu tenant khác. Reviewer cần bằng chứng gì ngoài số dòng? Hãy xác định test, contract, dữ liệu biên và rủi ro cần kiểm tra.

### Tình huống D: format-only diff

Một PR sửa một điều kiện nhưng IDE format lại 400 file. Hãy đề xuất cách tách thay đổi định dạng, giữ lịch sử Git hữu ích và giúp reviewer xác định dòng logic thực sự đổi.

### Tình huống E: stacked PR bị lệch base

PR B phụ thuộc PR A, nhưng PR A được cập nhật sau khi reviewer yêu cầu sửa API. Diff của PR B giờ hiển thị cả thay đổi của A và B.

Hãy giải thích nguyên nhân, cách cập nhật base/rebase và cách mô tả dependency để reviewer không đánh giá trùng lặp.

### Tình huống F: PR rất nhỏ nhưng không review được

Một PR chỉ thay một dòng `>` thành `>=`, không có mô tả, test hoặc liên kết yêu cầu. Reviewer không biết ngưỡng có bao gồm giá trị bằng hay không.

Hãy viết lại mục tiêu, test biên và phần mô tả ngắn đủ để người khác đánh giá độc lập.

### Tình huống G: thay đổi xuyên nhiều module

Một yêu cầu idempotency cần sửa controller, application service, repository, database migration và integration test. Nhóm muốn chia mỗi module thành một PR.

Hãy xác định bất biến chung cần bảo vệ, trạng thái trung gian có an toàn không và cách tổ chức commit/PR để reviewer theo được toàn bộ đường đi mà không làm mất tính nguyên tử.

Với mỗi tình huống, trả lời theo chuỗi: **mục tiêu → các phần liên quan → phần độc lập → trạng thái trung gian → bằng chứng kiểm chứng → cách trình bày cho reviewer**.

## 20. Ghi nhớ

Giữ thay đổi đủ tập trung để người khác đánh giá được là làm cho **mục đích, phạm vi, hành vi và bằng chứng** của một change set trở nên rõ ràng.

- Bắt đầu từ một vấn đề và mục tiêu có thể mô tả bằng một câu.
- Tách các mục tiêu độc lập, nhưng giữ cùng nhau những phần cần thiết để bảo vệ một contract hoặc bất biến.
- Phân biệt refactor bảo toàn hành vi với bugfix và thay đổi chức năng.
- Không dùng số dòng làm tiêu chí duy nhất; đánh giá theo độ gắn kết, rủi ro, khả năng đọc và trạng thái tích hợp.
- Dùng commit/PR có thứ tự, stacked PR hoặc rollout nhiều giai đoạn khi chúng tạo được trạng thái an toàn.
- Giải thích file migration, lockfile, generated code và format-only diff để reviewer biết cách đánh giá.
- Đưa test và bằng chứng liên quan vào cùng mục tiêu; PR nhỏ không có bằng chứng vẫn khó review.
- Viết mô tả và hướng dẫn review ngắn, cụ thể; nêu cả điều chưa kiểm tra.
- Review theo tác động và rủi ro, phân biệt blocker với đề xuất để tránh mở rộng phạm vi tùy tiện.

Một thay đổi dễ review không phải lúc nào cũng nhỏ nhất. Nó là thay đổi mà người khác có thể **hiểu vì sao cần, theo dõi điều gì đã đổi, kiểm tra bằng chứng và đánh giá rủi ro** mà không phải đoán ý định của tác giả.
