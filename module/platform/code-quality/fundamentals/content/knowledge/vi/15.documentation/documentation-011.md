# Cập nhật tri thức cùng thay đổi mã liên quan

Trong chương **Tài liệu** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu một nguyên tắc quan trọng đối với khả năng bảo trì: **khi mã nguồn thay đổi làm một hiểu biết về hệ thống không còn đúng, tri thức liên quan cũng phải được cập nhật theo cách có thể kiểm tra và bàn giao**.

Mục tiêu của module là hiểu những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Tài liệu đúng giúp người đọc biết hệ thống đang làm gì, vì sao một quyết định được đưa ra, cách sử dụng giao diện và cách vận hành an toàn. Nhưng tài liệu lỗi thời lại có thể gây hại: lập trình viên làm theo hợp đồng cũ, nhân viên vận hành dùng hướng dẫn khôi phục không còn phù hợp, hoặc người dùng tích hợp một API dựa trên ví dụ đã sai.

> **Định nghĩa “hoàn thành thay đổi” không nên chỉ dừng ở mã biên dịch và test đỗ. Nếu thay đổi ảnh hưởng đến cách người khác hiểu, sử dụng, kiểm thử hay vận hành hệ thống, hãy cập nhật đúng nguồn tri thức liên quan và xác minh rằng thông tin mới khớp với hành vi thực tế.**

Bài này không yêu cầu viết thêm tài liệu cho mọi dòng mã. Trọng tâm là nhận diện **thông tin nào đã bị tác động**, chọn **vị trí chịu trách nhiệm** để cập nhật và biến việc đồng bộ tri thức thành một phần tự nhiên của phát triển phần mềm.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao tri thức lỗi thời là rủi ro đối với tính đúng đắn, khả năng đọc và chi phí thay đổi mã.
2. Phân biệt **mã thực thi**, **kiểm thử**, **hợp đồng API**, **hướng dẫn vận hành**, **tài liệu sử dụng** và **bản ghi quyết định thiết kế**.
3. Xác định những thay đổi nào cần cập nhật tài liệu và những thay đổi nào không làm thay đổi tri thức công khai.
4. Thực hiện quy trình cập nhật mã, test, hợp đồng và tri thức liên quan trong cùng một vòng review.
5. Dùng ví dụ Java để xác minh rằng hướng dẫn về quy tắc nghiệp vụ vẫn đúng sau khi thay đổi.
6. Hạn chế tài liệu trùng lặp và chọn nguồn sự thật (*source of truth*) phù hợp với từng loại thông tin.
7. Thiết kế tiêu chí hoàn thành, checklist và kiểm tra tự động nhằm phát hiện tài liệu lỗi thời.
8. Đánh giá các tình huống cần cập nhật tài liệu trước, cùng lúc hoặc sau khi triển khai mà không làm người dùng nhận thông tin sai thời điểm.

## 2. “Tri thức” là gì trong một dự án phần mềm?

Tri thức ở đây là thông tin cần thiết để một người **hiểu và đưa ra hành động đúng** đối với phần mềm, không chỉ là câu chữ trong một thư mục tài liệu.

Một thay đổi mã có thể ảnh hưởng đến nhiều người đọc khác nhau:

- **Người dùng API:** cần biết endpoint, tham số, lỗi, tính tương thích và cách chuyển phiên bản.
- **Người bảo trì:** cần hiểu bất biến, ranh giới trách nhiệm, quy tắc nghiệp vụ và lý do của quyết định khó.
- **Người kiểm thử:** cần biết tiêu chí chấp nhận, ví dụ đầu vào–đầu ra và trường hợp biên quan trọng.
- **Người vận hành:** cần biết cấu hình, tín hiệu cảnh báo, cách khôi phục và những thao tác không an toàn.
- **Nhóm sản phẩm hoặc hỗ trợ:** cần biết hành vi người dùng có thể quan sát và cách giải thích tình huống khác thường.

### 2.1. Những nơi tri thức thường tồn tại

| Nơi chứa thông tin | Giỏi trả lời câu hỏi nào? | Khi nào cần kiểm tra cập nhật? |
| --- | --- | --- |
| **Mã nguồn và tên có ý nghĩa** | Cơ chế đang được thực thi là gì? | Khi logic, tên, ranh giới hoặc hợp đồng trong mã đổi. |
| **Test và fixture** | Hành vi nào được kiểm tra bằng ví dụ thực thi? | Khi yêu cầu, đầu vào hợp lệ, giá trị biên hoặc kết quả mong đợi đổi. |
| **JavaDoc / hợp đồng thư viện** | Người gọi được phép làm gì; ngoại lệ và hậu điều kiện ra sao? | Khi API hoặc bảo đảm hành vi đổi. |
| **Đặc tả API, schema** | Giao tiếp giữa các thành phần có hình dạng và quy tắc gì? | Khi request/response, trạng thái lỗi, version hoặc trường dữ liệu đổi. |
| **Tài liệu sử dụng** | Người dùng phải thao tác thế nào và sẽ thấy kết quả gì? | Khi cách dùng hoặc quy tắc quan sát được đổi. |
| **Runbook / tài liệu triển khai** | Thiết lập, giám sát, xử lý sự cố và rollback ra sao? | Khi cấu hình, hạ tầng, cảnh báo, bước vận hành hoặc điểm khôi phục đổi. |
| **ADR / nhật ký quyết định** | Vì sao chọn phương án này; đã loại phương án nào? | Khi có quyết định kiến trúc mới hoặc thay thế quyết định cũ. |
| **Release notes / migration guide** | Phiên bản mới thay đổi gì, người dùng cần làm gì? | Khi phát hành có tác động tới bên sử dụng hoặc người vận hành. |

Mỗi nguồn có một nhiệm vụ. Không nên biến tất cả thành những bản sao của cùng một đoạn giải thích. Ví dụ, test có thể mô tả hành vi “đúng ngưỡng được miễn phí vận chuyển”, còn tài liệu hướng dẫn nói rõ ngưỡng được xác định dựa trên tiền hàng trước giảm giá. Hai loại bằng chứng **bổ sung** cho nhau.

### 2.2. Tri thức không chỉ nằm trong repository

Một thông tin còn có thể nằm ở trang wiki, bảng điều hành, email thông báo, dashboard hoặc câu trả lời của nhóm hỗ trợ. Nếu nhóm chỉ cập nhật Markdown trong repository nhưng trang tài liệu được công bố vẫn hiển thị hợp đồng cũ, người dùng có thể tiếp tục nhận thông tin sai.

Vì vậy, cần biết **nguồn tri thức mà người đọc thực sự sử dụng** và **quy trình xuất bản** của nguồn đó. Tài liệu đặt gần mã có thể dễ review hơn, nhưng không tự đồng nghĩa đã được phát hành đúng nơi.

## 3. Tại sao cập nhật tài liệu cùng mã lại quan trọng?

### 3.1. Tài liệu lỗi thời tạo ra một phiên bản sự thật khác

Giả sử mã đã đổi từ điều kiện miễn phí vận chuyển “từ 500.000 trở lên” sang “từ 300.000 trở lên cho khách premium”, nhưng hướng dẫn tích hợp vẫn ghi chỉ có một ngưỡng 500.000. Các nhóm có thể:

1. Dựng test theo quy tắc cũ rồi báo lỗi sai.
2. Viết logic tính phí trùng lặp ở client và cho kết quả khác server.
3. Giải thích sai cho khách hàng.
4. Sửa “lỗi” trong mã vốn đang đúng theo yêu cầu mới.

Tài liệu không còn là công cụ hỗ trợ; nó đã trở thành **nguồn tạo sai lệch**.

### 3.2. Người viết mã biết bối cảnh nhất vào lúc thay đổi

Trong lúc sửa, nhóm đang nắm rõ yêu cầu, sự khác biệt trước–sau, các phương án đã cân nhắc và trường hợp biên. Sau vài tuần, lý do của một lựa chọn có thể khó nhớ hơn.

Cập nhật tri thức trong cùng vòng thay đổi giúp giữ lại phần ngữ cảnh đang có. Việc để một nhiệm vụ “bổ sung tài liệu sau” mà không có chủ sở hữu và thời hạn dễ tạo **nợ tài liệu**: có mã mới nhưng cách hiểu cũ vẫn lưu hành.

### 3.3. Cùng thay đổi không nhất thiết cùng thời điểm công bố

Quy trình kỹ thuật và thời điểm người dùng cần thấy thông tin **không luôn trùng nhau**:

- Với thay đổi nội bộ, có thể cập nhật tài liệu và mã trong cùng pull request.
- Với API có giai đoạn chuyển tiếp, cần công bố hướng dẫn migration **trước khi** xóa hành vi cũ.
- Với tính năng chưa bật, tài liệu có thể được chuẩn bị và review trước nhưng chỉ công bố khi tính năng sẵn sàng.
- Với quy trình vận hành có bước chuyển hạ tầng, runbook cần phản ánh trạng thái thực tế của từng giai đoạn, tránh công bố quá sớm các thao tác chưa hoạt động.

Nguyên tắc là **cùng được quản lý trong một kế hoạch thay đổi có thể kiểm chứng**, không nhất thiết buộc mọi bản tài liệu được xuất bản cùng giây với bản mã.

## 4. Phân loại thay đổi để biết cần cập nhật tri thức nào

Một thay đổi nhỏ theo số dòng vẫn có thể có phạm vi thông tin rộng. Hãy đánh giá **hành vi và người sử dụng**, không chỉ kích thước diff.

| Loại thay đổi | Ví dụ | Nguồn tri thức nên kiểm tra |
| --- | --- | --- |
| **Hành vi nghiệp vụ** | Đổi ngưỡng miễn phí hoặc điều kiện được hoàn tiền. | Tiêu chí chấp nhận, test biên, tài liệu người dùng, hướng dẫn hỗ trợ. |
| **Hợp đồng API** | Đổi kiểu trường, cách phân trang, mã lỗi, tính bắt buộc của tham số. | Schema/OpenAPI, JavaDoc hoặc SDK, contract test, migration/release notes. |
| **Cấu hình** | Thêm biến môi trường hoặc đổi giá trị mặc định. | Tài liệu triển khai, mẫu cấu hình, quy trình rollback, runbook. |
| **Dữ liệu và schema** | Thêm cột bắt buộc, thay ý nghĩa trạng thái. | Migration guide, mô hình dữ liệu, quy trình khôi phục, test tích hợp. |
| **Bảo mật và quyền truy cập** | Đổi quyền cần thiết để gọi endpoint. | Hướng dẫn dùng API, chính sách quyền, test phân quyền, thông báo liên quan. |
| **Vận hành** | Đổi health check, alert, retry hoặc cơ chế sao lưu. | Runbook, dashboard, chỉ dẫn on-call, hướng dẫn triển khai. |
| **Thiết kế / ranh giới module** | Tách một chính sách ra service khác. | ADR nếu là quyết định quan trọng, sơ đồ kiến trúc, trách nhiệm sở hữu. |
| **Refactor giữ nguyên hành vi** | Đổi tên biến cục bộ, trích xuất helper private. | Kiểm tra JavaDoc, sơ đồ hoặc hướng dẫn có phụ thuộc chi tiết cũ không; có thể không cần thêm tài liệu nếu không ảnh hưởng. |
| **Sửa lỗi** | Sửa điều kiện `>` thành `>=` tại đúng ngưỡng. | Test hồi quy, tài liệu nếu trước đó mô tả sai, release notes khi tác động người dùng. |

Bảng này là **bộ gợi ý**, không phải ma trận bắt buộc cập nhật tất cả tài liệu mỗi lần. Một thay đổi chỉ tác động code nội bộ và không làm đổi bất kỳ hợp đồng nào có thể chỉ cần test và mô tả PR rõ ràng.

## 5. Nhận diện “tri thức liên quan” thay vì viết tài liệu tràn lan

Có thể bắt đầu từ một câu hỏi:

> “Nếu có người tiếp tục làm theo thông tin hiện có sau khi thay đổi được triển khai, họ có khả năng đưa ra quyết định sai không?”

Nếu có, cần tìm nguồn thông tin đó và cập nhật hoặc đánh dấu phiên bản.

### 5.1. Ba lớp thông tin cần kiểm tra

**Lớp 1 — Điều hệ thống cam kết.** Ví dụ: phương thức tính phí nhận số tiền không âm, API trả lỗi 400 khi tham số sai, tính năng có giới hạn phiên bản. Đây là hợp đồng mà người gọi dựa vào.

**Lớp 2 — Điều người bảo trì cần biết.** Ví dụ: tại sao phí vận chuyển dựa trên tổng tiền hàng **trước** giảm giá, tại sao hai thao tác phải ở cùng một transaction, hoặc tại sao có điều kiện tương thích lùi.

**Lớp 3 — Điều người vận hành phải làm.** Ví dụ: cần bật feature flag ở môi trường nào, quy trình rollback, khi nào cache được refresh và cách phát hiện cấu hình chưa áp dụng.

Khi hành vi thay đổi, không nhất thiết cả ba lớp đều đổi. Nhưng phải **có chủ đích xem xét từng lớp**, không mặc định “đã viết unit test thì đã cập nhật đủ tri thức”.

### 5.2. Tránh chép lại mọi chi tiết dễ suy ra từ mã

Comment như sau ít giá trị:

~~~java
// Increase count by one
count++;
~~~

Người đọc đã thấy thao tác tăng đếm. Nếu business invariant là “mỗi giao dịch thành công chỉ được tăng số lượt sử dụng một lần”, thông tin ấy đáng được ghi rõ ở hợp đồng hoặc test; nó **không thể suy ra chắc chắn** chỉ từ một toán tử `++`.

Tài liệu tốt ưu tiên **mục đích, bảo đảm, ngoại lệ, giả định và cách sử dụng**, thay vì thuật lại từng dòng triển khai.

## 6. Ví dụ Java: đổi quy tắc vận chuyển và cập nhật tri thức cùng lúc

Xét một cửa hàng có chức năng tính phí vận chuyển. Chính sách cũ:

> Mọi khách hàng có đơn từ 500.000 đơn vị tiền nhỏ nhất trở lên được miễn phí vận chuyển. Đơn thấp hơn chịu phí 30.000.

Chính sách mới:

> Khách **STANDARD** được miễn phí từ 500.000; khách **PREMIUM** được miễn phí từ 300.000. Ngưỡng được so với **tổng tiền hàng trước chiết khấu**. Phí cố định của đơn chưa đạt ngưỡng vẫn là 30.000.

Đây là **ví dụ giả định** để minh họa cập nhật tri thức, không phải chính sách áp dụng chung cho mọi hệ thống.

### 6.1. Phiên bản mã trước thay đổi

~~~java
final class ShippingFeeCalculatorBefore {
    static long calculate(long merchandiseSubtotalCents) {
        if (merchandiseSubtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return merchandiseSubtotalCents >= 500_000 ? 0 : 30_000;
    }
}
~~~

Tài liệu cũ có thể ghi:

~~~markdown
Phí vận chuyển:
- Tổng tiền hàng từ 500.000 trở lên: miễn phí.
- Tổng tiền hàng dưới 500.000: phí 30.000.
~~~

Đối với phiên bản cũ, mô tả này hữu ích. Nhưng sau khi chính sách có thêm khách PREMIUM, nó không còn đầy đủ.

### 6.2. Phiên bản mã sau thay đổi

Ví dụ Java 17+:

~~~java
import java.util.Objects;

enum CustomerTier {
    STANDARD,
    PREMIUM
}

record ShippingPolicy(
        long standardFreeFromCents,
        long premiumFreeFromCents,
        long flatFeeCents) {

    ShippingPolicy {
        if (standardFreeFromCents < 0
                || premiumFreeFromCents < 0
                || flatFeeCents < 0) {
            throw new IllegalArgumentException("Negative policy value");
        }
    }
}

final class ShippingFeeCalculator {
    private final ShippingPolicy policy;

    ShippingFeeCalculator(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    long calculate(long merchandiseSubtotalCents, CustomerTier tier) {
        if (merchandiseSubtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? policy.premiumFreeFromCents()
                : policy.standardFreeFromCents();

        return merchandiseSubtotalCents >= threshold
                ? 0
                : policy.flatFeeCents();
    }
}
~~~

Cách gọi với chính sách minh họa:

~~~java
var policy = new ShippingPolicy(500_000, 300_000, 30_000);
var calculator = new ShippingFeeCalculator(policy);

long standardFee =
        calculator.calculate(400_000, CustomerTier.STANDARD); // 30_000
long premiumFee =
        calculator.calculate(400_000, CustomerTier.PREMIUM);  // 0
~~~

Giờ hành vi không chỉ phụ thuộc số tiền mà còn phụ thuộc **hạng khách hàng**. Tài liệu cũ thiếu một đầu vào quyết định phí. Nếu client tiếp tục tự tính bằng một ngưỡng 500.000, nó có thể hiển thị phí không khớp backend.

### 6.3. Cập nhật tài liệu hành vi tại nguồn có thẩm quyền

Một đoạn tài liệu mới có thể được viết:

~~~markdown
## Quy tắc phí vận chuyển

Ngưỡng miễn phí được so với **tổng tiền hàng trước chiết khấu**,
tính theo đơn vị tiền nhỏ nhất của hệ thống.

| Hạng khách hàng | Miễn phí khi tổng tiền hàng |
| --- | ---: |
| STANDARD | Từ 500.000 trở lên |
| PREMIUM | Từ 300.000 trở lên |

Nếu chưa đạt ngưỡng tương ứng, phí vận chuyển là 30.000.

- Tổng tiền hàng âm: dữ liệu không hợp lệ.
- Tại **đúng ngưỡng**: miễn phí.
- Các con số được cấu hình trong ShippingPolicy; không nhân bản
  hằng số vào nhiều phần của ứng dụng.

Ví dụ: tổng tiền hàng 400.000 → STANDARD trả 30.000,
PREMIUM trả 0.
~~~

Tài liệu này nêu **ý nghĩa nghiệp vụ** mà chữ ký một hàm chưa diễn đạt hết: sử dụng tổng trước chiết khấu, ngưỡng phân theo hạng, quy tắc đúng ngưỡng và đơn vị tiền.

Nếu các giá trị thực tế được thay bằng cấu hình tại thời gian chạy, không nên chép chúng vào một trang như thể chúng không bao giờ đổi. Có thể công bố **quy tắc lấy giá trị từ chính sách được quản lý**, kèm phiên bản hoặc thời gian hiệu lực, và giữ một nguồn sự thật cho các số đang áp dụng.

### 6.4. Cập nhật test tại cùng ranh giới nghiệp vụ

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeeCalculatorTest {
    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator(
                    new ShippingPolicy(500_000, 300_000, 30_000));

    @Test
    void standardJustBelowThresholdPaysFlatFee() {
        assertEquals(30_000,
                calculator.calculate(499_999, CustomerTier.STANDARD));
    }

    @Test
    void standardAtThresholdGetsFreeShipping() {
        assertEquals(0,
                calculator.calculate(500_000, CustomerTier.STANDARD));
    }

    @Test
    void premiumJustBelowThresholdPaysFlatFee() {
        assertEquals(30_000,
                calculator.calculate(299_999, CustomerTier.PREMIUM));
    }

    @Test
    void premiumAtThresholdGetsFreeShipping() {
        assertEquals(0,
                calculator.calculate(300_000, CustomerTier.PREMIUM));
    }

    @Test
    void bothTiersUseDifferentThresholdsOnSameSubtotal() {
        assertEquals(30_000,
                calculator.calculate(400_000, CustomerTier.STANDARD));
        assertEquals(0,
                calculator.calculate(400_000, CustomerTier.PREMIUM));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.calculate(-1, CustomerTier.PREMIUM));
    }

    @Test
    void rejectsMissingTier() {
        assertThrows(NullPointerException.class,
                () -> calculator.calculate(100_000, null));
    }
}
~~~

Bộ test khẳng định các hành vi mô tả trong tài liệu. Nếu sau này ngưỡng hoặc đối tượng áp dụng đổi, nhóm cần xem xét **cả test và tài liệu**. Test không thay thế mô tả dành cho người dùng; ngược lại, tài liệu không tự thực thi để phát hiện hồi quy.

### 6.5. Bản đồ tác động của thay đổi

| Thành phần | Cần xác minh điều gì? | Hành động thường phù hợp |
| --- | --- | --- |
| Mã tính phí | Có nhận đúng hạng và tính đúng ở ngưỡng không? | Sửa logic và hợp đồng gọi. |
| Unit test | Có ca STANDARD/PREMIUM tại sát ngưỡng không? | Cập nhật bảng test. |
| API hoặc SDK nếu có tham số hạng | Bên gọi có cần truyền thêm trường; giá trị mặc định là gì? | Cập nhật schema, contract test, hướng dẫn migration. |
| Tài liệu nghiệp vụ | Ngưỡng mới và ý nghĩa “trước chiết khấu” đã rõ chưa? | Cập nhật hướng dẫn tại nguồn có thẩm quyền. |
| Cấu hình và vận hành | Ai quản lý chính sách, cách rollback khi sai? | Cập nhật hướng dẫn cấu hình/runbook nếu cần. |
| Giao diện người dùng | Giá hiển thị có dùng cùng nguồn quyết định? | Kiểm tra thông báo hoặc tài liệu cho người dùng. |
| Release notes | Thay đổi có tác động người sử dụng phiên bản mới không? | Thông báo thay đổi và thời điểm hiệu lực phù hợp. |

**Giới hạn của ví dụ:** nó chỉ trình bày một phép tính trong bộ nhớ. Chưa có API, database, cơ chế thanh toán hoặc cập nhật chính sách trong production. Những mục ở bảng là **điểm cần đánh giá**, không phải tuyên bố hệ thống minh họa đã có các thành phần ấy.

## 7. Vì sao “đã cập nhật test” chưa đủ?

Test là tài liệu **có thể thực thi** cho những hành vi cụ thể. Chúng có giá trị lớn khi giữ lại ca biên và lỗi hồi quy, nhưng có một số giới hạn:

- Người sử dụng API không nhất thiết có quyền truy cập hoặc hiểu bộ test của service.
- Test ở mức đơn vị không mô tả đầy đủ định dạng giao tiếp, quyền truy cập hoặc yêu cầu tương thích.
- Test có thể bỏ sót nguyên nhân thiết kế: “tại sao ngưỡng dựa trên tổng trước chiết khấu?”.
- Test không hướng dẫn người trực ca cách xác minh triển khai, phát hiện cấu hình sai hoặc khôi phục.
- Test cũng có thể sai oracle nếu yêu cầu chưa được xác nhận.

Ngược lại, một tài liệu dài nhưng không có test hồi quy có thể nhanh chóng lệch khỏi mã.

**Kết hợp hữu ích:** hợp đồng diễn đạt *điều phải đúng*, test cung cấp ví dụ thực thi để phát hiện sai lệch, và mô tả quyết định giải thích *vì sao lựa chọn đó tồn tại*.

### 7.1. Không biến test thành bản sao giòn của triển khai

Một test chỉ xác minh rằng `calculate` gọi private helper tên `getThreshold` sẽ dễ vỡ khi refactor, dù phí trả về không đổi. Test nên ưu tiên **hành vi quan sát được**: ở đúng ngưỡng PREMIUM có được miễn phí hay không, và đầu vào sai được xử lý như đã cam kết hay không.

Tương tự, tài liệu không nên ghi chi tiết thứ tự gọi các helper private nếu người dùng không cần dựa vào đó.

## 8. Quản lý nguồn sự thật và tránh sao chép thông tin dễ lỗi thời

Một hệ thống có thể chứa ba bản quy tắc phí vận chuyển:

1. Hằng số trong source Java.
2. Cấu hình môi trường production.
3. Bảng số trong wiki.

Nếu cả ba đều được chỉnh thủ công, sớm muộn chúng có thể khác nhau. **Cập nhật “cùng mã” không có nghĩa sao chép cùng con số vào càng nhiều nơi càng tốt.**

### 8.1. Phân biệt nguồn sự thật theo loại dữ liệu

Không có một file duy nhất là nguồn sự thật cho mọi khía cạnh:

| Thông tin | Nguồn nên có trách nhiệm chính |
| --- | --- |
| Giá trị chính sách đang hiệu lực tại môi trường | Cấu hình/chính sách được quản lý theo quy trình và phiên bản. |
| Cách tính và các bất biến của thuật toán | Mã nguồn cùng hợp đồng và test phù hợp. |
| Hình dạng API công khai | Đặc tả API/schema có quản lý phiên bản. |
| Lý do chọn một kiến trúc | ADR hoặc bản ghi quyết định được quản lý. |
| Cách triển khai và khôi phục | Runbook có chủ sở hữu vận hành. |
| Cách người dùng sử dụng tính năng | Tài liệu người dùng được công bố đúng phiên bản. |

Điều quan trọng là người đọc biết **nơi nào có thẩm quyền đối với câu hỏi họ đang hỏi**.

### 8.2. Ưu tiên tạo dẫn xuất có kiểm soát khi có thể

Nếu API schema là nguồn có thẩm quyền, tài liệu tham chiếu API có thể được **sinh từ schema** để giảm sai lệch thủ công. Nếu một bảng cấu hình cần hiển thị ra cổng quản trị, có thể lấy dữ liệu từ chính nguồn cấu hình thay vì chép bảng vào nhiều nơi.

Tuy vậy, nội dung tự động sinh không tự giải thích **ý định nghiệp vụ** hoặc **lý do của quyết định**. Tài liệu mô tả hành vi, tình huống sử dụng và cảnh báo quan trọng vẫn cần được soạn hoặc xác nhận có chủ đích.

### 8.3. Khi phải lặp lại thông tin, hãy đặt quy tắc đồng bộ

Không phải lúc nào cũng tránh được việc lặp lại: release notes có thể cần tóm tắt thay đổi đã xuất hiện trong hướng dẫn API; bài đào tạo có thể cần một ví dụ độc lập.

Khi đó, nên:

- Dẫn đến nguồn thẩm quyền nếu người đọc cần thông tin mới nhất.
- Nêu phiên bản và thời gian hiệu lực của ví dụ.
- Có người chịu trách nhiệm rà soát khi hợp đồng đổi.
- Hạn chế chép nguyên bảng cấu hình dài vào nhiều trang.
- Kiểm tra các bản sao quan trọng trong quy trình phát hành.

## 9. Cập nhật JavaDoc và comment khi hợp đồng đổi

### 9.1. JavaDoc cần nói rõ thứ người gọi dựa vào

Với một API được dùng bởi nhiều nhóm, JavaDoc có thể mô tả:

~~~java
// Ví dụ về vị trí JavaDoc trên một giao diện minh họa.
interface ShippingFeeContract {
    /**
     * Calculates the shipping fee for a merchandise subtotal and customer tier.
     *
     * <p>The free-shipping threshold is applied to the merchandise subtotal
     * before discounts. The applicable threshold is selected by customer tier.
     *
     * @param merchandiseSubtotalCents subtotal before discounts, non-negative
     * @param tier customer tier, must not be null
     * @return zero when the subtotal meets the tier threshold;
     *         otherwise the configured flat shipping fee
     * @throws IllegalArgumentException if subtotal is negative
     * @throws NullPointerException if tier is null
     */
    long calculate(long merchandiseSubtotalCents, CustomerTier tier);
}
~~~

Đây là **ví dụ trình bày JavaDoc trên một giao diện**, không phải đề xuất tạo thêm interface chỉ để viết tài liệu. Với thiết kế `ShippingFeeCalculator` ở mục 6, ta có thể đặt phần JavaDoc tương tự trực tiếp trên phương thức `calculate` thật. Mục tiêu là ghi rõ hợp đồng mà người gọi cần, không tạo bản triển khai giả hoặc thêm tầng trừu tượng không có nhu cầu.

JavaDoc có ích vì nó nằm gần giao diện mà người bảo trì sẽ đọc. Nhưng nếu một hằng số ngưỡng thay đổi qua cấu hình, nên mô tả **quy tắc áp dụng** thay vì khẳng định giá trị cứng không còn ổn định.

### 9.2. Comment “vì sao” quan trọng hơn comment “làm gì”

Ví dụ:

~~~java
// Evaluate free shipping before applying discounts because the
// checkout policy defines eligibility using merchandise subtotal.
long threshold = tier == CustomerTier.PREMIUM
        ? policy.premiumFreeFromCents()
        : policy.standardFreeFromCents();
~~~

Comment giải thích một quyết định dễ bị hiểu sai nếu người sau chỉ nhìn biểu thức. Nhưng comment cũng cần được review khi chính sách đổi. Một comment sai nằm sát mã có thể gây hại hơn không có comment.

### 9.3. Không biến comment thành kho lưu trữ lịch sử

Không nên thêm chuỗi chú thích kiểu “2023 sửa A, 2024 sửa B, 2025 sửa lại A” vào mọi phương thức. Lịch sử Git, issue hoặc ADR là nơi phù hợp hơn cho bối cảnh thay đổi lâu dài khi thông tin đó thực sự cần giữ.

Trong mã, ưu tiên **hợp đồng đang đúng tại hiện tại** và những lý do không thể tự suy ra dễ dàng.

## 10. Ghi lại quyết định thiết kế khi đánh đổi có ý nghĩa

Một số thay đổi không chỉ đổi hành vi mà còn tạo **quyết định khó đảo ngược**: dùng cache với chính sách invalidation, chuyển từ API đồng bộ sang bất đồng bộ, chọn mô hình lưu trạng thái hay ranh giới module.

Trong trường hợp đó, một *Architecture Decision Record (ADR)* ngắn có thể giúp người sau hiểu không chỉ phương án đã chọn, mà còn **những điều kiện khiến phương án ấy hợp lý**.

Ví dụ về nội dung ADR:

~~~markdown
# Quyết định: dùng chính sách vận chuyển theo hạng khách hàng

Trạng thái: Được chấp nhận cho phiên bản đang phát triển

## Bối cảnh
Ngưỡng miễn phí khác nhau giữa STANDARD và PREMIUM.
Quy tắc phải nhất quán ở mọi nơi sử dụng phí vận chuyển.

## Quyết định
Dùng ShippingPolicy để chứa các ngưỡng và phí cố định;
ShippingFeeCalculator chọn ngưỡng theo CustomerTier.

## Phương án đã cân nhắc
- Nhân bản logic ở từng client.
- Tạo một rule engine tổng quát ngay từ đầu.
- Dùng một chính sách tập trung và phép tính đơn giản.

## Lý do
Nhu cầu hiện tại có hai biến thể rõ ràng; một rule engine
tổng quát chưa có bằng chứng cần thiết.

## Hệ quả
Phải quản lý nguồn cấu hình chính sách và cập nhật test
cho từng hạng khách hàng khi chính sách đổi.
~~~

ADR không cần liệt kê mọi dòng code, không thay thế JavaDoc hay test và không nên được viết cho mỗi lần đổi tên biến. Giá trị của nó là lưu **quyết định, lựa chọn khác và hậu quả** khi các thông tin ấy có khả năng tiếp tục ảnh hưởng tới kiến trúc trong tương lai.

Nếu một quyết định cũ bị thay thế, cần ghi rõ trạng thái đã bị thay thế và dẫn tới quyết định mới, tránh xóa lịch sử khiến người sau không hiểu vì sao hệ thống từng có cấu trúc hiện tại.

## 11. API và tương thích: tri thức phải đến được bên sử dụng

Một thay đổi có thể rất nhỏ trong service nhưng là thay đổi lớn với client.

Giả sử API hiện nhận:

~~~json
{
  "merchandiseSubtotalCents": 400000
}
~~~

Và tính phí theo hạng khách hàng mới. Nếu phiên bản API mới yêu cầu trường `customerTier`, cần làm rõ:

- Trường mới có **bắt buộc** không?
- Client cũ không gửi trường sẽ được xử lý ra sao?
- Backend có thể xác định hạng khách hàng từ danh tính đã xác thực thay vì tin vào trường do client gửi không?
- Mã lỗi nào được trả nếu giá trị không hợp lệ?
- Có giai đoạn chuyển tiếp hoặc phiên bản API mới không?
- Những client nào cần thay đổi trước khi triển khai?

Ví dụ hình dạng request mới, **chỉ để minh họa đặc tả**:

~~~json
{
  "merchandiseSubtotalCents": 400000,
  "customerTier": "PREMIUM"
}
~~~

**Lưu ý về bảo mật:** nếu quyền lợi premium được xác định từ hồ sơ phía server, API không nên tin ngay giá trị `customerTier` do client tự khai. Quy tắc xác minh danh tính và dữ liệu là một phần của hợp đồng, cần được giải thích và kiểm thử.

### 11.1. Khi có thay đổi phá tương thích

Một kế hoạch phù hợp có thể gồm:

1. Xác định các client hoặc service chịu ảnh hưởng.
2. Công bố hướng dẫn migration và thời hạn hỗ trợ trước khi ngắt hành vi cũ nếu có thể.
3. Cập nhật schema, ví dụ request/response và test hợp đồng.
4. Tạo cơ chế tương thích lùi hoặc versioning khi cần.
5. Triển khai theo thứ tự đã định và quan sát mức sử dụng phiên bản cũ.
6. Đánh dấu tài liệu cũ là dành cho phiên bản cũ; tránh để nó trông như hướng dẫn hiện hành.

Đừng sửa tài liệu thành API mới rồi công bố như thể nó đã hoạt động trong khi production vẫn chạy API cũ. Ngược lại, không được triển khai hợp đồng mới mà bỏ mặc client dựa trên tài liệu cũ.

## 12. Runbook, cấu hình và tri thức vận hành

Một thay đổi mã có thể không thấy ở giao diện người dùng nhưng vẫn tác động trực tiếp đến on-call.

Ví dụ: service bổ sung một cache chính sách có thể cần cập nhật:

- Cấu hình TTL, kích thước tối đa, nguồn refresh.
- Metric/cảnh báo cho cache miss hoặc lỗi refresh.
- Cách xác định một node đang dùng phiên bản chính sách nào.
- Quy trình tắt cache an toàn nếu nghi dữ liệu lỗi thời.
- Cách khôi phục sau khi thay đổi cấu hình sai.

Một runbook hữu ích thường trả lời:

| Câu hỏi vận hành | Ví dụ thông tin cần có |
| --- | --- |
| Làm sao biết hệ thống bị ảnh hưởng? | Tên metric, dấu hiệu cảnh báo, tác động tới người dùng. |
| Cách xác minh nguyên nhân? | Bước kiểm tra phiên bản/chính sách mà không cần truy cập bí mật. |
| Bước xử lý an toàn? | Cách rollback cấu hình, cách tạm dừng tính năng và điều kiện cần xem lại. |
| Điều gì **không nên** làm? | Không xóa dữ liệu đang được dùng; không tự chỉnh quota thủ công. |
| Khi nào cần chuyển cấp? | Dấu hiệu vượt khả năng xử lý và người/nhóm chịu trách nhiệm. |
| Làm sao biết đã khôi phục? | Bằng chứng hành vi, metric và test xác nhận. |

**Đừng ghi credential hoặc token thật vào runbook** chỉ để giúp người mới thao tác nhanh. Tài liệu nên chỉ dẫn tới cơ chế cấp quyền và quản lý bí mật thích hợp.

### 12.1. Một thay đổi vận hành có thể cần tài liệu trước khi mã chạy

Nếu rollout yêu cầu người vận hành tạo một cấu hình hoặc thực hiện migration trước, hướng dẫn nên được review và sẵn sàng trước bước triển khai có phụ thuộc. Điều quan trọng là ghi rõ **thứ tự, điều kiện an toàn và phương án khôi phục**.

## 13. Quy trình đồng bộ tri thức theo vòng đời của một thay đổi

### 13.1. Trước khi viết mã: xác định hợp đồng và nơi sẽ đổi

Khi nhận yêu cầu, có thể ghi một bảng tác động ngắn:

~~~text
Yêu cầu mới
    |
    +-- Hành vi nào thay đổi?
    +-- Ai dùng/kiểm thử/vận hành hành vi đó?
    +-- Nguồn tri thức hiện tại ở đâu?
    +-- Có thay đổi tương thích, cấu hình hoặc dữ liệu không?
    +-- Bằng chứng nào xác nhận hành vi mới?
~~~

Mục tiêu không phải mở một đợt viết tài liệu lớn. Chỉ cần xác định **đầu ra tri thức nào bị ảnh hưởng** và ai chịu trách nhiệm cập nhật.

### 13.2. Trong lúc triển khai: cập nhật mã và nguồn tri thức cùng một vòng review

Một quy trình dễ áp dụng:

1. Chuyển yêu cầu thành tiêu chí chấp nhận, gồm những trường hợp biên.
2. Sửa mã và thêm/chỉnh test cho hành vi được cam kết.
3. Cập nhật JavaDoc, schema, hướng dẫn hoặc runbook đã bị ảnh hưởng.
4. Liên kết các thay đổi trong PR để reviewer thấy được **mã–test–tài liệu** cùng mô tả một quy tắc.
5. Chỉ rõ tài liệu nào chưa thể công bố cho tới khi tính năng được bật hoặc phiên bản được phát hành.
6. Nếu có giai đoạn migration, ghi thời điểm và chủ sở hữu của từng bước.

Trường hợp tài liệu ở ngoài repository có quy trình riêng, PR có thể kèm một liên kết đến bản thảo hoặc nhiệm vụ xuất bản được theo dõi. Đừng đánh dấu hoàn tất nếu người dùng vẫn chỉ thấy hướng dẫn cũ mà không có kế hoạch cập nhật rõ.

### 13.3. Trong review: kiểm tra tính nhất quán, không chỉ lỗi chính tả

Reviewer có thể đối chiếu:

- Những con số và điều kiện biên có khớp giữa test, mã và tài liệu không?
- Input/output mới có được giải thích bằng cùng tên và đơn vị không?
- Ví dụ tài liệu có thực sự hoạt động với phiên bản đang đề cập không?
- Hợp đồng lỗi, quyền truy cập và thời gian hiệu lực có được nêu không?
- Lý do cho một quyết định bất thường đã được ghi ở nơi thích hợp chưa?
- Người vận hành có thể làm đúng theo runbook sau rollout không?
- Có tài liệu cũ nào cần cập nhật, ghi version hoặc đánh dấu không còn hiện hành không?

Review kiểu này biến tài liệu thành **một thành phần có thể kiểm chứng của thay đổi**, thay vì phụ lục chỉ được kiểm tra sau cùng.

### 13.4. Sau triển khai: xác nhận thông tin thực sự đã đến người đọc

Nếu tài liệu được xuất bản ở cổng web hoặc portal, cần xác nhận phiên bản hiển thị là phiên bản đúng. Với những thay đổi có migration, theo dõi việc client hoặc nhóm vận hành đã chuyển đổi hay chưa.

Nếu có sai lệch giữa hướng dẫn và thực tế phát hành, cần sửa cả hai mặt: **nguồn nội dung** và **kênh công bố**. Một bản Markdown đúng trong Git không giúp người đọc nếu họ đang được dẫn tới trang cũ.

## 14. Tự động hóa để giảm tài liệu lỗi thời

Không phải mọi loại tri thức đều kiểm tra tự động được, nhưng có thể kiểm soát một số sai lệch phổ biến.

| Kiểm tra | Mục đích | Giới hạn |
| --- | --- | --- |
| Build ví dụ Java trong tài liệu | Phát hiện cú pháp/API đã thay đổi. | Biên dịch được chưa chứng minh ví dụ đúng với nghiệp vụ. |
| Chạy doctest hoặc executable snippets | So sánh đầu ra và xử lý các ví dụ có thể chạy. | Chỉ với những ví dụ được đưa vào bộ chạy. |
| Sinh tài liệu tham chiếu từ schema | Giảm khác biệt giữa hợp đồng kỹ thuật và trang tham chiếu. | Không thay phần giải thích mục đích và đánh đổi. |
| Contract test giữa producer/consumer | Phát hiện khác biệt hình dạng hoặc bảo đảm API. | Không thay thế mọi luồng người dùng. |
| Link checker | Tìm liên kết hỏng và mục đích tham chiếu không còn tồn tại. | Link còn hoạt động chưa chứng minh nội dung đúng. |
| Kiểm tra mẫu cấu hình | Phát hiện khóa cấu hình thiếu hoặc không còn được hỗ trợ. | Giá trị mẫu đúng cú pháp chưa chắc an toàn cho production. |
| Lint tài liệu / kiểm tra heading | Giữ cấu trúc dễ đọc và hỗ trợ xuất bản. | Không xác minh ý nghĩa nghiệp vụ. |
| Checklist PR / CODEOWNERS | Nhắc người có trách nhiệm xem tác động tri thức. | Có thể thành hình thức nếu không đọc nội dung. |

### 14.1. Chọn kiểm tra có tỷ lệ giá trị/chi phí hợp lý

Một dự án nhỏ không nhất thiết cần hệ thống xuất bản phức tạp. Bắt đầu bằng **tài liệu ở gần nơi thay đổi, checklist ngắn và reviewer hiểu hợp đồng**. Khi số lượng client, phiên bản và tài liệu tăng, tự động hóa build ví dụ, contract test hoặc xuất bản từ schema có thể đáng đầu tư hơn.

### 14.2. Không dùng công cụ để thay thế người hiểu nghiệp vụ

Một ví dụ `shippingFee(500_000)` có thể biên dịch và chạy mà vẫn đưa ra phí sai nếu kỳ vọng bị viết nhầm. Công cụ kiểm tra sự nhất quán kỹ thuật; **người chịu trách nhiệm nghiệp vụ** cần xác nhận ý nghĩa của yêu cầu khi có thay đổi thực tế.

## 15. Các lỗi thường gặp khi quản lý tri thức

### 15.1. Chỉ cập nhật code vì “test đã xanh”

Test không giúp người dùng API hiểu tham số mới, không hướng dẫn triển khai và không giải thích lý do phải xử lý một nhánh đặc biệt.

**Cải thiện:** xác định những người đọc chịu tác động rồi cập nhật nguồn thông tin mà họ sử dụng.

### 15.2. Viết tài liệu sau nhiều tuần mà không có kế hoạch

Thông tin quan trọng từ lúc làm thay đổi có thể bị quên; nhóm khác đã kịp dùng hướng dẫn cũ.

**Cải thiện:** đưa cập nhật tri thức vào định nghĩa hoàn thành, hoặc có nhiệm vụ xuất bản được gắn trách nhiệm và điều kiện thời gian cụ thể khi việc xuất bản cần tách khỏi deploy.

### 15.3. Chép cùng con số vào nhiều nơi

Mỗi bản sao là một nơi có thể lỗi thời. Một thay đổi cấu hình nhỏ trở thành cuộc tìm kiếm tất cả wiki và comment.

**Cải thiện:** định nghĩa nguồn sự thật theo loại thông tin; khi có bản sao bắt buộc, gắn version hoặc dẫn nguồn và kiểm tra đồng bộ.

### 15.4. Ghi lại cách làm, không ghi lý do

Một sơ đồ cho thấy hai service giao tiếp nhưng không giải thích tại sao dùng hàng đợi thay vì lời gọi trực tiếp. Người bảo trì sau có thể “đơn giản hóa” mà vô tình phá yêu cầu chịu lỗi.

**Cải thiện:** ghi ràng buộc và đánh đổi trong ADR hoặc mô tả thiết kế khi có giá trị lâu dài.

### 15.5. Tài liệu quá chi tiết về triển khai private

Thay đổi helper private làm hàng chục trang tài liệu bị “sai” dù hành vi công khai không đổi.

**Cải thiện:** mô tả hợp đồng và khái niệm ổn định; chỉ tài liệu hóa chi tiết nội bộ khi người bảo trì thật sự cần để sửa an toàn.

### 15.6. Không phân biệt phiên bản hiệu lực

Tài liệu mới xuất hiện trước khi feature flag bật, hoặc tài liệu cũ không được đánh dấu khiến client dùng nhầm.

**Cải thiện:** ghi version, giai đoạn rollout và trạng thái hỗ trợ ở nơi người đọc có thể thấy.

### 15.7. Để tài liệu chứa thông tin nhạy cảm

Tài liệu hướng dẫn triển khai có thể vô tình chứa token, thông tin khách hàng, chuỗi kết nối thật hoặc dữ liệu production sao chép.

**Cải thiện:** dùng ví dụ giả, cơ chế quản lý bí mật và quyền truy cập phù hợp; kiểm tra nội dung trước khi công bố.

## 16. Bài tập tình huống: đổi API tạo đơn hàng

Một hệ thống trước đây cho phép client gửi request tạo đơn hàng rồi nhận kết quả ngay. Nhóm phát triển chuyển sang xử lý bất đồng bộ vì xác nhận tồn kho mất nhiều thời gian. API mới trả một mã công việc; client phải truy vấn trạng thái để biết đơn đã tạo thành công hay thất bại.

Code backend và unit test đã được sửa; dashboard tải có cải thiện. Tuy nhiên, hướng dẫn API vẫn có ví dụ response chứa `orderId` ngay lập tức, còn runbook vẫn nói “nếu request trả thành công thì đơn đã được lưu”.

**Câu hỏi:**

1. Những phát biểu nào trong tài liệu hiện đã sai?
2. Những nhóm người dùng nào chịu ảnh hưởng?
3. Cần cập nhật tối thiểu những nguồn tri thức nào?
4. Có thể coi thay đổi đã hoàn thành khi backend hoạt động tốt nhưng client chưa biết cách truy vấn công việc không?
5. Bằng chứng nào giúp kiểm tra tài liệu mới phù hợp hành vi thực tế?

**Gợi ý phân tích:**

- **Hợp đồng phản hồi đổi:** nhận mã công việc khác với nhận đơn đã hoàn tất. “Accepted” không được đồng nhất với “Completed” nếu nghiệp vụ không bảo đảm điều ấy.
- **Client và vận hành đều bị ảnh hưởng:** client phải xử lý trạng thái đang chờ, timeout, thất bại và retry; on-call phải biết cách phân biệt queue backlog với lỗi tạo đơn.
- **Tài liệu liên quan:** đặc tả API, ví dụ request/response, migration guide, trạng thái lỗi, contract test, runbook và release notes.
- **Thời điểm thông báo quan trọng:** nếu thay đổi phá tương thích, cần chiến lược phiên bản hoặc giai đoạn chuyển tiếp, không nên để client cũ tự suy đoán.
- **Bằng chứng:** test tích hợp luồng tạo đơn và truy vấn trạng thái, đối chiếu ví dụ tài liệu với môi trường thử, kiểm tra retry/idempotency và các điểm giám sát phù hợp.

Bài tập này minh họa rằng **sửa đúng thuật toán là chưa đủ** khi cách người khác sử dụng phần mềm cũng thay đổi.

## 17. Một checklist có thể dùng trong pull request

- [ ] Tôi đã xác định rõ hành vi, hợp đồng hoặc cách vận hành nào đổi.
- [ ] Những nhóm người đọc chịu ảnh hưởng đã được nhận diện.
- [ ] Test và tiêu chí chấp nhận phản ánh quy tắc mới, kể cả giá trị biên.
- [ ] JavaDoc/comment ở ranh giới liên quan còn mô tả đúng hành vi.
- [ ] API schema, ví dụ, SDK và contract test được cập nhật khi giao diện đổi.
- [ ] Hướng dẫn người dùng và nhóm hỗ trợ phản ánh đúng quy tắc có thể quan sát.
- [ ] Cấu hình, migration và runbook được cập nhật nếu có thay đổi vận hành.
- [ ] Quyết định kiến trúc quan trọng có ghi bối cảnh, lựa chọn và hệ quả khi cần.
- [ ] Không sao chép cùng một giá trị động vào nhiều nguồn khó đồng bộ.
- [ ] Tài liệu và mã dùng cùng thuật ngữ, đơn vị, trạng thái và phạm vi phiên bản.
- [ ] Các đoạn ví dụ quan trọng đã được kiểm tra theo cách phù hợp.
- [ ] Tài liệu không chứa mật khẩu, token hoặc dữ liệu khách hàng thật.
- [ ] Nếu tài liệu xuất bản sau deploy, có chủ sở hữu, thời điểm và điều kiện rõ.
- [ ] Tài liệu cũ đã được cập nhật, gắn version hoặc đánh dấu không còn hiện hành khi cần.
- [ ] Reviewer có thể đối chiếu mã–test–tài liệu và giải thích nhất quán hành vi mới.
- [ ] Nếu không cập nhật tài liệu, có lý do rõ rằng thay đổi không ảnh hưởng tri thức mà người khác cần dựa vào.

## 18. Quy tắc thực hành: thay đổi nhỏ thì cập nhật đúng mức

Không phải mọi diff đều cần một tài liệu mới. Khi đổi tên biến, format hoặc tối ưu nội bộ **không đổi hành vi và không đổi ranh giới**, việc xác minh tài liệu hiện tại vẫn đúng có thể là đủ.

Ngược lại, một thay đổi chỉ một ký tự từ `>=` sang `>` có thể thay hợp đồng về ngưỡng, làm sai hướng dẫn nghiệp vụ. **Tác động tới tri thức không tỷ lệ trực tiếp với số dòng sửa.**

Có thể dùng nguyên tắc ba mức:

| Mức tác động | Cách xử lý phù hợp |
| --- | --- |
| **Không đổi tri thức người khác dựa vào** | Xác nhận tài liệu hiện tại vẫn đúng; không thêm tài liệu vô ích. |
| **Đổi hành vi hoặc hợp đồng cục bộ** | Cập nhật test, JavaDoc hoặc tài liệu liên quan tại nguồn có trách nhiệm. |
| **Đổi cách tích hợp, triển khai hoặc vận hành** | Lập kế hoạch tài liệu, migration, thông báo và thời điểm phát hành tương ứng. |

Mục tiêu là **tài liệu đủ đúng và dễ duy trì**, không phải tối đa hóa số trang.

## 19. Tổng kết

**Cập nhật tri thức cùng thay đổi mã liên quan** là một thực hành bảo vệ tính đúng đắn và khả năng bảo trì. Mã mới mà hướng dẫn, test, hợp đồng hoặc runbook vẫn mô tả cách cũ sẽ tạo ra các phiên bản sự thật mâu thuẫn, khiến người khác sửa sai chỗ hoặc vận hành sai cách.

Trong **CODE_QUALITY_FUNDAMENTALS**, hãy bắt đầu từ tác động thật của thay đổi: **ai cần biết điều gì để sử dụng, kiểm thử, sửa và vận hành hệ thống an toàn?** Sau đó cập nhật đúng nguồn tri thức, kiểm tra tính nhất quán với hành vi thực thi và đưa việc review/phát hành tài liệu vào vòng đời thay đổi.

Một dự án đáng tin cậy không chỉ có mã chạy đúng hôm nay, mà còn có **tri thức đủ chính xác để người tiếp theo hiểu vì sao mã đúng, nhận ra khi nào nó đổi và tiếp tục thay đổi một cách an toàn**.

