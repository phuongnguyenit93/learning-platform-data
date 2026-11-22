# Xử lý từng phần và tránh tạo nợ mới trong quá trình sửa

Một hệ thống Java đã hoạt động nhiều năm có thể chứa các phương thức vừa tính tiền, vừa gọi cơ sở dữ liệu, vừa gửi thông báo; nhiều API đã có bên sử dụng; một số quy tắc nghiệp vụ còn thiếu kiểm thử. Đội phát triển biết cần cải tiến nhưng không thể dừng mọi tính năng để viết lại toàn bộ hệ thống. Nếu vội thay tất cả trong một lần, họ có nguy cơ gây lỗi hồi quy lớn. Nếu chỉ sửa tạm để giao tính năng mới, phần mềm lại tích lũy thêm những cấu trúc khó hiểu và khó thay đổi.

Trong chương **Nợ kỹ thuật** của module **CODE_QUALITY_FUNDAMENTALS**, bài học này tập trung vào một chiến lược thực tế: **trả nợ kỹ thuật bằng những thay đổi nhỏ có thể kiểm chứng**, đồng thời **ngăn phát sinh nợ mới** trong chính quá trình sửa. Mục tiêu cuối cùng không phải làm số dòng mã ít đi, mà là giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi** hơn mà vẫn duy trì giá trị của phần mềm đang hoạt động.

> Đừng coi xử lý nợ kỹ thuật là một lần “dọn sạch” rồi kết thúc. Hãy giảm rủi ro theo từng lát cắt, bảo vệ hợp đồng đang sử dụng và giữ chuẩn chất lượng cho phần mã mới.

## 1. Nợ kỹ thuật là gì và khi nào nên trả?

**Nợ kỹ thuật** (*technical debt*) là phép ẩn dụ cho những quyết định kỹ thuật khiến việc phát triển, sửa lỗi hoặc vận hành về sau tốn kém hơn so với một thiết kế phù hợp hơn. Có những khoản nợ được chấp nhận có chủ đích để đạt một mốc thời gian, nhưng cũng có nợ phát sinh do thiếu hiểu biết, thay đổi yêu cầu, phụ thuộc lỗi thời hoặc các giải pháp tạm không được dọn.

Ví dụ:

- Quy tắc tính giá bị sao chép ở nhiều nơi, khiến mỗi lần đổi chính sách phải sửa đồng thời nhiều tệp.
- Một service lưu dữ liệu từng request trong trường mutable, làm kiểm thử và xử lý đồng thời khó hơn.
- API đã có người dùng nhưng không có hợp đồng lỗi, timeout hoặc phiên bản rõ ràng.
- Một truy vấn SQL ghép chuỗi đầu vào thay vì dùng tham số.
- Một bảng DB có hai cột diễn đạt cùng một sự thật và phải cập nhật thủ công để giữ nhất quán.
- Nhiều module thiếu kiểm thử tại những ngưỡng nghiệp vụ dễ sai.
- Công cụ CI có quy tắc chất lượng nhưng bỏ qua module quan trọng.

Không phải mọi phần mã cũ hoặc khác phong cách mới đều là nợ kỹ thuật đáng trả ngay. Một utility ít thay đổi, không gây lỗi và có hợp đồng rõ có thể có **chi phí sửa cao hơn lợi ích**. Cần gắn khoản nợ với **tác động thực tế**.

### 1.1. Tiền gốc, “lãi” và rủi ro

| Khái niệm | Ý nghĩa khi áp dụng vào phần mềm | Ví dụ |
| --- | --- | --- |
| **Khoản nợ** | Quyết định hoặc cấu trúc làm giảm chất lượng | Logic tính phí nằm trong controller và batch |
| **Chi phí trả nợ** | Công cần để cải thiện kèm xác minh và triển khai | Tách quy tắc, thêm test, chuyển người gọi |
| **Chi phí phát sinh theo thời gian** | Công phải lặp lại vì cấu trúc hiện tại | Mỗi thay đổi mức phí phải sửa ở ba nơi |
| **Rủi ro** | Xác suất và hậu quả của lỗi hoặc gián đoạn | Phí sai gây thất thoát hoặc tranh chấp |
| **Giá trị khi trả nợ** | Khả năng giảm chi phí/rủi ro hoặc tăng tốc đổi mới | Thay một chính sách ở một nơi, có test biên |

Khái niệm “lãi” là **ẩn dụ**, không phải tỷ lệ lãi tài chính chính xác có thể tính từ số dòng code. Khi đánh giá ưu tiên, nên dùng số liệu quan sát được: số lỗi, thời gian thay đổi, tần suất sửa vùng mã, số lần rollback, thời gian xác định nguyên nhân hoặc tình trạng cảnh báo tồn đọng.

### 1.2. Trả nợ vì mục tiêu cụ thể, không vì vẻ ngoài

Một thay đổi được ưu tiên khi nó giúp giảm một trở ngại có thật, chẳng hạn:

- Làm một tính năng sắp thêm an toàn hơn.
- Giảm số lần sửa cùng một quy tắc.
- Giảm lỗi được phát hiện trong production.
- Thu hẹp vùng chịu tác động khi có thay đổi.
- Hỗ trợ nâng cấp Java hoặc thư viện đang bị chặn.
- Tạo điểm kiểm thử cho hành vi hiện chưa quan sát được.

**Không có nguyên tắc “càng refactor nhiều càng tốt”.** Trả nợ cũng tiêu tốn ngân sách kỹ thuật và có thể tạo rủi ro mới nếu làm quá rộng.

## 2. Vì sao nên xử lý theo từng phần?

**Xử lý từng phần** (*incremental remediation*) chia một vấn đề lớn thành các thay đổi nhỏ có đầu ra rõ ràng, có thể review, kiểm thử và triển khai riêng. Mỗi bước cần duy trì các bất biến quan trọng của hệ thống và đưa cấu trúc tiến gần mục tiêu hơn.

### 2.1. Thay đổi “big bang” tạo nhiều rủi ro cùng lúc

Giả sử một yêu cầu muốn cải thiện quy trình báo giá:

~~~text
Controller
  -> tính tiền
  -> lấy dữ liệu khách hàng
  -> ghi đơn hàng
  -> gọi thanh toán
  -> gửi thông báo
~~~

Nếu một pull request đồng thời đổi:

1. Tên DTO và schema JSON.
2. Cách tính phí vận chuyển.
3. Định dạng lưu trữ DB.
4. Cơ chế gọi cổng thanh toán.
5. Đường gửi thông báo.
6. Cách xử lý lỗi và retry.

thì khi kiểm thử lỗi, rất khó biết **thay đổi nào làm sai hành vi**. Khả năng rollback cũng giảm vì dữ liệu đã được ghi bằng schema mới, API bên ngoài đã thay đổi và có nhiều bước không dễ hoàn tác.

### 2.2. Một lát cắt tốt có thể kiểm chứng độc lập

Ví dụ trình tự cải tiến nhỏ hơn:

~~~text
Hiện trạng + xác định hợp đồng
       |
       v
Thêm characterization tests
       |
       v
Tách chính sách tính phí thành hàm thuần
       |
       v
Đổi một nhóm người gọi qua adapter
       |
       v
Kiểm tra kết quả, quan sát production
       |
       v
Chuyển nhóm người gọi còn lại
       |
       v
Xóa logic cũ và quy tắc tạm
~~~

Mỗi bước có thể đạt tiêu chí riêng mà không buộc mọi bước sau hoàn tất cùng lúc. Một lát cắt không nhất thiết phải “khép kín” về kiến trúc, nhưng nên để hệ thống trong **trạng thái có thể hiểu và vận hành an toàn**.

### 2.3. Khi nào phải thực hiện thay đổi nguyên tử?

Không nên chia nhỏ tùy tiện những thao tác **phải nhất quán**. Ví dụ, di chuyển một giá trị giữa hai bảng có thể cần transaction hoặc giai đoạn tương thích có chủ đích; tách thành hai commit triển khai mà không có đường đọc tương thích có thể làm hệ thống hỏng.

Nguyên tắc:

- **Chia theo đơn vị triển khai có thể an toàn**.
- **Giữ nguyên tử** ở những chỗ nghiệp vụ hoặc dữ liệu yêu cầu.
- Nếu hai thành phần phải cùng thay, hãy tạo **lớp tương thích** để chia chuyển đổi thành những bước an toàn.
- Không gọi một thay đổi là “nhỏ” chỉ vì diff ngắn; một dòng đổi ý nghĩa API có thể có phạm vi tác động rất lớn.

## 3. Chọn khoản nợ để xử lý theo giá trị và rủi ro

Trước khi refactor, cần biết khoản nợ đang cản trở điều gì. Một **debt register** hoặc danh sách công việc có bằng chứng thường hữu ích hơn một backlog chỉ ghi “clean up code”.

| Vùng mã | Vấn đề quan sát được | Tác động | Ưu tiên hợp lý |
| --- | --- | --- | --- |
| Chính sách giá bị trùng | Mỗi lần thay ngưỡng phải sửa nhiều nơi | Sai tiền nếu bỏ sót | Cao nếu chính sách thay đổi thường xuyên |
| Controller dài | Khó đọc nhưng ổn định, test đủ | Mất thời gian review | Trung bình, cải tiến khi sửa cùng khu vực |
| Lỗi bỏ qua ngắt thread | Tác vụ không dừng, giữ tài nguyên | Ảnh hưởng vận hành | Cao nếu đang gây sự cố |
| Package tên chưa nhất quán | Chủ yếu ảnh hưởng trình bày | Mức độ tác động thấp | Thấp nếu đổi gây diff lớn |
| Dependency có lỗ hổng liên quan môi trường triển khai | Có rủi ro bảo mật thực tế | Hậu quả có thể lớn | Ưu tiên xử lý theo mức độ ảnh hưởng |
| Không có test cho thanh toán retry | Có nguy cơ tác dụng phụ trùng | Hậu quả nghiêm trọng | Cao dù mã hiện ít thay đổi |

### 3.1. Gợi ý đánh giá trước khi nhận việc

Có thể đánh giá theo các câu hỏi:

1. **Mức độ ảnh hưởng:** nếu có lỗi, người dùng và hệ thống chịu hậu quả gì?
2. **Tần suất thay đổi:** khu vực này thường được sửa hay chỉ chạy ổn định?
3. **Rủi ro khi sửa:** có bao nhiêu người gọi, giao thức và trạng thái tồn tại?
4. **Khả năng tạo lát cắt:** có thể bảo vệ bằng test và chuyển dần không?
5. **Giá trị sắp tới:** có tính năng mới nào cần vùng mã này không?
6. **Chi phí duy trì:** mất bao lâu để hiểu, sửa, review và xử lý sự cố?

Nếu nhóm dùng điểm số để sắp xếp backlog, cần nói rõ đó là **ước lượng tương đối**, không nên diễn giải thành phép đo khách quan về độ an toàn hoặc số giờ tiết kiệm chính xác.

### 3.2. Xác định giới hạn thay đổi trước khi viết mã

Một mục tiêu tốt:

> “Tách cách tính phí vận chuyển ra khỏi controller, giữ nguyên số tiền trả về và JSON đang dùng, thêm kiểm thử dưới/bằng/trên hai ngưỡng, chưa đổi giao thức thanh toán.”

Một mục tiêu mơ hồ:

> “Viết lại toàn bộ checkout để code sạch.”

Mục tiêu tốt có **ranh giới**, **hợp đồng cần giữ** và **bằng chứng thành công**. Nó cho phép reviewer biết phần nào là cải thiện cấu trúc, phần nào là thay đổi chức năng.

## 4. Bắt đầu bằng cách hiểu và bảo vệ hành vi hiện tại

Trước khi sửa một vùng mã nhiều nợ, phải xác định **đường sử dụng thật** và **kết quả đang được người gọi phụ thuộc**.

### 4.1. Characterization tests: ghi nhận hệ thống hiện làm gì

**Characterization test** ghi nhận hành vi hiện tại của mã, kể cả khi hành vi đó chưa đẹp hoặc chưa đúng theo kỳ vọng mới. Đây là cách tạo lưới an toàn khi chưa có tài liệu đầy đủ.

Ví dụ, một API cũ xử lý:

~~~java
public long legacyShippingFee(long subtotalVnd) {
    return subtotalVnd > 500_000L ? 0L : 30_000L;
}
~~~

Nếu nghiệp vụ hiện tại thực sự yêu cầu **“từ 500.000 VND trở lên”**, biểu thức **>** là một lỗi. Characterization test có thể ghi nhận rằng hệ thống cũ tính **30.000 VND** đúng tại 500.000. Nhưng **không nên biến kết quả sai đã biết thành quy tắc vĩnh viễn**.

Cần tách hai tầng bằng chứng:

- **Hành vi hiện trạng:** điều mà người gọi và dữ liệu đã trải qua.
- **Hành vi mục tiêu:** điều hợp đồng nghiệp vụ yêu cầu.

Nếu hai tầng khác nhau, hãy lên kế hoạch **sửa lỗi có chủ đích**, với test theo hợp đồng mới, đánh giá tác động và thông báo nếu cần. Refactor theo nghĩa chặt chẽ **giữ nguyên hành vi quan sát được**, còn bug fix là thay đổi hành vi được cho phép. Có thể triển khai gần nhau, nhưng phải **ghi rõ ranh giới**.

### 4.2. Tạo test theo những điểm có khả năng thay đổi

Với chính sách tính phí vận chuyển, các ca có ích:

| Đầu vào | Mục đích | Oracle theo hợp đồng ví dụ |
| --- | --- | --- |
| Khách thường 499.999 VND | Dưới ngưỡng | Phí 30.000 |
| Khách thường 500.000 VND | Đúng ngưỡng | Phí 0 |
| Khách thường 500.001 VND | Trên ngưỡng | Phí 0 |
| VIP 299.999 VND | Dưới ngưỡng riêng | Phí 30.000 |
| VIP 300.000 VND | Đúng ngưỡng riêng | Phí 0 |
| Tổng âm | Đầu vào lỗi | Từ chối |
| Tổng rất lớn hợp lệ | Không tràn do logic phụ | Kết quả theo quy tắc đã định |

Oracle cần dựa vào **điều kiện kinh doanh đã xác minh**, không chỉ sao chép công thức cũ. Nếu chưa rõ hợp đồng, phải làm rõ với người chịu trách nhiệm thay vì tự kết luận rằng mã cũ là sự thật.

### 4.3. Những ranh giới phải quan sát thêm

Đối với mã có I/O hoặc tác dụng phụ, cần lưu ý:

- Kiểu, thứ tự và nội dung các phản hồi API.
- Lỗi được ném ở thời điểm nào, có được bọc hoặc chuyển thành mã lỗi không?
- Đơn hàng được commit trước hay sau khi gọi cổng thanh toán?
- Có idempotency key khi retry không?
- Có bao nhiêu thông điệp gửi ra khi một bước thất bại?
- DB có dữ liệu cũ không tương thích với schema mới không?
- Có client hoặc job theo lịch đang gọi một điểm vào cũ không?

Kiểm thử chỉ bao phủ một số trường hợp; đối với luồng phức tạp, cần kết hợp **review hợp đồng**, **logging/metrics được thiết kế an toàn** và **kế hoạch rollback**.

## 5. Ví dụ Java: tách quy tắc tính toán khỏi điều phối

Giả sử một service bán hàng cần tính phí vận chuyển rồi mới lưu đơn. Ban đầu cả hai trách nhiệm nằm trong cùng phương thức.

### 5.1. Trước khi cải tiến: logic lẫn với tác dụng phụ

~~~java
public final class LegacyCheckoutService {
    private final OrderRepository orders;

    public LegacyCheckoutService(OrderRepository orders) {
        this.orders = orders;
    }

    public long createOrder(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        long shippingFeeVnd = 30_000L;
        if ((vip && subtotalVnd >= 300_000L)
                || subtotalVnd >= 500_000L) {
            shippingFeeVnd = 0L;
        }

        long payableVnd =
                Math.addExact(subtotalVnd, shippingFeeVnd);
        orders.save(payableVnd);
        return payableVnd;
    }
}
~~~

**OrderRepository** là interface giả định với phương thức **save(long)**; đoạn này minh họa một phần service và chưa mô tả hợp đồng persistence cụ thể. Nếu một batch job có cùng công thức, quy tắc dễ bị sao chép. Trong mỗi lần đổi chính sách, phải vừa hiểu tính toán vừa không làm đổi hành vi ghi DB.

### 5.2. Lát cắt thứ nhất: tạo hàm thuần, giữ API cũ

Tệp **ShippingPolicy.java**:

~~~java
public final class ShippingPolicy {
    private static final long VIP_FREE_FROM_VND = 300_000L;
    private static final long ALL_FREE_FROM_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private ShippingPolicy() {}

    public static long feeVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        boolean freeShipping =
                (vip && subtotalVnd >= VIP_FREE_FROM_VND)
                || subtotalVnd >= ALL_FREE_FROM_VND;
        return freeShipping ? 0L : STANDARD_FEE_VND;
    }

    public static long payableVnd(long subtotalVnd, boolean vip) {
        return Math.addExact(
                subtotalVnd, feeVnd(subtotalVnd, vip));
    }
}
~~~

Service tiếp tục giữ **chữ ký createOrder**, nhưng ủy quyền phép tính:

~~~java
public final class CheckoutService {
    private final OrderRepository orders;

    public CheckoutService(OrderRepository orders) {
        this.orders = orders;
    }

    public long createOrder(long subtotalVnd, boolean vip) {
        long payableVnd =
                ShippingPolicy.payableVnd(subtotalVnd, vip);
        orders.save(payableVnd);
        return payableVnd;
    }
}
~~~

**Thay đổi có chủ đích trong lát cắt này**:

- Công thức miễn phí vận chuyển được chuyển tới một **chủ sở hữu duy nhất**.
- Service giữ nguyên đường gọi repository và giá trị trả về theo quy tắc đã nêu.
- Quy tắc có thể kiểm thử độc lập mà không cần DB.
- Chưa đổi DTO, bảng DB, giao thức thanh toán hoặc API công khai.

Một thay đổi **cấu trúc** vẫn cần bảo vệ hành vi: nếu service cũ thực sự có quy tắc khác với **ShippingPolicy** mục tiêu, phải xử lý sự khác biệt như một **bug fix hoặc migration nghiệp vụ riêng**. Không âm thầm coi hai phiên bản tương đương chỉ vì chúng trông tương tự.

### 5.3. Lát cắt thứ hai: chuyển các người gọi khác qua cùng chính sách

Giả sử có một batch job tính tổng tiền mà chưa lưu đơn. Thay vì sao chép công thức, có thể gọi:

~~~java
long previewPayableVnd =
        ShippingPolicy.payableVnd(subtotalVnd, vip);
~~~

Chỉ nên chia sẻ **chính sách thực sự giống nhau**. Nếu batch là một công cụ xử lý đơn hàng theo chính sách lịch sử ở thời điểm tạo đơn, không được tự ý áp dụng chính sách hiện tại; khi đó cần phiên bản chính sách hoặc dữ liệu đã chốt theo hợp đồng.

Đừng gom hai quy tắc chỉ vì hiện cùng trả mức phí **30.000 VND**. Việc tạo một trừu tượng không đúng bản chất có thể **tạo nợ mới** dù số dòng lặp giảm.

### 5.4. Lát cắt thứ ba: loại bỏ phiên bản cũ khi đủ điều kiện

Trước khi xóa đoạn logic hoặc API cũ:

1. Tất cả người gọi thuộc phạm vi cần chuyển đã dùng chính sách mới?
2. Hành vi các ngưỡng và đường lỗi đã được kiểm thử?
3. Có client bên ngoài hoặc job theo lịch vẫn gọi API cũ không?
4. Có dữ liệu lịch sử cần diễn giải theo phiên bản chính sách cũ không?
5. Có thể rollback an toàn mà không cần khôi phục một cấu trúc vừa xóa không?

Nếu còn người gọi bên ngoài chưa chuyển được, có thể giữ **adapter tương thích** với tên cũ trong một giai đoạn; gắn deprecation và lịch loại bỏ rõ ràng. Một adapter có chủ đích và được theo dõi **khác** với một lớp tạm không ai chịu trách nhiệm dọn.

## 6. Kiểm thử cho từng lát cắt, không chỉ cho đích cuối

Ví dụ JUnit 5 dùng **ShippingPolicy** đã tách:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingPolicyTest {
    @ParameterizedTest
    @CsvSource({
        "true, 299999, 30000",
        "true, 300000, 0",
        "true, 300001, 0",
        "false, 499999, 30000",
        "false, 500000, 0",
        "false, 500001, 0"
    })
    void calculatesFeeAtBoundaries(
            boolean vip, long subtotalVnd,
            long expectedFeeVnd) {
        assertEquals(
                expectedFeeVnd,
                ShippingPolicy.feeVnd(subtotalVnd, vip));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(
                IllegalArgumentException.class,
                () -> ShippingPolicy.feeVnd(-1L, false));
    }

    @Test
    void handlesMaxSubtotalWithoutOverflowWhenShippingIsFree() {
        // Đơn lớn vượt ngưỡng miễn phí: tổng không tràn.
        assertEquals(
                Long.MAX_VALUE,
                ShippingPolicy.payableVnd(Long.MAX_VALUE, false));
    }
}
~~~

Bài kiểm thử cuối minh họa **số rất lớn vẫn hợp lệ ở nhánh phí 0**. Tên **handlesMaxSubtotalWithoutOverflowWhenShippingIsFree** thể hiện đúng điều được kiểm chứng; không nên đặt tên “phát hiện tràn số” cho một test chỉ assert kết quả hợp lệ.

Một kiểm thử thực sự muốn chứng minh tràn số cần có dữ liệu khiến phép cộng không biểu diễn được trong **long**. Với chính sách hiện tại, nếu subtotal không âm và phí chỉ là 0 hoặc 30.000, phí 30.000 chỉ xuất hiện khi subtotal dưới ngưỡng 500.000, nên **không có đầu vào hợp lệ nào gây tràn khi cộng phí**. Không nên tạo một “ca tràn số” giả chỉ để đủ checklist.

**JUnit 5 và Jupiter Params** không nằm sẵn trong JDK; cần khai báo dependency phù hợp trong dự án thực. Ví dụ là bằng chứng kiểm thử cho **chính sách tính toán**, không tự bảo đảm service lưu đơn đúng transaction.

## 7. Chuyển đổi cơ sở dữ liệu bằng expand–migrate–contract

Một khoản nợ phổ biến là schema DB cũ có tên cột mơ hồ, dữ liệu thiếu ràng buộc hoặc cấu trúc không còn phù hợp. Đổi trực tiếp schema có thể làm phiên bản ứng dụng cũ bị lỗi nếu hệ thống vẫn có node đang chạy, job theo lịch hoặc tiến trình rollback.

**Expand–migrate–contract** là cách chia một thay đổi schema thành các giai đoạn có thể vận hành song song trong lúc chuyển đổi:

1. **Expand:** thêm cấu trúc mới nhưng giữ cấu trúc cũ còn dùng được.
2. **Migrate:** chuyển dữ liệu và người đọc/ghi dần sang cấu trúc mới.
3. **Contract:** chỉ loại bỏ cấu trúc cũ khi không còn người dùng và đủ bằng chứng an toàn.

### 7.1. Ví dụ đổi tên một cột

Giả sử bảng **orders** có cột **total** không nêu đơn vị, và thiết kế mới muốn lưu **total_vnd**. Với dữ liệu hiện tại đều là số nguyên VND theo hợp đồng, có thể lập kế hoạch:

| Giai đoạn | Schema | Ứng dụng | Điều kiện đạt |
| --- | --- | --- | --- |
| Hiện trạng | **total** | Đọc/ghi total | Có snapshot về dữ liệu và client đang dùng |
| Expand | Thêm **total_vnd** cho phép null trong giai đoạn chuyển | Ứng dụng cũ vẫn dùng total | Mở rộng schema không phá ứng dụng cũ |
| Migrate dữ liệu | Có cả hai cột | Backfill từ total sang total_vnd | Dữ liệu được đối chiếu, không bỏ sót |
| Chuyển ghi | Có cả hai cột | Cơ chế ghi tương thích, giữ dữ liệu thống nhất theo kế hoạch | Không có sai khác do các phiên bản ứng dụng cùng chạy |
| Chuyển đọc | Có cả hai cột | Ứng dụng mới ưu tiên dữ liệu đã sẵn sàng ở cột mới | Kết quả đọc đúng khi rolling deploy |
| Contract | Bỏ cột total khi an toàn | Chỉ còn đọc/ghi total_vnd | Không còn phiên bản hoặc job phụ thuộc cột cũ |

**Đừng coi bảng này là kịch bản SQL có thể áp dụng nguyên trạng**: mỗi hệ quản trị có đặc tính DDL, khóa, replication, migration transaction và cơ chế triển khai riêng. Các câu lệnh thực tế cần được kiểm tra trên schema và phiên bản DB đang dùng.

### 7.2. Backfill không được làm mất cập nhật mới

Nếu bắt đầu backfill trong lúc ứng dụng vẫn ghi, một bản cập nhật có thể đến sau khi hàng đã được backfill. Nếu chỉ sao chép dữ liệu một lần rồi chuyển đọc sang cột mới, **total_vnd** có thể bị cũ.

Vì vậy cần một cơ chế nhất quán có thiết kế, có thể là:

- Một giai đoạn ghi tương thích trên cả hai cột **trong cùng transaction DB** khi áp dụng được.
- Trigger hoặc tầng dữ liệu chuyển đổi có kiểm soát khi kiến trúc cho phép.
- Cơ chế backfill lặp an toàn kết hợp đối chiếu và kiểm soát cập nhật.
- Chuyển toàn bộ writer trước khi coi cột mới là nguồn sự thật duy nhất.

**Dual write** không tự động an toàn: nếu ghi hai đích thuộc hai hệ thống khác nhau, một bên có thể thành công và bên kia thất bại. Khi đó phải tính đến outbox, idempotency, retry và đối soát tùy nghiệp vụ. Không nên “tách nhỏ” thành các bước ghi không nguyên tử rồi giả định dữ liệu luôn nhất quán.

### 7.3. Thời điểm xóa cột mới là quyết định rủi ro

Chỉ bỏ **total** khi đã xác nhận:

- Không còn phiên bản ứng dụng cũ cần đọc/ghi cột đó.
- Các job theo lịch, báo cáo, script và tích hợp liên quan đã chuyển.
- Việc backfill và đối soát dữ liệu đã đạt tiêu chí.
- Có phương án khôi phục nếu triển khai lỗi, kể cả khi schema đã thay đổi.
- Constraint mới đã được xác minh với toàn bộ dữ liệu hiện có.

Một migration hoàn tất về mặt code nhưng vẫn phải giữ cột cũ vô hạn có thể biến **lớp tương thích tạm thời thành nợ mới**. Cần ghi rõ chủ sở hữu và điều kiện dọn.

## 8. Cải tiến API theo kiểu chuyển dần thay vì phá hợp đồng

Nợ kỹ thuật cũng nằm ở **API cũ không còn diễn đạt tốt ý nghĩa**, chẳng hạn trả **null** thay vì kiểu kết quả rõ hoặc tên phương thức không thể hiện đơn vị. Nhưng đổi ngay một API công khai có thể làm hỏng người gọi cũ.

### 8.1. Bổ sung API mới, giữ adapter có chủ đích

Ví dụ muốn thay tên **getShipFee** bằng **shippingFeeVnd**. Nếu hợp đồng tính phí không đổi:

~~~java
public final class ShippingFacade {
    public long shippingFeeVnd(
            long subtotalVnd, boolean vip) {
        return ShippingPolicy.feeVnd(subtotalVnd, vip);
    }

    /**
     * Kept temporarily for clients of the legacy API.
     * New callers should use shippingFeeVnd.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public long getShipFee(long subtotalVnd, boolean vip) {
        return shippingFeeVnd(subtotalVnd, vip);
    }
}
~~~

Ví dụ trên minh họa **adapter tên gọi**. Nếu API cũ từng có quy tắc khác, không được dùng chuyển tiếp như trên làm thay đổi hành vi cũ mà không có kế hoạch phiên bản, dữ liệu và tương thích.

Các bước chuyển dần có thể là:

1. Công bố phương thức mới và hợp đồng rõ.
2. Giữ entry point cũ làm adapter.
3. Chuyển các người gọi nội bộ, thêm contract test cho hai đường gọi.
4. Theo dõi người gọi bên ngoài nếu có cơ chế quan sát phù hợp và không thu dữ liệu nhạy cảm.
5. Công bố lịch loại bỏ hoặc tiếp tục hỗ trợ theo chính sách phiên bản.
6. Chỉ xóa adapter khi điều kiện tương thích thực sự cho phép.

**Đừng đặt tên một adapter “temporary” nhưng không có kế hoạch kết thúc**. Nó chỉ thật sự là biện pháp chuyển đổi khi có người chịu trách nhiệm, tiêu chí hoàn tất và cách kiểm tra còn người dùng hay không.

### 8.2. Thay đổi bằng chiến lược strangler

Với một module lớn, có thể đặt một lớp điều phối hoặc adapter tại ranh giới để chuyển **một nhóm chức năng** sang triển khai mới:

~~~text
Client
  |
  v
Stable API / routing boundary
  |                      |
  +--> Legacy checkout   +--> New checkout component
          |                       |
          +---- shared contracts -+
~~~

Đây thường được gọi là cách tiếp cận **strangler pattern**: phần mới thay dần một phần trách nhiệm của phần cũ. Hợp đồng dữ liệu, lỗi, idempotency và các tác dụng phụ phải được xác định tại ranh giới. **Không nên chỉ route luồng mới sang code mới mà quên dữ liệu lịch sử hoặc client rollback.**

Một lộ trình hợp lý có thể chuyển trước **chức năng chỉ đọc** hoặc **quy tắc tính toán thuần**, vì thường dễ quan sát và đảo chiều hơn quy trình ghi nhiều hệ thống. Sau khi có bằng chứng mới chuyển các bước có tác dụng phụ.

### 8.3. Feature flag hỗ trợ rollout, nhưng cũng là nợ nếu không dọn

**Feature flag** có thể giúp chọn giữa cách triển khai cũ và mới:

~~~java
public final class QuoteRouter {
    private final QuoteEngine legacy;
    private final QuoteEngine replacement;
    private final boolean useReplacement;

    public QuoteRouter(
            QuoteEngine legacy,
            QuoteEngine replacement,
            boolean useReplacement) {
        this.legacy = legacy;
        this.replacement = replacement;
        this.useReplacement = useReplacement;
    }

    public Quote calculate(QuoteRequest request) {
        return useReplacement
                ? replacement.calculate(request)
                : legacy.calculate(request);
    }
}
~~~

Trong đoạn này, **QuoteEngine**, **Quote** và **QuoteRequest** là các kiểu miền nghiệp vụ giả định; mục tiêu là minh họa điểm chuyển hướng. Cờ cấu hình là giá trị được chụp tại lúc tạo router, nên ví dụ **không** tự hỗ trợ thay cờ động khi đang chạy.

Flag giúp triển khai theo nhóm nhỏ và rollback đường gọi **nếu hai nhánh tương thích**. Nhưng cần làm rõ:

- **Ai sở hữu cờ** và ai được phép bật/tắt?
- Khi bật, phần dữ liệu mới ghi có đọc được bằng đường cũ không?
- Có theo dõi lỗi, độ trễ và sai khác nghiệp vụ theo từng nhánh không?
- Khi nào xóa flag và mã cũ?
- Có bao nhiêu tổ hợp flag với các tính năng khác cần kiểm thử?

**Tắt flag không tự hoàn tác dữ liệu hay các tác dụng phụ đã xảy ra.** Với quy trình thu tiền, gửi email hoặc ghi DB, không nên xem rollback qua flag như rollback giao dịch.

### 8.4. Shadow comparison phải tránh tác dụng phụ trùng

Khi muốn so sánh hai thuật toán, có thể chạy cả hai trên cùng dữ liệu **nếu chúng là phép tính thuần hoặc đầu đọc không gây tác dụng phụ được thiết kế an toàn**, rồi so sánh kết quả:

~~~java
long oldFee = legacyFeePolicy.feeVnd(subtotalVnd, vip);
long newFee = ShippingPolicy.feeVnd(subtotalVnd, vip);

if (oldFee != newFee) {
    recordDifferenceWithoutSensitiveData();
}
~~~

**legacyFeePolicy** và **recordDifferenceWithoutSensitiveData** là thành phần minh họa. Sự khác nhau có thể là lỗi của triển khai mới, hoặc là một khác biệt nghiệp vụ đã được chấp thuận.

**Không** shadow-execute một tác vụ **ghi DB, trừ tiền hoặc gửi thông báo** ở hai nhánh rồi so sánh: việc đó có thể làm tác dụng phụ xảy ra hai lần. Với đường ghi, cần thiết kế shadow mode không có side effect hoặc dùng dữ liệu và môi trường kiểm thử phù hợp.

## 9. Ngăn nợ mới trong lúc sửa: “stop the bleed”

Một nhóm có thể liên tục trả nợ cũ nhưng tổng nợ vẫn tăng nếu thay đổi mới tiếp tục sao chép logic, tạo coupling hoặc bổ sung đường tắt khó phục hồi. Vì vậy, chiến lược trả nợ phải có một phần **kiểm soát nợ mới**.

### 9.1. Definition of Done cho vùng đang thay đổi

Ví dụ chuẩn hoàn tất công việc, tùy mức độ rủi ro:

- Mã mới có **tên, phạm vi sở hữu và hợp đồng rõ**.
- Không thêm **một bản sao quy tắc nghiệp vụ** khi đã có nơi sở hữu phù hợp.
- Có **kiểm thử giá trị biên và lỗi** cho hành vi mới hoặc sửa đổi.
- Không tạo đường tắt **bỏ kiểm tra đầu vào, phân quyền hoặc tham số hóa SQL**.
- Không giữ **state của một request** trong service dùng chung nếu không có lý do và cơ chế đồng thời phù hợp.
- Đã xem xét các đường **timeout, retry, hủy và cleanup** khi có I/O.
- Cảnh báo quan trọng của CI được xử lý hoặc có ngoại lệ đã ghi lý do.
- Nếu tạo flag, adapter hoặc cấu trúc tạm, có **điều kiện loại bỏ và người sở hữu**.
- Thay đổi API/schema có **kế hoạch tương thích** và cách theo dõi triển khai.

Đây là tiêu chí chất lượng cho **phần mã liên quan**, không nhất thiết là yêu cầu sửa sạch mọi cảnh báo tồn đọng trong toàn bộ repository trước khi merge một thay đổi nhỏ.

### 9.2. “Không tăng nợ” không có nghĩa cấm mọi đánh đổi

Có tình huống nhóm cần chấp nhận một giải pháp tạm để xử lý sự cố nghiêm trọng. Điều quan trọng là **quyết định được nhìn thấy và có trách nhiệm**:

~~~text
Quyết định: Dùng adapter cũ thêm một phiên bản phát hành.
Lý do: Client bên ngoài chưa hoàn tất chuyển đổi.
Rủi ro: Hai entry point phải giữ cùng kết quả.
Giảm thiểu: Contract test + cảnh báo deprecation.
Người sở hữu: Nhóm duy trì API.
Điều kiện gỡ bỏ: Client cũ đã di trú theo kế hoạch hỗ trợ.
~~~

Ghi chú này là một mẫu quyết định, không phải biên bản công việc thực tế. Một **TODO không có ngữ cảnh, người chịu trách nhiệm hoặc điều kiện hoàn tất** thường dễ bị lãng quên và trở thành khoản nợ mới không quản lý.

### 9.3. Nguyên tắc “cải thiện nơi mình chạm tới”

Khi sửa một vùng mã cho tính năng mới, có thể tranh thủ:

- Đặt tên một biến rõ hơn.
- Trích xuất quy tắc nhỏ đã được kiểm thử.
- Thêm test cho ca biên vừa phát hiện.
- Loại bỏ một đường xử lý đã chắc chắn không còn người gọi.
- Thay một biến trung gian ở field bằng local nếu không đổi hành vi.

Nhưng **đừng biến mỗi PR nghiệp vụ thành đại tu kiến trúc**. Một cải thiện nên liên quan trực tiếp tới thay đổi và có thể được reviewer hiểu. Những cải tiến lớn hơn nên được tách thành lát cắt hoặc công việc riêng.

### 9.4. Quality gate có phạm vi và baseline minh bạch

Trong codebase có nhiều cảnh báo cũ, có thể dùng baseline và áp dụng quy tắc nghiêm hơn cho **code mới**. Tuy vậy:

- **“Không có cảnh báo mới”** không đồng nghĩa không còn cảnh báo cũ.
- Scanner phải quét đúng **module, source set và artifact**; không được “đạt” bằng cách bỏ đường dẫn lỗi.
- Suppression cần **lý do, phạm vi hẹp và điều kiện xem lại**.
- Tỷ lệ coverage hoặc số cảnh báo không thay thế test oracle và review hợp đồng.
- Một quality gate chạy xanh không chứng minh feature flag, migration hoặc hành vi runtime đã an toàn.

Mục tiêu của gate là **không để những rủi ro lặp đi lặp lại lọt qua**, chứ không phải tạo một bảng điều khiển đẹp bằng cách tắt quy tắc.

## 10. Xác minh, triển khai và phản hồi theo từng bước

Từng lát cắt chỉ có ích nếu có thể trả lời **“đã cải thiện điều gì và có phá gì không?”**. Kiểm thử cục bộ là cần thiết nhưng chưa đủ cho các thay đổi liên quan tích hợp và triển khai.

### 10.1. Các lớp bằng chứng bổ trợ

| Lớp bằng chứng | Câu hỏi | Giới hạn |
| --- | --- | --- |
| Characterization test | Hành vi cũ đã được ghi nhận ở các ca đại diện chưa? | Có thể đang ghi nhận cả lỗi cũ |
| Unit test theo hợp đồng | Quy tắc mới đúng với ca bình thường/biên/lỗi chưa? | Không chứng minh I/O thực |
| Contract test | API cũ/mới có đáp ứng giao thức người gọi phụ thuộc không? | Không bao phủ mọi client |
| Integration test | DB, message, transaction và rollback có tương tác đúng không? | Môi trường test có thể khác production |
| Migration verification | Dữ liệu cũ/mới có được đối chiếu và không mất mát không? | Cần giám sát tiếp khi rolling deploy |
| Canary/rollout quan sát | Tỷ lệ lỗi, độ trễ, tác dụng phụ có ổn định trong nhóm thử không? | Dữ liệu ban đầu có thể chưa đại diện toàn bộ tải |
| Review và static analysis | Có lỗi cấu trúc, rủi ro bảo mật hoặc phạm vi bỏ sót không? | Không thay thế kết quả runtime |

Chọn bằng chứng theo **loại thay đổi**. Với hàm tính thuần, unit test và review có thể đủ cho lát cắt nhỏ. Với schema, quyền truy cập hoặc thanh toán, cần kiểm tra tích hợp, vận hành và kế hoạch xử lý sự cố.

### 10.2. Triển khai theo mức độ rủi ro

Một lộ trình có thể là:

~~~text
Thêm test + cấu trúc mới
        |
        v
Merge và chạy CI
        |
        v
Triển khai chưa chuyển lưu lượng
        |
        v
Bật cho nhóm nhỏ phù hợp
        |
        v
Theo dõi và so sánh
        |
        +---- Lỗi vượt ngưỡng ---> dừng rollout, điều tra,
        |                         rollback nếu an toàn
        |
        v
Mở rộng lưu lượng
        |
        v
Ổn định, dọn cờ/adapter cũ
~~~

Không phải ứng dụng nào cũng có hạ tầng canary hoặc feature flag. Lộ trình trên là **một phương án**, không phải yêu cầu kỹ thuật bắt buộc.

### 10.3. Chỉ số cần gắn với mục tiêu

Nếu mục tiêu là giảm lỗi phí vận chuyển, các chỉ số có thể gồm:

- Số lỗi tính phí được xác nhận theo phiên bản phát hành.
- Số sai khác giữa chính sách cũ và mới trên các ca đầu vào hợp lệ được đối chiếu.
- Số nơi còn sao chép công thức và số người gọi chưa chuyển.
- Thời gian thực hiện một thay đổi chính sách ở lần tiếp theo.
- Tỷ lệ rollback hoặc hotfix liên quan vùng mã.

Nếu mục tiêu là giảm rủi ro schema, chỉ số phù hợp khác:

- Số bản ghi chưa backfill hoặc chưa đối chiếu.
- Số writer/readers cũ còn hoạt động.
- Số xung đột dữ liệu hoặc sự kiện xử lý lại.
- Thời gian migration và mức độ ảnh hưởng tải DB.

**Không nên bịa ra con số cải thiện.** Trước thay đổi cần ghi dữ liệu nền nếu có; sau thay đổi mới có căn cứ so sánh. Một PR ít dòng hơn không tự chứng minh thời gian bảo trì giảm.

### 10.4. Rollback phải xét dữ liệu và tác dụng phụ

Một nút rollback code không phải phương án khôi phục hoàn chỉnh nếu:

- Schema mới đã loại bỏ cột mà code cũ cần.
- Dữ liệu đã được viết ở định dạng code cũ không đọc được.
- API đã gửi thông điệp hoặc thu tiền ở hệ thống bên ngoài.
- Phần mềm mới đã tạo bản ghi theo một quy tắc nghiệp vụ khác.

Vì vậy cần **kiểm tra tính tương thích ngược trong giai đoạn chuyển đổi**, kế hoạch khôi phục dữ liệu nếu phù hợp, và cơ chế đối soát tác dụng phụ không thể hoàn tác. Với những bước không an toàn để đảo chiều, ưu tiên **fix-forward có kiểm soát** thay vì khẳng định rollback luôn khả thi.

## 11. Những cách “trả nợ” dễ tạo thêm nợ

### 11.1. Viết lại toàn bộ vì mã cũ không đẹp

Một bản viết lại toàn diện có thể làm mất những hành vi không được tài liệu hóa: chính sách dữ liệu lịch sử, thứ tự trả lỗi, ràng buộc tương thích hoặc các cách phục hồi sự cố. Nếu không có ranh giới, lộ trình và bằng chứng, việc “xóa sạch nợ cũ” có thể tạo ra **một hệ thống mới còn thiếu kiểm thử và khó triển khai hơn**.

**Cách tốt hơn:** xác định phần thực sự gây trở ngại, tách theo khả năng triển khai, giữ adapter ở ranh giới cần thiết và đối chiếu hành vi. Một bản viết lại lớn vẫn có thể hợp lý khi có lý do như nền tảng không còn hỗ trợ, nhưng phải được quản lý như **một dự án thay thế có rủi ro**, không phải refactor thông thường.

### 11.2. Gom mọi mã trùng thành một helper

Hai công thức trông giống nhau không nhất thiết cùng một quy tắc. Nếu chính sách bán lẻ và chính sách đối tác có **lý do thay đổi độc lập**, gom lại chỉ để xóa ba dòng trùng có thể khiến chúng phụ thuộc không đáng có.

**Cách tốt hơn:** xác định **nguồn sự thật nghiệp vụ**. Chỉ chia sẻ khi các bên thực sự phải tuân theo cùng hợp đồng; nếu không, giữ hai quy tắc có tên rõ và kiểm thử riêng.

### 11.3. Thêm lớp trừu tượng rồi không chuyển ai sang dùng

Một lớp **NewCheckoutService** hoàn chỉnh nhưng không có đường gọi thực tế, thiếu test chuyển đổi và không có kế hoạch dọn code cũ chỉ làm dự án tăng thêm số khái niệm phải hiểu.

**Cách tốt hơn:** mỗi lát cắt nên có một kết quả thật, ví dụ chuyển một người gọi, thêm oracle hoặc đưa một phần quy tắc về một nơi. Tránh để hai hệ triển khai sống song song vô thời hạn.

### 11.4. Che nợ bằng suppression hoặc flag vĩnh viễn

Nếu dùng một cấu hình tắt warning toàn module hoặc feature flag không bao giờ gỡ, báo cáo có thể xanh hơn nhưng chi phí suy luận tăng vì:

- Người đọc không biết rule nào còn hiệu lực.
- Mọi sửa đổi phải xét nhiều nhánh hoạt động.
- Code cũ vẫn được đóng gói và có thể trở thành đường chạy ít kiểm thử.
- Phạm vi test tăng theo các tổ hợp cấu hình.

**Cách tốt hơn:** giới hạn suppression ở chỗ có căn cứ, ghi người chịu trách nhiệm, điều kiện dọn và rà soát sau khi rollout đạt kết quả.

### 11.5. Refactor và sửa nghiệp vụ cùng lúc nhưng không phân biệt

Nếu vừa trích xuất **ShippingPolicy** vừa đổi ngưỡng phí, một test đỏ có thể đến từ lỗi refactor hoặc từ quy tắc mới. Người review khó biết phần nào phải giữ hành vi, phần nào được phép thay đổi.

**Cách tốt hơn:** tách thành hai commit hoặc hai PR khi có thể:

1. Tái cấu trúc **không đổi hành vi** với characterization/contract tests.
2. Thay đổi quy tắc theo yêu cầu mới với test oracle cập nhật.

Khi không thể tách vật lý, cần chỉ ra rõ **bảng chênh lệch hành vi đã được chấp thuận**, dữ liệu cần migration và lý do.

### 11.6. “Sửa nhanh” không có ngày kết thúc

Một workaround có thể đúng khi xử lý sự cố, nhưng trở thành nợ không được quản lý nếu không có chủ sở hữu, điều kiện thay thế hoặc nơi lưu quyết định.

**Cách tốt hơn:** cho phép đánh đổi có giới hạn, nhưng ghi **vì sao cần, rủi ro còn lại, cách giảm thiểu, ai theo dõi và khi nào xem lại**. Không nên đo chất lượng bằng số lượng TODO; quan trọng là công việc tồn đọng có được quản lý theo mức ảnh hưởng hay không.

## 12. Mẫu kế hoạch xử lý một khoản nợ theo lát cắt

Giả sử dịch vụ báo giá có ba biểu hiện:

- Công thức phí được sao chép ở controller và batch.
- Một phiên bản dùng **> 500.000** trong khi hợp đồng đã xác nhận **>= 500.000**.
- Service ghi DB trước khi tất cả giá trị đầu vào được kiểm tra.

Không nên coi cả ba chỉ là một công việc “refactor phí vận chuyển”. Có thể lập kế hoạch:

| Lát cắt | Nội dung | Bằng chứng hoàn tất | Điều cố tình chưa làm |
| --- | --- | --- | --- |
| **A — Làm rõ hợp đồng** | Xác nhận ngưỡng, đơn vị, dữ liệu lỗi và các đường gọi | Bảng ca test và danh sách consumer | Chưa đổi logic hay schema |
| **B — Bảo vệ hiện trạng** | Thêm test ghi nhận hành vi cũ, kể cả sai khác đã biết | Characterization test được gắn nhãn rõ | Chưa kết luận mã cũ đúng nghiệp vụ |
| **C — Tách chính sách** | Tạo ShippingPolicy, giữ API và thứ tự tác dụng phụ | Unit test + contract test trên đường gọi | Chưa đổi ngưỡng trong cùng bước |
| **D — Sửa ngưỡng** | Chuyển **>** sang **>=** theo quyết định nghiệp vụ | Test tại 499.999, 500.000, 500.001 | Chưa viết lại toàn bộ checkout |
| **E — Chuyển người gọi** | Controller và batch dùng chính sách phù hợp | Integration/contract tests, kiểm tra dữ liệu lịch sử | Chưa xóa API cũ khi còn consumer |
| **F — Dọn cấu trúc tạm** | Xóa đoạn trùng, adapter/flag hết hạn | Không còn consumer; rollback được đánh giá | Không mở rộng thành đại tu module khác |

Nếu một lát cắt quá lớn để hiểu hoặc kiểm chứng độc lập, chia tiếp theo **đường gọi**, **chính sách con** hoặc **giai đoạn tương thích**, nhưng không phá tính nguyên tử ở các bước ghi dữ liệu.

### 12.1. Tiêu chí chấp nhận nên đo được

Một lát cắt tốt có tiêu chí:

~~~text
Lát cắt: Tách ShippingPolicy

Giữ nguyên:
  - Chữ ký API createOrder.
  - Đơn vị VND và ý nghĩa các tham số.
  - Quy tắc phí hiện hành đã được xác nhận.
  - Thứ tự ghi DB và cách trả lỗi.

Thay đổi:
  - Chỉ còn một nơi sở hữu công thức tính phí.

Xác minh:
  - Unit test cho hai ngưỡng và tổng âm.
  - Test service bảo đảm vẫn gọi repository một lần
    cho trường hợp thành công.
  - Không gọi repository nếu validation hoặc
    tính toán thất bại trước bước lưu.

Không nằm trong phạm vi:
  - Đổi JSON API, schema DB và giao thức thanh toán.

Điều kiện kết thúc:
  - Các consumer được lên danh sách và có kế hoạch chuyển.
~~~

Đây là **mẫu thiết kế công việc**, không phải kết quả đã chạy trong một dự án cụ thể. Khi có thay đổi thực tế, tiêu chí cần dựa trên hợp đồng và khả năng test của hệ thống.

### 12.2. Cân bằng tiến độ tính năng và trả nợ

Không có một tỷ lệ thời gian cố định phù hợp cho mọi nhóm. Có thể tổ chức theo các cách:

- Gắn cải tiến nhỏ vào những hạng mục đang phải sửa vùng mã đó.
- Dành công việc rõ ràng cho những khoản nợ có rủi ro cao và khó gắn với feature.
- Ưu tiên sửa cấu trúc trước khi mở rộng một đường xử lý vốn dễ gây lỗi.
- Theo dõi khoản nợ đã phát hiện nhưng chưa sửa, với lý do ưu tiên và trách nhiệm rõ.

Điều quan trọng là **không để các cải tiến phòng ngừa luôn bị đẩy ra khỏi lịch**, đồng thời không ngừng giao giá trị cho người dùng vì những thay đổi trình bày ít ảnh hưởng.

## 13. Checklist review: có đang trả nợ hay chuyển nợ sang chỗ khác?

Khi review một pull request được giới thiệu là “giảm nợ kỹ thuật”, hãy kiểm tra:

1. **Vấn đề được nêu cụ thể chưa?** Có bằng chứng về chi phí, lỗi hoặc rủi ro thay vì chỉ nói “code xấu”?
2. **Hợp đồng cần giữ rõ chưa?** API, schema, ngoại lệ, tác dụng phụ và thứ tự xử lý có được ghi nhận?
3. **Lát cắt có triển khai an toàn không?** Nếu dừng ở bước này, hệ thống vẫn hoạt động theo hợp đồng?
4. **Dữ liệu có đường chuyển đổi không?** Có xét backfill, writer cũ/mới và khả năng rollback?
5. **Refactor có đổi hành vi không?** Sai khác nào là bug fix được phép, sai khác nào là hồi quy?
6. **Có test theo rủi ro không?** Test biên, lỗi, tương thích, tích hợp và đồng thời được chọn phù hợp?
7. **Có tạo trừu tượng thiếu chủ sở hữu không?** Đoạn logic mới được đặt đúng nơi chịu trách nhiệm?
8. **Có nợ tạm mới không?** Flag, adapter, dual write, suppression hoặc TODO có người sở hữu và điều kiện loại bỏ?
9. **Pipeline có quét phần mã mới không?** Không đạt quality gate nhờ bỏ scope hoặc tắt rule.
10. **Thay đổi có thể quan sát không?** Có cách kiểm tra kết quả khi triển khai, dừng rollout và xử lý sự cố?
11. **Tài liệu có được cập nhật không?** Hợp đồng, ví dụ, kế hoạch migration và tình trạng chuyển đổi có còn đúng?
12. **Nợ thực sự giảm ở đâu?** Đã giảm một phụ thuộc, số điểm sửa, trạng thái không hợp lệ, thời gian chẩn đoán hay rủi ro đáng kể nào?

**Câu hỏi tổng kết:** “Nếu người khác tiếp tục sửa khu vực này vào tháng sau, họ sẽ cần hiểu ít ngoại lệ hơn, sửa ít nơi hơn hoặc ít có khả năng gây lỗi hơn chứ?” Nếu câu trả lời không rõ, hãy xem lại liệu PR chỉ **đổi vị trí của sự phức tạp**.

## 14. Tình huống luyện tập

Một hệ thống đặt hàng có các đặc điểm:

~~~text
CheckoutController
  - tự tính chiết khấu và phí vận chuyển
  - gọi PaymentGateway
  - cập nhật trạng thái đơn

OrderBatch
  - sao chép công thức phí nhưng ngưỡng khác

Database
  - cột total không ghi đơn vị
  - cần đổi thành total_vnd

API
  - nhiều client cũ gọi createOrder(...)

CI
  - có unit test cho controller
  - chưa có test retry thanh toán và migration
~~~

Nhóm phát triển đề xuất một PR rất lớn: thay API, đổi schema, viết lại controller, đưa payment sang bất đồng bộ, xóa batch cũ và cập nhật công thức tính phí. Họ cho rằng làm cùng lúc sẽ “trả hết nợ một lần”.

### 14.1. Câu hỏi

1. Hãy nêu ít nhất **bốn nhóm rủi ro** nếu triển khai toàn bộ đề xuất trong một PR.
2. Những hành vi và đường sử dụng nào cần **characterization hoặc contract test** trước khi đổi?
3. Nếu ngưỡng ở batch khác controller, làm sao biết đó là **lỗi trùng logic** hay **hai chính sách độc lập**?
4. Hãy sắp xếp việc tách chính sách, chuyển caller, mở rộng schema, backfill, chuyển đọc/ghi và xóa cấu trúc cũ thành các lát cắt an toàn.
5. Nếu cổng thanh toán nhận lệnh thành công nhưng server mất phản hồi, cần bảo vệ gì trước khi thêm retry?
6. Feature flag có thể hỗ trợ rollout thế nào, và tại sao không nên mặc định chạy song song hai lệnh thu tiền để so sánh?
7. Sau khi đưa tính năng mới vào production, những **chỉ số nào** cho biết việc trả nợ thực sự giúp giảm rủi ro?
8. Với mỗi lớp/flag/cột tạm tạo ra trong giai đoạn chuyển đổi, cần ghi **điều kiện loại bỏ** nào?

### 14.2. Gợi ý đối chiếu

- Rủi ro gồm **breaking API**, **mất hoặc lệch dữ liệu khi migration**, **thay đổi nghiệp vụ không được nhận diện**, **tác dụng phụ thanh toán trùng**, **khó rollback** và **khó xác định nguyên nhân lỗi**.
- Nên xác nhận hợp đồng về phí vận chuyển, chiết khấu, tiền tệ, thứ tự cập nhật trạng thái và hành vi lỗi trước khi đổi.
- Hai mức ngưỡng khác nhau chỉ là lỗi nếu **nghiệp vụ yêu cầu cùng một chính sách**. Không được xóa khác biệt chưa được giải thích bằng cách buộc cả hai gọi một helper chung.
- Có thể tách chính sách và kiểm thử trước, chuyển dần controller/batch theo hợp đồng, sau đó thực hiện **expand–migrate–contract** cho DB với cơ chế giữ nhất quán và đối chiếu dữ liệu.
- Retry thanh toán cần có hợp đồng **idempotency**, xử lý kết quả chưa rõ và đối soát. Không gọi hai nhánh có tác dụng phụ cùng lúc chỉ để so sánh.
- Cần xác định consumer cũ trước khi xóa API/column, và theo dõi tỷ lệ lỗi, độ trễ, chênh lệch dữ liệu, trạng thái migration và các hành vi bất thường khi rollout.
- Flag, adapter, cột cũ và logic đối chiếu nên có **chủ sở hữu, điều kiện dọn và bằng chứng cho phép xóa**, tránh biến kế hoạch chuyển đổi thành nhiều lớp nợ mới.

## 15. Ghi nhớ

- **Trả nợ kỹ thuật theo từng phần** là chia thay đổi thành các lát cắt nhỏ, có hợp đồng và bằng chứng rõ, không phải chỉ chia một PR lớn thành nhiều PR tùy ý.
- **Characterization tests** ghi lại hành vi hiện trạng; **kiểm thử theo hợp đồng** xác nhận hành vi mục tiêu. Đừng vô tình giữ lỗi cũ hoặc sửa nghiệp vụ mà gọi đó là refactor không đổi hành vi.
- Với mã Java, ưu tiên tách **quy tắc thuần** khỏi điều phối và tác dụng phụ, chuyển người gọi dần qua adapter hoặc ranh giới ổn định.
- Với dữ liệu và API, cần chiến lược **tương thích, migration, rollout và rollback/fix-forward** phù hợp; không xóa cấu trúc cũ khi vẫn còn phụ thuộc.
- Để **tránh tạo nợ mới**, phải quản lý flag, adapter, suppression, workaround và các lớp tương thích có phạm vi, người chịu trách nhiệm và điều kiện kết thúc rõ ràng.
- Giá trị của trả nợ thể hiện ở **rủi ro thấp hơn, ít nơi phải sửa hơn và khả năng thay đổi an toàn hơn**, không chỉ ở số dòng mã, số cảnh báo hoặc cảm giác “mã sạch”.
