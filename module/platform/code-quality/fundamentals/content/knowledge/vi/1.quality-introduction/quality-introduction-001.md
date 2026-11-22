# Chất lượng mã nguồn (code quality) là gì?

## 1. Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích chất lượng mã nguồn là gì và vì sao chương trình chạy đúng vẫn có thể chứa mã nguồn chất lượng thấp.
- Nhận diện những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**.
- Phân tích một ví dụ Java đơn giản, phân biệt cải thiện cách viết mã với việc chứng minh mã hoạt động đúng.
- Đặt câu hỏi phù hợp khi đánh giá chất lượng mã trong bối cảnh một dự án thực tế.

Trong module **CODE_QUALITY_FUNDAMENTALS**, trọng tâm là hiểu những thuộc tính quyết định liệu mã nguồn có đáng tin cậy, dễ hiểu và có thể thay đổi an toàn theo thời gian hay không.

## 2. Định nghĩa chất lượng mã nguồn

**Chất lượng mã nguồn (code quality)** là mức độ mà mã của một hệ thống đáp ứng các yêu cầu và ràng buộc của nó, đồng thời giúp con người hiểu, kiểm tra, vận hành và điều chỉnh hành vi của hệ thống một cách an toàn, với chi phí hợp lý.

Định nghĩa này gồm hai khía cạnh liên quan nhưng không đồng nhất:

1. **Hành vi khi chạy:** chương trình giải quyết đúng bài toán, xử lý những tình huống dự kiến, bảo vệ dữ liệu và đáp ứng các yêu cầu vận hành quan trọng.
2. **Khả năng làm việc với mã nguồn:** người phát triển có thể đọc hiểu ý định, tìm lỗi, viết kiểm thử và thực hiện thay đổi mà không dễ gây ra lỗi ngoài ý muốn.

Ví dụ, một chức năng tính phí giao hàng có thể trả về đúng số tiền cho các đơn hàng hiện tại. Tuy nhiên, nếu công thức được viết bằng những con số khó hiểu, lặp lại ở nhiều vị trí và thiếu kiểm thử tại các ngưỡng, việc điều chỉnh chính sách phí trong tháng sau có thể tốn nhiều công sức và dễ xảy ra sai sót.

Vì vậy, câu hỏi không chỉ là *“Chương trình có chạy không?”* mà còn là *“Chạy đúng trong điều kiện nào, và có thể sửa đổi nó an toàn khi yêu cầu thay đổi không?”*

### Chất lượng phụ thuộc vào bối cảnh

Không có một kiểu mã duy nhất tốt nhất cho mọi hệ thống. Một ứng dụng xử lý giao dịch tài chính có thể đặc biệt coi trọng tính đúng đắn, khả năng truy vết và an toàn dữ liệu. Một dịch vụ xử lý hàng triệu yêu cầu mỗi giây cũng phải chú ý đến độ trễ và mức sử dụng tài nguyên. Một công cụ nội bộ nhỏ thường cần ưu tiên sự đơn giản và khả năng bảo trì.

Các ưu tiên có thể khác nhau, nhưng quyết định kỹ thuật vẫn cần dựa trên **yêu cầu có thật, rủi ro thực tế và bằng chứng kiểm chứng được**. Không nên dùng lý do “tối ưu hiệu năng” để biện minh cho một đoạn mã khó hiểu khi chưa đo được vấn đề hiệu năng nào.

## 3. Các thuộc tính thường dùng để đánh giá

Chất lượng mã nguồn có nhiều chiều. Những thuộc tính dưới đây giúp nhóm phát triển thảo luận cụ thể hơn thay vì chỉ nhận xét “mã sạch” hoặc “mã xấu”.

| Thuộc tính | Câu hỏi cần trả lời | Dấu hiệu thực tế |
| --- | --- | --- |
| **Tính đúng đắn (correctness)** | Mã có thực hiện đúng quy tắc nghiệp vụ và hợp đồng đầu vào/đầu ra không? | Kết quả đúng với trường hợp thông thường, trường hợp biên và dữ liệu không hợp lệ theo đặc tả. |
| **Độ tin cậy (reliability)** | Hệ thống có hoạt động ổn định trước lỗi hoặc điều kiện bất thường đã dự liệu không? | Có cách xử lý lỗi rõ ràng; sự cố được phát hiện, cô lập hoặc phục hồi phù hợp. |
| **Tính dễ đọc, dễ hiểu (readability)** | Người khác có hiểu mã đang làm gì và vì sao không? | Tên có nghĩa, luồng xử lý rõ ràng, mức độ phức tạp vừa phải. |
| **Khả năng bảo trì, thay đổi (maintainability)** | Có thể sửa một quy tắc mà ít ảnh hưởng không mong muốn đến phần khác không? | Trách nhiệm được phân chia hợp lý, ít trùng lặp tri thức, phụ thuộc dễ kiểm soát. |
| **Khả năng kiểm thử (testability)** | Có thể kiểm tra hành vi bằng những phép thử đáng tin cậy không? | Hợp đồng rõ ràng, phụ thuộc có thể kiểm soát, kiểm thử bao phủ các rủi ro chính. |
| **Tính an toàn (security)** | Mã có bảo vệ hệ thống và dữ liệu khỏi những hành vi không được phép không? | Kiểm soát quyền truy cập, xử lý đầu vào, dữ liệu nhạy cảm và lỗi theo mô hình đe dọa. |
| **Hiệu quả (efficiency)** | Mã có đáp ứng các ràng buộc về thời gian, bộ nhớ và tài nguyên không? | Độ trễ, thông lượng và mức sử dụng tài nguyên đạt mục tiêu đo được. |

Những thuộc tính này có liên quan nhưng **không thay thế cho nhau**. Mã có tên biến rõ ràng vẫn có thể tính sai; mã chạy nhanh vẫn có thể không an toàn; nhiều kiểm thử chưa chắc đã kiểm tra đúng các trường hợp quan trọng. Một số thuộc tính còn phản ánh chất lượng của cả hệ thống và quá trình vận hành, nên không thể kết luận chỉ bằng cách nhìn một hàm riêng lẻ.

### Ba câu hỏi nền tảng

Khi mới bắt đầu đánh giá một đoạn mã, có thể ưu tiên ba câu hỏi sau:

1. **Đáng tin cậy không?** Hành vi được xác định rõ và có bằng chứng kiểm chứng cho các rủi ro chính không?
2. **Dễ hiểu không?** Người chưa viết đoạn mã có thể xác định ý định và các trường hợp xử lý quan trọng không?
3. **Dễ thay đổi không?** Khi quy tắc thay đổi, có thể xác định nơi cần sửa và tự tin rằng phần liên quan vẫn hoạt động đúng không?

## 4. Ví dụ Java: cùng một chức năng, mức độ dễ hiểu khác nhau

Giả sử cửa hàng áp dụng quy tắc phí giao hàng:

- Tổng tiền hàng từ **500.000 VND** trở lên: miễn phí giao hàng.
- Dưới ngưỡng đó, khách hàng **Premium** trả **15.000 VND**.
- Khách hàng còn lại trả **30.000 VND**.

Đoạn mã dưới đây hiện thực quy tắc bằng biểu thức ngắn:

```java
static int f(int x, boolean p) {
    return x >= 500000 ? 0 : (p ? 15000 : 30000);
}
```

Với những đầu vào thông thường, hàm có thể trả về kết quả đúng. Tuy vậy, `f`, `x`, `p` và các con số không giải thích được ý nghĩa nghiệp vụ. Người đọc phải tự suy luận từ ngữ cảnh bên ngoài; việc đổi ngưỡng hoặc mức phí có thể dễ nhầm lẫn.

Có thể viết lại như sau, vẫn giữ **cùng quy tắc tính phí**:

```java
static int shippingFee(int subtotalVnd, boolean premiumCustomer) {
    final int freeShippingFromVnd = 500_000;
    final int premiumFeeVnd = 15_000;
    final int standardFeeVnd = 30_000;

    if (subtotalVnd >= freeShippingFromVnd) {
        return 0;
    }

    return premiumCustomer ? premiumFeeVnd : standardFeeVnd;
}
```

Điểm cải thiện nằm ở chỗ:

- Tên hàm, tham số và biến diễn đạt **ý định**, đơn vị tiền và quy tắc nghiệp vụ.
- Điều kiện miễn phí được trình bày tách biệt, thuận tiện khi đọc hoặc kiểm tra tại ngưỡng.
- Các mức phí có tên cụ thể, giúp giảm nguy cơ thay nhầm một giá trị khi chính sách thay đổi.
- Hàm chỉ phụ thuộc vào các tham số và trả về kết quả, nên dễ kiểm thử mà không cần thiết lập cơ sở dữ liệu hay mạng.

**Lưu ý:** Đổi tên và trình bày mã không tự chứng minh tính đúng đắn. Cả hai phiên bản đều chưa quy định cách xử lý `subtotalVnd` âm. Nếu yêu cầu nghiệp vụ cấm giá trị âm, hợp đồng và hành vi khi gặp đầu vào này cần được xác định và kiểm thử riêng. Việc chuyển sang kiểu dữ liệu khác hay thêm xác thực cũng phải xét yêu cầu thực tế, không tự động được xem là cải thiện đúng cho mọi trường hợp.

### Kiểm tra hành vi tại ranh giới

Ví dụ các ca kiểm thử với JUnit 5 (giả sử `shippingFee` nằm trong phạm vi gọi được của lớp kiểm thử):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

@Test
void calculatesShippingFeeAroundThreshold() {
    assertEquals(0, shippingFee(500_000, false));
    assertEquals(30_000, shippingFee(499_999, false));
    assertEquals(15_000, shippingFee(499_999, true));
}
```

Các ca này ghi nhận một phần hành vi mong đợi, đặc biệt ở ranh giới `499_999` và `500_000`. Chúng **không** chứng minh hàm đúng cho mọi đầu vào hoặc toàn bộ hệ thống hoạt động an toàn. Chẳng hạn, yêu cầu về số tiền âm, giá trị cực lớn hoặc cách tính tổng đơn hàng phải được quyết định và kiểm tra theo hợp đồng riêng.

## 5. Vì sao chất lượng mã nguồn ảnh hưởng đến dự án?

Mã nguồn thường được đọc và sửa nhiều lần sau khi viết lần đầu. Khi hệ thống tồn tại lâu, các quyết định nhỏ tích lũy thành chi phí thực tế:

| Tình huống | Khi chất lượng chưa phù hợp | Khi chất lượng được chú trọng |
| --- | --- | --- |
| Bổ sung chính sách mới | Phải tìm và sửa cùng quy tắc ở nhiều vị trí; dễ bỏ sót. | Vị trí chứa quy tắc và phạm vi tác động rõ ràng hơn. |
| Sửa lỗi sản xuất | Khó tái hiện lỗi, không biết nhánh nào tạo ra kết quả sai. | Có ranh giới trách nhiệm, thông tin chẩn đoán và kiểm thử hỗ trợ. |
| Thành viên mới tiếp nhận | Mất thời gian giải mã tên viết tắt và luồng xử lý rối. | Tên gọi, cấu trúc và hợp đồng giúp hiểu nhanh hơn. |
| Nâng cấp thư viện hoặc kiến trúc | Phụ thuộc lan rộng khiến thay đổi gây nhiều lỗi dây chuyền. | Phụ thuộc được quản lý, dễ xác định chỗ cần cập nhật và hồi quy. |

Chất lượng mã vì thế liên quan trực tiếp đến **tốc độ phát triển bền vững**: một cách viết tiết kiệm vài phút hôm nay có thể làm những thay đổi sau này chậm hơn. Ngược lại, quá nhiều lớp trừu tượng cho một quy tắc đơn giản cũng khiến mã khó đọc và khó sửa. Mục tiêu là mức độ cấu trúc vừa đủ với nhu cầu hiện tại và những thay đổi có cơ sở dự kiến.

## 6. Những ngộ nhận phổ biến

**“Chạy được và qua kiểm thử là mã chất lượng cao.”** Đây là bằng chứng tích cực cho một phần tính đúng đắn, nhưng chỉ mạnh trong phạm vi những điều kiện đã kiểm tra. Nó chưa cho biết mã có dễ hiểu, an toàn hay dễ sửa hay không.

**“Càng ít dòng càng tốt.”** Mã ngắn không đồng nghĩa với mã đơn giản. Một biểu thức lồng nhiều toán tử có thể ít dòng hơn các câu `if`, nhưng khó đọc và khó kiểm tra hơn.

**“Không trùng lặp mới là mã tốt.”** Loại bỏ hai đoạn giống nhau đôi khi tạo ra một hàm dùng chung hữu ích; đôi khi lại buộc hai quy tắc nghiệp vụ độc lập phụ thuộc vào nhau. Cần xem chúng có thực sự cùng một trách nhiệm và có xu hướng thay đổi cùng nhau không.

**“Chỉ cần dùng công cụ phân tích là đo được toàn bộ chất lượng.”** Công cụ có thể phát hiện mẫu lỗi, cảnh báo bảo mật hoặc độ phức tạp đáng ngờ; nó không hiểu đầy đủ yêu cầu nghiệp vụ, ưu tiên người dùng và mọi rủi ro vận hành.

**“Mã có nhiều thiết kế trừu tượng hơn sẽ dễ mở rộng hơn.”** Trừu tượng có ích khi cô lập được những lý do thay đổi có thật. Nếu tạo quá sớm hoặc không đúng ranh giới, nó có thể tăng số lớp phải đọc và tăng chi phí sửa đổi.

## 7. Đánh giá chất lượng bằng bằng chứng nào?

Không có một chỉ số đơn lẻ nào đại diện đầy đủ cho chất lượng mã nguồn. Thay vào đó, có thể kết hợp nhiều nguồn bằng chứng:

| Nguồn bằng chứng | Cho biết điều gì | Giới hạn cần nhớ |
| --- | --- | --- |
| Kiểm thử tự động | Một số hành vi đã được kiểm chứng và có thể kiểm tra lại khi sửa mã. | Bỏ sót trường hợp biên hoặc đặc tả sai vẫn có thể khiến kiểm thử xanh. |
| Review mã nguồn | Người khác đánh giá cách đặt tên, thiết kế, thay đổi hành vi và rủi ro. | Phụ thuộc vào ngữ cảnh và chất lượng phản hồi của người review. |
| Phân tích tĩnh | Phát hiện quy tắc bị vi phạm, mẫu lỗi và dấu hiệu phức tạp. | Có thể có cảnh báo không phù hợp hoặc bỏ sót lỗi nghiệp vụ. |
| Đo hiệu năng và quan sát hệ thống | Cung cấp số liệu về độ trễ, tài nguyên, lỗi và hành vi thực tế. | Cần môi trường và tải đo phù hợp; chỉ số tốt chưa chứng minh mọi mặt khác. |
| Tần suất lỗi hồi quy, thời gian sửa lỗi | Gợi ý khó khăn trong thay đổi và vận hành qua thời gian. | Còn chịu ảnh hưởng bởi quy mô thay đổi, quy trình và môi trường. |

Các số đo như **độ phức tạp**, **mức độ lặp**, **số cảnh báo** hay **tỷ lệ bao phủ kiểm thử** là tín hiệu để điều tra thêm. Chẳng hạn, độ bao phủ 100% theo dòng lệnh không có nghĩa mọi nhánh logic và mọi yêu cầu nghiệp vụ đều đã được kiểm chứng. Khi dùng chỉ số, cần biết nó đo cái gì, không đo cái gì và mục tiêu của hệ thống là gì.

## 8. Cách áp dụng khi đọc hoặc viết một thay đổi nhỏ

Khi chỉnh sửa một đoạn mã, có thể áp dụng quy trình thực tế sau:

1. **Làm rõ yêu cầu:** Ghi lại đầu vào, đầu ra, các quy tắc và trường hợp biên quan trọng. Nếu quy tắc chưa rõ, cần xác minh trước khi kết luận mã đúng hoặc sai.
2. **Đọc luồng xử lý hiện tại:** Xác định ai gọi đoạn mã, nó dùng dữ liệu nào và có tác dụng phụ gì. Tìm những điểm liên quan trực tiếp đến thay đổi.
3. **Chọn cấu trúc dễ hiểu nhất đáp ứng yêu cầu:** Đặt tên rõ nghĩa, giới hạn trách nhiệm, chỉ tách hàm hoặc tạo trừu tượng khi việc đó làm mã dễ nắm bắt hơn.
4. **Bổ sung bằng chứng kiểm chứng:** Kiểm thử hành vi quan trọng, trường hợp biên và lỗi có khả năng gây thiệt hại. Với yêu cầu phi chức năng, đo bằng công cụ và điều kiện phù hợp.
5. **Review tác động:** Kiểm tra xem sửa một quy tắc có làm thay đổi hành vi khác không; xem lại độ rõ ràng và những phụ thuộc mới phát sinh.

Trong quá trình đó, **chất lượng là kết quả của các quyết định có thể giải thích và kiểm chứng**, không phải danh sách quy tắc hình thức áp dụng máy móc.

## 9. Tự kiểm tra hiểu biết

Hãy thử trả lời trước khi xem phần gợi ý:

1. Một hàm Java đặt tên rõ ràng nhưng trả kết quả sai ở ngưỡng giá trị. Hàm đó có chất lượng tốt không? Vì sao?
2. Nếu hai cách viết cùng đúng, một cách ngắn hơn nhưng khó đọc hơn, bạn cần xem xét điều gì để lựa chọn?
3. Một dự án báo cáo tỷ lệ bao phủ kiểm thử cao. Bạn còn cần loại bằng chứng nào để đánh giá độ tin cậy của chức năng thanh toán?

**Gợi ý:** (1) Chưa đạt tính đúng đắn, nên tên đẹp không đủ. (2) Đánh giá khả năng đọc hiểu, thay đổi, rủi ro và bối cảnh sử dụng, thay vì số dòng đơn thuần. (3) Kiểm tra các kịch bản nghiệp vụ và trường hợp biên, review an toàn dữ liệu, quan sát lỗi thực tế và các yêu cầu vận hành liên quan.

## 10. Ghi nhớ

Chất lượng mã nguồn thể hiện ở cả **hành vi đáng tin cậy** lẫn **khả năng hiểu và thay đổi mã an toàn**. Mã chạy đúng hôm nay là điều cần thiết, nhưng chưa đủ để kết luận chất lượng tổng thể. Hãy đánh giá theo yêu cầu của dự án, dùng các thuộc tính cụ thể để thảo luận, và kết hợp kiểm thử, review, phân tích cùng số liệu vận hành để đưa ra nhận định có cơ sở.
