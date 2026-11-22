# Tài liệu gần mã nhưng vẫn cần người chịu trách nhiệm

Một nhóm phát triển đặt README, hướng dẫn cấu hình, đặc tả API và ví dụ sử dụng ngay trong repository. Mỗi pull request đều chạy kiểm tra Markdown và liên kết. Dù vậy, tài liệu vẫn có thể sai: mã đã đổi cách tính phí, README vẫn mô tả chính sách cũ, còn người trực hệ thống chỉ biết điều đó sau khi có khách hàng phản hồi.

**Đặt tài liệu gần mã giúp người sửa dễ nhìn thấy và cập nhật, nhưng không tự bảo đảm tài liệu đúng, đủ và có người duy trì.**

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không. Ở chương **Tài liệu**, chất lượng không chỉ là có bao nhiêu trang hướng dẫn. Tài liệu tốt phải giúp người khác **sử dụng đúng hợp đồng, hiểu lý do thiết kế, thay đổi an toàn và xử lý sự cố**. Để đạt điều đó cần kết hợp **vị trí tài liệu hợp lý, vòng đời cập nhật và trách nhiệm sở hữu rõ ràng**.

Bài học tập trung vào cách vận hành tài liệu gần mã (**docs-as-code**) mà không nhầm sự thuận tiện của công cụ với trách nhiệm của con người.

## 1. “Tài liệu gần mã” nghĩa là gì?

**Tài liệu gần mã (documentation close to code)** nghĩa là thông tin cần thiết để hiểu và sử dụng một thành phần nằm ở vị trí người sửa thành phần đó dễ khám phá, thường ngay trong repository hoặc công cụ quản lý thay đổi gắn với mã.

Ví dụ:

- **Javadoc** cạnh API Java công khai, mô tả đầu vào, đầu ra, ngoại lệ và các điều kiện quan trọng.
- **README của module** mô tả mục đích, cách chạy thử, cấu hình tối thiểu và điểm tích hợp.
- **Ví dụ sử dụng** hoặc sample request nằm gần định nghĩa hợp đồng API.
- **ADR (Architecture Decision Record)** ghi lại quyết định kiến trúc và đánh đổi có ảnh hưởng tới module.
- **Tài liệu schema/migration** đi kèm các thay đổi dữ liệu liên quan.
- **Runbook vận hành** được liên kết từ component hoặc service tương ứng, dù bản chính được giữ trong hệ thống tài liệu vận hành.

“Gần” không bắt buộc có nghĩa là cùng một thư mục. Quan trọng hơn là **dễ tìm thấy từ nơi làm việc**, có đường dẫn đến nguồn đáng tin cậy và có thể cập nhật cùng thay đổi.

### Ví dụ bố trí trong một repository

~~~text
checkout/
  README.md                      # Cách dùng và vận hành module
  docs/
    decisions/
      0003-shipping-policy.md     # Lý do chọn cấu trúc chính sách
    api-contract.md               # Hợp đồng giao tiếp của module
  src/
    main/java/
      com/example/checkout/
        ShippingFeePolicy.java    # Mã và Javadoc của API
    test/java/
      com/example/checkout/
        ShippingFeePolicyTest.java
~~~

Sơ đồ này minh họa **cách tổ chức có thể dùng**, không phải một cấu trúc bắt buộc. Một dự án nhỏ có thể chỉ cần README và Javadoc. Một nền tảng nhiều dịch vụ có thể dùng trang tài liệu trung tâm nhưng vẫn đặt **liên kết chuẩn** cạnh mã.

## 2. Vì sao tài liệu gần mã có ích?

Khi tài liệu và mã xuất hiện trong cùng luồng review, nhóm có thêm cơ hội nhận ra chúng đang không nhất quán.

| Lợi ích | Cơ chế tạo ra lợi ích | Giới hạn |
| --- | --- | --- |
| **Dễ khám phá** | Người đọc lớp Java thấy Javadoc, README hoặc đường dẫn thiết kế liên quan. | Vị trí gần không bảo đảm nội dung dễ hiểu. |
| **Dễ sửa cùng lúc** | Một pull request có thể sửa cả mã, test, ví dụ và tài liệu. | Người viết mã vẫn có thể bỏ qua tài liệu. |
| **Theo dõi lịch sử** | Git cho biết tài liệu được sửa trong thay đổi nào. | Lịch sử chỉ cho biết ai sửa, không chứng minh quyết định được phê duyệt đúng. |
| **Review trong ngữ cảnh** | Reviewer thấy sự khác nhau giữa hợp đồng cũ và mới ngay trong diff. | Nếu không có reviewer đủ hiểu nghiệp vụ, nội dung vẫn có thể sai. |
| **Tự động hóa một phần** | CI có thể kiểm tra liên kết, ví dụ chạy được, cấu trúc và định dạng. | Máy không tự biết câu giải thích có còn phản ánh chính sách thực tế không. |
| **Hỗ trợ người mới** | README và ví dụ giúp hiểu cách chạy và mục đích module. | Dữ liệu hoặc môi trường thay đổi có thể làm hướng dẫn lỗi thời. |

**Lợi ích chính là giảm ma sát giữa hành động sửa mã và hành động cập nhật tài liệu**, chứ không phải loại bỏ nhu cầu có người chịu trách nhiệm.

## 3. Vì sao gần mã vẫn có thể sai?

Xét chuỗi sự kiện:

1. Hợp đồng ban đầu quy định đơn từ **500.000 VND** được miễn phí giao hàng tiêu chuẩn.
2. Nhóm sản phẩm yêu cầu bổ sung **phụ phí giao nhanh 20.000 VND**, kể cả khi đơn được miễn phí giao tiêu chuẩn.
3. Developer sửa hàm Java và thêm test cho giao nhanh.
4. Pull request chỉ chứa mã và test, trong khi README vẫn ghi “đơn từ 500.000 VND được miễn mọi phí giao hàng”.
5. CI kiểm tra định dạng Markdown và link đều xanh.

Không có bước nào ở trên đảm bảo nội dung README đã được rà lại. Đường dẫn hợp lệ không có nghĩa thông tin được liên kết là đúng. File nằm cùng repository không có nghĩa người sửa hiểu **tác động đến người dùng, API và vận hành**.

Vấn đề chính là **documentation drift (tài liệu lệch so với hệ thống thực tế)**. Nó có thể bắt nguồn từ:

- Quy tắc nghiệp vụ đổi nhưng Javadoc và README không đổi.
- Một giá trị cấu hình hoặc default đổi nhưng hướng dẫn triển khai vẫn dùng giá trị cũ.
- API đổi mã lỗi nhưng ví dụ HTTP vẫn ghi mã cũ.
- Thao tác khôi phục thay đổi nhưng runbook không cập nhật.
- Tên hoặc phạm vi trách nhiệm module đổi, trong khi sơ đồ kiến trúc vẫn mô tả cách cũ.
- Chủ sở hữu nghỉ hoặc chuyển nhóm, khiến không ai biết phải review nội dung nào.
- Người viết chỉ kiểm tra “có trang tài liệu” mà không kiểm tra “trang này có trả lời đúng câu hỏi quan trọng không”.

**Tài liệu có thể sai mà không chứa lỗi cú pháp nào.** Đây là lý do cần người sở hữu, tiêu chí review và bằng chứng xác minh.

## 4. Ai chịu trách nhiệm cho tài liệu?

Tài liệu không nên là việc “để khi nào rảnh thì bổ sung”. Mỗi loại tài liệu cần có **chủ thể chịu trách nhiệm về tính đúng và độ mới**, dù việc viết có thể được chia sẻ.

Một mô hình vai trò thực dụng:

| Vai trò | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **Chủ sở hữu nội dung (owner)** | Bảo đảm thông tin có người theo dõi, được cập nhật khi hợp đồng hoặc quy trình thay đổi. | Nhóm Checkout sở hữu chính sách giao hàng và README của module. |
| **Người tạo thay đổi (author)** | Xác định tác động đến tài liệu, cập nhật nội dung liên quan trong pull request. | Developer sửa công thức và ví dụ sử dụng. |
| **Reviewer kỹ thuật** | Kiểm tra tài liệu khớp mã, hợp đồng và các trường hợp thất bại. | Reviewer so sánh Javadoc với code và test. |
| **Reviewer nghiệp vụ hoặc vận hành** | Xác nhận diễn giải chính sách hoặc runbook đúng nhu cầu thực tế. | Product owner xác nhận phụ phí; SRE xác nhận quy trình khôi phục. |
| **Người sử dụng tài liệu (consumer)** | Phản hồi điểm khó hiểu, lỗi thời hoặc thiếu thông tin, nhưng không mặc nhiên phải tự sửa mọi tài liệu. | Nhóm tích hợp phát hiện ví dụ API không dùng được. |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ. **Điều cần tránh là trách nhiệm tập thể không có người quyết định**: ai cũng “có thể cập nhật”, nhưng không ai phải xác nhận lần cuối.

### Trách nhiệm gắn với thành phần, không chỉ gắn với cá nhân

Nếu chỉ ghi “tài liệu do bạn A phụ trách” mà không có cơ chế chuyển giao, tài liệu sẽ dễ bị bỏ quên khi A nghỉ phép hoặc chuyển dự án. Có thể gắn trách nhiệm với **nhóm sở hữu service/module**, kèm người trực hoặc cơ chế thay thế khi cần.

Ví dụ một bảng quản trị đơn giản:

| Tài liệu | Nhóm chịu trách nhiệm | Khi nào bắt buộc rà lại? |
| --- | --- | --- |
| ShippingFeePolicy Javadoc | Checkout Engineering | Khi đổi tham số, công thức, ngoại lệ hoặc ý nghĩa giá trị trả về. |
| Checkout README | Checkout Engineering | Khi đổi cách chạy, cấu hình hoặc ca sử dụng chính. |
| Đặc tả phí giao hàng | Product + Checkout | Khi đổi ngưỡng, phụ phí hoặc chính sách áp dụng. |
| Runbook xử lý lỗi gửi thông báo | Nhóm vận hành service | Khi đổi cảnh báo, thành phần phụ thuộc hoặc cách khôi phục. |
| ADR về chiến lược tính phí | Người giữ quyết định kiến trúc của nhóm | Khi quyết định được thay thế hoặc bối cảnh đổi đáng kể. |

Đây là cách phân công minh họa; mỗi tổ chức cần xác định rõ vai trò phê duyệt theo quy trình hiện có.

## 5. Ví dụ Java: hợp đồng của hàm tính phí giao hàng

Giả sử chính sách đã xác nhận gồm:

- Tổng tiền hàng **subtotalVnd** phải không âm.
- Nếu tổng tiền **nhỏ hơn 500.000 VND**, phí tiêu chuẩn là **30.000 VND**.
- Từ **500.000 VND** trở lên, phí tiêu chuẩn là **0 VND**.
- Nếu chọn giao nhanh, cộng thêm **20.000 VND**, kể cả khi phí tiêu chuẩn bằng 0.
- Hàm không có tác dụng phụ, trả tổng phí bằng VND nguyên.

Đây là ví dụ Java 17 với **Javadoc mô tả đúng các trường hợp quyết định**:

~~~java
public final class ShippingFeePolicy {
    private static final long FREE_STANDARD_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;

    private ShippingFeePolicy() {
    }

    /**
     * Tính phí giao hàng theo đơn vị VND nguyên.
     *
     * <p>Đơn có tổng tiền từ 500.000 VND được miễn phí
     * giao hàng tiêu chuẩn. Giao nhanh luôn cộng thêm
     * 20.000 VND, kể cả với đơn được miễn phí tiêu chuẩn.</p>
     *
     * @param subtotalVnd tổng giá trị hàng, không được âm
     * @param express true nếu yêu cầu giao nhanh
     * @return tổng phí giao hàng, tính theo VND
     * @throws IllegalArgumentException nếu subtotalVnd âm
     */
    public static long calculate(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException(
                    "Subtotal must not be negative");
        }

        long standardFee =
                subtotalVnd >= FREE_STANDARD_THRESHOLD
                        ? 0L : STANDARD_FEE;

        return standardFee + (express ? EXPRESS_SURCHARGE : 0L);
    }
}
~~~

Với chính sách này, bảng ví dụ có thể đưa vào README hoặc đặc tả:

| subtotalVnd | express | Phí tiêu chuẩn | Phụ phí giao nhanh | Tổng phí |
| ---: | :---: | ---: | ---: | ---: |
| 499.999 | false | 30.000 | 0 | **30.000** |
| 499.999 | true | 30.000 | 20.000 | **50.000** |
| 500.000 | false | 0 | 0 | **0** |
| 500.000 | true | 0 | 20.000 | **20.000** |
| 700.000 | true | 0 | 20.000 | **20.000** |

Hàm minh họa được đơn giản hóa: chưa xét vùng xa, mã ưu đãi, thuế, loại dịch vụ khác hoặc tính hợp lệ của số tiền từ hệ thống thanh toán. **Không tự suy diễn** những trường hợp chưa có trong đặc tả.

### Ví dụ tài liệu lỗi thời

Sau khi mã đã thêm phụ phí giao nhanh, đoạn hướng dẫn sau trở nên sai:

~~~markdown
Đơn hàng từ 500.000 VND được miễn toàn bộ phí giao hàng,
bất kể phương thức giao.
~~~

Bản diễn đạt phù hợp hơn:

~~~markdown
Đơn hàng từ 500.000 VND được miễn phí giao hàng tiêu chuẩn.
Nếu chọn giao nhanh, hệ thống cộng phụ phí 20.000 VND.
~~~

Thay đổi chỉ một từ hoặc một dòng có thể sửa hiểu nhầm lớn đối với khách hàng và đội hỗ trợ. Điều kiện để phát hiện không nằm ở Markdown linter, mà ở **người đối chiếu tài liệu với quy tắc đã được phê duyệt**.

## 6. Kiểm thử có thể làm một phần tài liệu trở nên thực thi được

Các ví dụ minh họa hợp đồng có thể được xác minh bằng test. Với chính sách ở phần 5, các ca JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    @Test
    void belowThresholdPaysStandardFee() {
        assertEquals(30_000L,
                ShippingFeePolicy.calculate(499_999L, false));
    }

    @Test
    void atThresholdStandardShippingIsFree() {
        assertEquals(0L,
                ShippingFeePolicy.calculate(500_000L, false));
    }

    @Test
    void expressSurchargeStillAppliesAtThreshold() {
        assertEquals(20_000L,
                ShippingFeePolicy.calculate(500_000L, true));
    }

    @Test
    void expressBelowThresholdPaysBothParts() {
        assertEquals(50_000L,
                ShippingFeePolicy.calculate(499_999L, true));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.calculate(-1L, false));
    }
}
~~~

Các test này hỗ trợ xác minh **bảng giá trị và hợp đồng của hàm**, nhưng không tự đồng bộ Javadoc hoặc README. Một test có thể xanh trong khi câu “miễn toàn bộ phí” vẫn nằm nguyên trong tài liệu.

Một số phần tài liệu dễ kiểm tra tự động hơn:

- Ví dụ Java được biên dịch hoặc chạy như một phần test.
- Mẫu JSON được kiểm tra cú pháp và schema.
- Tên tham số, endpoint hoặc mã lỗi được trích xuất từ một hợp đồng có nguồn chuẩn.
- Lệnh CLI trong hướng dẫn được kiểm tra ở môi trường thử nghiệm.
- Link, tiêu đề, file tham chiếu và sơ đồ được xác minh có tồn tại hoặc render được.

Nhưng các ý như **“người dùng nên làm gì khi lỗi xảy ra”**, **“vì sao chọn thiết kế này”** hoặc **“rủi ro nào cần ưu tiên”** thường vẫn cần người hiểu bối cảnh kiểm tra.

## 7. Tự động hóa được gì và không được gì?

| Việc kiểm tra | Có thể tự động hóa? | Điều vẫn cần người chịu trách nhiệm |
| --- | --- | --- |
| Định dạng Markdown, heading, link nội bộ | Thường có | Cấu trúc dễ đọc và ý nghĩa nội dung. |
| Biên dịch ví dụ Java | Có nếu ví dụ được đưa vào quy trình build/test | Ví dụ có thực sự dạy đúng hành vi cần thiết không? |
| So khớp OpenAPI với schema triển khai | Có thể một phần, tùy cách quản lý hợp đồng | HTTP contract có đáp ứng nhu cầu người dùng và tương thích không? |
| Kiểm tra tên biến, kiểu tham số từ Javadoc | Có thể một phần | Mô tả tiền điều kiện hoặc ngoại lệ có đúng nghiệp vụ không? |
| Nhắc cập nhật tài liệu khi code liên quan đổi | Có thể dựa trên đường dẫn hoặc rule | Bản thay đổi có thực sự ảnh hưởng tài liệu nào và tác động ra sao? |
| Kiểm tra sự tồn tại của runbook | Có | Runbook còn dùng được khi có sự cố thật không? |
| Kiểm tra người review theo ownership | Có thể qua quy tắc repository | Reviewer có đủ năng lực và đã đọc nội dung chưa? |
| Kiểm tra mô tả “giao nhanh được miễn phí” | Không đáng tin cậy chỉ bằng linter cú pháp | Người hiểu chính sách phải xác nhận nội dung. |

**CI xanh không đồng nghĩa tài liệu đúng về ngữ nghĩa.** Cần ghép kiểm tra tự động với review có chủ sở hữu và bằng chứng thực tế.

### Tránh tạo gánh nặng hình thức

Một quy trình yêu cầu “mọi PR phải sửa README” có thể tạo những thay đổi không cần thiết. Ngược lại, tùy chọn “không bao giờ cần giải thích” cũng dễ dẫn tới tài liệu lệch mã.

Cách hiệu quả hơn là yêu cầu **đánh giá tác động tài liệu**:

- Có thay đổi hành vi người dùng thấy không?
- Có đổi tham số, mã lỗi, trạng thái, cấu hình hoặc cách vận hành không?
- Có thay đổi ranh giới phụ thuộc, quy tắc nghiệp vụ hoặc quyết định kiến trúc không?
- Nếu không cần sửa tài liệu, vì sao?

Với PR chỉ đổi tên biến nội bộ mà không ảnh hưởng hợp đồng, câu trả lời **“không cần cập nhật tài liệu; hành vi và API không đổi”** có thể hoàn toàn hợp lý.

## 8. Gắn tài liệu vào vòng đời một thay đổi

Hãy xem quy trình phát triển có trách nhiệm như một chuỗi có thể kiểm chứng:

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi"] --> B["Xác định hợp đồng và người sở hữu"]
    B --> C["Sửa mã và kiểm thử"]
    C --> D["Đánh giá tài liệu bị ảnh hưởng"]
    D --> E{"Có thay đổi cách dùng hoặc vận hành?"}
    E -- "Có" --> F["Cập nhật Javadoc, README, API docs hoặc runbook"]
    E -- "Không" --> G["Ghi rõ lý do không cập nhật"]
    F --> H["Kiểm tra tự động và review theo trách nhiệm"]
    G --> H
    H --> I["Triển khai và kiểm chứng"]
    I --> J["Theo dõi phản hồi, sửa tài liệu khi cần"]
~~~

### Trước khi sửa mã

Xác định **nguồn sự thật** của quy tắc:

- Đặc tả nghiệp vụ nào xác định ngưỡng 500.000 VND?
- API và Javadoc hiện cam kết điều gì?
- Dữ liệu, cấu hình và vận hành có ràng buộc nào?
- Ai có quyền quyết định cách giải thích khi nguồn mâu thuẫn?

Nếu đặc tả đã cũ hoặc hai tài liệu mâu thuẫn, không nên chỉ sao chép cách diễn đạt từ một file gần mã rồi gọi đó là hợp đồng chính thức.

### Trong pull request

Cập nhật đồng bộ các thành phần bị ảnh hưởng:

1. **Mã:** áp dụng quy tắc đã được thống nhất.
2. **Test:** bảo vệ ca thường, ca biên và ca thất bại.
3. **Javadoc/API docs:** nêu tiền điều kiện, hậu điều kiện, lỗi và thay đổi hành vi công khai.
4. **README/ví dụ:** cho người tiêu thụ biết cách dùng đúng.
5. **Runbook/ADR nếu có tác động:** nêu cách vận hành mới hoặc lý do kiến trúc thay đổi.

Không nhất thiết tất cả đều phải đổi trong mọi PR. Điều cần có là **không bỏ sót loại tài liệu bị ảnh hưởng**.

### Sau triển khai

Đối chiếu tài liệu với hành vi được triển khai, đặc biệt nếu triển khai có feature flag, rollout theo vùng hoặc nhiều phiên bản client cùng tồn tại. Tài liệu có thể cần ghi **phạm vi phiên bản** để tránh mô tả một hành vi “đã áp dụng cho tất cả” khi thực tế mới bật cho một nhóm người dùng.

Nếu phản hồi từ hỗ trợ khách hàng hoặc người tích hợp cho thấy hướng dẫn khó hiểu, owner cần có cách nhận và ưu tiên sửa, không để góp ý chìm trong cuộc trò chuyện riêng.

## 9. Sở hữu tài liệu trong quy trình review

Một số repository hỗ trợ cấu hình người review theo đường dẫn. Ví dụ **CODEOWNERS** trong môi trường hỗ trợ cơ chế này:

~~~text
# Minh họa quy tắc sở hữu theo đường dẫn:
/checkout/README.md                     @team-checkout
/checkout/docs/                         @team-checkout
/checkout/src/main/java/                @team-checkout
/operations/checkout-runbook.md         @team-platform
~~~

Đây là **ví dụ cấu hình minh họa**, không phải lệnh cần ghi vào dự án hiện tại. Tên nhóm, cấu trúc đường dẫn và quy tắc bắt buộc review phụ thuộc nền tảng quản lý mã và thiết lập của repository.

CODEOWNERS có thể giúp **đưa yêu cầu review đến đúng nhóm**, nhưng không tự đảm bảo:

- Người được gán còn là owner thực tế.
- Nội dung tài liệu là đúng với chính sách vừa thay đổi.
- Người review đã kiểm tra ví dụ trên môi trường phù hợp.
- Quyết định giữa nghiệp vụ và kỹ thuật không mâu thuẫn.
- Một tài liệu ngoài repository cũng đã được cập nhật.

Vì thế, owner cần giữ **trách nhiệm thực chất**: trả lời câu hỏi, giải quyết mâu thuẫn, xác nhận thay đổi và tổ chức cập nhật khi có phản hồi.

## 10. Một nguồn chuẩn, nhiều nơi cần giải thích

Có thông tin cần xuất hiện ở nhiều nơi:

- Chính sách giảm phí trong tài liệu sản phẩm.
- Javadoc của hàm tính phí.
- Bảng ví dụ ở README.
- Test giá trị biên.
- Câu trả lời trong tài liệu hỗ trợ khách hàng.

Nếu mọi nơi đều lưu cùng một công thức bằng văn bản độc lập, mỗi thay đổi sẽ có nguy cơ **quên một bản sao**.

Cách giảm sai lệch:

1. **Chọn một nguồn có thẩm quyền** cho quy tắc hoặc hợp đồng; xác định ai phê duyệt.
2. **Trích dẫn, liên kết hoặc sinh tài liệu tự động** từ nguồn phù hợp khi có thể.
3. **Để mỗi nơi mô tả đúng nhu cầu người đọc**, không nhất thiết sao chép y nguyên văn bản.
4. **Kiểm tra các ví dụ quan trọng** bằng test và phản hồi của người sử dụng.
5. **Gắn phiên bản hoặc phạm vi áp dụng** khi nhiều cách triển khai cùng tồn tại.

Không phải mọi thứ đều nên sinh ra từ code. **Code mô tả hệ thống đang làm gì**, nhưng chưa chắc đại diện cho **quy tắc sản phẩm mong muốn** nếu implementation đang có lỗi. Nếu tài liệu được sinh hoàn toàn từ code sai, ta có thể tạo một bản giải thích rất nhất quán về một hành vi sai.

**Nguồn sự thật là vấn đề quyền quyết định và mục đích**, không chỉ là file nào dễ trích xuất nhất.

## 11. ADR: lưu lý do, không lặp lại toàn bộ mã

Một quyết định kiến trúc thường không đọc ra được từ mã. Ví dụ tại sao nhóm chọn tách **ShippingFeePolicy** khỏi **CheckoutService**?

Một ADR ngắn có thể gồm:

~~~markdown
# Quyết định: Tách chính sách phí giao hàng

Trạng thái: Accepted

Bối cảnh:
- Nhiều luồng cần tính cùng một chính sách phí.
- Ngưỡng và phụ phí có thể thay đổi theo nghiệp vụ.

Quyết định:
- Đặt công thức trong ShippingFeePolicy.
- Các luồng gọi qua hợp đồng rõ; không tự sao chép công thức.

Đánh đổi:
- Tăng một thành phần cần duy trì.
- Giảm nguy cơ các luồng tính phí không nhất quán.

Khi xem lại:
- Khi có thêm nhiều phương thức giao, thị trường hoặc chính sách riêng.
~~~

ADR không phải thứ cần viết cho mỗi dòng code. Nó hữu ích khi có **lựa chọn thiết kế đáng kể, phương án thay thế và đánh đổi** mà người sửa sau này cần hiểu.

Người chịu trách nhiệm ADR cần biết khi nào quyết định **được thay thế**. Một ADR đã bị thay thế có thể vẫn cần giữ vì giá trị lịch sử, nhưng phải được đánh dấu và liên kết đến quyết định mới. Không nên lặng lẽ sửa lịch sử thành lý do của phương án hiện tại.

## 12. README, Javadoc, API docs và runbook phục vụ các câu hỏi khác nhau

| Loại tài liệu | Câu hỏi chính | Ví dụ nội dung | Cách xác minh |
| --- | --- | --- | --- |
| **Javadoc** | Dùng lớp/phương thức thế nào và hợp đồng của nó là gì? | Đơn vị VND, điều kiện ngưỡng, lỗi khi số âm. | Review cùng code, test trường hợp biên. |
| **README module** | Module làm gì, cách chạy và sử dụng cơ bản? | Cấu hình, lệnh chạy thử, ví dụ đầu vào/đầu ra. | Thử làm theo ở môi trường sạch. |
| **API specification** | Client gọi endpoint bằng dữ liệu và phản hồi nào? | Request/response schema, status, error code. | Contract tests, schema validation, review tương thích. |
| **ADR** | Vì sao quyết định kiến trúc được chọn? | Bối cảnh, phương án, đánh đổi, trạng thái quyết định. | Người tham gia quyết định xác nhận, liên kết quyết định thay thế. |
| **Runbook** | Khi có sự cố, phải quan sát và xử lý theo bước nào? | Cảnh báo, dashboard, cách kiểm tra, phương án rollback. | Diễn tập, thử thủ tục trong điều kiện an toàn. |
| **Tài liệu sản phẩm** | Người dùng được hưởng hành vi nào? | Điều kiện miễn phí giao tiêu chuẩn và phụ phí giao nhanh. | Xác nhận với chủ chính sách, phản hồi từ người dùng. |

Các tài liệu này có thể liên kết nhau nhưng không nên trở thành **bản sao giống hệt**. Người đọc Javadoc không cần toàn bộ runbook vận hành; người trực sự cố không cần đọc tất cả chi tiết triển khai để tìm dashboard cần xem.

## 13. Tài liệu phải mô tả được cả trường hợp thất bại

Một README chỉ ghi luồng thành công thường không đủ để tích hợp an toàn. Với API tạo đơn, tài liệu cần nêu:

- Điều kiện nào làm request bị từ chối?
- Đầu vào sai định dạng trả loại lỗi nào?
- Hết hàng khác với timeout kho dữ liệu ra sao?
- Sau timeout tạo đơn, phía gọi có thể kiểm tra kết quả bằng cách nào?
- Việc gửi lại request có yêu cầu idempotency key không?
- Mã lỗi nào ổn định cho client, thông điệp nào chỉ để hiển thị?

Tương tự, runbook cần phân biệt **sự cố kỹ thuật** với **từ chối nghiệp vụ bình thường**. Nếu một biểu đồ có nhiều lỗi 409 do hết hàng, không được kết luận ngay CSDL hỏng.

**Tài liệu đúng phải giúp người đọc xử lý tình huống không lý tưởng**, không chỉ mô tả điều sẽ xảy ra khi mọi thứ hoạt động bình thường.

## 14. Lỗi thời theo phiên bản và môi trường

Trong thực tế, có thể tồn tại:

- Phiên bản API v1 và v2 đang hoạt động song song.
- Feature flag chỉ bật ở một số tenant.
- Tài liệu “mới” được merge trước khi phần mềm triển khai.
- Cấu hình production khác môi trường local.
- Nhóm hỗ trợ khách hàng dùng hướng dẫn cũ dành cho phiên bản chưa nâng cấp.

Khi ấy, câu “phí giao nhanh luôn 20.000 VND” cần rõ **phạm vi áp dụng** nếu hệ thống chưa triển khai đồng nhất. Tài liệu có thể ghi phiên bản áp dụng, ngày hiệu lực, điều kiện feature flag hoặc liên kết đến trang tương ứng.

Không nên dùng một mốc “đã cập nhật ngày hôm nay” để thay cho thông tin **hợp đồng nào áp dụng cho ai**.

### Chiến lược cập nhật theo thời điểm

- **Trước merge:** mô tả thay đổi dự kiến rõ ràng, cùng code và test.
- **Trước rollout:** bảo đảm người vận hành và tài liệu phát hành có hướng dẫn phù hợp.
- **Trong rollout:** chỉ ra phạm vi triển khai; hỗ trợ nhiều phiên bản nếu cần.
- **Sau rollout:** kiểm chứng hành vi thực tế, cập nhật hoặc bỏ ghi chú chuyển tiếp.
- **Khi ngừng hỗ trợ:** đánh dấu deprecated, hướng dẫn di chuyển và lưu thông tin lịch sử nếu cần.

Ownership phải bao phủ toàn bộ chu trình này, không chỉ khoảnh khắc pull request được phê duyệt.

## 15. Khi tài liệu do nhóm khác sở hữu

Không phải mọi tài liệu liên quan đến thay đổi đều nằm cùng repository. Ví dụ team Checkout thay đổi chính sách tính phí, nhưng trang trợ giúp khách hàng do nhóm sản phẩm hoặc hỗ trợ vận hành quản lý.

Lúc đó, “tài liệu gần mã” vẫn có thể cung cấp **đường dẫn hoặc đầu mối chuyển giao**, nhưng cập nhật cuối cần người sở hữu tài liệu bên kia.

Cách xử lý thực dụng:

1. Xác định **thay đổi nào ảnh hưởng người dùng hoặc đội vận hành**.
2. Ghi rõ **tài liệu cần cập nhật, người nhận và thời điểm hiệu lực**.
3. Cung cấp **ví dụ, dữ liệu biên và nguồn quy tắc đã phê duyệt** để tránh diễn giải khác nhau.
4. Theo dõi việc cập nhật đến khi hoàn tất, nhất là trước đợt triển khai có tác động lớn.
5. Chừa một đầu mối để phản hồi khi người dùng phát hiện hướng dẫn chưa đúng.

Đừng coi việc gửi một tin nhắn “nhờ update docs” là bằng chứng tài liệu đã được cập nhật. Cần kết quả có thể xem và xác nhận, phù hợp với cách tổ chức theo dõi công việc của nhóm.

## 16. Đừng để công cụ tạo tài liệu mới trở thành nguồn sai lệch mới

Các công cụ có thể giúp tóm tắt mã, sinh Javadoc, đề xuất README hoặc tạo bảng endpoint. Dù được sinh tự động, bản mô tả vẫn cần kiểm tra:

- **Nó có nhầm trạng thái hiện tại với hành vi mong muốn không?**
- **Nó có bỏ qua tiền điều kiện, lỗi hoặc tác dụng phụ không?**
- **Nó có suy ra một chính sách chưa từng được phê duyệt không?**
- **Ví dụ sinh ra có chạy được và đúng phiên bản Java/API không?**
- **Nội dung có làm lộ secret, dữ liệu cá nhân hoặc chi tiết nội bộ không được phép công khai không?**

Tương tự với sơ đồ tạo tự động: sơ đồ call graph thể hiện một phần đường gọi, nhưng không tự giải thích **lý do thiết kế** hoặc ranh giới bảo mật. Người có hiểu biết bối cảnh vẫn phải kiểm tra và chịu trách nhiệm nội dung được chấp nhận.

## 17. Đo chất lượng tài liệu bằng khả năng sử dụng, không chỉ bằng số trang

Một số chỉ số dễ đếm nhưng dễ gây hiểu nhầm:

| Chỉ số | Cho biết gì? | Điều không chứng minh được |
| --- | --- | --- |
| Số file Markdown | Khối lượng tài liệu đã lưu | Tài liệu đúng, hữu ích hoặc không trùng lặp. |
| Tỷ lệ link hợp lệ | Liên kết có thể truy cập theo kiểm tra | Nội dung ở đích còn đúng. |
| Tỷ lệ method có Javadoc | Mức độ có chú thích | Chú thích mô tả đúng hợp đồng và trường hợp thất bại. |
| Số PR cập nhật docs | Mức độ hoạt động cập nhật | Những thay đổi quan trọng có được ghi nhận đầy đủ. |
| Số lỗi tài liệu được báo | Có tín hiệu phản hồi | Không có lỗi được báo không có nghĩa không có lỗi. |
| Thời gian người mới hoàn thành tác vụ theo hướng dẫn | Khả năng tài liệu hỗ trợ một tác vụ thực tế | Các tác vụ khác cũng được hỗ trợ tốt. |

Để đánh giá thực chất hơn, thử giao cho người chưa quen module làm một tác vụ: **chạy test, thêm một chính sách phí, dùng API hoặc khôi phục một sự cố mô phỏng**. Ghi nhận nơi họ cần hỏi đồng nghiệp hoặc phát hiện tài liệu mâu thuẫn.

**Tài liệu chất lượng làm giảm sự phụ thuộc vào kiến thức chỉ nằm trong đầu một người**, đồng thời cho phép người mới tự kiểm chứng những điều quan trọng.

## 18. Quy trình review một thay đổi có tác động đến tài liệu

Một checklist ngắn để áp dụng trong code review:

1. **Hành vi nào đổi?** Mô tả thành một câu có thể kiểm chứng.
2. **Ai chịu trách nhiệm nội dung?** Owner có rõ và còn phù hợp không?
3. **Hợp đồng công khai nào bị ảnh hưởng?** API, Javadoc, schema, CLI, config, hướng dẫn người dùng?
4. **Người vận hành có phải đổi cách làm không?** Runbook, cảnh báo, rollback, cấu hình?
5. **Tài liệu nào đang là nguồn có thẩm quyền?** Có bản sao mâu thuẫn không?
6. **Có ví dụ hoặc test bảo vệ tuyên bố quan trọng không?** Kiểm tra cả ranh giới và lỗi.
7. **Có cần review liên chức năng không?** Chính sách nghiệp vụ, bảo mật, vận hành hoặc trải nghiệm người dùng?
8. **Phạm vi phiên bản/triển khai đã rõ chưa?** Không ghi như đã triển khai toàn bộ khi mới ở dạng flag.
9. **Nếu không sửa docs, lý do có thuyết phục không?** Chẳng hạn refactor nội bộ giữ nguyên hợp đồng.
10. **Ai sẽ xử lý phản hồi sau triển khai?** Có nơi tiếp nhận và ưu tiên sửa thông tin lỗi thời?

Ví dụ ghi nhận trong pull request:

~~~markdown
### Tác động tài liệu

- Thay đổi hành vi: thêm phụ phí giao nhanh 20.000 VND.
- Javadoc ShippingFeePolicy: đã cập nhật.
- Ví dụ README: đã cập nhật trường hợp đơn >= 500.000 VND.
- Kiểm thử: đã bổ sung ca ngưỡng và giao nhanh.
- Tài liệu hỗ trợ khách hàng: đã chuyển owner xác nhận trước rollout.
- Runbook vận hành: không đổi, vì không có thay đổi quy trình sự cố.
~~~

Đoạn checklist chỉ có giá trị khi câu trả lời **có thể đối chiếu với diff, test và yêu cầu**, không phải tích dấu cho đủ hình thức.

## 19. Tình huống tự luyện

### Tình huống A — CI xanh nhưng README sai

Một pull request sửa chính sách giao nhanh và thêm đầy đủ unit test. README vẫn ghi “từ 500.000 VND miễn mọi phí”. CI Markdown và link đều xanh.

**Câu hỏi:** Vì sao quy trình vẫn chưa đủ? Ai nên xử lý?

**Gợi ý:** Kiểm tra cú pháp không hiểu chính sách. Author phải đánh giá tác động tài liệu; owner/reviewer đối chiếu với đặc tả; nếu có trang người dùng ngoài repository thì cần chuyển đúng nhóm sở hữu.

### Tình huống B — Có tài liệu nhưng không có owner

Một module có bốn README và hai runbook, nhưng mỗi lần sự cố, mọi người đều hỏi “ai đã viết hướng dẫn này?” và không ai dám cập nhật.

**Câu hỏi:** Nên cải thiện thứ gì trước khi viết thêm tài liệu?

**Gợi ý:** Làm rõ ownership theo nhóm hoặc trách nhiệm và quy trình review. Sau đó kiểm tra nguồn chính, loại trùng lặp và xác định khi nào phải cập nhật.

### Tình huống C — Javadoc được sinh từ code sai

Một công cụ đọc implementation và tạo Javadoc mô tả phép tính mới. Nhưng implementation đã dùng sai ngưỡng 550.000 VND thay vì 500.000 VND theo chính sách đã phê duyệt.

**Câu hỏi:** Javadoc và code nhất quán có chứng minh hệ thống đúng không?

**Gợi ý:** Không. Cả hai có thể cùng sai. Cần nguồn nghiệp vụ độc lập và ca kiểm thử tại ngưỡng được phê duyệt.

### Tình huống D — Một API có hai phiên bản đang chạy

Tài liệu chính chỉ mô tả v2. Một số client vẫn dùng v1, trong đó mã lỗi và trường dữ liệu khác v2.

**Câu hỏi:** Tài liệu cần bổ sung điều gì?

**Gợi ý:** Phạm vi phiên bản, đường dẫn và điều kiện tương thích; hướng dẫn nâng cấp hoặc deprecation; không trình bày hành vi v2 như áp dụng cho mọi client.

### Tình huống E — Thay đổi hoàn toàn nội bộ

Developer đổi tên biến và tách một phương thức dài thành hai phương thức nhỏ, nhưng API và hành vi công khai không đổi.

**Câu hỏi:** Có phải bắt buộc sửa README cho có diff không?

**Gợi ý:** Không. Quan trọng là xác nhận **không có tài liệu bị ảnh hưởng** và test bảo vệ hành vi. Tạo nội dung dư thừa chỉ để hoàn thành checklist có thể làm tăng gánh nặng bảo trì.

---

**Ghi nhớ:** **Đặt tài liệu gần mã tạo điều kiện cho tài liệu được nhìn thấy, sửa cùng và kiểm tra tự động; nhưng tính đúng, độ mới và sự phù hợp vẫn cần người chịu trách nhiệm.** Hãy xác định chủ sở hữu theo thành phần, gắn cập nhật tài liệu vào thay đổi hành vi, giữ nguồn quy tắc rõ ràng và kiểm chứng bằng ví dụ, test cùng review theo bối cảnh. Mục tiêu không phải nhiều tài liệu hơn, mà là tài liệu giúp người khác **hiểu đúng, dùng đúng và thay đổi an toàn**.
