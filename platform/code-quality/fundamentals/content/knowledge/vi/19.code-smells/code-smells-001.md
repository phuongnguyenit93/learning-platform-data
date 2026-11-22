# Mùi mã là tín hiệu điều tra chứ chưa phải kết luận lỗi

Trong chương **Mùi mã** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta bắt đầu bằng một nguyên tắc quan trọng: **nhận ra một dấu hiệu đáng nghi trong mã nguồn không đồng nghĩa đã chứng minh mã sai hoặc phải refactor ngay**.

Module **CODE_QUALITY_FUNDAMENTALS** hướng đến việc hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Những đặc điểm như một phương thức rất dài, nhiều nhánh điều kiện, logic trùng lặp, tên khó hiểu hoặc một lớp có nhiều trách nhiệm có thể làm việc bảo trì khó hơn. Chúng thường được gọi là *code smells* — **mùi mã**.

Tuy nhiên, không có quy tắc “một phương thức trên 50 dòng là lỗi”, “mọi mã lặp phải gộp” hay “dùng `switch` là thiết kế xấu” đúng trong mọi hệ thống. Một cấu trúc có thể phù hợp hôm nay, nhưng trở thành khó bảo trì khi yêu cầu, quy mô dữ liệu hoặc đội ngũ thay đổi. Điều cần học là **dùng mùi mã để định hướng điều tra nguyên nhân và rủi ro**, không biến nó thành phán quyết chỉ dựa trên hình thức.

> **Mùi mã là dấu hiệu gợi ý rằng một quyết định thiết kế có thể gây chi phí hiểu, sửa đổi hoặc kiểm thử. Muốn kết luận và hành động, cần xem ngữ cảnh, hành vi, mức rủi ro và bằng chứng.**

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **mùi mã**, **lỗi chức năng**, **lỗ hổng bảo mật**, **vi phạm quy ước** và **nợ kỹ thuật**.
2. Nhận diện các nhóm mùi mã thường gặp: phương thức dài, lớp gánh nhiều trách nhiệm, mã lặp, nhiều tham số, primitive obsession, feature envy, trạng thái chia sẻ và trừu tượng hóa không cần thiết.
3. Giải thích vì sao cùng một biểu hiện có thể chấp nhận được ở ngữ cảnh này nhưng cần sửa ở ngữ cảnh khác.
4. Dùng câu hỏi điều tra để tìm **chi phí thực tế và nguyên nhân thiết kế** phía sau dấu hiệu.
5. Đề xuất refactor nhỏ, đúng trách nhiệm và có bằng chứng, thay vì tự động tạo nhiều class/helper.
6. Bảo toàn hành vi Java khi refactor, đặc biệt với điều kiện biên, ngoại lệ, số học, trạng thái và tác dụng phụ.
7. Ưu tiên vấn đề theo tần suất thay đổi, rủi ro nghiệp vụ, chi phí bảo trì và mức độ an toàn khi sửa.
8. Viết nhận xét code review phân biệt **quan sát**, **giả thuyết**, **bằng chứng** và **đề xuất**.

## 2. Mùi mã không phải một loại lỗi được chứng minh

### 2.1. Bốn khái niệm cần phân biệt

| Khái niệm | Điều đã biết | Ví dụ | Cách xử lý phù hợp |
| --- | --- | --- | --- |
| **Mùi mã (code smell)** | Có dấu hiệu cấu trúc *có thể* làm mã khó bảo trì. | Một phương thức 120 dòng thực hiện nhiều công việc. | Điều tra trách nhiệm, tần suất sửa, phụ thuộc và tác động thực tế. |
| **Lỗi chức năng (bug)** | Hành vi quan sát được không khớp yêu cầu. | Đơn đúng ngưỡng 500.000 vẫn bị tính phí. | Tái hiện, xác nhận đặc tả, sửa lỗi và thêm test hồi quy. |
| **Lỗ hổng bảo mật** | Có điều kiện gây vi phạm yêu cầu hoặc giả định bảo mật. | Tin vào quyền do client tự khai; SQL ghép chuỗi đầu vào không tin cậy. | Phân tích khả năng khai thác/tác động, ưu tiên xử lý bảo mật và xác minh. |
| **Vi phạm quy ước** | Mã không tuân theo thỏa thuận/công cụ của dự án. | Tên class sai quy ước hoặc định dạng không thống nhất. | Làm rõ quy ước và sửa nhất quán khi cần. |
| **Nợ kỹ thuật** | Một quyết định tạo nghĩa vụ hoặc chi phí cho thay đổi tương lai. | Cùng quy tắc nghiệp vụ nằm ở ba service, khiến mỗi lần đổi phải sửa cả ba. | Đánh giá chi phí và ưu tiên hoàn trả nợ theo mục tiêu phát triển. |

Các khái niệm có thể liên quan nhưng **không đồng nhất**. Mã lặp có thể là mùi mã, song chưa gây lỗi ở hiện tại. Khi thay đổi một bản sao mà quên bản còn lại, một **bug** mới xuất hiện. Một lỗ hổng bảo mật phải được đánh giá theo tác động thực tế, không thể xếp chung vào nhóm “chỉ nên dọn khi có thời gian”.

### 2.2. Cùng một đoạn mã có thể có nhiều nhận định

Ví dụ:

~~~java
static int shippingFee(long subtotalCents) {
    if (subtotalCents > 500_000) {
        return 0;
    }
    return 30_000;
}
~~~

Nếu đặc tả là “miễn phí khi tổng tiền **từ 500.000 trở lên**”, điều kiện `>` thay vì `>=` là **lỗi chức năng có thể chứng minh** bằng test ở đúng ngưỡng. Nó không chỉ là mùi mã.

Nếu chưa có đặc tả về điểm ngưỡng, việc thấy `>` không cho phép tự kết luận là sai. Câu hỏi đầu tiên phải là **hợp đồng nghiệp vụ quy định gì?**

### 2.3. “Không sai hôm nay” không có nghĩa “không có rủi ro”

Một lớp giữ cả logic thanh toán, gửi email và tạo báo cáo có thể vẫn trả kết quả đúng. Tuy nhiên, khi ba quy tắc thay đổi độc lập, mỗi lần sửa có nguy cơ ảnh hưởng hành vi khác. Đây là **rủi ro bảo trì** đáng điều tra ngay cả trước khi có bug.

Ngược lại, một hàm tính toán tuyến tính 70 dòng, rõ dữ liệu, ít thay đổi và có test tốt chưa chắc cần tách chỉ vì vượt ngưỡng số dòng.

## 3. Mùi mã cho biết nên hỏi gì, không trả lời sẵn nguyên nhân

Khi nhìn thấy mùi mã, hãy tách ba lớp thông tin:

**Quan sát:** điều có thể kiểm tra trực tiếp, ví dụ “phương thức có sáu tầng `if`”, “ba lớp cùng chứa quy tắc 500.000”.

**Giả thuyết:** vì sao biểu hiện đó có thể gây hại, ví dụ “thay đổi phí sẽ phải sửa nhiều nơi”, “người đọc khó phân biệt nhánh lỗi”.

**Bằng chứng:** điều gì hỗ trợ hoặc bác bỏ giả thuyết, ví dụ lịch sử ba PR cùng sửa nhiều file, bug do bỏ sót một bản sao, test khó tạo, hoặc người review phải lần theo quá nhiều trạng thái.

~~~text
Phát hiện mùi mã
      |
      v
Mô tả dấu hiệu cụ thể
      |
      v
Đặt giả thuyết về chi phí/rủi ro
      |
      v
Kiểm tra ngữ cảnh và bằng chứng
      |
      +--> Có vấn đề đáng giải quyết --> Chọn thay đổi nhỏ nhất phù hợp
      |
      +--> Chưa đủ cơ sở -----------> Theo dõi, đặt câu hỏi hoặc giữ nguyên
      |
      v
Bảo vệ hành vi và đánh giá kết quả
~~~

Cách làm này tránh hai cực đoan: **lờ đi mọi cảnh báo vì “code vẫn chạy”** và **refactor mọi chỗ bị công cụ đánh dấu mà không hiểu chức năng**.

## 4. Nhóm mùi mã về độ dài và cấu trúc

### 4.1. Phương thức dài (*Long Method*)

Một phương thức dài có thể buộc người đọc giữ nhiều điều kiện và biến cục bộ trong đầu, đặc biệt khi xen kẽ nhiều trách nhiệm.

Dấu hiệu cần tìm sâu hơn:

- Phương thức vừa xác thực dữ liệu, tính giá, truy cập database và gửi email.
- Các biến tồn tại từ đầu đến cuối nhưng chỉ được dùng ở vài vị trí xa nhau.
- Thay đổi một quy tắc buộc đọc nhiều nhánh không liên quan.
- Khó viết test cho một trường hợp vì không thể điều khiển các tác dụng phụ còn lại.

**Nhưng không nên kết luận chỉ từ số dòng.** Một thuật toán có các bước gắn kết chặt, với tên rõ ràng và phạm vi trạng thái kiểm soát được, có thể dễ đọc hơn sau khi bị cắt thành nhiều helper trung gian.

### 4.2. Lớp quá lớn hoặc gánh nhiều trách nhiệm (*Large Class / God Class*)

Một class có nhiều field, nhiều phương thức và nhiều lý do thay đổi là tín hiệu đáng xem xét. Ví dụ `OrderManager` vừa tính khuyến mại, quản lý kho, thanh toán, gửi email và xuất báo cáo.

Các câu hỏi quan trọng:

- Những phần này có **thay đổi vì cùng một lý do** không?
- Có trường dữ liệu nào chỉ phục vụ một nhóm phương thức?
- Các nhóm chức năng có test và phụ thuộc riêng không?
- Có thể đặt tên rõ trách nhiệm để tách mà không tạo tầng liên kết phức tạp hơn không?

Một class nhiều dòng chỉ chứa các phương thức cùng phục vụ một thuật toán hoặc dữ liệu cấu hình có cấu trúc không tự là “God Class”.

### 4.3. Lồng nhau sâu (*Deep Nesting*)

~~~java
if (customer != null) {
    if (customer.active()) {
        if (order.paid()) {
            if (!order.cancelled()) {
                releaseOrder(order);
            }
        }
    }
}
~~~

Người đọc cần nhớ nhiều điều kiện để biết khi nào `releaseOrder` xảy ra. Có thể cân nhắc guard clauses hoặc đặt tên cho điều kiện nghiệp vụ. Tuy nhiên, nếu thay đổi thứ tự kiểm tra ảnh hưởng ngoại lệ hoặc tác dụng phụ, **làm phẳng mã không được đồng nghĩa đổi hành vi một cách vô ý**.

### 4.4. Truyền quá nhiều tham số (*Long Parameter List*)

~~~java
void createInvoice(
        String customerId,
        String address,
        String currency,
        long subtotal,
        long tax,
        long discount,
        String paymentMethod,
        String campaignCode) {
    // ...
}
~~~

Một danh sách dài có thể báo hiệu nhiều dữ liệu luôn đi cùng nhau hoặc quá nhiều trách nhiệm. Nhưng tạo một object `EverythingContext` chứa mọi biến không liên quan chỉ để rút ngắn chữ ký **không tự làm thiết kế tốt hơn**.

Cần hỏi dữ liệu có thuộc một **khái niệm nghiệp vụ** thật như `InvoiceAmount` hay `BillingAddress` không, và hợp đồng có dễ hiểu hơn sau khi nhóm lại không.

## 5. Nhóm mùi mã về trùng lặp và quan hệ giữa thành phần

### 5.1. Mã lặp (*Duplicated Code*)

Hai đoạn mã chứa cùng điều kiện có thể tạo rủi ro cập nhật không đồng bộ. Nhưng **giống nhau về cú pháp chưa chắc giống nhau về trách nhiệm**.

- Nếu hai đoạn thực hiện **cùng một quy tắc** do cùng nơi sở hữu, việc có hai bản sao là tín hiệu mạnh để xem lại.
- Nếu chúng thuộc **hai nghiệp vụ có lý do thay đổi độc lập**, gộp vào một helper dùng chung có thể khiến chúng bị buộc thay đổi cùng nhau một cách sai lầm.
- Nếu là vài dòng hiển nhiên, chi phí thêm abstraction và coupling có thể vượt lợi ích loại lặp.

Trước khi áp dụng nguyên tắc *Don't Repeat Yourself* (DRY), cần xác định thứ đang trùng là **tri thức/quy tắc thật sự**, không chỉ là hình dạng câu lệnh.

### 5.2. *Shotgun Surgery*: một thay đổi nhỏ phải chạm nhiều nơi

Giả sử ngưỡng vận chuyển đổi từ 500.000 thành 550.000 và lập trình viên phải sửa ở controller, service, exporter, thông báo email và một job định kỳ.

Đây có thể là mùi mã mạnh hơn việc “trông thấy ba số 500.000”, vì **lịch sử thay đổi cho thấy chi phí và nguy cơ bỏ sót thực tế**.

Hãy xác định nơi nào là nguồn sự thật của chính sách. Có thể cần một service/chính sách chung, hoặc một dữ liệu cấu hình được các thành phần truy cập bằng hợp đồng rõ ràng. Không nên chuyển vội mọi thứ vào một thư viện chia sẻ nếu các service thực sự cần chính sách phiên bản độc lập.

### 5.3. *Divergent Change*: một lớp thay đổi vì nhiều lý do không liên quan

Trái với shotgun surgery, ở đây một lớp bị sửa thường xuyên bởi các yêu cầu **khác nhau**: đổi cấu trúc báo cáo, đổi phí vận chuyển, thêm phương thức thanh toán.

Lớp có thể đang trộn nhiều trách nhiệm. Cần xem lịch sử PR và các phần mã thường bị sửa độc lập; chỉ số số phương thức không đủ chỉ ra ranh giới nên tách.

### 5.4. *Feature Envy*: logic quan tâm quá nhiều dữ liệu của đối tượng khác

~~~java
boolean canShip(Order order) {
    return order.paid()
            && !order.cancelled()
            && order.address().validated();
}
~~~

Nếu quy tắc này là **bất biến nội tại của đơn hàng**, có thể phù hợp để đặt gần mô hình `Order` hoặc một chính sách dành cho đơn hàng. Nếu đây là quy tắc phối hợp giữa đơn hàng và hệ thống vận chuyển, để ở service điều phối lại có thể đúng.

Chỉ nhìn thấy nhiều lần `order.xxx()` không đủ kết luận phải chuyển phương thức vào `Order`. Cần xem **ai sở hữu ý nghĩa của quyết định**.

## 6. Nhóm mùi mã về dữ liệu và trạng thái

### 6.1. *Primitive Obsession*: dùng giá trị nguyên thủy khi cần một khái niệm

~~~java
void transfer(String from, String to, long amount) {
    // amount tính bằng đồng, xu hay đơn vị nhỏ nhất?
}
~~~

Ba tham số nguyên thủy không sai tự thân. Nhưng nếu `amount` cần đơn vị, miền hợp lệ, quy tắc làm tròn và bất biến xuyên nhiều lớp, một kiểu dữ liệu có ý nghĩa có thể giúp giảm nhầm lẫn:

~~~java
record MoneyCents(long value) {
    MoneyCents {
        if (value < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }
}
~~~

Kiểu `MoneyCents` giúp nêu đơn vị và một tiền điều kiện. Nó **chưa phải một mô hình tiền tệ đầy đủ**: không chứa loại tiền, chính sách chuyển đổi, thuế hoặc độ chính xác đa tiền tệ. Nếu nghiệp vụ thật cần những thuộc tính đó, hợp đồng phải được thiết kế tương ứng.

Với một phép tính cục bộ rất nhỏ, tạo kiểu mới có thể chưa đáng. Mùi mã trở nên đáng xử lý khi nhầm đơn vị hoặc kiểm tra lặp xuất hiện thường xuyên.

### 6.2. Dữ liệu luôn đi thành cụm (*Data Clumps*)

Ví dụ ba giá trị `street`, `district`, `postalCode` luôn được truyền cùng nhau qua nhiều phương thức. Chúng có thể đại diện cho một `ShippingAddress` có bất biến rõ ràng.

Nhưng nhóm các tham số chỉ vì “chúng xuất hiện trên cùng dòng” có thể tạo một object tiện ích không có ý nghĩa, làm việc sửa khó hơn.

### 6.3. Trạng thái dùng chung khó kiểm soát

~~~java
final class CheckoutService {
    private String lastCoupon;

    boolean eligible(String couponCode) {
        lastCoupon = couponCode;
        return "SAVE10".equals(lastCoupon);
    }
}
~~~

Nếu `CheckoutService` được dùng bởi nhiều request, field `lastCoupon` không cần thiết và có thể bị ghi đè khi các lời gọi chạy đồng thời. Dấu hiệu cần điều tra là **một phép kiểm tra chỉ cần tham số nhưng lại lưu thông tin request vào object sống lâu**.

Một phiên bản không có trạng thái ngầm dễ suy luận hơn:

~~~java
static boolean eligible(String couponCode) {
    return "SAVE10".equals(couponCode);
}
~~~

Trong ví dụ này, thay đổi chỉ là tổ chức dữ liệu đầu vào; với cùng `couponCode`, hai phép kiểm tra cho kết quả Boolean như nhau trong thực thi tuần tự. Tuy nhiên, nếu hệ thống đang dựa vào `lastCoupon` cho chức năng khác, việc bỏ field cần xác minh toàn bộ hợp đồng và nơi dùng trước khi sửa.

### 6.4. Biến mutable đi xuyên nhiều giai đoạn

Một object `ProcessingContext` có hàng chục field được cập nhật ở nhiều helper có thể khiến thứ tự gọi trở thành hợp đồng ngầm.

Cần hỏi liệu mỗi giai đoạn có thể nhận dữ liệu rõ ràng rồi trả một kết quả có tên hay không. Nhưng cũng có những quy trình như builder hoặc phiên giao dịch cần trạng thái qua nhiều bước — khi ấy hãy làm rõ **phạm vi và chủ sở hữu**, thay vì cấm trạng thái mutable tuyệt đối.

## 7. Nhóm mùi mã về tên, điều kiện và trừu tượng hóa

### 7.1. Tên mơ hồ và *Magic Numbers*

~~~java
int x = 500_000;

if (total >= x) {
    fee = 0;
}
~~~

Người đọc không biết đây là ngưỡng nào, đơn vị gì hoặc ai quản lý. Tên như `freeShippingFromCents` và ranh giới chính sách phù hợp thường giúp hiểu hơn.

Tuy nhiên, không phải mọi literal đều cần hằng số. Số `0` trong điều kiện `count == 0` vốn có ý nghĩa hiển nhiên; việc trích xuất thành `ZERO_COUNT` có thể làm mã dài hơn mà không thêm tri thức.

### 7.2. Cờ Boolean điều khiển hai hành vi (*Flag Argument*)

~~~java
void exportReport(Report report, boolean sendEmail) {
    // ...
}
~~~

Nếu `sendEmail` dẫn tới hai quy trình khác nhau với nhiều điều kiện, phương thức có thể đang ôm hai trách nhiệm. Nhưng nếu cờ chỉ quyết định một lựa chọn nhỏ và hợp đồng đã rõ, tạo hai class chiến lược có thể là thiết kế quá mức.

Cần xem mức độ độc lập của các hành vi, cách gọi có dễ đọc và sự mở rộng có thực sự xảy ra không.

### 7.3. Các nhánh điều kiện dài và điều kiện phủ định

~~~java
if (!(!order.paid() || order.cancelled())) {
    dispatch(order);
}
~~~

Biểu thức có thể tương đương với:

~~~java
if (order.paid() && !order.cancelled()) {
    dispatch(order);
}
~~~

Cách sau giúp diễn đạt ý định rõ hơn. Nhưng khi biến đổi điều kiện có lời gọi **có tác dụng phụ**, ngoại lệ hoặc phụ thuộc thứ tự, không nên đổi toán tử và vị trí mệnh đề máy móc. Trong Java, `&&`/`||` đánh giá từ trái sang phải và ngắn mạch.

### 7.4. Trừu tượng hóa suy đoán (*Speculative Generality*)

Một tính năng đơn giản có thể đi qua `Factory`, `Strategy`, `Provider`, `Resolver`, `Registry` và `Adapter` dù hiện chỉ có một hành vi không dự kiến thay đổi. Đây có thể là mùi mã vì **người đọc phải theo quá nhiều tầng để hiểu một quyết định nhỏ**.

Mặt khác, các tầng ấy có thể cần cho một hợp đồng framework, khả năng thay thế dependency, bảo mật hoặc versioning. Nên điều tra trách nhiệm thật của từng tầng trước khi xóa.

### 7.5. Comment nhiều không luôn là xấu

Một đoạn có comment dài giải thích vì sao phải giữ thứ tự ghi dữ liệu để tuân thủ hợp đồng bên ngoài có thể rất quan trọng. Nhưng comment lặp lại từng dòng hoặc luôn phải sửa theo mã có thể chỉ ra tên và cấu trúc chưa rõ, hoặc tri thức đang được đặt sai chỗ.

Câu hỏi không phải “bao nhiêu comment là quá nhiều?” mà là “comment có giữ **nguyên nhân, bất biến và quyết định** mà mã không thể tự diễn đạt không?”.

## 8. Ví dụ Java: nhìn thấy mã lặp rồi xác minh vấn đề thực

Giả sử hai thành phần xử lý cùng một chính sách vận chuyển của cửa hàng:

- Khách `STANDARD` được miễn phí từ 500.000 đơn vị tiền nhỏ nhất.
- Khách `PREMIUM` được miễn phí từ 300.000.
- Đơn dưới ngưỡng chịu phí 30.000.
- Ngưỡng dựa trên tổng tiền hàng **trước chiết khấu**.
- Tổng tiền âm là đầu vào không hợp lệ.

Đây là đặc tả minh họa cho ví dụ, không phải chính sách của hệ thống cụ thể.

### 8.1. Quan sát: quy tắc xuất hiện ở hai nơi

~~~java
enum CustomerTier { STANDARD, PREMIUM }

final class CheckoutFee {
    static long calculate(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        java.util.Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? 300_000 : 500_000;
        return subtotalCents >= threshold ? 0 : 30_000;
    }
}

final class ReportFee {
    static long calculate(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        java.util.Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? 300_000 : 500_000;
        return subtotalCents >= threshold ? 0 : 30_000;
    }
}
~~~

**Quan sát chắc chắn:** có hai bản công thức giống nhau. Nhưng điều đó chưa đủ để kết luận phải gộp.

### 8.2. Điều tra: hai quy tắc có cùng chủ sở hữu không?

Hãy hỏi:

1. Checkout và báo cáo có phải hiển thị **cùng phí vận chuyển thực tế** không?
2. Khi chính sách thay đổi, **cả hai nơi có phải cùng đổi** không?
3. Lịch sử có từng xảy ra báo cáo dùng ngưỡng cũ còn checkout dùng ngưỡng mới không?
4. Báo cáo có yêu cầu giữ **ảnh chụp lịch sử** của phí tại thời điểm tạo đơn không?
5. Có nhiều phiên bản chính sách hiệu lực cùng lúc không?

Điểm thứ tư đặc biệt quan trọng: một báo cáo lịch sử có thể cần **số phí đã chốt trong đơn**, không phải tính lại theo chính sách hiện tại. Nếu vậy, cách sửa đúng có thể là đọc khoản phí đã được lưu, **không phải ép cả hai nơi gọi một công thức mới nhất**.

Ở đây, giả định sau điều tra là **cả hai nơi đều cần phí dự tính hiện hành và phải dùng cùng một chính sách**. Khi ấy, mùi mã lặp đại diện cho một chi phí đồng bộ có thật.

### 8.3. Refactor: tập trung chính sách ở một ranh giới có ý nghĩa

Ví dụ Java 17+:

~~~java
import java.util.Objects;

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

    long feeFor(long subtotalCents, CustomerTier tier) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        Objects.requireNonNull(tier, "tier");

        long threshold = tier == CustomerTier.PREMIUM
                ? premiumFreeFromCents
                : standardFreeFromCents;
        return subtotalCents >= threshold ? 0 : flatFeeCents;
    }
}
~~~

Trong các thành phần cần **phí dự tính hiện hành**, có thể dùng cùng một chính sách có cấu hình rõ:

~~~java
ShippingPolicy currentPolicy =
        new ShippingPolicy(500_000, 300_000, 30_000);

long checkoutFee =
        currentPolicy.feeFor(400_000, CustomerTier.STANDARD); // 30_000

long reportEstimate =
        currentPolicy.feeFor(400_000, CustomerTier.PREMIUM);  // 0
~~~

Ví dụ này dùng một nguồn tính phí để minh họa, không thiết kế vòng đời cấu hình hay cách chia sẻ instance giữa nhiều service. Nếu triển khai phân tán, cần quyết định nguồn chính sách, phiên bản hiệu lực, cơ chế cập nhật và tính nhất quán. **Không tự động biến một record dùng chung trong cùng tiến trình thành thư viện phụ thuộc chặt giữa nhiều hệ thống.**

### 8.4. Điều thực sự được cải thiện

Sau refactor, thay đổi một ngưỡng trong chính sách không phải tìm và sửa lại hai công thức giống nhau. Tên `ShippingPolicy` thể hiện ranh giới nghiệp vụ. Nếu muốn thêm một quy tắc mới, người đọc biết nơi tập trung quyết định phí.

Nhưng refactor cũng tạo một **phụ thuộc chung**. Nếu hai nghiệp vụ thực sự cần thay đổi độc lập, việc gộp có thể làm thiết kế tệ hơn. Cải thiện chỉ có cơ sở khi giả định **cùng một tri thức cần được đồng bộ** là đúng.

## 9. Kiểm thử để bảo vệ hành vi trước và sau refactor

Một thay đổi cấu trúc chỉ nên được gọi là **refactor giữ hành vi** khi kết quả quan sát được vẫn phù hợp hợp đồng ban đầu. Với `ShippingPolicy`, các giá trị biên là bằng chứng quan trọng.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    private final ShippingPolicy policy =
            new ShippingPolicy(500_000, 300_000, 30_000);

    @Test
    void standardBelowThresholdPaysFlatFee() {
        assertEquals(30_000,
                policy.feeFor(499_999, CustomerTier.STANDARD));
    }

    @Test
    void standardAtThresholdGetsFreeShipping() {
        assertEquals(0,
                policy.feeFor(500_000, CustomerTier.STANDARD));
    }

    @Test
    void premiumBelowThresholdPaysFlatFee() {
        assertEquals(30_000,
                policy.feeFor(299_999, CustomerTier.PREMIUM));
    }

    @Test
    void premiumAtThresholdGetsFreeShipping() {
        assertEquals(0,
                policy.feeFor(300_000, CustomerTier.PREMIUM));
    }

    @Test
    void sameSubtotalMayHaveDifferentFeesByTier() {
        assertEquals(30_000,
                policy.feeFor(400_000, CustomerTier.STANDARD));
        assertEquals(0,
                policy.feeFor(400_000, CustomerTier.PREMIUM));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.feeFor(-1, CustomerTier.STANDARD));
    }

    @Test
    void rejectsMissingTier() {
        assertThrows(NullPointerException.class,
                () -> policy.feeFor(100_000, null));
    }
}
~~~

Những test này kiểm tra **hành vi quan sát được** chứ không kiểm tra phương thức private nào được gọi. Chúng giúp phát hiện lỗi ở ngưỡng và ràng buộc dữ liệu, nhưng không tự chứng minh tính đúng đắn của cấu hình production hoặc dữ liệu báo cáo lịch sử.

Nếu hai triển khai cũ có **hành vi khác nhau ngoài ý muốn**, việc chọn phiên bản chung cần được xem như một quyết định sửa lỗi có xác nhận đặc tả, thay vì mặc định hai bên luôn tương đương.

### 9.1. Bảo vệ những điểm refactor dễ làm thay đổi hành vi

- **Thứ tự kiểm tra:** kiểm tra `null` trước khi gọi phương thức trên object.
- **Ngoại lệ:** giữ loại/điều kiện lỗi theo hợp đồng đang có.
- **Giá trị biên:** phân biệt `>=` với `>`, số âm và giá trị rất lớn.
- **Số học:** giữ đơn vị, làm tròn và cách xử lý tràn số nếu chúng thuộc hợp đồng.
- **Tác dụng phụ:** không vô tình thay đổi số lần gửi event, cập nhật DB hoặc retry.
- **Thứ tự và đồng thời:** không làm mất tính nguyên tử hay thay đổi thứ tự nghiệp vụ bắt buộc.

Mục tiêu của bài là học cách **xử lý tín hiệu mùi mã**; ví dụ dùng JUnit 5 để minh họa kiểm chứng, chưa chạy test thực tế và không bao quát các phần tích hợp bên ngoài.

## 10. Khi refactor theo mùi mã lại gây hại

### 10.1. Gộp hai đoạn giống nhau nhưng sẽ thay đổi khác nhau

Hai màn hình hiển thị hóa đơn có cùng đoạn format ngày. Một màn dùng lịch nghiệp vụ theo địa phương, màn kia dùng UTC theo hợp đồng audit. Hôm nay định dạng nhìn giống nhau, nhưng gộp cả hai vào một helper không có tham số ngữ cảnh có thể khiến lần đổi múi giờ sau làm một bên sai.

**Bài học:** trùng lặp cú pháp không nhất thiết là trùng lặp tri thức.

### 10.2. Tách phương thức chỉ để giảm số dòng

~~~java
int calculateFee(long subtotal) {
    validateStep(subtotal);
    return chooseStep(subtotal);
}
~~~

Nếu `validateStep` và `chooseStep` không cho biết ý định, người đọc phải mở nhiều nơi để hiểu một điều kiện ngắn. Điểm complexity của hàm gọi có thể giảm nhưng **chi phí điều hướng** tăng.

Nên hỏi mỗi phương thức mới có trách nhiệm riêng, tên rõ và hợp đồng đủ hữu ích không.

### 10.3. Đưa logic vào class khác chỉ vì “Feature Envy”

Việc một service đọc nhiều thuộc tính của `Order` không luôn có nghĩa `Order` phải chứa cả logic gọi repository, phát sự kiện và thanh toán. Đẩy các phụ thuộc hạ tầng vào entity có thể làm ranh giới trách nhiệm xấu hơn.

### 10.4. Xóa “mã chết” mà chưa kiểm tra điểm sử dụng động

Một phương thức không có lời gọi trực tiếp trong tìm kiếm code có thể được dùng qua reflection, serialization, plugin, cấu hình, script hoặc client bên ngoài. Công cụ static analysis đưa ra tín hiệu đáng điều tra, không chứng minh tuyệt đối mã không còn được sử dụng.

Cần xem các hợp đồng runtime và khả năng quan sát trước khi xóa, đặc biệt với API công khai.

### 10.5. Thêm tầng trừu tượng để “dễ mở rộng” khi chưa có nhu cầu

Một phép kiểm tra Boolean đơn giản có thể không cần interface, factory, registry và dependency injection. Nếu có thật nhiều chính sách thay đổi độc lập, abstraction có thể đáng giá; nếu không, nó tạo thêm nơi phải tìm và sửa.

## 11. Đánh giá bằng bối cảnh thay đổi và quyền sở hữu

Một mùi mã nghiêm trọng hay nhẹ thường phụ thuộc vào **chiều thay đổi** của hệ thống.

| Bối cảnh | Điều cần xem xét | Phản ứng có thể phù hợp |
| --- | --- | --- |
| Mã ít thay đổi, trách nhiệm rõ, test ổn | Cảnh báo chủ yếu về hình thức? | Ghi nhận và có thể để nguyên. |
| Một quy tắc đổi thường xuyên ở nhiều nơi | Có lỗi do cập nhật thiếu hoặc PR chạm nhiều file? | Tập trung quy tắc hay nguồn dữ liệu khi phù hợp. |
| Nhiều người cùng sửa một class lớn | Có merge conflict, chồng trách nhiệm, khó review? | Xem lại ranh giới module và ownership. |
| Logic tính tiền, quyền truy cập hoặc trạng thái quan trọng | Hậu quả khi sai là gì, có test biên và test lỗi? | Ưu tiên bảo vệ hành vi, sửa bug/lỗ hổng trước; refactor có kiểm soát. |
| Hệ thống chuẩn bị ngừng sử dụng | Chi phí refactor có hoàn vốn trong thời gian còn lại không? | Tập trung sửa rủi ro thực, tránh mở dự án cấu trúc lớn nếu không cần. |
| Chuyển đổi API đang diễn ra | Có hai phiên bản cần cùng tồn tại hợp lệ không? | Ghi rõ vòng đời tương thích; không ép gộp quá sớm. |

**Một mùi mã có thể trở nên đáng xử lý khi hoàn cảnh đổi**, dù code không đổi. Chẳng hạn, hàm 80 dòng do một người duy nhất bảo trì có thể đủ rõ với người đó; khi nhiều nhóm cùng sửa, thiếu ranh giới trách nhiệm mới bộc lộ chi phí.

Nhưng cũng không nên dựa vào việc “người viết hiểu nó” làm bằng chứng mã tốt: cần kiểm tra khả năng người khác hiểu và sửa an toàn.

## 12. Dùng chỉ số và công cụ tự động như tín hiệu

Static analyzer, IDE hoặc dashboard có thể báo những điều như:

- Phương thức vượt ngưỡng số dòng.
- Cyclomatic/cognitive complexity cao.
- Mã trùng lặp theo token hoặc cấu trúc.
- Danh sách tham số dài.
- Class nhiều phụ thuộc hoặc field.
- Cảnh báo về trạng thái mutable, mã chưa sử dụng hay quy tắc đặt tên.

Chúng giúp **lọc những vùng có khả năng cần review**, nhất là trong codebase lớn.

### 12.1. Các chỉ số không đồng nghĩa đánh giá cuối cùng

| Tín hiệu công cụ | Nó thực sự hỗ trợ | Nó không tự chứng minh |
| --- | --- | --- |
| LOC cao | Phạm vi đáng đọc kỹ. | Mã khó hiểu hoặc sai. |
| Cyclomatic complexity cao | Nhiều đường đi/nhánh đáng kiểm tra. | Tất cả nhánh đều gây lỗi hoặc cần tách class. |
| Cognitive complexity cao | Có cấu trúc luồng điều khiển khó theo dõi theo mô hình công cụ. | Mọi người đọc đều gặp đúng mức khó đó. |
| Duplicate code cao | Có đoạn giống nhau đáng kiểm tra nguồn tri thức. | Các đoạn phải có một chủ sở hữu chung. |
| Số dependency nhiều | Có quan hệ giữa nhiều thành phần. | Mọi dependency đều không cần thiết. |
| Cảnh báo method chưa được dùng | Không tìm được điểm dùng theo phạm vi phân tích. | Không có lời gọi động hoặc client ngoài. |

### 12.2. False positive và false negative

- **False positive:** công cụ báo mùi mã nhưng trong bối cảnh thật đó là thiết kế hợp lý. Ví dụ một bảng quyết định tường minh dài nhưng cần để kiểm toán từng trường hợp.
- **False negative:** công cụ không báo nhưng mã rất khó sửa. Ví dụ ba phương thức ngắn phụ thuộc một trạng thái toàn cục, cùng làm sai dữ liệu giữa request.

Ngưỡng từ công cụ có thể hỗ trợ review nhất quán, nhưng đừng coi việc “đạt điểm” là mục tiêu kỹ thuật tối cao.

### 12.3. Dùng lịch sử thay đổi để bổ sung góc nhìn

Một phương thức dài nhưng năm năm không sửa có thể ít rủi ro hơn một quy tắc 10 dòng bị sao chép sáu nơi và mỗi tuần đều đổi. Khi có quyền truy cập phù hợp, có thể xem tần suất sửa, lỗi hồi quy, số nơi liên quan và sự cố sau khi thay đổi.

Lịch sử cũng cần được diễn giải: file đổi thường xuyên có thể đơn giản vì nó phục vụ tính năng đang phát triển mạnh, không tự chứng minh thiết kế sai.

## 13. Ưu tiên mùi mã theo rủi ro và giá trị cải thiện

Một danh sách có 200 cảnh báo không có nghĩa phải tạo 200 PR refactor. Nên ưu tiên theo một số yếu tố:

1. **Tác động nếu lỗi xảy ra:** tiền, dữ liệu, quyền truy cập, tính liên tục vận hành.
2. **Tần suất sửa:** mã có thường thay đổi theo yêu cầu thực không?
3. **Chi phí hiện tại:** review lâu, test khó, nhiều nơi phải sửa, thường xuất hiện bug do bỏ sót.
4. **Độ tin cậy của giả thuyết:** có bằng chứng hay chỉ là cảm giác khó chịu?
5. **Phạm vi refactor:** có thể tách một bước nhỏ, dễ rollback hay sẽ đụng toàn kiến trúc?
6. **Bằng chứng bảo vệ hành vi:** test/contract có đủ mạnh để thay đổi an toàn không?
7. **Thời điểm:** nhóm đang triển khai tính năng nào, có rủi ro trộn refactor với thay đổi nghiệp vụ không?

### 13.1. Bảng ưu tiên minh họa

| Dấu hiệu | Bối cảnh | Ưu tiên có thể hợp lý |
| --- | --- | --- |
| Hai bản logic tính phí thường xuyên lệch ngưỡng | Từng gây sai tiền và còn nhiều thay đổi dự kiến. | Cao: sửa sai lệch, thêm test, xác định nguồn chính sách. |
| Helper private dài 60 dòng nhưng chức năng rõ | Ít thay đổi, test hành vi đủ tốt. | Thấp: chỉ refactor khi có lợi ích rõ. |
| Field `static` chứa customer ID của request | Service dùng chung, có nguy cơ trộn dữ liệu người dùng. | Rất cao: đánh giá và xử lý rủi ro bảo mật/đồng thời. |
| Năm dòng format ngày lặp trong hai domain | Hai domain có quy tắc múi giờ khác nhau. | Có thể giữ tách biệt; viết rõ lý do. |
| Một class lớn thường gây merge conflict | Nhiều nhóm độc lập cùng sửa. | Trung bình–cao: điều tra ranh giới và ownership. |

Thứ tự không phải luật cố định. **Giả định và ràng buộc hệ thống thực** quyết định ưu tiên.

## 14. Quy trình điều tra mùi mã trong code review

### Bước 1 — Ghi nhận quan sát không phán xét

Ví dụ: “Điều kiện xác định phí vận chuyển xuất hiện trong ba class với cùng ngưỡng.”

Tránh kết luận ngay “thiết kế tệ” hoặc quy trách nhiệm cho người viết.

### Bước 2 — Nói rõ hệ quả đang lo

“Ngưỡng thường đổi theo chính sách; nếu ba class không được sửa cùng lúc, người dùng và báo cáo có thể thấy phí khác nhau.”

Nhờ đó, người đọc hiểu **vì sao quan sát đáng quan tâm**.

### Bước 3 — Tìm bằng chứng

- Ba class có thật sự mô tả một chính sách không?
- Lịch sử PR có thường phải sửa cùng nhau không?
- Có lỗi do bỏ sót một bản sao không?
- Có test/đặc tả cho tình huống biên không?
- Có báo cáo lịch sử bắt buộc dùng giá trị tại thời điểm giao dịch không?

Một giả thuyết bị bác bỏ là kết quả điều tra hữu ích: không cần refactor sai chỗ.

### Bước 4 — Xác định chi phí và phạm vi thay đổi

Cần biết trích xuất chính sách chung sẽ làm ai phụ thuộc vào ai. Nếu chỉ có thể giảm trùng lặp bằng cách đưa thêm một thư viện xuyên ba service độc lập, phải xem versioning và coupling.

### Bước 5 — Chọn hành động nhỏ nhất có ích

Có thể là:

- Thêm test hồi quy và giữ nguyên cấu trúc.
- Đổi tên một điều kiện để rõ ý định.
- Thu hẹp biến mutable hoặc truyền tham số tường minh.
- Trích xuất một quy tắc theo trách nhiệm.
- Tách class ở một ranh giới thay đổi độc lập.
- Ghi lý do chấp nhận mùi mã và hoãn refactor.

### Bước 6 — Kiểm tra lại kết quả

Khi sửa cấu trúc, cần xác nhận hành vi không đổi; sau đó đánh giá người bảo trì có dễ tìm và sửa quy tắc hơn không. Nếu thay đổi vẫn buộc mở nhiều file/helper hoặc gây thêm lỗi, “mùi mã biến mất” trên dashboard chưa đủ chứng minh cải thiện.

## 15. Viết phản hồi review dựa trên bằng chứng

### 15.1. Nhận xét chưa hữu ích

> “Hàm dài quá. Tách cho đẹp. Static analyzer báo đỏ thì phải sửa.”

Nhận xét này thiếu hành vi rủi ro, thiếu đề xuất ranh giới, và có thể khiến người viết tạo các helper không thêm ý nghĩa.

### 15.2. Nhận xét có thể hành động

> “Trong `checkout`, phần xác thực input, tính phí và gửi email đang cùng nằm trong một phương thức. Đợt thay đổi chính sách vận chuyển trước chỉ cần sửa phần phí nhưng buộc review cả đường gửi email. Có thể tách phép tính phí thành một thành phần nhận subtotal và hạng khách hàng, trả phí và không có tác dụng phụ không? Chúng ta nên giữ test ở ngưỡng 300.000/500.000 và xác nhận đường lỗi không gửi email trước khi checkout hợp lệ.”

Nhận xét này có **quan sát, rủi ro, hướng cải thiện và bằng chứng cần bảo vệ**. Nó để chỗ cho thảo luận nếu tác giả có bối cảnh khác.

### 15.3. Khi không refactor cũng cần giải thích

Một nhóm có thể quyết định:

> “Bảng ánh xạ trạng thái này có 80 dòng nhưng từng trường hợp phải được nhìn thấy và đối chiếu trong review kiểm toán. Việc tách thành nhiều helper sẽ che sự đầy đủ của bảng. Chúng ta giữ cấu trúc hiện tại, thêm test cho những trạng thái còn thiếu và ghi rõ lý do.”

Đó là quyết định có căn cứ, không phải “bỏ qua chất lượng”. Điều quan trọng là **giữ được lý do và điều kiện áp dụng**, không biến ngoại lệ thành giấy phép cho mọi mã khó hiểu.

## 16. Refactor, sửa bug và thêm tính năng: nên phân biệt mục đích

Khi gặp một mùi mã trong lúc làm tính năng mới, người phát triển có thể đồng thời muốn:

1. Đổi cấu trúc để dễ hiểu.
2. Sửa một bug được phát hiện.
3. Thay đổi chính sách theo yêu cầu mới.

Ba mục tiêu này có mức rủi ro và tiêu chí kiểm tra khác nhau.

**Refactor** nhằm cải thiện cấu trúc mà giữ hành vi quan sát được theo hợp đồng hiện tại. **Bug fix** chủ động thay hành vi sai thành đúng. **Feature change** thêm hoặc đổi hành vi dựa trên yêu cầu mới.

Nếu trộn tất cả trong một diff lớn, reviewer khó biết chỗ nào thay đổi có chủ đích và chỗ nào là sai lệch ngoài ý muốn.

### 16.1. Một chiến lược an toàn

1. Viết test mô tả hành vi hiện tại và đặc tả đúng; xác định rõ chỗ đang sai.
2. Nếu cần, tạo một bước refactor nhỏ **giữ hành vi** để làm cấu trúc dễ sửa hơn.
3. Thực hiện bug fix/feature change riêng ở mức thay đổi có chủ đích, kèm test thể hiện kỳ vọng mới.
4. Với thay đổi tác động giao diện hoặc vận hành, cập nhật hợp đồng và tài liệu liên quan.
5. Review mỗi bước bằng câu hỏi phù hợp: cấu trúc có rõ hơn không, hành vi nào đổi, có test xác minh không?

Không phải dự án nào cũng cần nhiều PR; có thể tách commit logic và mô tả rõ trong một PR. Mục tiêu là **phân biệt thay đổi cấu trúc với thay đổi hành vi**, không tạo thêm thủ tục hình thức.

### 16.2. Đừng “sửa luôn” các thay đổi không liên quan

Một lập trình viên nhìn thấy tên biến xấu trong module thanh toán rồi quyết định đổi cả flow xác thực và xử lý retry trong PR sửa báo cáo. Dù một số thay đổi có thể có ích, phạm vi rộng khiến review và rollback khó hơn.

Ưu tiên **điều tra và đưa vấn đề vào đúng lần thay đổi**, trừ khi rủi ro nghiêm trọng cần xử lý ngay.

## 17. Khi nào dấu hiệu cần được xử lý ngay?

Không nên dùng câu “chỉ là mùi mã” để hạ mức độ ưu tiên của **lỗi đã được chứng minh** hoặc tình huống có nguy cơ lớn.

Ví dụ:

- Dữ liệu request của người dùng A được giữ trong singleton và có thể bị trả cho người dùng B.
- Hai giao dịch đồng thời có thể vượt hạn mức tồn kho vì kiểm tra và cập nhật không nguyên tử.
- Mã xây SQL từ đầu vào không tin cậy theo cách tạo nguy cơ injection.
- Hệ thống bỏ qua kiểm tra quyền khi tham số đặc biệt được truyền vào.
- Một phép tính tiền tràn số và cho ra giá trị âm khi dữ liệu hợp lệ lớn.

Khi thấy những tình huống ấy, cần **điều tra và xử lý như lỗi về tính đúng đắn, bảo mật hoặc tính nhất quán** theo mức độ tác động. Refactor có thể nằm trong cách sửa, nhưng tên gọi “code smell” không thay thế phân tích rủi ro.

Ở chiều ngược lại, một dấu hiệu về tên chưa rõ hoặc class dài nhưng ổn định, không có bằng chứng gây cản trở thay đổi, có thể được theo dõi mà chưa cần ưu tiên hơn công việc có rủi ro thực.

## 18. Bài tập tình huống

### Tình huống A: hai đoạn mã giống nhau

Checkout và hệ thống in hóa đơn cùng có điều kiện phí vận chuyển giống nhau. Sau điều tra, hệ thống in hóa đơn phải thể hiện **phí đã áp dụng khi tạo đơn**, còn checkout phải tính **phí hiện tại**.

**Câu hỏi:** nên gộp hai đoạn thành một phương thức chung để loại bỏ mã lặp không?

**Gợi ý:** chưa chắc. Hai nghiệp vụ có cách xử lý thời gian và dữ liệu khác nhau. Hóa đơn lịch sử có thể nên đọc giá trị đã chốt, trong khi checkout dùng chính sách mới. Hãy xác định nguồn sự thật cho mỗi hành vi trước khi refactor.

### Tình huống B: phương thức 150 dòng

Một hàm duyệt dữ liệu có 150 dòng, một vòng lặp tuyến tính, hai biến tạm và những bước tính toán gắn chặt. Công cụ báo `Long Method`.

**Câu hỏi:** cần bằng chứng gì trước khi chia hàm?

**Gợi ý:** người đọc có hiểu luồng không, có nhiều trách nhiệm/lý do thay đổi không, các biến có phạm vi quá rộng không, test có khó viết không? Nếu trích xuất làm tăng số tham số và điều hướng mà không tạo khái niệm riêng, có thể giữ nguyên.

### Tình huống C: lớp 20 phương thức, sáu lý do thay đổi

Lớp `CustomerService` vừa tính hạng khách hàng, xuất CSV, gửi email, kiểm tra chính sách truy cập và quản lý địa chỉ. Lịch sử cho thấy các thay đổi độc lập thường gây merge conflict.

**Câu hỏi:** đây là bằng chứng gì, và nên tách theo tiêu chí nào?

**Gợi ý:** có dấu hiệu nhiều trách nhiệm và chi phí thay đổi thật. Xác định các nhóm phương thức dùng dữ liệu/phụ thuộc nào, lý do thay đổi và ownership; tách theo trách nhiệm với hợp đồng rõ thay vì chia đều mỗi class năm phương thức.

### Tình huống D: “mã chết” và reflection

Static analyzer báo không có lời gọi trực tiếp tới một phương thức. Nhưng ứng dụng tải handler từ cấu hình tên class và gọi qua reflection.

**Câu hỏi:** có thể xóa phương thức chỉ dựa vào cảnh báo không?

**Gợi ý:** không. Cần kiểm tra hợp đồng động, cấu hình và test tích hợp. Static analysis có thể không nhìn thấy mọi đường sử dụng runtime.

### Tình huống E: flag argument

Một phương thức `sendNotification(message, urgent)` có hai nhánh: bình thường đưa vào queue, khẩn cấp gửi qua kênh riêng và retry. Nhánh khẩn cấp có lỗi và cấu hình độc lập.

**Câu hỏi:** khi nào nên tách hai hành vi, và làm gì trước?

**Gợi ý:** xác định hợp đồng, tác dụng phụ, lý do thay đổi, kiểm thử đường lỗi/retry. Nếu hai quy trình thực sự độc lập, tách trách nhiệm có thể giúp kiểm soát; nếu chỉ đổi một thuộc tính nhỏ, dùng flag có tên rõ có thể đủ.

## 19. Checklist khi phát hiện và xử lý mùi mã

- [ ] Tôi mô tả được **dấu hiệu quan sát được** mà không lập tức gọi đó là bug.
- [ ] Tôi biết hợp đồng nghiệp vụ hiện tại để phân biệt lỗi thực với rủi ro cấu trúc.
- [ ] Tôi có giả thuyết về **chi phí hiểu, sửa, test hoặc tích hợp** mà mùi mã có thể gây ra.
- [ ] Tôi đã kiểm tra ngữ cảnh: tần suất thay đổi, độ rủi ro, quyền sở hữu và hướng phát triển.
- [ ] Với mã trùng, tôi phân biệt **tri thức giống nhau** với **đoạn cú pháp tình cờ giống nhau**.
- [ ] Với phương thức/class dài, tôi xem trách nhiệm và trạng thái, không chỉ số dòng.
- [ ] Tôi không tự động tạo helper, interface hoặc DTO chỉ để giảm cảnh báo.
- [ ] Tôi biết chỉ số từ công cụ là tín hiệu có thể có false positive/false negative.
- [ ] Tôi cân nhắc lịch sử bug, PR và phản hồi review khi có dữ liệu phù hợp.
- [ ] Tôi ưu tiên lỗi đúng đắn, bảo mật và dữ liệu có rủi ro cao trước thay đổi hình thức.
- [ ] Phương án refactor có tên và ranh giới trách nhiệm thực sự rõ hơn.
- [ ] Test bảo vệ kết quả, ngoại lệ, biên số học, tác dụng phụ và bất biến liên quan.
- [ ] Tôi phân biệt refactor giữ hành vi với thay đổi chính sách hoặc sửa bug.
- [ ] Sau khi sửa, tôi đánh giá **chi phí bảo trì thực tế**, không chỉ số cảnh báo biến mất.
- [ ] Nếu quyết định giữ nguyên, tôi có thể giải thích lý do và điều kiện cần xem lại.

## 20. Kết luận

**Mùi mã là tín hiệu điều tra chứ chưa phải kết luận lỗi.** Một cấu trúc đáng nghi có thể báo hiệu coupling cao, trách nhiệm không rõ, trạng thái ngầm hoặc chi phí sửa đổi lớn. Nhưng chỉ nhìn số dòng, độ lồng nhau, hình dạng câu lệnh hay cảnh báo tĩnh chưa đủ biết hệ thống đang sai ở đâu và cách sửa nào tốt nhất.

Trong **CODE_QUALITY_FUNDAMENTALS**, cách tiếp cận hữu ích là **quan sát → đặt giả thuyết → kiểm tra bối cảnh và bằng chứng → chọn hành động → xác minh kết quả**. Khi phát hiện bug hoặc lỗ hổng, xử lý theo rủi ro thực; khi chỉ có mùi mã, cân nhắc giá trị refactor và khả năng bảo vệ hành vi trước khi thay đổi.

Một mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi** không phải mã không còn cảnh báo nào, mà là mã có những quyết định thiết kế **đủ rõ để giải thích, đủ bằng chứng để tin cậy và đủ linh hoạt để thay đổi an toàn**.

