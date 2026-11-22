# Dừng khi mục tiêu cải thiện đã được chứng minh

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích vì sao **tái cấu trúc (refactoring)** cần có **mục tiêu và điểm dừng** thay vì tiếp tục đến khi mã “đẹp” theo cảm giác.
2. Phân biệt **bằng chứng giữ nguyên hành vi** với **bằng chứng đạt mục tiêu chất lượng**, chẳng hạn giảm phụ thuộc, dễ kiểm thử hơn hoặc giảm chi phí sửa một quy tắc.
3. Đặt **tiêu chí hoàn tất (exit criteria)** có thể kiểm tra được trước khi refactor: phạm vi, chỉ số, trường hợp biên, điều kiện không được xấu đi và mức rủi ro chấp nhận.
4. Chọn cách thu thập bằng chứng phù hợp: test hành vi, characterization test, contract/integration test, review phụ thuộc, đo thời gian thay đổi và benchmark trên workload đại diện.
5. Nhận biết dấu hiệu **over-refactoring**, **gold-plating**, abstraction quá sớm và việc tiếp tục sửa mã khi lợi ích bổ sung không còn xứng đáng với chi phí/rủi ro.
6. Ghi nhận quyết định **dừng, tiếp tục, thu hẹp phạm vi hoặc quay lui** theo bằng chứng, đồng thời nêu rõ giới hạn còn lại để người bảo trì không nhầm lẫn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Tái cấu trúc là một kỹ thuật cải thiện cấu trúc bên trong mà vẫn bảo vệ hành vi có thể quan sát từ bên ngoài. Tuy nhiên, một vòng refactor không có điểm dừng có thể gây thêm rủi ro, tạo abstraction không cần thiết và trì hoãn việc giao giá trị cho người dùng.

**Ý chính:** Dừng không phải vì “đã mệt” hay “không còn ý tưởng sửa”, mà vì **mục tiêu cải thiện được xác định trước đã có bằng chứng đáp ứng, các điều kiện bảo vệ vẫn đạt và phần thay đổi thêm chưa có lợi ích rõ ràng**. Nếu gặp rủi ro mới nghiêm trọng, có thể cần dừng để đánh giá hoặc quay lui dù chưa đạt mục tiêu.

## 1. Vì sao cần đặt điểm dừng cho refactoring?

Giả sử một nhóm nhận nhiệm vụ giảm rủi ro khi đổi chính sách tính chiết khấu. Trước khi sửa, công thức chiết khấu được lặp trong ba luồng: tính trước khi đặt hàng, xác nhận đơn và nhập đơn từ đối tác.

Nhóm dự định:
- Đưa quyết định chiết khấu về một thành phần có tên rõ.
- Để ba luồng gọi cùng một hợp đồng.
- Kiểm tra kết quả ở dưới, bằng và trên ngưỡng.
- Giữ phản hồi API và số tiền đã chốt trên đơn cũ không đổi.

Sau khi hoàn thành các việc này, một thành viên đề xuất đổi tiếp tất cả DTO sang interface, tạo một rule engine tổng quát và chuyển cả hệ thống sang một mô hình sự kiện mới vì “đang tiện sửa”.

Những đề xuất mới **có thể** có giá trị trong bối cảnh khác, nhưng **không tự động thuộc phạm vi refactor hiện tại**. Nếu không chứng minh chúng giải quyết rủi ro còn tồn tại, nhóm có nguy cơ biến một thay đổi nhỏ, dễ review thành thay đổi kiến trúc lớn, khó kiểm chứng.

### Điều gì có thể xảy ra nếu không biết dừng?

| Hậu quả | Biểu hiện | Vì sao ảnh hưởng chất lượng |
| --- | --- | --- |
| **Phạm vi tăng liên tục** | Đang trích policy lại đổi cả mô hình dữ liệu và framework | Khó kiểm tra nguyên nhân nếu có lỗi |
| **Abstraction quá sớm** | Tạo interface/factory/registry dù chỉ có một chính sách | Tăng nơi phải đọc và cấu hình |
| **Rủi ro hồi quy tăng** | Sửa thêm các đường ít liên quan | Có thể phá hành vi vốn ổn định |
| **Review khó hơn** | PR vừa sửa logic, vừa đổi tên, vừa format hàng nghìn dòng | Người review khó phân biệt thay đổi cấu trúc với thay đổi hành vi |
| **Chậm giao việc khác** | Tiếp tục “làm sạch” dù mục tiêu đã đạt | Tăng chi phí cơ hội |
| **Đánh mất bằng chứng ban đầu** | Đo nhiều chỉ số khác nhau và chọn con số đẹp nhất | Không biết mục tiêu thật đã cải thiện hay chưa |
| **Đổi rủi ro này lấy rủi ro khác** | Giảm trùng code nhưng tạo phụ thuộc chung quá lớn | Khả năng thay đổi có thể tệ hơn |

**Refactoring có chủ đích là hoạt động có giới hạn.** Điều này không có nghĩa phải bỏ qua một lỗ hổng bảo mật hoặc lỗi dữ liệu vừa phát hiện. Những vấn đề cấp thiết cần được phân loại và xử lý phù hợp, không dùng “đã đạt điểm dừng” để che đi rủi ro không thể chấp nhận.

## 2. “Mục tiêu cải thiện” phải là gì?

Một mục tiêu tốt nói rõ **điều cần tốt hơn**, **vì sao quan trọng** và **bằng chứng nào chứng minh**.

Ví dụ:

> “Giảm nguy cơ preview và checkout dùng hai công thức chiết khấu khác nhau. Sau refactor, cả hai dùng một chính sách có hợp đồng rõ; test ở dưới, bằng và trên ngưỡng đạt; contract API không đổi.”

Đây là mục tiêu đủ cụ thể để đánh giá. Trái lại, những tuyên bố như “code phải sạch hơn”, “thiết kế phải hiện đại”, “cần áp dụng SOLID triệt để” quá rộng và khó xác định khi nào nên dừng.

### Bốn thành phần của mục tiêu

1. **Vấn đề ban đầu:** hiện tồn tại rủi ro hoặc chi phí nào? Có bằng chứng gì?
2. **Trạng thái mong muốn:** thay đổi cấu trúc cụ thể nào giải quyết vấn đề?
3. **Điều kiện giữ nguyên:** hợp đồng nghiệp vụ, API, dữ liệu, quyền, transaction, hiệu năng hoặc vận hành nào không được suy giảm?
4. **Cách kiểm chứng:** test, đo, review hoặc quan sát nào là bằng chứng đủ?

Một mục tiêu tốt thường gắn với một **lý do thay đổi**:
- Một quy tắc nghiệp vụ hiện bị sửa ở nhiều nơi.
- Một phép tính khó test vì bị trộn với I/O.
- Một module phụ thuộc vào chi tiết kỹ thuật của nhiều adapter.
- Một phương thức khó hiểu vì phải giữ quá nhiều trạng thái và nhánh trong đầu.
- Một khu vực có hồi quy lặp lại sau những thay đổi tương tự.

Không cần lúc nào cũng có số đo tuyệt đối. Với mục tiêu cấu trúc, một **sơ đồ phụ thuộc trước/sau** hoặc chứng minh rằng **thay đổi ngưỡng chỉ cần sửa một policy** có thể đáng tin hơn một chỉ số “clean-code score”.

## 3. Phân biệt hai câu hỏi chứng minh

Refactoring đòi hỏi ít nhất hai loại bằng chứng riêng:

**Câu hỏi A — Có giữ nguyên hành vi được yêu cầu không?**

- Cùng đầu vào hợp lệ cho cùng kết quả nghiệp vụ theo hợp đồng?
- Trường hợp biên, lỗi, tác dụng phụ và thứ tự quan trọng còn đúng?
- API công khai, JSON, sự kiện, database và quyền truy cập có còn tương thích?
- Có thay đổi ngoài ý muốn về thời gian, tính đồng thời hoặc tài nguyên không?

**Câu hỏi B — Có đạt cải thiện được đặt ra không?**

- Quy tắc lặp đã được quy về một nơi sở hữu?
- Đường tính toán có thể test độc lập khỏi I/O?
- Số điểm phải sửa cho một thay đổi dự kiến đã giảm?
- Phụ thuộc không cần thiết đã được loại bỏ?
- Độ trễ hoặc tài nguyên đã cải thiện trên workload cần phục vụ?
- Người review có thể theo dõi luồng xử lý rõ hơn?

**Test xanh chỉ trả lời một phần của câu A**. Nó không tự chứng minh mục tiêu B đã đạt. Ngược lại, việc giảm số dòng hoặc số dependency không chứng minh hành vi còn đúng.

### Ma trận quyết định đơn giản

| Hành vi và điều kiện bảo vệ | Mục tiêu cải thiện | Quyết định phù hợp |
| --- | --- | --- |
| **Đạt** | **Đạt** | Có cơ sở **dừng refactor trong phạm vi hiện tại** |
| **Đạt** | **Chưa đạt** | Điều tra nguyên nhân, tiếp tục trong phạm vi hợp lý hoặc thay đổi kế hoạch |
| **Không đạt** | **Đạt** | Không thể coi là hoàn tất; sửa hoặc quay lui thay đổi gây hồi quy |
| **Không đạt** | **Chưa đạt** | Dừng mở rộng phạm vi, chẩn đoán và xem xét quay lui |
| **Chưa đủ bằng chứng** | Bất kỳ | Bổ sung kiểm chứng hoặc ghi rõ rủi ro chưa xác nhận; không tuyên bố thành công |

Đây không phải bảng cho phép bỏ qua sự cố: một lỗi nghiêm trọng phát hiện trong lúc refactor cần được xử lý theo mức độ ảnh hưởng, kể cả khi nó đã tồn tại từ trước.

## 4. Viết exit criteria trước khi thay đổi mã

**Exit criteria** là điều kiện để có thể kết luận “đủ cho mục tiêu lần này”. Một bộ tiêu chí tốt vừa **đủ cụ thể** vừa **không ép sửa những phần không liên quan**.

Ví dụ cho công việc tách chính sách tính phí:

| Nhóm tiêu chí | Điều kiện minh họa |
| --- | --- |
| **Phạm vi** | Chỉ sửa policy và những caller đang tự tính cùng chính sách |
| **Hợp đồng** | API response, mã tiền, làm tròn và dữ liệu lịch sử giữ đúng yêu cầu |
| **Đúng đắn** | Test dưới, bằng, trên ngưỡng; đơn không đủ điều kiện; đầu vào lỗi |
| **Cấu trúc** | Một thành phần sở hữu công thức; không còn bản sao logic độc lập ở các caller liên quan |
| **Kiểm thử** | Policy test chạy độc lập, đường API/job quan trọng được kiểm chứng |
| **Vận hành** | Không phát sinh thay đổi bất ngờ về transaction, I/O, timeout hoặc logging |
| **Review** | PR có thể đọc theo từng bước; phần format không liên quan được tách ra |
| **Điểm dừng** | Khi các mục trên được xác nhận, không thêm generic rule engine nếu chưa có nhu cầu riêng |

Một tiêu chí như **“tất cả test phải xanh”** là cần thiết trong nhiều dự án, nhưng chưa đủ: nếu test hiện không kiểm tra trường hợp bằng ngưỡng, một sai lệch **>** so với **>=** vẫn có thể bị bỏ sót. Cần chỉ rõ **những test mới bảo vệ rủi ro của công việc**.

### Đừng biến exit criteria thành mục tiêu giả

Ví dụ “giảm 30% số dòng” hoặc “mọi phương thức dưới 20 dòng” có vẻ đo được, nhưng có thể khuyến khích:
- Tách một hàm rõ thành nhiều helper một dòng khó điều hướng.
- Gộp nhiều ý nghĩa vào một biểu thức ngắn khó đọc.
- Xóa kiểm tra phòng vệ để đạt số dòng.
- Tạo abstraction chung chỉ để giảm trùng chữ.

Hãy ưu tiên **chỉ số có quan hệ rõ với vấn đề**. Số dòng, cyclomatic complexity hoặc duplication có thể là tín hiệu hỗ trợ, nhưng không tự thay thế đánh giá ngữ nghĩa và khả năng thay đổi.

## 5. Baseline: biết điểm xuất phát trước khi khẳng định tốt hơn

Không thể chứng minh một cải thiện nếu không biết tình trạng ban đầu.

**Baseline** không nhất thiết là bộ benchmark lớn. Tùy mục tiêu, nó có thể là:
- Danh sách những nơi đang giữ bản sao một công thức.
- Sơ đồ các dependency khiến lớp nghiệp vụ khó test.
- Một bộ characterization tests ghi lại hành vi hiện tại.
- Bảng các nhánh điều kiện hoặc trường hợp biên cần bảo vệ.
- Số bước cần thực hiện để thêm một loại chính sách mới.
- Các metric p95/p99, số query, allocation hoặc tài nguyên trên workload đại diện.
- Một tình huống sửa đổi thực tế và các file bắt buộc phải chỉnh.

### Ví dụ baseline cho lặp quy tắc

**Trước khi sửa:**
- Preview có một biểu thức tính giảm giá.
- Checkout có biểu thức khác.
- Job nhập đơn có một phiên bản viết bằng số nguyên.
- Khi ngưỡng đổi, ít nhất ba đoạn logic phải sửa đồng bộ.
- Một ca bằng ngưỡng cho hai kết quả khác nhau.

**Sau khi sửa mong muốn:**
- Một policy quyết định giảm giá.
- Các caller chỉ truyền dữ liệu và sử dụng kết quả.
- Test chính sách ở ba vùng ngưỡng xác định kết quả.
- Test luồng xác nhận kiểm tra output và tác dụng phụ còn đúng.
- Mỗi lần đổi chính sách, không cần sửa lại công thức ở từng caller.

Đây là bằng chứng cụ thể hơn nhiều so với câu “mã nhìn sạch hơn”.

## 6. Bảo toàn hành vi không chỉ là cùng giá trị trả về

Hai phiên bản có thể trả cùng kết quả cho một test đơn giản nhưng khác nhau ở **hành vi bên ngoài**.

Ví dụ:
- Phiên bản mới lưu đơn hàng **sau** khi gửi sự kiện, thay vì trước.
- Thêm cache làm thay đổi độ mới của dữ liệu.
- Đổi kiểu tiền từ **BigDecimal** sang **double** gây sai số làm tròn.
- Đổi thời điểm dùng **Instant.now()** khiến một giao dịch qua ranh giới ngày.
- Chuyển từ vòng lặp sang stream song song làm thay đổi thứ tự tác dụng phụ.
- Đổi exception thành giá trị mặc định khiến lỗi thật biến thành dữ liệu có vẻ hợp lệ.
- Đổi tên thuộc tính JSON hoặc mã lỗi khiến client cũ không còn tương thích.
- Một helper được tách riêng nhưng bỏ sót kiểm tra quyền trước khi ghi.

### Hợp đồng được quan sát từ đâu?

| Đường quan sát | Điều có thể cần giữ | Cách kiểm tra |
| --- | --- | --- |
| Kết quả thuần | Giá tiền, trạng thái, trường hợp biên | Unit test, bảng quyết định |
| Lưu trữ | Bản ghi, transaction, constraint, thời điểm ghi | Integration test với database |
| Giao tiếp | JSON, HTTP status, schema message, header | API/contract test |
| Tác dụng phụ | Lệnh gửi email, phát sự kiện, thanh toán | Test hợp đồng ở port và integration test |
| Bảo mật | Quyền theo người gọi và tài nguyên | Test đường được phép/bị từ chối |
| Tài nguyên | Timeout, bộ nhớ, số query, connection | Đo trên workload đại diện |
| Đồng thời | Thứ tự, idempotency, update có điều kiện | Test concurrency/transaction thích hợp |
| Dữ liệu lịch sử | Giá trị đã chốt, phiên bản quy tắc | Test đọc/migration/đối soát |

**Không thể chứng minh tuyệt đối mọi hành vi chỉ bằng một số hữu hạn test.** Trong thực tế, ta xây dựng **bằng chứng đủ mạnh cho mức rủi ro**, đồng thời ghi rõ phần chưa kiểm chứng và không khẳng định chắc chắn quá mức.

## 7. Chu trình refactoring có điểm dừng

Một chu trình thực dụng:

~~~mermaid
flowchart TD
    A[Nhận diện vấn đề cụ thể] --> B[Đặt mục tiêu và exit criteria]
    B --> C[Thu baseline và test bảo vệ]
    C --> D[Thay đổi nhỏ, có thể review]
    D --> E[Chạy test và thu bằng chứng]
    E --> F{Hành vi và guardrails còn đúng?}
    F -- Không --> G[Sửa hồi quy hoặc quay lui]
    G --> D
    F -- Có --> H{Mục tiêu đã chứng minh?}
    H -- Chưa --> I{Lợi ích tiếp tục còn rõ?}
    I -- Có --> D
    I -- Không hoặc rủi ro tăng --> J[Thu hẹp phạm vi, ghi phần còn lại]
    H -- Rồi --> K[Dừng refactor trong phạm vi]
    K --> L[Review, ghi bằng chứng và kết thúc]
~~~

Chu trình giúp chống lại hai khuynh hướng đối lập:

- **Dừng quá sớm:** chỉ đổi tên biến nhưng vẫn để các luồng tính chính sách khác nhau, mục tiêu cốt lõi chưa đạt.
- **Dừng quá muộn:** đã tách thành phần độc lập và test đầy đủ nhưng tiếp tục đổi cả mô hình hệ thống để đạt “độ sạch hoàn hảo”.

Bước nhỏ không có nghĩa một thay đổi lớn không bao giờ cần thiết. Với một migration hay chuyển kiến trúc bắt buộc, cần **phân kỳ và điều kiện hoàn tất cho từng giai đoạn**, không gộp tất cả vào một vòng refactor không có ranh giới.

## 8. Ví dụ Java 17: tách quy tắc tính toán, rồi dừng đúng chỗ

Một dịch vụ checkout hiện vừa tra giá, vừa tính tổng, áp dụng giảm giá và lưu kết quả. Chính sách giảm giá giả định:

1. Giá đơn vị được lấy từ **catalog tin cậy** chứ không lấy từ client.
2. Mỗi dòng hàng có SKU không rỗng và số lượng dương.
3. **subtotalVnd** là tổng đơn giá nhân số lượng.
4. Khách **preferred** với subtotalVnd từ **1.000.000 VND trở lên** được giảm **5%**.
5. Tiền giảm được làm tròn đến **VND nguyên**, theo **RoundingMode.HALF_UP**.
6. **payableVnd = subtotalVnd − discountVnd**.
7. Kết quả được gửi tới kho lưu trữ bằng một lệnh **save(...)**.

Đây chỉ là **hợp đồng ví dụ**. Trong sản phẩm thật, cần xác định giá trị tiền hợp lệ, thời điểm bảng giá, các loại tiền, thuế, khuyến mại chồng nhau, phí và cách ghi dữ liệu theo giao dịch.

### 8.1. Kiểu miền và port nhỏ, rõ nghĩa

~~~java
import java.math.BigDecimal;
import java.util.Objects;

record OrderItem(String sku, int quantity) {
    OrderItem {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid order item");
        }
    }
}

record CheckoutTotal(
        BigDecimal subtotalVnd,
        BigDecimal discountVnd,
        BigDecimal payableVnd) {
    CheckoutTotal {
        Objects.requireNonNull(subtotalVnd, "subtotalVnd");
        Objects.requireNonNull(discountVnd, "discountVnd");
        Objects.requireNonNull(payableVnd, "payableVnd");
        if (subtotalVnd.signum() < 0
                || discountVnd.signum() < 0
                || payableVnd.signum() < 0
                || subtotalVnd.subtract(discountVnd)
                        .compareTo(payableVnd) != 0) {
            throw new IllegalArgumentException("invalid checkout total");
        }
    }
}

@FunctionalInterface
interface UnitPriceCatalog {
    BigDecimal unitPriceVnd(String sku);
}

@FunctionalInterface
interface CheckoutResultStore {
    void save(CheckoutTotal total);
}
~~~

**OrderItem** là dữ liệu yêu cầu đã được kiểm tra về SKU và số lượng; **UnitPriceCatalog** biểu diễn ranh giới lấy giá. Ví dụ không bao gồm xác minh quyền, tồn kho và phí. **CheckoutTotal** dùng bất biến để đảm bảo các thành phần kết quả nhất quán.

### 8.2. Phiên bản trước: mọi việc ở cùng phương thức

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

final class CheckoutServiceBefore {
    private final UnitPriceCatalog catalog;
    private final CheckoutResultStore store;

    CheckoutServiceBefore(
            UnitPriceCatalog catalog, CheckoutResultStore store) {
        this.catalog = Objects.requireNonNull(catalog);
        this.store = Objects.requireNonNull(store);
    }

    CheckoutTotal checkout(List<OrderItem> items, boolean preferred) {
        Objects.requireNonNull(items, "items");
        if (items.isEmpty()) {
            throw new IllegalArgumentException("empty order");
        }

        BigDecimal subtotal = BigDecimal.ZERO;
        for (OrderItem item : items) {
            Objects.requireNonNull(item, "item");
            BigDecimal price = Objects.requireNonNull(
                    catalog.unitPriceVnd(item.sku()), "catalog price");
            if (price.signum() < 0) {
                throw new IllegalStateException("negative catalog price");
            }
            subtotal = subtotal.add(
                    price.multiply(BigDecimal.valueOf(item.quantity())));
        }

        BigDecimal discount = BigDecimal.ZERO;
        if (preferred
                && subtotal.compareTo(new BigDecimal("1000000")) >= 0) {
            discount = subtotal.multiply(new BigDecimal("0.05"))
                    .setScale(0, RoundingMode.HALF_UP);
        }

        CheckoutTotal result = new CheckoutTotal(
                subtotal, discount, subtotal.subtract(discount));
        store.save(result);
        return result;
    }
}
~~~

Phiên bản này không nhất thiết có bug. Vấn đề cụ thể được nhóm chọn xử lý là **chính sách giảm giá chưa được tách khỏi điều phối tra giá và lưu**, khiến khó kiểm thử quy tắc độc lập và khó thay chính sách mà không đụng tới service.

**Mục tiêu refactor có giới hạn:** Tách chính sách giảm giá thành phép tính thuần có hợp đồng rõ, giữ **vòng lặp lấy giá và thao tác save** như cũ; không tự đổi transaction, API, cơ chế catalog hay cách phát sự kiện.

### 8.3. Sau bước refactor: policy nhỏ và service điều phối

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

final class DiscountPolicyV1 {
    private static final BigDecimal ELIGIBLE_SUBTOTAL_VND =
            new BigDecimal("1000000");
    private static final BigDecimal DISCOUNT_RATE =
            new BigDecimal("0.05");

    CheckoutTotal calculate(
            BigDecimal subtotalVnd, boolean preferred) {
        Objects.requireNonNull(subtotalVnd, "subtotalVnd");
        if (subtotalVnd.signum() < 0) {
            throw new IllegalArgumentException("negative subtotal");
        }

        BigDecimal discountVnd = BigDecimal.ZERO;
        boolean eligible = preferred
                && subtotalVnd.compareTo(ELIGIBLE_SUBTOTAL_VND) >= 0;

        if (eligible) {
            discountVnd = subtotalVnd.multiply(DISCOUNT_RATE)
                    .setScale(0, RoundingMode.HALF_UP);
        }

        return new CheckoutTotal(
                subtotalVnd,
                discountVnd,
                subtotalVnd.subtract(discountVnd));
    }
}
~~~

Và service sau refactor:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

final class CheckoutServiceAfter {
    private final UnitPriceCatalog catalog;
    private final CheckoutResultStore store;
    private final DiscountPolicyV1 discountPolicy;

    CheckoutServiceAfter(
            UnitPriceCatalog catalog,
            CheckoutResultStore store,
            DiscountPolicyV1 discountPolicy) {
        this.catalog = Objects.requireNonNull(catalog);
        this.store = Objects.requireNonNull(store);
        this.discountPolicy = Objects.requireNonNull(discountPolicy);
    }

    CheckoutTotal checkout(List<OrderItem> items, boolean preferred) {
        Objects.requireNonNull(items, "items");
        if (items.isEmpty()) {
            throw new IllegalArgumentException("empty order");
        }

        BigDecimal subtotalVnd = BigDecimal.ZERO;
        for (OrderItem item : items) {
            Objects.requireNonNull(item, "item");
            BigDecimal priceVnd = Objects.requireNonNull(
                    catalog.unitPriceVnd(item.sku()), "catalog price");
            if (priceVnd.signum() < 0) {
                throw new IllegalStateException("negative catalog price");
            }
            subtotalVnd = subtotalVnd.add(
                    priceVnd.multiply(BigDecimal.valueOf(item.quantity())));
        }

        CheckoutTotal result =
                discountPolicy.calculate(subtotalVnd, preferred);
        store.save(result);
        return result;
    }
}
~~~

Những phần cố ý giữ lại:
- Thứ tự tra giá từng dòng.
- Cách xử lý catalog trả null hoặc giá âm.
- Điều kiện đơn rỗng.
- Một lời gọi **store.save(...)** với tổng tính được.
- Kết quả và quy tắc làm tròn.

Nhóm chỉ thay **nơi sở hữu logic giảm giá**. Không có bằng chứng buộc phải thay **UnitPriceCatalog** thành HTTP client bất đồng bộ hoặc tạo một hệ thống plugin cho nhiều chính sách chưa tồn tại.

### 8.4. Bằng chứng cần có trước khi dừng

**Bằng chứng cấu trúc:** Điều kiện ngưỡng và tỷ lệ giảm giá được quyết định ở **DiscountPolicyV1**; service không còn bản sao chính sách. Policy không phụ thuộc kho lưu trữ hoặc network.

**Bằng chứng hành vi:** Các trường hợp không phải preferred, dưới ngưỡng, đúng ngưỡng, trên ngưỡng, làm tròn và giá catalog bất thường có kết quả đúng theo hợp đồng.

**Bằng chứng ranh giới:** Service vẫn tra giá, lưu một kết quả đúng; dữ liệu request sai bị từ chối và không lưu.

**Bằng chứng giới hạn:** Chưa kiểm chứng SQL transaction hay hoạt động hạ tầng thật; đó là trách nhiệm của integration test ở tầng adapter. Nếu phạm vi refactor không đổi adapter, test hiện có của adapter vẫn cần chạy ở quy trình CI phù hợp.

Một lưu ý quan trọng: việc tạo policy chưa chứng minh mọi code path ngoài ví dụ đang dùng policy ấy. Trong một ứng dụng thật, cần rà soát **những caller thuộc phạm vi** và test đường đi cần được bảo vệ.

## 9. Unit test chứng minh kết quả và trường hợp biên

Ví dụ dưới đây dùng **JUnit Jupiter (JUnit 5)**. Nó bảo vệ quy tắc mới **độc lập với database**.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class DiscountPolicyV1Test {
    private final DiscountPolicyV1 policy = new DiscountPolicyV1();

    @Test
    void noDiscountForNonPreferredCustomer() {
        var result = policy.calculate(new BigDecimal("2000000"), false);

        assertEquals(BigDecimal.ZERO, result.discountVnd());
        assertEquals(
                new BigDecimal("2000000"), result.payableVnd());
    }

    @Test
    void noDiscountBelowThreshold() {
        var result = policy.calculate(new BigDecimal("999999"), true);

        assertEquals(BigDecimal.ZERO, result.discountVnd());
    }

    @Test
    void discountAppliesAtExactThreshold() {
        var result = policy.calculate(new BigDecimal("1000000"), true);

        assertEquals(new BigDecimal("50000"), result.discountVnd());
        assertEquals(
                new BigDecimal("950000"), result.payableVnd());
    }

    @Test
    void discountRoundsToWholeVndUsingHalfUp() {
        var result = policy.calculate(new BigDecimal("1000010"), true);

        // 5% của 1.000.010 = 50.000,5 VND;
        // HALF_UP tới VND nguyên thành 50.001.
        assertEquals(new BigDecimal("50001"), result.discountVnd());
        assertEquals(
                new BigDecimal("950009"), result.payableVnd());
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.calculate(new BigDecimal("-1"), true));
    }
}
~~~

Test ở **đúng ngưỡng** đặc biệt quan trọng vì dễ nhầm **>** và **>=**. Test làm tròn bảo vệ một chi tiết nghiệp vụ mà refactor biểu thức có thể vô tình thay đổi.

**Nhưng:** Các assertion trên chứng minh **DiscountPolicyV1 đáp ứng các ví dụ đã chọn**, chưa chứng minh mọi giá trị đều đúng. Với khu vực tính tiền quan trọng, nên cân nhắc thêm **property-based tests**, dữ liệu mẫu từ nghiệp vụ, contract test và các trường hợp cực trị theo yêu cầu thực.

## 10. Kiểm thử service vẫn điều phối và lưu đúng

Một đơn vị refactor an toàn cũng cần kiểm tra tác dụng phụ đã cam kết. Test sau dùng một catalog stub và store ghi nhận, không cần database thật.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CheckoutServiceAfterTest {

    @Test
    void calculatesUsingTrustedCatalogAndSavesOnce() {
        UnitPriceCatalog catalog = sku -> {
            assertEquals("SKU-01", sku);
            return new BigDecimal("500000");
        };
        List<CheckoutTotal> saved = new ArrayList<>();
        CheckoutResultStore store = saved::add;

        var service = new CheckoutServiceAfter(
                catalog, store, new DiscountPolicyV1());

        CheckoutTotal result = service.checkout(
                List.of(new OrderItem("SKU-01", 2)), true);

        assertEquals(
                new BigDecimal("1000000"), result.subtotalVnd());
        assertEquals(
                new BigDecimal("50000"), result.discountVnd());
        assertEquals(1, saved.size());
        assertEquals(result, saved.get(0));
    }

    @Test
    void rejectsInvalidCatalogPriceWithoutSaving() {
        UnitPriceCatalog catalog = sku -> new BigDecimal("-1");
        List<CheckoutTotal> saved = new ArrayList<>();

        var service = new CheckoutServiceAfter(
                catalog, saved::add, new DiscountPolicyV1());

        assertThrows(IllegalStateException.class,
                () -> service.checkout(
                        List.of(new OrderItem("SKU-01", 1)), false));
        assertEquals(0, saved.size());
    }
}
~~~

Test có giá trị vì nó xác minh:
- Kết quả cuối cùng phù hợp hợp đồng.
- Service sử dụng bảng giá được truyền qua port.
- Kết quả được **lưu đúng một lần** trong tình huống thành công.
- Giá catalog sai dẫn đến lỗi trước tác dụng phụ lưu.

Không nhất thiết phải mock và verify mọi phép cộng, mọi lời gọi helper hoặc thứ tự của các câu lệnh nội bộ. Nếu chúng không phải hợp đồng, việc kiểm tra quá chi tiết có thể khiến test bị phá khi refactor hợp lệ.

### So sánh trước/sau có thật sự tương đương?

Ví dụ đã dùng hai class riêng để đặt cạnh nhau. Trong công việc thực, nhóm có thể chạy cùng bộ test hành vi trên cả hai triển khai để phát hiện khác biệt không mong muốn, nhưng vẫn phải xác định **hành vi cũ có đúng hợp đồng không**.

Nếu phiên bản cũ có bug (ví dụ dùng **>** thay vì **>=**), test so sánh hai phiên bản có thể muốn giữ cả bug. Khi đó nên:
1. Xác nhận hợp đồng nghiệp vụ đúng.
2. Tách quyết định **sửa bug** khỏi mục tiêu **refactor không đổi hành vi**.
3. Ghi thay đổi hành vi một cách minh bạch và bổ sung test hồi quy.

Không nên tuyên bố “chỉ refactor” khi thực tế đã thay giá trị nghiệp vụ.

## 11. Khi nào có thể dừng ví dụ trên?

Hãy quay lại mục tiêu đã đặt: **tách quy tắc giảm giá khỏi điều phối tra giá/lưu** để có thể kiểm thử độc lập.

Một quyết định dừng có thể dựa trên bảng:

| Tiêu chí | Bằng chứng | Kết luận |
| --- | --- | --- |
| Quy tắc giảm giá chỉ có một nơi sở hữu | **DiscountPolicyV1** chứa ngưỡng, tỷ lệ và làm tròn | Đạt trong phạm vi minh họa |
| Policy có thể test độc lập | Test trực tiếp **calculate(...)** không cần catalog/store | Đạt |
| Nhánh nghiệp vụ quan trọng được kiểm tra | Test dưới, bằng ngưỡng, không preferred và làm tròn | Đạt với các trường hợp đã xác định |
| Ranh giới service còn đúng | Test catalog và store, đường lỗi không lưu | Đạt ở mức unit test |
| Thay đổi không cần thiết được tránh | Không đổi giao thức, database, async hoặc transaction | Đạt theo phạm vi |
| Test/tích hợp dự án thật | Phải xác nhận trong build và môi trường đại diện | Chưa có bằng chứng chỉ từ snippet |

Vì bài học này chỉ trình bày code minh họa, **không thể khẳng định đã chạy test hay pipeline thật**. Trong dự án, người thực hiện cần chạy kiểm tra được yêu cầu và thu bằng chứng trước khi kết luận hoàn tất.

Nếu mọi tiêu chí áp dụng đều đạt, **đây là điểm dừng hợp lý**. Không cần:
- Tạo **IDiscountPolicyFactoryRegistry** cho một policy.
- Chuyển mọi kiểu dữ liệu sang inheritance.
- Thay toàn bộ API bằng event sourcing.
- Viết lại cơ chế lưu đơn chưa liên quan.
- Tái cấu trúc mọi service khác chỉ vì có cơ hội.

Những công việc ấy có thể được đề xuất riêng với **vấn đề, bằng chứng và mục tiêu độc lập**.

## 12. Đo độ dễ thay đổi: đừng chỉ đếm số dòng

Khi mục tiêu là **maintainability**, có thể cần một bằng chứng khác hiệu năng.

### 12.1. Một tình huống thay đổi giả định

Giả sử chính sách giảm từ 5% sang 7%, giữ nguyên ngưỡng. Trước refactor, công thức có thể ở nhiều service; sau refactor, thay đổi có thể chỉ cần ở policy và test hợp đồng.

Hãy hỏi:
- **Có bao nhiêu nơi chứa quyết định nghiệp vụ cần sửa?**
- **Có bao nhiêu module cần triển khai/kiểm chứng?**
- **Người sửa có phải hiểu chi tiết I/O hoặc transaction để thay một công thức thuần không?**
- **Có test báo chính xác lỗi thuộc chính sách không?**
- **Tác động sang caller có được kiểm soát qua hợp đồng không?**

Có thể ghi **change scenario**: “Đổi tỷ lệ, giữ nguyên quy tắc chọn khách”. Thử xác định các phần phải sửa trên mã trước và sau. Đây là bằng chứng trực tiếp về chi phí thay đổi dự kiến.

### 12.2. Đếm dependency ở đúng phạm vi

Trước refactor, để test phép tính giảm giá có thể phải cấu hình catalog và store. Sau refactor, policy không cần các phụ thuộc đó.

Bằng chứng:
- Kiểu **DiscountPolicyV1** không giữ tham chiếu tới **UnitPriceCatalog** hoặc **CheckoutResultStore**.
- Unit test của policy tạo được đối tượng và assert kết quả bằng một dòng gọi hàm thuần.
- Logic điều phối vẫn được giữ ở service.

Nhưng không nên biến “số dependency bằng 0” thành mục tiêu tuyệt đối. Một thành phần cần kiểm tra chính sách động ở database có thể hợp lý khi phụ thuộc vào một port phù hợp. Đúng hay sai phụ thuộc hợp đồng và lý do thay đổi.

### 12.3. Complexity metrics là công cụ hỗ trợ

Các metric như số nhánh, cyclomatic complexity, độ dài phương thức hoặc số lớp phụ thuộc có thể giúp nhận ra vùng khó hiểu. Tuy nhiên:
- Giảm số nhánh trong một lớp bằng cách chuyển toàn bộ nhánh sang lớp khác **không nhất thiết giảm độ phức tạp toàn hệ thống**.
- Tạo nhiều phương thức nhỏ có tên mơ hồ có thể tăng chi phí điều hướng.
- Một thuật toán nhiều nhánh nhưng có bảng quyết định rõ có thể dễ kiểm tra hơn chuỗi callback khó đọc.
- Một điểm số tĩnh không biết các ràng buộc nghiệp vụ mà con người phải giữ.

Hãy dùng metric như **bằng chứng bổ trợ**, không phải mục tiêu thay thế cho khả năng thay đổi thực tế.

## 13. Khi mục tiêu là hiệu năng: cách chứng minh để biết dừng

Có những refactor nhằm giảm số truy vấn, memory allocation hoặc độ trễ. Với mục tiêu này, **đánh giá trên workload đại diện** rất quan trọng.

Ví dụ đặt mục tiêu:

> “Ở kịch bản 300 request/giây với phân bố tenant như production, giảm p95 endpoint tìm đơn xuống dưới SLO 250 ms mà không tăng tỷ lệ lỗi, p99, bộ nhớ hoặc chi phí database vượt giới hạn đã thống nhất.”

Đây là ví dụ về cách phát biểu mục tiêu, **không phải SLO mặc định cho mọi dự án**.

### Đo trước và sau như thế nào?

1. **Giữ cùng loại workload**: tỷ lệ endpoint, kích thước payload, số key nóng, phân bố tenant và dữ liệu.
2. **Ghi cấu hình**: JDK, heap, GC, số instance, connection pool, database, giới hạn tài nguyên.
3. **Có warm-up hợp lý**: JIT, class loading và cache có thể ảnh hưởng số liệu.
4. **Quan sát cả kết quả và lỗi**: throughput thành công, p50/p95/p99, timeout, số request từ chối.
5. **Đo tài nguyên**: CPU, allocation, heap, GC, số query, DB wait, connection wait.
6. **Chạy lặp đủ để biết biến thiên**: không kết luận từ một lần đo có nhiễu hoặc môi trường khác nhau.
7. **Xác định phần thay đổi thực sự gây cải thiện**: tránh cùng lúc nâng DB, đổi cache và refactor code rồi gán mọi lợi ích cho một yếu tố.

Nếu p95 đã đạt mục tiêu nhưng p99 tệ đi đáng kể, **guardrail chưa đạt**. Không nên tuyên bố hoàn tất chỉ vì chọn một chỉ số đẹp nhất.

### Microbenchmark không thay thế load test

**JMH** hữu ích khi cần đo một đoạn Java nhỏ dưới JVM. Nhưng microbenchmark một hàm map hoặc stream nhanh hơn 20% chưa chứng minh API nhanh hơn nếu phần lớn thời gian nằm ở database hoặc network.

Điểm dừng phải gắn với **cấp độ vấn đề ban đầu**:
- Tối ưu thuật toán thuần → có thể dùng benchmark thuật toán kèm test đúng đắn.
- Giảm p99 API → phải đo ở mức luồng API và phụ thuộc liên quan.
- Giảm database load → cần số query, execution plan và số liệu DB đại diện.
- Giảm GC pressure → cần allocation/GC trong tải thực tế.

### Khi kết quả không rõ ràng

Nếu p95 thay đổi từ 248 ms sang 246 ms trong khi biến thiên giữa các lần chạy lớn hơn khoảng chênh, không đủ bằng chứng để kết luận cải thiện đáng kể. Có thể:
- Đo thêm với phương pháp ổn định hơn.
- Đổi giả thuyết về điểm nghẽn.
- Giữ phiên bản đơn giản nếu refactor không đem lại lợi ích được chứng minh.
- Tách công việc nghiên cứu hiệu năng khỏi một PR refactor đang mở quá lâu.

**Không nên tự tạo phần trăm cải thiện không được đo.** Nếu chưa có đủ dữ liệu, ghi “chưa chứng minh”, không tô màu xanh cho tiêu chí.

## 14. Tránh đo sai mục tiêu

Một nguyên tắc đo lường quan trọng: **khi chỉ số trở thành mục tiêu độc lập, người ta có thể tối ưu chỉ số mà không cải thiện chất lượng thật**.

Ví dụ:

| Chỉ số bị theo đuổi riêng lẻ | Hành vi tối ưu sai | Điều thực sự nên kiểm chứng |
| --- | --- | --- |
| Ít dòng code | Dùng biểu thức nén, bỏ validation | Ý định rõ, hợp đồng và trường hợp biên đúng |
| Ít class | Dồn mọi trách nhiệm vào một service | Coupling hợp lý, ranh giới dễ thay đổi |
| Ít dependency | Tạo global state hoặc tự dựng I/O bên trong | Phụ thuộc rõ, tiêm được, dễ kiểm thử |
| 100% line coverage | Test chạy qua dòng nhưng không assert hợp đồng | Test có khả năng phát hiện lỗi quan trọng |
| Cyclomatic complexity thấp | Đẩy nhánh sang framework cấu hình động khó hiểu | Độ phức tạp thực của quyết định được kiểm soát |
| p50 giảm | Bỏ qua p99 và timeout | Trải nghiệm và SLO của các nhóm request quan trọng |
| Số query giảm | Gộp thành một query nặng làm DB tốn RAM | Tổng chi phí/độ trễ/đúng đắn của workload |
| Không còn duplicate lines | Gộp hai chính sách độc lập vào một helper | Cùng tri thức có đúng một nơi sở hữu |

Thay vì tiêu chí “giảm số dòng”, hãy dùng tiêu chí “một thay đổi ngưỡng khuyến mại không cần chạm vào tầng I/O và không tạo kết quả khác nhau giữa các luồng”.

## 15. Khi dừng quá sớm cũng là vấn đề

Sự thận trọng không nên trở thành lý do bỏ dở vấn đề đã được chấp nhận xử lý.

### Ví dụ 1 — Chỉ đổi tên mà bỏ nguyên nhân

Một lớp **OrderManager** vừa kiểm tra quyền, tính giá, gọi cổng thanh toán và gửi sự kiện. Mục tiêu là **có thể test riêng phép tính giá**. Nhóm đổi tên thành **CheckoutCoordinator**, thêm comment và formatter, nhưng vẫn không thể test phép tính mà không khởi tạo bốn phụ thuộc.

**Kết luận:** Định dạng/tên tốt hơn, nhưng **mục tiêu chưa đạt**. Dừng với tuyên bố hoàn tất sẽ gây hiểu nhầm.

### Ví dụ 2 — Thêm test nhưng vẫn có hai nguồn quy tắc

Hai service cùng tự tính ngưỡng miễn phí vận chuyển. Nhóm thêm test giống nhau cho cả hai, nhưng mỗi nơi vẫn giữ literal riêng.

**Kết luận:** Test có thể phát hiện một số sai lệch, nhưng khi chính sách đổi vẫn phải sửa hai nơi. Nếu mục tiêu là giảm chi phí cập nhật đồng bộ, cần xem **nguồn sở hữu** hoặc cơ chế đồng bộ hợp đồng, không chỉ tăng test.

### Ví dụ 3 — Tách method nhưng không giảm phụ thuộc

Một phương thức dài được chia thành mười phương thức private, tất cả cùng đọc/ghi một tập field mutable. Người đọc vẫn phải theo dõi trạng thái chung và thứ tự gọi để hiểu một thao tác.

**Kết luận:** Có thể làm mã ngắn hơn, nhưng chưa chứng minh **có thể suy luận và thay đổi độc lập**. Cần xem lại ranh giới dữ liệu, bất biến và trách nhiệm.

### Ví dụ 4 — Chỉ đo phần code mới, không đo hệ thống

Một phép tính được cải thiện bằng cấu trúc dữ liệu mới trong microbenchmark, nhưng API vẫn bị nghẽn connection pool. Mục tiêu ban đầu là giảm p99 API.

**Kết luận:** Có cải thiện cục bộ, nhưng chưa chứng minh cải thiện **đúng cấp độ đã cam kết**.

## 16. Khi dừng quá muộn gây chi phí mới

### 16.1. “Đang tiện sửa” biến thành thiết kế lại cả hệ thống

Một refactor nhằm loại bỏ điều kiện lặp ở hai nơi lại kết thúc bằng:
- Đổi tên tất cả DTO.
- Viết một framework rule registry.
- Thêm nhiều lớp adapter chưa có người dùng.
- Chuyển dữ liệu hiện tại sang cấu trúc mới.
- Thay đổi schema message.
- Đổi cơ chế transaction.

Mỗi quyết định mới có thể cần thảo luận độc lập. Gộp tất cả làm tăng bề mặt hồi quy, khó review và khó rollback.

### 16.2. Trừu tượng hóa cho biến thể chưa tồn tại

Nếu hệ thống chỉ có một chính sách cố định, tạo **PolicyFactory**, **PolicyProvider**, **PolicyRegistry** và DSL để “chuẩn bị cho tương lai” có thể khiến người mới phải đi qua nhiều lớp trước khi thấy công thức thật.

Khi chưa có bằng chứng về những biến thể sắp tới, một lớp policy có tên rõ và test đầy đủ có thể là **điểm dừng tốt hơn**.

### 16.3. Thay mọi cấu trúc quen thuộc bằng một phong cách mới

Không có lý do kỹ thuật để chuyển toàn bộ vòng lặp sang Stream, mọi class sang record hoặc mọi if sang pattern matching chỉ vì các khả năng Java mới xuất hiện.

Nếu cách cũ rõ, đúng, được test và không nằm trong mục tiêu cải thiện, thay đổi phong cách có thể tạo diff mà không giảm rủi ro. **Quy ước nhất quán** vẫn quan trọng, nhưng nên xử lý trong phạm vi và kế hoạch riêng.

### 16.4. Kéo dài refactor làm mất cơ hội xác nhận thực tế

Một PR duy trì hàng tuần có thể liên tục xung đột với thay đổi của các nhóm khác, tăng rủi ro merge và khiến mục tiêu ban đầu không còn phù hợp. Chia thành các PR nhỏ, mỗi PR có tiêu chí riêng, giúp thu bằng chứng từng bước và dừng khi đủ.

## 17. Quy tắc quyết định dừng, tiếp tục hoặc quay lui

Một cuộc review ngắn có thể dùng bốn câu hỏi:

1. **Vấn đề gốc còn xảy ra ở phạm vi đã định không?**
2. **Bằng chứng hành vi và guardrail còn đạt không?**
3. **Thay đổi tiếp theo giải quyết rủi ro cụ thể nào?**
4. **Lợi ích bổ sung có tương xứng chi phí, phạm vi và rủi ro không?**

Từ đó có bốn lựa chọn:

| Tình huống | Quyết định | Điều cần ghi lại |
| --- | --- | --- |
| Mục tiêu đạt, hợp đồng còn đúng | **Dừng** | Bằng chứng, phạm vi và giới hạn |
| Mục tiêu chưa đạt nhưng còn hướng xử lý nhỏ, rõ | **Tiếp tục có kiểm soát** | Bước kế tiếp, tiêu chí mới, rủi ro |
| Mục tiêu chưa đạt, nguyên nhân cần nghiên cứu thêm | **Thu hẹp/tạm dừng để đo hoặc spike** | Câu hỏi chưa biết, cách thu dữ liệu |
| Phát sinh hồi quy, sai dữ liệu hoặc rủi ro vượt ngưỡng | **Sửa hoặc quay lui** | Ảnh hưởng, đường khôi phục và kiểm chứng |

Dừng hoặc quay lui **không tự động là thất bại**. Nếu giả thuyết refactor không được bằng chứng ủng hộ, việc dừng trước khi làm hệ thống phức tạp hơn là một quyết định kỹ thuật có trách nhiệm.

### Phân biệt dừng phạm vi và bỏ qua khoản nợ

Có thể refactor hoàn tất đúng mục tiêu **“tách policy để test”**, trong khi hệ thống vẫn còn **nợ về database transaction hoặc API versioning**. Những vấn đề khác cần được ghi nhận và ưu tiên riêng, không nhất thiết kéo tất cả vào cùng một PR.

Không dùng “đã dừng refactor” làm lý do quên một rủi ro đang gây sự cố hoặc vi phạm bảo mật. Trường hợp đó phải được xử lý theo quy trình phù hợp với mức độ ảnh hưởng.

## 18. Điểm dừng trong refactor lớn hoặc migration nhiều giai đoạn

Một dự án chuyển từ repository trực tiếp sang tầng adapter có thể cần nhiều tuần, nhiều module và nhiều lần triển khai. Nếu đặt duy nhất tiêu chí “mọi module đã chuyển” cho cả giai đoạn, khó biết khi nào một phần đã an toàn để merge.

Hãy đặt **milestone có bằng chứng riêng**:

| Giai đoạn | Mục tiêu | Điểm dừng giai đoạn |
| --- | --- | --- |
| **1. Bảo vệ hành vi** | Có characterization/contract test cho đường hiện tại | Test bao phủ các đường quan trọng và lỗi đã biết |
| **2. Tạo hợp đồng port** | Mô hình miền không phụ thuộc API của driver cụ thể | Build/test của miền không cần driver, contract của port rõ |
| **3. Chuyển một caller** | Một luồng hoạt động qua adapter mới | Unit/integration test và observability của luồng đạt |
| **4. Chuyển các caller còn lại** | Không còn dùng driver trực tiếp trong phạm vi | Kiểm tra usage, test hồi quy, rollout có kiểm soát |
| **5. Loại bỏ đường cũ** | Tránh hai implementation không cần thiết | Không còn consumer cũ, rollback/migration đạt yêu cầu |

Mỗi giai đoạn có thể dừng độc lập để review, đo và hạn chế rủi ro. Nếu phát sinh dữ liệu cho thấy cách tiếp cận không phù hợp, nhóm có thể thay phương án sớm thay vì cố hoàn tất kiến trúc đã chọn trước khi biết vấn đề thật.

### Feature flag và rollout

Với thay đổi có rủi ro vận hành, **feature flag**, canary hoặc shadow comparison có thể giúp quan sát trước khi chuyển toàn bộ traffic. Nhưng những cơ chế này cũng có chi phí:
- Hai đường code cùng tồn tại cần kiểm soát thời hạn.
- Phải bảo đảm không thực thi tác dụng phụ trùng trong shadow mode.
- Metric so sánh phải có nguồn và quy tắc đồng nhất.
- Cần kế hoạch gỡ flag và code cũ sau khi ổn định.

Vì vậy, điểm dừng có thể bao gồm **“đường mới đạt SLO và hợp đồng; đường cũ đã được loại bỏ sau rollout”**, thay vì chỉ “đã thêm feature flag”.

## 19. Khi nào cần so sánh hành vi trước/sau bằng dữ liệu thật?

Test thủ công hoặc unit test thường không thấy hết các ràng buộc hệ thống cũ, đặc biệt với dữ liệu lịch sử. Trong một số trường hợp, có thể so sánh kết quả **phiên bản trước và sau** trên một tập dữ liệu có kiểm soát.

Ví dụ:
- Tính tổng hóa đơn cho các đơn có giảm giá, thuế và hoàn tiền khác nhau.
- So sánh kết quả parser cũ/mới trên dữ liệu có định dạng lỗi.
- So sánh danh sách bản ghi của truy vấn SQL được tối ưu.
- So sánh API serialization của hai phiên bản.

### Quy trình so sánh đáng tin

1. **Xác định phạm vi dữ liệu:** đủ đại diện cho trường hợp thường, biên, dữ liệu cũ và dữ liệu bất thường.
2. **Bảo vệ thông tin:** chỉ dùng dữ liệu được phép, đã kiểm soát truy cập và xử lý theo chính sách.
3. **Định nghĩa quy tắc so sánh:** giá trị nào phải bằng tuyệt đối, giá trị nào có thể khác vì nguyên tắc đã phê duyệt.
4. **Phân biệt thời gian và dữ liệu động:** bảng giá, thời gian hiện tại, ID ngẫu nhiên hoặc trạng thái bên ngoài cần được kiểm soát.
5. **Không thực thi tác dụng phụ hai lần:** đặc biệt với thanh toán, email, kho hàng và cập nhật DB.
6. **Ghi lại chênh lệch:** phân loại khác biệt do bug cũ, thay đổi có chủ đích hay hồi quy.
7. **Chỉ kết luận khi khác biệt được giải thích đủ cho mức rủi ro**.

**Cẩn trọng:** Nếu phiên bản cũ chứa bug, kết quả cũ không phải tiêu chuẩn đúng. Việc so sánh giúp phát hiện **thay đổi**, còn hợp đồng nghiệp vụ quyết định thay đổi nào đúng.

## 20. Chỉ số định lượng và bằng chứng định tính bổ trợ nhau

Một số cải thiện có thể đo bằng số:
- Số nơi phải sửa khi thay một chính sách.
- Số phụ thuộc trực tiếp của miền vào thư viện hạ tầng.
- Số query hoặc network call trên một request.
- Độ trễ p95/p99 và memory allocation ở workload cố định.
- Thời gian build/test một module sau khi tách ranh giới.

Một số cải thiện cần đánh giá bằng tình huống và review:
- Tên lớp có diễn đạt trách nhiệm không?
- Một người chưa biết code có thể tìm nơi sở hữu quy tắc không?
- Test có diễn đạt trường hợp biên và lỗi rõ ràng không?
- Một thay đổi dự kiến có thể làm mà không hiểu phần không liên quan không?
- Abstraction có giảm giả định hay chỉ thêm tầng gián tiếp?

**Đừng biến đánh giá định tính thành tuyên bố không có bằng chứng.** Có thể dùng **task-based review**: giao một tình huống thay đổi cụ thể cho reviewer và xem họ tìm được điểm sửa, test và phụ thuộc không. Nếu nhóm có điều kiện, thử với hai người phát triển không trực tiếp thực hiện refactor.

Điều này không cần một nghiên cứu lớn cho mọi PR. Một câu hỏi đúng trong review thường đã đủ hữu ích: **“Nếu ngày mai thay ngưỡng, người mới sửa ở đâu và biết mình đúng bằng cách nào?”**

## 21. Ghi nhận điểm dừng trong pull request

Một mô tả PR có thể dùng cấu trúc sau:

~~~text
MỤC TIÊU
Tách chính sách giảm giá khỏi CheckoutService để kiểm thử độc lập
và tránh sửa logic trực tiếp trong tầng I/O.

TRƯỚC KHI SỬA
- Logic discount nằm trong phương thức checkout, cùng tra giá và lưu.
- Test discount đòi cấu hình catalog/store.
- Trường hợp tại ngưỡng và làm tròn chưa được kiểm tra riêng.

SAU KHI SỬA
- DiscountPolicyV1 sở hữu ngưỡng/tỷ lệ/làm tròn.
- CheckoutService chỉ tính subtotal, gọi policy và lưu kết quả.
- Không thay đổi public API, cơ chế tra giá hoặc lưu đơn.

BẰNG CHỨNG
- Unit test: dưới/bằng ngưỡng, không preferred, làm tròn, input lỗi.
- Service test: tổng đúng, save một lần, giá catalog sai không lưu.
- Build/integration checks: [ghi lệnh và kết quả thực đã chạy].
- Diff review: không có thay đổi hợp đồng ngoài phạm vi.

ĐIỂM DỪNG
Mục tiêu tách policy và kiểm chứng hành vi đã đạt.
Không thêm factory/registry khi chưa có policy thứ hai.

GIỚI HẠN CÒN LẠI
- Adapter/database transaction do test tích hợp riêng bảo vệ.
- Các chính sách thuế và vận chuyển không thuộc PR này.
~~~

Mẫu này buộc người viết phân biệt **kết quả thực đã đo** với **những việc chưa kiểm chứng**. Không nên điền “PASS” cho build, integration hoặc benchmark chưa chạy; nếu môi trường không cho phép, ghi rõ thiếu bằng chứng và chuyển trách nhiệm kiểm tra đến bước thích hợp.

### Ghi việc còn lại như thế nào?

Nếu trong lúc refactor phát hiện một vấn đề khác nhưng không có lý do đưa vào PR, có thể ghi backlog:
- Vấn đề cụ thể và tác động.
- Phạm vi liên quan.
- Lý do không thuộc mục tiêu hiện tại.
- Bằng chứng/rủi ro ban đầu.
- Điều kiện xử lý hoặc người chịu trách nhiệm.

Không nên ghi hàng chục TODO mơ hồ như “clean more”. Những việc khác chỉ nên được mở nếu có **vấn đề và lợi ích rõ**.

## 22. Case study: API báo cáo đơn hàng

Một API xuất lịch sử đơn hàng chậm khi dữ liệu của một khách doanh nghiệp tăng nhanh. Nhóm xác định một query **N+1**: với mỗi dòng đơn hàng, code lại truy vấn thông tin khách. Mục tiêu refactor là **giảm số truy vấn theo số dòng**, không đổi response và không tạo thêm rủi ro về bộ nhớ.

### Trước refactor

Với 100 đơn, hệ thống thực hiện một query lấy danh sách và khoảng 100 query phụ. Trường hợp này chỉ để minh họa: số query thực tế phụ thuộc ORM, cache và code cụ thể.

Nhóm dự định gom dữ liệu cần thiết thành một truy vấn hợp lý hoặc tải dữ liệu theo batch.

### Sau thay đổi đầu tiên

Nhóm đạt:
- Không còn truy vấn phụ theo từng dòng cho cùng nhu cầu.
- Contract response và thứ tự kết quả giữ nguyên trong các test đã xác định.
- Số query ở kịch bản đại diện giảm từ mức tăng theo số dòng sang số lượng giới hạn theo batch.
- p95 API cải thiện theo bài load test có cùng dữ liệu và cấu hình.
- p99 và bộ nhớ không xấu đi ngoài giới hạn đã thống nhất.

Có người đề xuất đổi luôn từ ORM sang raw JDBC, chuyển API sang GraphQL và xây cache phân tán.

### Có nên tiếp tục?

Nếu mục tiêu gốc là **loại bỏ N+1** và các guardrail đã đạt, nhóm có lý do tốt để **dừng**. Các đề xuất mới cần yêu cầu và bằng chứng riêng.

Nhưng nếu bài đo cho thấy giải pháp mới tạo một **join quá lớn** khiến p99 tệ đi cho khách có dữ liệu lệch phân bố, thì **chưa đủ điều kiện dừng** dù số query giảm. Cần điều tra fan-out, kích thước kết quả, khả năng phân trang hoặc phương án batch thích hợp.

### Bài học từ case study

- “Ít query hơn” không phải mục tiêu cuối nếu trải nghiệm và tài nguyên xấu đi.
- “Đã hết N+1” có thể là bằng chứng cấu trúc, nhưng vẫn cần kiểm tra trên workload đúng.
- Một refactor thành công không phải lý do đổi thêm kiến trúc không liên quan.
- Điểm dừng dựa trên **điều kiện đã thỏa**, không dựa trên mức độ hài lòng chủ quan về độ mới của code.

## 23. Case study: lớp nghiệp vụ quá lớn

Một lớp **CustomerAccountService** có 1.200 dòng, gồm:
- Kiểm tra dữ liệu tài khoản.
- Tra quyền.
- Tính hạn mức.
- Gọi cổng thanh toán.
- Ghi audit.
- Trả kết quả API.

Nhóm đặt mục tiêu: **có thể thay quy tắc hạn mức mà không cần thay hoặc chạy các phụ thuộc thanh toán, audit và HTTP**.

### Một bước refactor phù hợp

Tách **CreditLimitPolicy** nhận dữ liệu đã được xác minh, trả quyết định có tên rõ. Service còn nhiệm vụ điều phối và kiểm tra quyền ở ranh giới thích hợp.

Bằng chứng để dừng:
- Unit test của policy không khởi tạo payment client hay audit repository.
- Thay đổi một mức hạn chỉ chạm policy và test phù hợp.
- Test service xác nhận lệnh thanh toán/audit không xảy ra khi từ chối.
- API/contract test xác nhận kết quả và lỗi giữ nguyên.
- Không phát sinh thay đổi giao thức hoặc transaction ngoài mục tiêu.

### Một bước tiếp tục có thể không cần

Tách ngay 1.200 dòng thành 50 class chỉ để mỗi class dưới 30 dòng chưa chắc giúp ích. Việc cần hỏi là **phần còn lại có chứa cùng vấn đề đang cản trở yêu cầu sắp tới không**. Nếu chưa, đó là đề xuất khác.

### Nếu phát hiện bảo mật sai thì sao?

Nếu trong lúc tách policy nhóm phát hiện có đường thanh toán không kiểm tra quyền, đây là **rủi ro an toàn cần phân loại và xử lý riêng theo mức ảnh hưởng**. Không được xem nó như một thay đổi phong cách tùy chọn, hoặc tuyên bố kết thúc an toàn chỉ vì refactor ban đầu đã đạt.

## 24. Checklist trước khi kết thúc một refactor

Hãy kiểm tra theo nhóm, không chỉ nhìn kết quả formatter.

### Mục tiêu và phạm vi
- [ ] Vấn đề ban đầu và lý do thay đổi đã được ghi rõ.
- [ ] Có tiêu chí hoàn tất đủ cụ thể để người khác đánh giá.
- [ ] Phần code được sửa nằm trong phạm vi hoặc được giải thích vì sao cần mở rộng.
- [ ] Không còn sửa thêm chỉ vì “đang tiện” mà thiếu lợi ích xác định.

### Hành vi và an toàn
- [ ] Những trường hợp biên và lỗi nghiệp vụ quan trọng được kiểm tra.
- [ ] API, schema, dữ liệu lịch sử và tác dụng phụ không bị đổi ngoài chủ đích.
- [ ] Kiểm tra quyền, transaction, xử lý đồng thời hoặc idempotency được bảo vệ ở đúng tầng khi liên quan.
- [ ] Rủi ro hồi quy hoặc sai lệch được phát hiện đã sửa, giải thích hoặc quay lui.
- [ ] Không gán “PASS” cho kiểm tra chưa được thực thi.

### Bằng chứng cải thiện
- [ ] Có so sánh với baseline phù hợp.
- [ ] Bằng chứng gắn với mục tiêu thật: dễ thay đổi, coupling, đúng đắn hoặc hiệu năng.
- [ ] Chỉ số phụ không bị dùng thay thế hợp đồng.
- [ ] Các guardrail như p99, lỗi và tài nguyên không xấu đi ngoài giới hạn.
- [ ] Người review có thể xác định nơi sở hữu quy tắc và cách sửa lần sau.

### Kết thúc và bàn giao
- [ ] Giới hạn còn lại đã được ghi nhận nếu có.
- [ ] Công việc mới được tách ticket khi có lý do và người sở hữu.
- [ ] Rollback/migration được xem xét nếu có thay đổi vận hành.
- [ ] PR và test có thể kiểm tra ở phạm vi đủ nhỏ.
- [ ] Quyết định dừng được giải thích bằng bằng chứng, không bằng cảm giác.

Checklist là công cụ hỗ trợ **đánh giá theo rủi ro**. Một refactor đổi tên biến cục bộ không cần quy trình migration hay benchmark; một thay đổi transaction quan trọng cần kiểm tra kỹ hơn nhiều.

## 25. Những lỗi tư duy phổ biến về điểm dừng

| Nhận định | Vấn đề | Cách nghĩ chính xác hơn |
| --- | --- | --- |
| “Hết code smell thì mới được dừng.” | Không có codebase hoàn toàn không còn điểm có thể cải thiện | Dừng khi mục tiêu được chứng minh và rủi ro còn lại được quản lý |
| “Mọi test xanh nghĩa là xong.” | Test có thể thiếu hợp đồng hoặc đường tích hợp | Cần cả bằng chứng đạt mục tiêu và kiểm tra guardrail |
| “Giảm số dòng 40% là thành công.” | Có thể tăng độ phức tạp ngầm | Đánh giá khả năng hiểu, thay đổi và hành vi |
| “Đã sửa một lớp thì sửa hết những lớp tương tự.” | Mở rộng phạm vi không cần thiết | Phân biệt cùng tri thức và chỉ giống cú pháp |
| “Có interface là dễ mở rộng.” | Interface chưa có biến thể có thể là tầng gián tiếp dư | Tạo abstraction khi có nhu cầu thay thế thật |
| “Benchmark nhanh hơn nên API chắc nhanh hơn.” | Có thể tối ưu sai điểm nghẽn | Đo ở cấp độ đã cam kết |
| “Không được dừng cho đến khi kiến trúc hoàn hảo.” | Kiến trúc luôn có đánh đổi và bối cảnh thay đổi | Dùng exit criteria theo vấn đề cụ thể |
| “Một bước refactor thất bại thì phải cố hoàn tất.” | Có thể làm tăng chi phí và rủi ro | Đánh giá lại giả thuyết, thu hẹp hoặc rollback |
| “Đã dừng thì không cần ghi nợ còn lại.” | Người kế tiếp có thể hiểu nhầm mức hoàn tất | Ghi phạm vi chưa xử lý và trigger thích hợp |
| “Dừng refactor đồng nghĩa bỏ qua bug vừa thấy.” | Rủi ro nghiêm trọng cần đường xử lý riêng | Phân loại và xử lý theo mức ảnh hưởng |

## 26. Bài tập tự luyện

### Bài tập 1 — Viết exit criteria

Một lớp **InvoiceService** vừa tính thuế vừa ghi database. Nhóm muốn tách công thức thuế thành thành phần có thể kiểm thử độc lập.

Hãy viết ít nhất năm tiêu chí, gồm:
- Mục tiêu cấu trúc.
- Trường hợp biên tính thuế và làm tròn.
- Ranh giới không được thay đổi.
- Cách chứng minh công thức không còn phụ thuộc I/O.
- Điều kiện để dừng, không thêm abstraction không cần thiết.

*Gợi ý:* Một policy thuần có test, service vẫn giữ hợp đồng lưu và API; không nhất thiết thay toàn bộ repository.

### Bài tập 2 — Test xanh nhưng mục tiêu chưa đạt

Hai service cùng tự viết điều kiện miễn phí vận chuyển. Nhóm sửa sai dấu so sánh và thêm unit test cho mỗi service. Cả hai đều xanh.

**Có thể dừng chưa**, nếu mục tiêu là “giảm nguy cơ hai service lệch công thức khi ngưỡng thay đổi”? Hãy giải thích bằng hai loại bằng chứng: **đúng đắn hiện tại** và **khả năng thay đổi sau này**.

*Gợi ý:* Test xanh bảo vệ một số ca hiện tại; việc có hai nơi sở hữu công thức vẫn là rủi ro nếu phải cập nhật đồng bộ.

### Bài tập 3 — Refactor quá mức

Sau khi tách một chính sách giảm giá có test tốt, đồng nghiệp đề xuất:
- Tạo năm interface.
- Thêm factory và plugin registry.
- Đổi mọi DTO sang inheritance.
- Chuyển database sang một công nghệ khác.

Hãy nêu câu hỏi cần yêu cầu trước khi mở rộng phạm vi. Chọn một đề xuất có thể có giá trị trong tương lai và mô tả **bằng chứng nào khiến nó thành một công việc riêng có mục tiêu rõ**.

### Bài tập 4 — Đo cải thiện hiệu năng

Một endpoint có p95 = 270 ms, p99 = 1.500 ms ở 300 req/s. Sau refactor, p95 = 230 ms nhưng p99 = 2.100 ms. Mục tiêu đề ra là p95 dưới 250 ms **và p99 không xấu đi đáng kể**.

Hãy xác định điều kiện nào đạt, điều kiện nào chưa đạt, cần phân tích thêm gì và vì sao không thể tuyên bố hoàn tất chỉ dựa trên p95.

*Gợi ý:* Tail latency và phân bố dữ liệu có thể đang thay đổi; cần kiểm tra cấu hình, tỷ lệ lỗi, dữ liệu nóng và độ biến thiên đo lường.

### Bài tập 5 — Giữ hành vi của hệ thống cũ

Khi refactor một module tính phí, test so sánh trước/sau phát hiện khác biệt ở đúng ngưỡng. Code cũ dùng **>**, code mới dùng **>=**.

Hãy nêu:
- Phải tìm hiểu hợp đồng nghiệp vụ thế nào?
- Khi nào đây là bug fix thay vì refactor thuần?
- Cần test gì?
- Nên ghi thay đổi vào PR và thông báo tới caller thế nào?

*Gợi ý:* Không xem output cũ là chân lý chỉ vì nó đã tồn tại lâu.

### Bài tập 6 — Dừng sau một thay đổi nhỏ

Một service có 900 dòng. Mục tiêu lần này là ngăn việc thay chính sách cấp quyền gây sửa code thanh toán. Nhóm đã tách **AuthorizationPolicy** và có unit/integration tests bảo vệ luồng thanh toán.

Một thành viên đề xuất tiếp tục chia toàn bộ service thành các class dưới 50 dòng. Hãy viết một nhận xét code review nêu:
- Bằng chứng mục tiêu đã đạt.
- Vì sao chưa có cơ sở cho thay đổi mở rộng.
- Điều kiện nào sẽ khiến nhóm xem xét thêm một refactor mới.

### Bài tập 7 — Lập milestone

Một migration từ API v1 sang v2 phải giữ client cũ hoạt động trong ba tháng. Hãy chia thành các milestone nhỏ, mỗi milestone có **mục tiêu, bằng chứng, rollback** và **điểm dừng**. Giải thích khi nào có thể xóa API v1 mà không dựa vào giả định “không còn ai gọi”.

### Bài tập 8 — Viết mô tả PR

Chọn một mùi mã có thật trong dự án học tập của bạn và viết mô tả PR theo mẫu: **vấn đề – baseline – mục tiêu – điều kiện bảo vệ – bằng chứng – điểm dừng – giới hạn còn lại**. Không cần sửa thật nếu không có môi trường; tập trung vào khả năng xác minh quyết định.

## 27. Tự kiểm tra kiến thức

**Câu 1.** Mã sau refactor ngắn hơn 30% có chứng minh chất lượng tốt hơn không?

*Trả lời:* Không. Số dòng không mô tả đầy đủ hợp đồng, coupling, khả năng hiểu hoặc rủi ro hồi quy. Cần bằng chứng gắn với vấn đề ban đầu.

**Câu 2.** Tại sao unit test xanh chưa đủ để kết luận refactor thành công?

*Trả lời:* Unit test chỉ bao phủ những trường hợp được viết và có thể không kiểm tra tích hợp, tác dụng phụ hoặc mục tiêu cấu trúc. Cần cả bảo vệ hành vi lẫn chứng minh cải thiện.

**Câu 3.** Khi nào nên dừng refactor một chính sách đã được tách ra?

*Trả lời:* Khi hợp đồng và trường hợp biên đã được kiểm chứng ở mức phù hợp, nơi sở hữu chính sách rõ, caller dùng đúng policy và không còn lợi ích được xác định cho thay đổi mở rộng trong phạm vi hiện tại.

**Câu 4.** Nếu refactor làm p95 tốt hơn nhưng p99 vi phạm guardrail, có nên coi là hoàn tất?

*Trả lời:* Không. Cần điều tra độ trễ đuôi, xác nhận phép đo và xử lý hoặc quay lui phần gây suy giảm trước khi tuyên bố đạt.

**Câu 5.** Một điểm dừng tốt có bắt buộc cần chỉ số định lượng không?

*Trả lời:* Không. Với chất lượng thiết kế, bằng chứng về ranh giới phụ thuộc, số nơi sở hữu quy tắc và khả năng test độc lập có thể phù hợp. Nhưng bằng chứng vẫn phải kiểm chứng được, không chỉ là sở thích.

**Câu 6.** Nếu phát hiện lỗi bảo mật nghiêm trọng sau khi đạt mục tiêu refactor, có thể bỏ qua vì “đã dừng” không?

*Trả lời:* Không. Rủi ro ấy phải được phân loại và xử lý theo quy trình bảo mật/khắc phục tương ứng. Điểm dừng của refactor không phải quyền bỏ qua vấn đề an toàn.

**Câu 7.** Vì sao nên phân biệt baseline với target?

*Trả lời:* Baseline cho biết trạng thái trước sửa; target mô tả trạng thái muốn đạt. Không có baseline, khó nói cải thiện có thực; không có target, khó biết khi nào đủ để dừng.

**Câu 8.** Tạo nhiều interface và factory có luôn làm hệ thống dễ thay đổi hơn không?

*Trả lời:* Không. Nếu không có biến thể hoặc lý do thay đổi độc lập, các tầng gián tiếp có thể tăng chi phí đọc hiểu và coupling. Cần chứng minh nhu cầu và lợi ích.

**Câu 9.** Tại sao cần lưu giới hạn còn lại sau khi refactor hoàn tất?

*Trả lời:* Để người tiếp theo biết điều gì đã được chứng minh, điều gì chưa kiểm chứng và vấn đề nào cần đánh giá riêng; tránh hiểu nhầm “hoàn tất mục tiêu” thành “mọi nợ kỹ thuật đã được xóa”.

**Câu 10.** Khi nào dừng trước khi đạt mục tiêu là quyết định đúng?

*Trả lời:* Khi giả thuyết cải thiện không còn phù hợp, chi phí/rủi ro tăng vượt lợi ích, hoặc xuất hiện hồi quy cần chẩn đoán/rollback. Quyết định phải được ghi rõ cùng bằng chứng và bước tiếp theo.

## Ghi nhớ

**Dừng khi mục tiêu cải thiện đã được chứng minh** là một phần của kỹ năng tái cấu trúc có trách nhiệm. Trước khi sửa, hãy nêu vấn đề gốc, baseline, kết quả mong muốn và những hợp đồng không được phá. Trong quá trình sửa, tiến từng bước nhỏ, kiểm tra **đúng đắn và guardrail**, đồng thời đo hoặc đánh giá **lợi ích thật** ở cấp độ phù hợp. Khi mục tiêu đã đạt và không còn thay đổi mở rộng có lợi ích được chứng minh, **dừng đúng chỗ** giúp hạn chế phạm vi hồi quy, giữ PR dễ review và dành năng lực cho những vấn đề quan trọng hơn. Nếu bằng chứng chưa đủ hoặc rủi ro mới xuất hiện, hãy **đo lại, thu hẹp, xử lý hoặc quay lui** thay vì tiếp tục theo quán tính. Một refactor tốt không cần làm cho mọi dòng code trở nên “hoàn hảo”; nó cần làm hệ thống **đáng tin cậy, dễ hiểu và dễ thay đổi hơn theo mục tiêu đã được xác nhận**.
