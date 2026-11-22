# Khả năng kiểm thử và xác minh

Trong chương **Các chiều chất lượng** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính giúp đánh giá mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Hai thuộc tính gắn chặt với mục tiêu này là **khả năng kiểm thử** (*testability*) và **khả năng xác minh** (*verifiability*). Khi thay đổi một đoạn mã, nhóm phát triển cần vừa kiểm tra được hành vi của nó, vừa có bằng chứng đáng tin cậy rằng hành vi ấy đáp ứng các yêu cầu đã đặt ra.

Một chương trình chạy được chưa có nghĩa là chương trình đúng; có nhiều bài kiểm thử cũng chưa chắc đã chứng minh được điều cần chứng minh. Chất lượng nằm ở việc thiết kế hành vi dễ quan sát, dễ tạo tình huống kiểm tra và có tiêu chí rõ ràng để đánh giá kết quả.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt khả năng kiểm thử, khả năng xác minh và hoạt động kiểm thử phần mềm.
2. Nhận ra những đặc điểm của mã nguồn khiến lỗi khó tái hiện, khó cô lập hoặc khó phát hiện.
3. Thiết kế lại logic nghiệp vụ để kiểm thử tự động, lặp lại và ít phụ thuộc môi trường.
4. Chuyển yêu cầu thành tiêu chí kiểm tra, trường hợp kiểm thử và bằng chứng xác minh.
5. Đánh giá chất lượng hoạt động kiểm thử bằng nhiều loại bằng chứng, thay vì chỉ nhìn vào tỷ lệ bao phủ mã.

## 2. Hai khái niệm liên quan nhưng không đồng nhất

### 2.1. Khả năng kiểm thử (testability)

**Khả năng kiểm thử** là mức độ dễ dàng khi thiết lập điều kiện đầu vào, thực thi một phần hệ thống và quan sát kết quả để phát hiện sai lệch. Đây là một **thuộc tính của thiết kế và mã nguồn**, chứ không phải số lượng bài test đã viết.

Ví dụ, hàm tính tổng tiền chỉ nhận dữ liệu đơn hàng và trả về một số tiền sẽ dễ kiểm thử hơn hàm vừa tính tiền, vừa đọc cơ sở dữ liệu, lấy thời gian hệ thống, gọi dịch vụ thanh toán và gửi email. Với hàm đầu tiên, ta kiểm soát được đầu vào và biết chính xác đầu ra mong đợi; với hàm thứ hai, rất nhiều yếu tố bên ngoài có thể làm kết quả thay đổi.

### 2.2. Khả năng xác minh (verifiability)

**Khả năng xác minh** là mức độ có thể xác lập và thu thập **bằng chứng kiểm tra được** để kết luận sản phẩm hoặc một phần sản phẩm có đáp ứng những yêu cầu, hợp đồng hay quy tắc xác định trước hay không.

Muốn xác minh, cần biết **đúng theo tiêu chí nào**. Một yêu cầu như “hệ thống xử lý đơn hàng nhanh” rất khó xác minh vì chưa nói thế nào là nhanh. Yêu cầu “ở tải 200 yêu cầu/giây, thời gian phản hồi phân vị 95 không vượt quá 300 ms trong môi trường kiểm thử xác định” tạo ra một tiêu chí có thể đo và đối chiếu. Ngưỡng này chỉ là ví dụ minh họa; giá trị thực tế phải xuất phát từ yêu cầu sản phẩm.

Các hoạt động cung cấp bằng chứng xác minh có thể gồm: rà soát mã, phân tích tĩnh, kiểm thử tự động, kiểm thử thủ công có kịch bản, đo hiệu năng, kiểm tra tính tương thích và đối chiếu log/kết quả với tiêu chí chấp nhận.

### 2.3. Phân biệt ba thuật ngữ thường gặp

| Thuật ngữ | Câu hỏi trung tâm | Ví dụ |
| --- | --- | --- |
| **Testability** (khả năng kiểm thử) | Có dễ tạo điều kiện và quan sát hành vi để phát hiện lỗi không? | Có thể kiểm tra quy tắc hết hạn mã giảm giá mà không cần chờ sang ngày mới. |
| **Testing** (hoạt động kiểm thử) | Khi chạy các trường hợp cụ thể, kết quả thực tế có khác kết quả mong đợi không? | Chạy test với mã giảm giá hết hạn hôm qua và xác nhận bị từ chối. |
| **Verifiability** (khả năng xác minh) | Có thể đưa ra bằng chứng đối chiếu được với tiêu chí đã định nghĩa không? | Tiêu chí chấp nhận nêu rõ ngày hết hạn có hiệu lực đến hết ngày; test ở đúng ngày biên chứng minh quy tắc được triển khai như mô tả. |

Trong kỹ nghệ phần mềm còn có cách phân biệt **verification** (xác minh sản phẩm so với đặc tả: “xây dựng đúng theo yêu cầu đã định?”) và **validation** (thẩm định sản phẩm có đáp ứng nhu cầu sử dụng thực sự hay không: “đang xây dựng đúng thứ người dùng cần?”). Kiểm thử có thể hỗ trợ cả hai; hai câu hỏi không thay thế cho nhau.

## 3. Đặc điểm làm mã nguồn dễ kiểm thử

| Đặc điểm | Biểu hiện tích cực | Dấu hiệu gây khó khăn |
| --- | --- | --- |
| **Quan sát được (observability)** | Đầu ra, trạng thái hoặc sự kiện có thể kiểm tra bằng giao diện rõ ràng. | Hàm thất bại âm thầm; chỉ biết lỗi nhờ nhìn log thủ công. |
| **Điều khiển được (controllability)** | Test có thể cung cấp dữ liệu, thời gian, cấu hình và phản hồi của phụ thuộc. | Hàm tự đọc đồng hồ, gọi API thật, lấy dữ liệu ngẫu nhiên. |
| **Cô lập được (isolation)** | Có thể kiểm tra riêng quy tắc nghiệp vụ và thay thế phụ thuộc ở ranh giới. | Kiểm tra một quy tắc buộc phải khởi động toàn bộ hệ thống. |
| **Tính xác định (determinism)** | Cùng đầu vào và trạng thái kiểm soát thì cùng kết quả. | Test khi qua khi trượt vì thứ tự chạy, thời gian hoặc luồng nền. |
| **Khả năng tái lập (repeatability)** | Có thể tái hiện lỗi bằng dữ liệu và điều kiện được ghi lại. | Lỗi chỉ xuất hiện trên máy một người hoặc một lần ngẫu nhiên. |
| **Khả năng chẩn đoán (diagnosability)** | Thông báo lỗi và assertion giúp khoanh vùng nguyên nhân. | Chỉ nhận thông báo “test failed” mà thiếu giá trị thực tế. |

Các đặc điểm này hỗ trợ lẫn nhau. Chẳng hạn, khả năng thay thế đồng hồ hệ thống vừa giúp **điều khiển** thời gian kiểm thử, vừa làm kết quả **ổn định** và dễ **tái lập**.

### 3.1. Tách nghiệp vụ khỏi tác dụng phụ

**Tác dụng phụ** là hoạt động tác động tới thế giới bên ngoài hoặc trạng thái dùng chung, như ghi cơ sở dữ liệu, gọi mạng, gửi email, cập nhật biến toàn cục. Tác dụng phụ không phải lúc nào cũng xấu; nhiều chương trình bắt buộc phải có chúng. Vấn đề là khi chúng bị trộn vào những quy tắc tính toán lẽ ra có thể kiểm tra độc lập.

Một cấu trúc dễ kiểm thử thường có dạng:

~~~text
Đầu vào từ HTTP/DB/đồng hồ
            |
            v
      Chuyển thành dữ liệu
            |
            v
     Quy tắc nghiệp vụ   <-- kiểm thử độc lập
            |
            v
     Kết quả/quyết định
            |
            v
  Ghi DB / gọi API / gửi sự kiện  <-- kiểm thử tích hợp ở ranh giới
~~~

Ta kiểm thử riêng logic cốt lõi bằng dữ liệu trực tiếp, đồng thời vẫn cần kiểm thử tích hợp để xác minh các kết nối thực sự hoạt động.

### 3.2. Ranh giới phụ thuộc rõ ràng

Một lớp dễ kiểm thử thường nhận những thứ nó phụ thuộc thông qua constructor, tham số hoặc interface. Ví dụ, dịch vụ cần gửi thông báo có thể phụ thuộc vào một interface `NotificationSender`; bài unit test cung cấp một bản giả lập có thể ghi lại thông báo đã gửi, còn chương trình thực sử dụng bộ gửi thật.

Tuy nhiên, không phải phụ thuộc nào cũng cần tạo interface. Với một quy tắc nhỏ chỉ cần giá trị “ngày hôm nay”, truyền `LocalDate` vào hàm thường đơn giản và rõ ý hơn việc xây dựng nhiều tầng trừu tượng.

## 4. Ví dụ Java: kiểm thử quy tắc hết hạn mã giảm giá

Giả sử yêu cầu nghiệp vụ là:

> Mã giảm giá được chấp nhận nếu còn bật, tổng tiền đơn hàng đạt mức tối thiểu và **ngày hiện tại không sau ngày hết hạn**. Mã vẫn sử dụng được trong đúng ngày hết hạn.

### 4.1. Cách viết khó kiểm thử

~~~java
// Mã minh họa: CouponRepository và Coupon là các thành phần hệ thống giả định.
class CheckoutService {
    boolean canApply(String code, int subtotalCents) {
        Coupon coupon = CouponRepository.findByCode(code);
        return coupon != null
                && coupon.enabled()
                && subtotalCents >= coupon.minimumCents()
                && !LocalDate.now().isAfter(coupon.expiresOn());
    }
}
~~~

Một bài test muốn chạy phương thức này phải chuẩn bị dữ liệu trong repository và phụ thuộc vào ngày trên máy đang thực thi. Test cho tình huống “ngày hết hạn” khó lặp lại vì `LocalDate.now()` tự đọc thời gian thực. Lỗi kết nối repository cũng có thể bị nhầm với lỗi của quy tắc giảm giá.

### 4.2. Tách quy tắc thành một thành phần xác định

~~~java
import java.time.LocalDate;
import java.util.Objects;

public final class CouponPolicy {
    public record Coupon(boolean enabled, int minimumCents, LocalDate expiresOn) {
        public Coupon {
            if (minimumCents < 0) {
                throw new IllegalArgumentException("minimumCents must be >= 0");
            }
            Objects.requireNonNull(expiresOn, "expiresOn");
        }
    }

    public boolean canApply(Coupon coupon, int subtotalCents, LocalDate today) {
        Objects.requireNonNull(today, "today");
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("subtotalCents must be >= 0");
        }

        return coupon != null
                && coupon.enabled()
                && subtotalCents >= coupon.minimumCents()
                && !today.isAfter(coupon.expiresOn());
    }
}
~~~

Ở phiên bản này:

- **Đầu vào rõ ràng:** mã giảm giá, tổng tiền tính bằng đơn vị nhỏ nhất của tiền tệ và ngày cần xét đều được truyền vào.
- **Không phụ thuộc I/O:** không cần database, HTTP hay thời gian thật để chạy quy tắc.
- **Ranh giới hợp đồng rõ ràng:** `subtotalCents < 0` là dữ liệu không hợp lệ và được báo bằng ngoại lệ; mã không tồn tại (`null`) được hiểu là không áp dụng.
- **Trường hợp biên nhìn thấy được:** toán tử `!today.isAfter(expiresOn)` cho phép sử dụng đúng ngày hết hạn.

Giả định ở đây là ngày đầu vào đã được xác định theo múi giờ nghiệp vụ. Nếu hệ thống phục vụ nhiều múi giờ, phần chuyển thời điểm thực tế thành `LocalDate` phải tuân theo quy tắc múi giờ đã thỏa thuận và cần có kiểm thử riêng.

### 4.3. Kiểm thử unit với JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class CouponPolicyTest {
    private final CouponPolicy policy = new CouponPolicy();

    @Test
    void acceptsCouponOnExpiryDateAndAtMinimumAmount() {
        var coupon = new CouponPolicy.Coupon(
                true, 100_000, LocalDate.of(2026, 12, 31));

        assertTrue(policy.canApply(
                coupon, 100_000, LocalDate.of(2026, 12, 31)));
    }

    @Test
    void rejectsCouponAfterExpiryDate() {
        var coupon = new CouponPolicy.Coupon(
                true, 100_000, LocalDate.of(2026, 12, 31));

        assertFalse(policy.canApply(
                coupon, 100_000, LocalDate.of(2027, 1, 1)));
    }

    @Test
    void rejectsOrderBelowMinimumAmount() {
        var coupon = new CouponPolicy.Coupon(
                true, 100_000, LocalDate.of(2026, 12, 31));

        assertFalse(policy.canApply(
                coupon, 99_999, LocalDate.of(2026, 12, 1)));
    }

    @Test
    void rejectsDisabledCoupon() {
        var coupon = new CouponPolicy.Coupon(
                false, 100_000, LocalDate.of(2026, 12, 31));

        assertFalse(policy.canApply(
                coupon, 150_000, LocalDate.of(2026, 12, 1)));
    }

    @Test
    void rejectsMissingCoupon() {
        assertFalse(policy.canApply(
                null, 150_000, LocalDate.of(2026, 12, 1)));
    }

    @Test
    void rejectsNegativeOrderAmount() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.canApply(
                        null, -1, LocalDate.of(2026, 12, 1)));
    }
}
~~~

Các test tự tạo dữ liệu và ngày, không phải chờ thời gian trôi qua hoặc kết nối dịch vụ bên ngoài. Cùng với tính **dễ kiểm thử**, các tên test và assertion cũng cho ta bằng chứng trực tiếp về những quy tắc đang được xác minh.

Đoạn Java trên dùng `record` (Java 16 trở lên) và API JUnit Jupiter của JUnit 5. Trong dự án thực tế, cần đặt `CouponPolicy` và `CouponPolicyTest` vào các file, source set phù hợp và khai báo thư viện JUnit trong công cụ build.

### 4.4. Từ quy tắc đến ma trận trường hợp kiểm tra

| Tình huống | Tiền đơn hàng | Ngày hiện tại | Trạng thái mã | Kỳ vọng |
| --- | ---: | --- | --- | --- |
| Đủ điều kiện thông thường | 150.000 | Trước hạn | Bật | Chấp nhận |
| Đúng ngưỡng tiền | 100.000 | Trước hạn | Bật | Chấp nhận |
| Đúng ngày hết hạn | 100.000 | Bằng ngày hết hạn | Bật | Chấp nhận |
| Qua hạn một ngày | 100.000 | Sau hạn | Bật | Từ chối |
| Thiếu một đơn vị tiền | 99.999 | Trước hạn | Bật | Từ chối |
| Mã bị tắt | 150.000 | Trước hạn | Tắt | Từ chối |
| Không có mã | 150.000 | Trước hạn | Không tồn tại | Từ chối |
| Tổng tiền âm | -1 | Bất kỳ ngày hợp lệ | Bất kỳ | Báo dữ liệu không hợp lệ |

Ma trận có ích vì buộc người viết test nghĩ tới **phân hoạch tương đương** (nhóm đầu vào có hành vi giống nhau), **giá trị biên** và các đường đi bất thường. Các con số là ví dụ cho chính sách đã mô tả, không phải mức áp dụng chung cho mọi cửa hàng.

## 5. Làm cho yêu cầu có thể xác minh

Khả năng kiểm thử của mã sẽ phát huy hiệu quả khi yêu cầu có thể được chuyển thành tiêu chí chấp nhận. Một quy trình thực tế:

1. **Phát biểu quy tắc có thể quan sát:** “Mã còn hiệu lực trong đúng ngày hết hạn”.
2. **Xác định dữ liệu và điều kiện:** ngày hiện tại, múi giờ áp dụng, mức tối thiểu, trạng thái mã.
3. **Xác định kết quả mong đợi:** trả về `true`, `false` hoặc một lỗi hợp đồng cụ thể.
4. **Liên kết tiêu chí với trường hợp kiểm thử:** đúng ngày hết hạn, qua hạn một ngày, tiền bằng ngưỡng và thấp hơn ngưỡng một đơn vị.
5. **Lưu bằng chứng:** kết quả test, phiên bản mã, cấu hình chạy và các thông tin đủ để tái lập khi test thất bại.

~~~mermaid
flowchart LR
    A["Yêu cầu nghiệp vụ"] --> B["Tiêu chí chấp nhận"]
    B --> C["Trường hợp kiểm thử"]
    C --> D["Chạy và quan sát"]
    D --> E["Bằng chứng có thể đối chiếu"]
    E --> F{"Đáp ứng tiêu chí?"}
    F -->|Có| G["Chấp nhận kết quả kiểm tra"]
    F -->|Không| H["Điều tra và sửa sai lệch"]
    H --> C
~~~

Không phải mọi yêu cầu đều được xác minh bằng unit test. Ví dụ, yêu cầu chịu tải cần phép đo trong môi trường xác định; yêu cầu phân quyền cần kịch bản quyền truy cập; yêu cầu tính nhất quán dữ liệu cần kiểm thử tích hợp hoặc kiểm tra giao dịch. **Loại bằng chứng phải phù hợp với loại rủi ro và yêu cầu.**

### 5.1. Nhiều lớp bằng chứng bổ sung cho nhau

| Hoạt động | Xác minh tốt điều gì? | Giới hạn quan trọng |
| --- | --- | --- |
| Kiểm tra biên dịch, kiểu dữ liệu và phân tích tĩnh | Lỗi cú pháp, sai kiểu, một số mẫu lỗi hoặc vi phạm quy tắc mã. | Không tự chứng minh quy tắc nghiệp vụ đúng. |
| Unit test | Quy tắc và nhánh xử lý riêng lẻ trong điều kiện kiểm soát. | Không khẳng định các thành phần kết nối đúng trong môi trường thật. |
| Integration test | Tương tác giữa mã ứng dụng, database, message broker hoặc API. | Thường tốn thời gian và công sức thiết lập hơn unit test. |
| Contract test | Kỳ vọng ở ranh giới giữa các thành phần, như schema và hành vi API. | Không thay thế toàn bộ kiểm thử hành trình người dùng. |
| End-to-end test | Luồng người dùng hoàn chỉnh qua nhiều thành phần. | Dễ bị ảnh hưởng bởi môi trường, dữ liệu và các phụ thuộc ngoài. |
| Review và đối chiếu đặc tả | Tính phù hợp với ý định thiết kế, trường hợp còn thiếu, lập luận về rủi ro. | Phụ thuộc chất lượng đặc tả và người thực hiện. |
| Đo hiệu năng/bảo mật có kịch bản | Những thuộc tính phi chức năng trong điều kiện đo đã xác định. | Kết quả chỉ có ý nghĩa trong phạm vi tải, cấu hình và kịch bản đã đo. |

Cần phối hợp các hoạt động theo rủi ro, thay vì cố sử dụng một loại kiểm thử để trả lời tất cả câu hỏi.

## 6. Dấu hiệu mã nguồn khó kiểm thử và hướng cải thiện

### 6.1. Phụ thuộc cứng vào môi trường

**Dấu hiệu:** một test cần API bên ngoài, đồng hồ thực, biến môi trường không kiểm soát hoặc database đang có sẵn dữ liệu đặc biệt.

**Cải thiện:** truyền phụ thuộc qua interface hoặc constructor; cung cấp clock có thể điều khiển; khởi tạo dữ liệu test độc lập; tách logic cốt lõi khỏi I/O. Khi cần kiểm thử tích hợp, quản lý môi trường và dữ liệu một cách có chủ đích.

### 6.2. Trạng thái dùng chung và thứ tự chạy ẩn

**Dấu hiệu:** test chạy riêng thì đỗ, chạy cả bộ lại trượt; kết quả phụ thuộc bài test nào đã chạy trước.

**Cải thiện:** tránh biến toàn cục có thể thay đổi không cần thiết; làm sạch dữ liệu dùng chung; khởi tạo trạng thái riêng cho mỗi ca; không để test tự ý chia sẻ tài nguyên có thể bị sửa.

### 6.3. Không thể quan sát kết quả

**Dấu hiệu:** phương thức nuốt ngoại lệ, ghi log thay cho trả kết quả hoặc phát tín hiệu không có cách theo dõi.

**Cải thiện:** dùng giá trị trả về, kiểu kết quả, ngoại lệ có ý nghĩa hoặc sự kiện có thể thu nhận; đặt assertion trên hành vi quan sát được. Tránh kiểm tra các chi tiết cài đặt riêng tư nếu hành vi công khai đã đủ xác minh yêu cầu.

### 6.4. Bài test không ổn định (flaky test)

**Dấu hiệu:** không thay đổi mã nhưng cùng test lúc đỗ lúc trượt; nguyên nhân thường là thời gian, bất đồng bộ, race condition, dữ liệu hoặc mạng.

**Cải thiện:** loại bỏ thời gian chờ tùy tiện, đồng bộ theo điều kiện thực, kiểm soát dữ liệu ngẫu nhiên bằng seed nếu phù hợp, cô lập tài nguyên và lưu bằng chứng khi thất bại. Chạy lại test có thể giúp điều tra, nhưng không sửa được nguyên nhân gốc.

### 6.5. Kiểm thử gắn chặt vào chi tiết cài đặt

**Dấu hiệu:** đổi cách tách hàm hoặc tên phương thức private là hàng loạt test thất bại dù hành vi bên ngoài không đổi.

**Cải thiện:** ưu tiên kiểm tra hợp đồng và kết quả người dùng nhận được; chỉ kiểm tra tương tác nội bộ khi chính tương tác đó là yêu cầu cần xác minh, ví dụ “không gửi yêu cầu thanh toán lần thứ hai”.

## 7. Đọc đúng các chỉ số kiểm thử

### 7.1. Code coverage không đồng nghĩa với chất lượng xác minh

**Code coverage** cho biết phần mã hoặc nhánh nào được thực thi trong lần chạy test theo cách đo đã chọn. Nó có ích để phát hiện vùng mã chưa được kiểm tra, nhưng **không trả lời được assertion có đúng và đủ mạnh hay không**.

Ví dụ, một test chỉ gọi `canApply(...)` rồi không kiểm tra kết quả vẫn có thể làm tăng độ bao phủ dòng lệnh. Ngược lại, một nhóm test bao phủ các ranh giới nghiệp vụ quan trọng có thể giá trị hơn nhiều test lặp lại cùng một tình huống. Bao phủ nhánh cung cấp thêm thông tin so với bao phủ dòng trong một số trường hợp, nhưng vẫn không phải bằng chứng đầy đủ về tính đúng đắn.

### 7.2. Mutation testing là một tín hiệu bổ sung

**Mutation testing** tạo những thay đổi nhỏ có chủ đích vào mã (ví dụ đổi `>=` thành `>`), sau đó chạy bộ test. Nếu test thất bại do phát hiện thay đổi thì mutant được gọi là “bị tiêu diệt”; nếu test vẫn đỗ, ta có thể đang thiếu trường hợp kiểm tra hoặc assertion.

Với quy tắc giảm giá, nếu đổi điều kiện “đủ ngưỡng” từ `>=` sang `>`, test ở đúng ngưỡng `100_000` sẽ giúp phát hiện sai lệch. Tuy nhiên, mutant sống sót không phải lúc nào cũng là lỗi test: có mutant tương đương về hành vi hoặc nằm ngoài phạm vi đầu vào đang xét.

### 7.3. Đánh giá theo rủi ro và chất lượng tín hiệu

Khi đánh giá bộ kiểm thử, hãy cùng xem xét:

- Những yêu cầu và ranh giới nghiệp vụ quan trọng đã có test hay chưa?
- Assertion có phân biệt được kết quả đúng với sai không?
- Có thể chạy lại và tái hiện lỗi ở môi trường nhất quán không?
- Kết quả thất bại có giúp tìm được nguyên nhân không?
- Những thay đổi rủi ro cao có thêm kiểm thử phù hợp ở tầng tích hợp, bảo mật hoặc hiệu năng không?

Không có một tỷ lệ coverage hay một số lượng test chung nào tự động bảo đảm sản phẩm đáng tin cậy.

## 8. Tình huống thực tế: sửa lỗi mà vẫn tự tin thay đổi mã

Giả sử nhóm nhận báo cáo: *“Mã giảm giá hết hạn ngày 31/12 nhưng không áp dụng được vào chính ngày 31/12.”* Cách tiếp cận có thể xác minh:

1. **Khẳng định quy tắc:** yêu cầu nghiệp vụ cho phép áp dụng đến hết ngày 31/12 theo múi giờ đã định.
2. **Tái hiện lỗi:** tạo bài test có `today = expiresOn`, xác định kết quả mong đợi là `true`.
3. **Khoanh vùng nguyên nhân:** kiểm tra liệu mã dùng phép so sánh `today.isBefore(expiresOn)` (loại cả ngày hết hạn) hoặc đã chuyển múi giờ sai hay không.
4. **Sửa và kiểm tra:** dùng quy tắc bao gồm cả ngày cuối; chạy test đúng ngày, trước ngày và sau ngày hết hạn.
5. **Xác minh ở ranh giới:** nếu dữ liệu ngày được truyền từ HTTP hay DB, kiểm tra cách parse ngày, múi giờ và tích hợp với lớp gọi `CouponPolicy`.
6. **Lưu bằng chứng hồi quy:** giữ test cho lỗi này để những lần chỉnh sửa sau dễ phát hiện việc lỗi xuất hiện trở lại.

Điểm cốt lõi là mỗi bước đều có **đầu vào, kết quả kỳ vọng và bằng chứng**. Thiết kế dễ kiểm thử cho phép tiến hành các bước này nhanh, ít nhiễu và có khả năng tái lập.

## 9. Checklist áp dụng khi viết hoặc review mã

- [ ] Tôi mô tả được hành vi đúng bằng những điều kiện và kết quả cụ thể.
- [ ] Đầu vào quan trọng (thời gian, dữ liệu, cấu hình, phản hồi từ phụ thuộc) có thể kiểm soát trong test.
- [ ] Quy tắc nghiệp vụ quan trọng không bị trộn không cần thiết với truy cập mạng, file hoặc database.
- [ ] Test có thể chạy độc lập và kết quả ổn định với cùng điều kiện.
- [ ] Có trường hợp bình thường, trường hợp biên, dữ liệu sai và nhánh thất bại phù hợp.
- [ ] Assertion kiểm tra hành vi có ý nghĩa, không chỉ gọi hàm để tăng coverage.
- [ ] Có kiểm thử tích hợp cho những ranh giới có nguy cơ sai lệch giữa các thành phần.
- [ ] Lỗi kiểm thử cung cấp đủ thông tin để tái hiện và khoanh vùng.
- [ ] Các tiêu chí chấp nhận quan trọng liên kết được với bằng chứng kiểm tra.

## 10. Tổng kết

**Khả năng kiểm thử** giúp tạo điều kiện, thực thi và quan sát hành vi một cách thuận tiện. **Khả năng xác minh** giúp đối chiếu hành vi ấy với yêu cầu và đưa ra bằng chứng có thể kiểm tra lại. Hai thuộc tính củng cố độ tin cậy của mã nguồn và tạo nền tảng cho việc thay đổi mã an toàn hơn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, điều cần ghi nhớ là **viết mã dễ kiểm thử ngay từ thiết kế, diễn đạt quy tắc thành tiêu chí rõ ràng và chọn bằng chứng phù hợp với từng rủi ro**. Test tự động là công cụ quan trọng, nhưng chất lượng của kết luận còn phụ thuộc vào đặc tả, dữ liệu, assertion và phạm vi các tình huống đã được kiểm tra.

