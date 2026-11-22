# Chi phí hiểu, kiểm tra, thay đổi và khắc phục lỗi

> **Chương:** Nhập môn  
> **Phạm vi:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`)

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao chất lượng mã nguồn ảnh hưởng đến thời gian và rủi ro trong suốt vòng đời phần mềm, kể cả khi chức năng hiện tại vẫn chạy đúng.
- Phân biệt bốn nhóm chi phí: **hiểu mã**, **kiểm tra hành vi**, **thay đổi chức năng** và **khắc phục lỗi**.
- Nhận diện những đặc điểm thiết kế làm tăng hoặc giảm từng loại chi phí.
- Đánh giá một quyết định cải thiện chất lượng bằng ví dụ và tín hiệu thực tế, thay vì chỉ dựa vào sở thích viết mã.

## 1. Chất lượng mã nguồn có giá trị ở đâu?

Viết xong một tính năng không có nghĩa là công việc với đoạn mã đó đã kết thúc. Trong các tháng hoặc năm tiếp theo, thành viên trong nhóm sẽ phải đọc nó để trả lời câu hỏi, kiểm tra nó khi hệ thống thay đổi, chỉnh sửa để đáp ứng yêu cầu mới và tìm nguyên nhân khi có sự cố. Những hoạt động này tốn thời gian, đòi hỏi phối hợp và có thể gây gián đoạn dịch vụ.

**Chất lượng mã nguồn** có thể nhìn từ góc độ rất thực dụng: mã giúp con người **hiểu đúng, xác minh đúng, sửa đổi an toàn và chẩn đoán lỗi** với bao nhiêu công sức. Một đoạn mã ngắn chưa chắc rẻ để bảo trì; một đoạn mã có thêm vài hàm, bài kiểm thử hoặc tài liệu có thể tốn công ban đầu nhưng tiết kiệm đáng kể ở các lần làm việc sau.

Ta có thể dùng mô hình tư duy:

```text
Chi phí liên quan đến mã trong vòng đời
  ≈ chi phí hiểu
  + chi phí kiểm tra
  + chi phí thay đổi
  + chi phí khắc phục lỗi
  + các chi phí khác (vận hành, triển khai, phối hợp, ...)
```

Đây là **cách phân loại để thảo luận**, không phải công thức kế toán chính xác. Một giờ tìm hiểu để sửa lỗi có thể thuộc cả hoạt động hiểu và khắc phục lỗi; khi đo lường thực tế cần quy định cách phân bổ để không cộng trùng.

| Nhóm chi phí | Câu hỏi người làm phần mềm phải trả lời | Điều khiến công việc trở nên đắt đỏ |
| --- | --- | --- |
| **Hiểu** | Mã này làm gì, vì sao làm như vậy, ai phụ thuộc vào nó? | Tên khó hiểu, luồng xử lý rối, quy tắc ngầm, phụ thuộc không rõ |
| **Kiểm tra** | Làm sao biết hành vi đúng và không gây hồi quy? | Khó dựng dữ liệu, lệ thuộc dịch vụ bên ngoài, kết quả kiểm thử không ổn định |
| **Thay đổi** | Cần sửa ở đâu, ảnh hưởng tới đâu, triển khai có an toàn không? | Logic trùng lặp, ghép nối chặt, ranh giới trách nhiệm mờ |
| **Khắc phục lỗi** | Lỗi xuất hiện khi nào, nguyên nhân nào, làm sao ngăn tái diễn? | Thiếu tín hiệu quan sát, khó tái hiện, nhiều trạng thái ẩn và tác dụng phụ |

## 2. Chi phí hiểu mã (cost of understanding)

Chi phí hiểu là công sức để một người xây dựng được **mô hình tinh thần đúng** về hệ thống trước khi tự tin trả lời hoặc chỉnh sửa. Người đó có thể là thành viên mới, người viết mã sau một thời gian dài hoặc đồng nghiệp đang review pull request.

Ví dụ: một hàm `process()` dài hàng trăm dòng vừa tính giảm giá, ghi cơ sở dữ liệu, gửi email, vừa gọi cổng thanh toán. Muốn biết thay đổi quy tắc giảm giá có ảnh hưởng đến email hay không, người đọc phải lần theo nhiều nhánh điều kiện và tác dụng phụ. Kể cả khi hàm không có lỗi, mỗi lần đọc lại vẫn tốn thời gian.

Những yếu tố thường làm tăng chi phí hiểu:

- Tên biến/hàm chung chung (`data`, `handle`, `doProcess`) không bộc lộ ý định.
- Một đơn vị mã ôm nhiều trách nhiệm, làm người đọc phải giữ quá nhiều thông tin trong đầu.
- Các giá trị cố định, quy tắc nghiệp vụ và giả định đầu vào xuất hiện rải rác mà không được giải thích.
- Logic trùng nhau nhưng khác một vài chi tiết, khiến người đọc không biết đâu là nguồn sự thật.
- Tài liệu mô tả hành vi cũ hoặc giải thích *cái gì* mà bỏ qua quyết định *vì sao*.

Cải thiện không đồng nghĩa với thêm chú thích vào mọi dòng. Tên đúng, cấu trúc rõ, chức năng có trách nhiệm cụ thể và ví dụ về hành vi quan trọng thường giúp người đọc nhanh hơn. Chú thích hữu ích nhất khi giải thích **lý do, ràng buộc hoặc ngoại lệ** mà bản thân câu lệnh không nói lên được.

**Dấu hiệu có thể quan sát:** người sửa một quy tắc nhỏ phải hỏi nhiều người, mở hàng loạt file không liên quan hoặc đọc mã rất lâu trước khi dám đưa ra thay đổi. Tuy nhiên, thời gian đọc cũng phụ thuộc độ quen thuộc của người đọc và độ phức tạp tự nhiên của bài toán; không nên quy mọi khó khăn cho cách viết mã.

## 3. Chi phí kiểm tra (cost of verification)

Một thay đổi chỉ thật sự sẵn sàng khi nhóm có đủ bằng chứng rằng hành vi mong đợi được giữ nguyên và các trường hợp quan trọng hoạt động đúng. Chi phí kiểm tra bao gồm chuẩn bị dữ liệu, cấu hình môi trường, viết/chạy kiểm thử, đọc kết quả, kiểm tra thủ công khi cần và xử lý báo động sai.

Giả sử muốn kiểm tra quy tắc tính giảm giá nhưng mã hiện tại chỉ tính giá bên trong luồng thanh toán thật. Người kiểm thử có thể phải dựng tài khoản, kết nối cơ sở dữ liệu, giả lập cổng thanh toán và dọn dữ liệu sau khi chạy. Một phép tính đơn giản trở thành bài kiểm thử tích hợp chậm, khó tái hiện và dễ hỏng bởi yếu tố ngoài phạm vi cần kiểm chứng.

Các nguyên nhân điển hình làm chi phí kiểm tra tăng:

- **Logic và tác dụng phụ trộn lẫn:** phép tính cần mạng, đồng hồ hệ thống hoặc cơ sở dữ liệu mới chạy được.
- **Đầu ra khó quan sát:** hàm thay đổi trạng thái toàn cục thay vì trả kết quả rõ ràng.
- **Thiếu trường hợp biên:** chỉ kiểm tra đường đi thành công, bỏ qua đầu vào rỗng, số âm, giới hạn giá trị và lỗi từ dịch vụ ngoài.
- **Kiểm thử không ổn định (flaky):** cùng mã, cùng dữ liệu nhưng lúc qua lúc trượt vì thời gian, thứ tự hoặc môi trường.
- **Bộ kiểm thử chậm:** mỗi sửa đổi nhỏ đều phải chờ phản hồi quá lâu.

Thiết kế thuận tiện cho kiểm tra thường tách **quy tắc thuần** (tính toán, xác thực) khỏi phần **tương tác bên ngoài** (lưu trữ, mạng, gửi thông báo). Khi đó các bài unit test nhanh giúp xác minh quy tắc, còn integration/end-to-end test xác minh cách các thành phần phối hợp. Unit test nhiều không thay thế được kiểm tra tích hợp khi hợp đồng giữa các dịch vụ mới là nguồn rủi ro.

**Dấu hiệu có thể quan sát:** mất nhiều công dựng môi trường cho một kiểm thử nhỏ, cần thao tác tay lặp đi lặp lại hoặc khó tin kết quả test vì thường xuyên thất bại ngẫu nhiên.

## 4. Chi phí thay đổi (cost of change)

Chi phí thay đổi là toàn bộ công sức và rủi ro khi chuyển từ hành vi hiện tại sang hành vi mới: xác định nơi cần sửa, cập nhật mã, giữ tương thích, kiểm tra hồi quy, review và triển khai. Số dòng code phải sửa chỉ là một phần nhỏ của chi phí này.

Ví dụ: doanh nghiệp thay đổi ngưỡng áp dụng ưu đãi VIP. Nếu ngưỡng được chép vào API, giao diện, tác vụ nền và báo cáo, người sửa cần tìm đủ bốn nơi và kiểm tra kết quả có nhất quán không. Bỏ sót một nơi có thể làm cùng một đơn hàng được tính khác nhau giữa các luồng.

Các đặc điểm giúp thay đổi an toàn hơn gồm:

- **Một nguồn sự thật** cho mỗi quy tắc nghiệp vụ quan trọng, tránh các bản sao dễ lệch nhau.
- **Trách nhiệm rõ** để chỉnh chính sách giá mà ít phải chạm vào xử lý email, thanh toán hay truy xuất dữ liệu.
- **Giao diện và hợp đồng ổn định** giữa các thành phần, giúp dự đoán phạm vi ảnh hưởng.
- **Kiểm thử hồi quy phù hợp** để phản hồi nhanh khi hành vi cũ bị tác động ngoài dự kiến.
- **Thay đổi nhỏ, dễ review** để người khác hiểu rõ ý định và rủi ro.

Không nên tách mỗi dòng thành một lớp hoặc tạo hệ thống trừu tượng chỉ vì có thể sẽ thay đổi trong tương lai. Quá nhiều lớp và cấp gián tiếp cũng khiến đường đi của một yêu cầu khó theo dõi, từ đó tăng chi phí hiểu và thay đổi. Mức phân tách hợp lý phụ thuộc vào những phần **thực sự thay đổi độc lập**.

**Dấu hiệu có thể quan sát:** mỗi yêu cầu nhỏ kéo theo sửa nhiều file không cùng trách nhiệm, nhiều nhánh `if` giống nhau, hoặc thời gian review và hồi quy lớn hơn nhiều so với thời gian viết logic mới.

## 5. Chi phí khắc phục lỗi (cost of defect resolution)

Chi phí khắc phục lỗi không chỉ là thời gian gõ bản vá. Một sự cố thường đi qua chuỗi việc:

```text
Phát hiện → Xác định tác động → Tái hiện → Khoanh vùng nguyên nhân
          → Sửa lỗi → Kiểm tra hồi quy → Triển khai/khôi phục → Theo dõi
```

Ở mỗi bước, chất lượng mã và khả năng quan sát của hệ thống có thể làm khác biệt lớn. Nếu một đơn hàng bị tính sai, nhóm cần biết chính sách nào đã áp dụng, phiên bản dịch vụ nào xử lý, dữ liệu đầu vào nào hợp lệ và tại đâu số tiền thay đổi. Thiếu những thông tin này, nhóm có thể phải đoán qua nhiều nhánh mã hoặc đợi lỗi tái diễn.

Một số cách giảm chi phí khắc phục lỗi:

- Kiểm tra và làm rõ điều kiện đầu vào, đầu ra; báo lỗi gần nguồn phát sinh để dễ khoanh vùng.
- Giữ thao tác có tác dụng phụ ở ranh giới rõ ràng; nếu có thể, làm logic quyết định dễ tái hiện bằng dữ liệu đầu vào.
- Ghi log/sự kiện có ngữ cảnh hữu ích như mã yêu cầu, bước xử lý và loại lỗi; bảo vệ dữ liệu nhạy cảm.
- Viết bài kiểm thử tái hiện lỗi trước hoặc song song với bản vá, rồi giữ nó để ngăn tái diễn.
- Phân biệt **triệu chứng** với **nguyên nhân gốc**: thêm `try/catch` để nuốt lỗi có thể giảm thông báo lỗi nhưng làm khó phát hiện sự cố sau này.

Ngoài giờ kỹ thuật, lỗi còn có thể gây mất doanh thu, gián đoạn dịch vụ, chi phí hỗ trợ khách hàng hoặc tổn hại niềm tin. Mức tác động phụ thuộc bối cảnh: lỗi hiển thị văn bản và lỗi tính tiền không có cùng mức độ ưu tiên.

**Dấu hiệu có thể quan sát:** nhóm khó tái hiện lỗi, thiếu thông tin để truy vết, liên tục sửa một loại sự cố hoặc thường xuyên phát sinh lỗi khác sau bản vá.

## 6. Ví dụ xuyên suốt: quy tắc giảm giá khi đặt hàng

Giả định một cửa hàng có quy tắc minh họa:

1. Khách VIP được giảm 10% **giá trị hàng ban đầu** khi giá trị đó từ `1_000_000` VND.
2. Mã `SAVE50` giảm thêm `50_000` VND và được cộng dồn với ưu đãi VIP.
3. Tổng cần thanh toán không được âm.

Trong phiên bản ban đầu, phần tính giá nằm ngay giữa các thao tác với hệ thống bên ngoài:

```java
void completeOrder(Order order) {
    int amount = order.subtotalVnd();
    if (order.isVip() && amount >= 1_000_000) {
        amount -= amount / 10;
    }
    if ("SAVE50".equals(order.coupon())) {
        amount -= 50_000;
    }
    amount = Math.max(0, amount);

    paymentGateway.charge(order.customerId(), amount);
    orderRepository.save(order, amount);
    emailGateway.sendReceipt(order.customerId(), amount);
}
```

Với đoạn mã này, người chỉ muốn xác minh phép tính phải đi vào một phương thức thực hiện thanh toán, lưu dữ liệu và gửi email. Thay đổi chính sách giá cũng buộc người sửa đọc một luồng có nhiều trách nhiệm, làm tăng phạm vi cần cân nhắc.

Ta có thể **tách quy tắc tính giá** thành một đơn vị thuần, có hợp đồng rõ:

```java
final class PricingPolicy {
    private PricingPolicy() {}

    static int amountDue(int subtotalVnd, boolean vip, String coupon) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Subtotal cannot be negative");
        }

        int vipDiscount = (vip && subtotalVnd >= 1_000_000)
                ? subtotalVnd / 10
                : 0;
        int couponDiscount = "SAVE50".equals(coupon) ? 50_000 : 0;

        return Math.max(0, subtotalVnd - vipDiscount - couponDiscount);
    }
}
```

Luồng đặt hàng khi đó giữ nhiệm vụ phối hợp:

```java
void completeOrder(Order order) {
    int amount = PricingPolicy.amountDue(
            order.subtotalVnd(), order.isVip(), order.coupon());

    paymentGateway.charge(order.customerId(), amount);
    orderRepository.save(order, amount);
    emailGateway.sendReceipt(order.customerId(), amount);
}
```

Nhờ phép tính không phụ thuộc cơ sở dữ liệu hoặc mạng, ta có thể xác minh trực tiếp các tình huống quan trọng bằng JUnit 5 (giả sử đã có import `@Test`, `assertEquals` và `assertThrows`):

```java
@Test
void combinesVipAndCouponDiscount() {
    assertEquals(1_030_000,
            PricingPolicy.amountDue(1_200_000, true, "SAVE50"));
}

@Test
void totalNeverBecomesNegative() {
    assertEquals(0,
            PricingPolicy.amountDue(30_000, false, "SAVE50"));
}

@Test
void rejectsNegativeSubtotal() {
    assertThrows(IllegalArgumentException.class,
            () -> PricingPolicy.amountDue(-1, false, null));
}
```

Kết quả khi đối chiếu với bốn chi phí:

| Chi phí | Trước khi tách | Sau khi tách |
| --- | --- | --- |
| Hiểu | Cần đọc phép tính cùng luồng thanh toán/lưu/gửi | Có thể đọc quy tắc giá độc lập rồi mới đọc luồng đặt hàng |
| Kiểm tra | Phải xử lý hoặc giả lập các phụ thuộc của phương thức đặt hàng | Kiểm tra được các nhánh tính giá bằng test nhanh, không cần dịch vụ ngoài |
| Thay đổi | Sửa chính sách ngay trong phương thức nhiều tác dụng phụ | Tập trung sửa ở `PricingPolicy`, có test hỗ trợ phát hiện hồi quy |
| Khắc phục lỗi | Khó xác định sai giá do chính sách hay do khâu bên ngoài | Có thể tái hiện phép tính riêng rồi tiếp tục điều tra tích hợp nếu cần |

**Giới hạn của ví dụ:** việc tách hàm không tự đảm bảo một giao dịch thanh toán an toàn. Hệ thống thật vẫn cần kiểm thử tích hợp, xử lý lỗi/thử lại, tránh thanh toán trùng, kiểm soát nhất quán dữ liệu và quan sát hành vi. Kiểu `int` ở đây chỉ minh họa giá trị VND nguyên và quy tắc đơn giản; với nhiều loại tiền tệ hoặc cách làm tròn phức tạp cần mô hình tiền tệ phù hợp.

## 7. Nhìn vào tổng chi phí, không chỉ công sức lúc viết

Xét **ví dụ giả định** cho cùng một chức năng trong một năm:

| Hoạt động | Cách A: triển khai nhanh, khó kiểm tra | Cách B: tách trách nhiệm và có kiểm thử |
| --- | ---: | ---: |
| Viết ban đầu | 8 giờ | 12 giờ |
| 8 lần sửa yêu cầu × thời gian trung bình | 8 × 3 = 24 giờ | 8 × 1,5 = 12 giờ |
| Kiểm tra các lần sửa | 8 × 2 = 16 giờ | 8 × 1 = 8 giờ |
| Điều tra và sửa sự cố phát sinh | 2 × 6 = 12 giờ | 1 × 3 = 3 giờ |
| **Tổng giả định** | **60 giờ** | **35 giờ** |

Các con số **chỉ để minh họa cách suy nghĩ**, không phải kết quả đo hay lời hứa rằng tách hàm sẽ giảm một tỉ lệ lỗi cố định. Bốn giờ đầu tư thêm vào việc tổ chức mã và kiểm thử có thể được bù lại nếu thành phần đó tiếp tục thay đổi. Ngược lại, một đoạn mã dùng một lần, ít rủi ro và không dự kiến sửa có thể không cần mức đầu tư tương đương.

Khi ra quyết định, nên hỏi:

- Thành phần này có thường xuyên được đọc, chỉnh sửa hoặc tích hợp với phần khác không?
- Nếu sai, hậu quả và thời gian phát hiện/khôi phục là bao nhiêu?
- Cách cải thiện có thực sự giảm công sức tương lai hay chỉ chuyển độ phức tạp sang một nơi khác?
- Có thể thực hiện bước nhỏ nào giúp nhóm quan sát được lợi ích trước khi mở rộng thiết kế?

## 8. Đo lường và cải thiện trong công việc thực tế

Không có một chỉ số đơn lẻ đo được toàn bộ chất lượng mã nguồn. Có thể kết hợp **tín hiệu định lượng** với đánh giá trực tiếp trong quá trình bảo trì:

| Điều muốn hiểu | Tín hiệu tham khảo | Lưu ý khi diễn giải |
| --- | --- | --- |
| Dễ hiểu đến đâu? | Thời gian làm quen một khu vực mã; câu hỏi lặp lại trong review; số lần phải hỏi về quy tắc | Phụ thuộc kinh nghiệm, độ khó bài toán và chất lượng tài liệu |
| Kiểm tra tốn công ra sao? | Thời gian chạy suite; tỷ lệ test không ổn định; công chuẩn bị dữ liệu | Chạy nhanh nhưng thiếu tình huống quan trọng chưa phải là tốt |
| Thay đổi an toàn đến đâu? | Thời gian từ nhận yêu cầu đến hoàn tất thay đổi; số khu vực bị ảnh hưởng; lỗi hồi quy | Quy mô yêu cầu không đồng nhất nên cần so sánh trường hợp tương đương |
| Sửa lỗi hiệu quả đến đâu? | Thời gian phát hiện, khoanh vùng, khôi phục; lỗi tái diễn; chất lượng log/tracing | Sự cố có độ nghiêm trọng rất khác nhau; cần xem bối cảnh |

Những số liệu này hữu ích để tìm **nút thắt của quy trình hoặc thiết kế**. Tránh dùng một chỉ số duy nhất để xếp hạng cá nhân: điều đó dễ khuyến khích tối ưu số đo thay vì cải thiện chất lượng thật.

Một vòng cải thiện thực tế có thể diễn ra như sau:

1. **Chọn một vấn đề cụ thể:** chẳng hạn, mỗi lần sửa công thức giá đều phải kiểm tra thủ công qua cổng thanh toán.
2. **Xác định nguyên nhân:** logic giá bị trộn với thao tác bên ngoài, khó chạy độc lập.
3. **Thực hiện thay đổi nhỏ:** tách hàm tính giá, mô tả quy tắc và bổ sung kiểm thử cho trường hợp biên.
4. **Quan sát lần thay đổi kế tiếp:** thời gian chuẩn bị kiểm thử có giảm không, review có dễ hơn không, có phát sinh lỗi mới không?
5. **Giữ hoặc điều chỉnh giải pháp:** chỉ mở rộng cách làm khi lợi ích phù hợp với chi phí duy trì.

## 9. Những ngộ nhận cần tránh

- **“Chạy đúng là mã đã có chất lượng tốt.”** Chạy đúng ở hiện tại rất quan trọng, nhưng chưa nói lên khả năng kiểm tra và thích ứng với yêu cầu sau này.
- **“Ít dòng hơn luôn rẻ hơn.”** Mã quá cô đọng, nhiều biểu thức lồng nhau có thể khó hiểu và khó sửa hơn mã dài hơn nhưng rõ ý.
- **“Nhiều abstraction luôn giảm chi phí thay đổi.”** Trừu tượng hóa thiếu nhu cầu thực khiến người đọc phải lần theo nhiều tầng, tăng công bảo trì.
- **“Nhiều unit test nghĩa là an toàn tuyệt đối.”** Còn có lỗi tích hợp, sai giả định nghiệp vụ và vấn đề vận hành mà unit test không kiểm chứng được.
- **“Sửa lỗi nhanh chỉ là vá đúng dòng sai.”** Tái hiện, đánh giá tác động, kiểm tra hồi quy và theo dõi sau triển khai là một phần của công việc sửa lỗi.

## 10. Tự kiểm tra hiểu biết

1. Một thay đổi chỉ sửa ba dòng nhưng yêu cầu kiểm thử thủ công trên năm hệ thống. Trong bốn nhóm chi phí, nhóm nào nổi bật và nguyên nhân thiết kế nào có thể dẫn đến điều đó?
2. Nếu nhóm tách logic nghiệp vụ thành hàm thuần, hoạt động nào trở nên rẻ hơn trước tiên? Điều gì vẫn cần integration test?
3. Vì sao chép cùng một quy tắc vào nhiều dịch vụ có thể làm tăng cả chi phí hiểu, thay đổi và khắc phục lỗi?
4. Một thành phần hiếm khi thay đổi có cần được tách thành nhiều interface và lớp hay không? Bạn sẽ dựa trên tín hiệu nào để quyết định?
5. Khi đánh giá hiệu quả cải thiện chất lượng, vì sao không nên chỉ đếm số dòng code hoặc số bài kiểm thử?

**Thông điệp cốt lõi:** chất lượng mã là khả năng duy trì hành vi đúng với chi phí và rủi ro hợp lý qua nhiều lần đọc, kiểm tra, thay đổi và sửa lỗi. Lựa chọn thiết kế tốt là lựa chọn giúp những hoạt động thực tế của nhóm trở nên rõ ràng, dễ xác minh và an toàn hơn theo thời gian.
