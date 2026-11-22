# Giữ hành vi hợp lệ khi thay đổi cách triển khai

Một phương thức dài được tách thành các hàm nhỏ hơn, một vòng lặp được chuyển thành Stream, hoặc một đoạn xử lý được đưa sang lớp mới. Mã có thể trở nên dễ đọc hơn và chạy nhanh hơn. Nhưng câu hỏi quan trọng là: **với cùng những điều kiện được hỗ trợ, người sử dụng hệ thống có còn nhận được kết quả và tác dụng phụ đúng như đã cam kết hay không?**

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu các thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Tính đúng đắn**, một kỹ năng thiết yếu là bảo vệ **hành vi hợp lệ** trong quá trình chỉnh sửa cách triển khai. Đây là nền tảng của refactoring an toàn, tối ưu hiệu năng, thay thư viện và chuyển đổi cấu trúc hệ thống.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **hành vi được cam kết** với **chi tiết triển khai** và với **lỗi đang tồn tại**.
- Xác định những khía cạnh cần giữ nguyên: kết quả, lỗi, trạng thái, tác dụng phụ, thứ tự và hợp đồng tích hợp.
- Viết kiểm thử hồi quy và kiểm thử đặc trưng (characterization tests) để tạo bằng chứng trước khi refactor.
- Nhận diện trường hợp hai đoạn Java trông tương đương nhưng khác hành vi ở giá trị biên hoặc khi có tác dụng phụ.
- Thực hiện thay đổi nhỏ, kiểm chứng kết quả và phân biệt refactoring với thay đổi yêu cầu có chủ đích.

## 1. “Giữ nguyên hành vi” thực sự có nghĩa gì?

**Refactoring** là thay đổi cấu trúc bên trong của mã mà không có chủ đích thay đổi hành vi bên ngoài đã được xác định. Các hoạt động quen thuộc là đổi tên, tách phương thức, di chuyển trách nhiệm giữa các lớp, loại bỏ mã lặp và thay cấu trúc điều khiển bằng cách diễn đạt rõ hơn.

Tuy nhiên, không phải mọi thứ quan sát được đều đơn giản như giá trị trả về của một hàm. Với một chức năng, hành vi có thể bao gồm:

| Khía cạnh | Điều cần làm rõ | Ví dụ |
| --- | --- | --- |
| Giá trị trả về | Kiểu, giá trị, đơn vị và quy tắc làm tròn | 2 điểm thưởng, không phải 3 |
| Xử lý đầu vào không hợp lệ | Từ chối, trả giá trị mặc định hay phát sinh ngoại lệ? | Số tiền âm phải bị từ chối |
| Trạng thái lưu trữ | Dữ liệu nào được tạo, sửa, xóa? | Đơn hàng chỉ chuyển sang PAID một lần |
| Tác dụng phụ | Có gửi email, tạo sự kiện, gọi API không? | Không gửi trùng thông báo thanh toán |
| Thứ tự và tính nguyên tử | Hành động nào xảy ra trước, có giao dịch chung không? | Chỉ phát sự kiện sau khi lưu thành công |
| Hợp đồng công khai | API, dữ liệu, trạng thái lỗi có còn tương thích? | Ứng dụng khách cũ vẫn đọc được JSON |
| Đặc tính phi chức năng đã cam kết | Có ràng buộc thời gian hoặc tài nguyên cần giữ? | Không vượt timeout của API |

**Hành vi hợp lệ** là hành vi phù hợp với yêu cầu, hợp đồng và những quy tắc đã được xác nhận. Việc phần mềm hiện tại đang làm điều gì đó **không tự chứng minh điều đó là đúng**. Nếu hệ thống cũ có lỗi, việc sao chép chính xác lỗi ấy có thể trái với mục tiêu chất lượng.

Ví dụ: một hàm đang trả 0 điểm thưởng cho mọi đơn hàng vì bỏ quên phép tính. Kiểm thử ghi nhận hành vi hiện có sẽ cho thấy 0 là kết quả của phiên bản cũ, nhưng nếu chính sách nghiệp vụ quy định phải cộng điểm thì đó là lỗi cần sửa. **Bảo vệ hành vi hợp lệ không có nghĩa là đóng băng mọi lỗi cũ.**

## 2. Hợp đồng quan sát được và chi tiết triển khai

Giả sử hệ thống có chính sách điểm thưởng giả định:

- Mỗi **10.000 VND tiền mua hàng hợp lệ** được **1 điểm**.
- Khách hàng **Premium** nhận **2 điểm cho mỗi khối 10.000 VND**.
- Phần tiền lẻ dưới 10.000 VND không tạo thêm điểm.
- Số tiền âm là đầu vào không hợp lệ và phải bị từ chối.
- Hàm tính điểm không đọc hoặc thay đổi dữ liệu bên ngoài.

Chính sách này là **hợp đồng hành vi** của ví dụ. Cách đặt tên biến, số phương thức phụ, việc dùng `if` hay toán tử ba ngôi là **chi tiết triển khai**, miễn kết quả và những cam kết liên quan không thay đổi.

| Đầu vào: tiền hợp lệ (VND) | Khách thường | Premium | Lý do |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Chưa đủ một khối |
| 9.999 | 0 | 0 | Còn thiếu 1 VND |
| 10.000 | 1 | 2 | Vừa đạt một khối |
| 19.999 | 1 | 2 | Phần lẻ bị bỏ |
| 20.000 | 2 | 4 | Đủ hai khối |
| -1 | Lỗi | Lỗi | Đầu vào không hợp lệ |

Điểm đáng chú ý ở bảng là **độ chính xác của phép chia nguyên và thứ tự các phép toán**. Một refactor sai có thể không bị phát hiện nếu chỉ thử những số tròn chục nghìn.

## 3. Ví dụ Java: refactor tương đương về hành vi

Giả sử phiên bản hiện tại được viết như sau:

~~~java
public final class RewardPoints {
    private RewardPoints() {
    }

    public static long calculate(long purchaseVnd, boolean premium) {
        if (purchaseVnd < 0) {
            throw new IllegalArgumentException("purchaseVnd must be non-negative");
        }

        long completeBlocks = purchaseVnd / 10_000L;
        if (premium) {
            return completeBlocks + completeBlocks;
        }
        return completeBlocks;
    }
}
~~~

Một phiên bản dễ mở rộng hơn có thể viết:

~~~java
public final class RewardPoints {
    private static final long VND_PER_POINT_BLOCK = 10_000L;
    private static final long PREMIUM_MULTIPLIER = 2L;

    private RewardPoints() {
    }

    public static long calculate(long purchaseVnd, boolean premium) {
        validatePurchase(purchaseVnd);
        long completeBlocks = purchaseVnd / VND_PER_POINT_BLOCK;
        long multiplier = premium ? PREMIUM_MULTIPLIER : 1L;
        return completeBlocks * multiplier;
    }

    private static void validatePurchase(long purchaseVnd) {
        if (purchaseVnd < 0) {
            throw new IllegalArgumentException("purchaseVnd must be non-negative");
        }
    }
}
~~~

Hai cách triển khai có cùng hành vi theo chính sách đã nêu:

1. Cùng từ chối số tiền âm bằng `IllegalArgumentException`.
2. Cùng tính **số khối đầy đủ trước khi nhân hệ số**.
3. Cùng trả về kiểu `long` và cùng cho kết quả khi đủ, thiếu hoặc vượt các mốc 10.000 VND.
4. Cùng không tạo tác dụng phụ.

Trong phạm vi đầu vào `long` không âm, số khối nhiều nhất là `Long.MAX_VALUE / 10_000`; nhân với 2 vẫn nằm trong khoảng của `long`. Vì vậy cách nhân hệ số ở đây không phát sinh tràn số đối với miền đầu vào đã xác định.

### Một cách “rút gọn” làm thay đổi hành vi

Đoạn sau trông tương tự, nhưng thực hiện phép toán theo thứ tự khác:

~~~java
// Sai so với quy tắc "mỗi khối 10.000 VND hoàn chỉnh".
long multiplier = premium ? 2L : 1L;
return (purchaseVnd * multiplier) / 10_000L;
~~~

Với `purchaseVnd = 19_999` và `premium = true`:

| Cách tính | Biểu thức | Kết quả |
| --- | --- | ---: |
| Theo chính sách | `(19_999 / 10_000) * 2` | **2** |
| Đổi thứ tự phép toán | `(19_999 * 2) / 10_000` | **3** |

Đây là lỗi **đổi quy tắc làm tròn ngầm**. Với số tiền lớn, việc nhân trước còn có thể gây **tràn `long`** trong khi cách chia trước vẫn an toàn. Do đó, phép biến đổi đại số quen thuộc trên số thực chưa chắc bảo toàn kết quả khi dùng số nguyên có giới hạn.

## 4. Đặt lưới an toàn trước khi thay mã

Để biết bản mới có giữ hành vi hợp lệ hay không, cần **bằng chứng kiểm thử có kết quả mong đợi độc lập với triển khai**. Ví dụ với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class RewardPointsTest {
    @ParameterizedTest
    @CsvSource({
        "0,     false, 0",
        "0,     true,  0",
        "9999,  false, 0",
        "9999,  true,  0",
        "10000, false, 1",
        "10000, true,  2",
        "19999, false, 1",
        "19999, true,  2",
        "20000, false, 2",
        "20000, true,  4"
    })
    void preservesRewardRules(long purchaseVnd, boolean premium, long expected) {
        assertEquals(expected, RewardPoints.calculate(purchaseVnd, premium));
    }

    @Test
    void rejectsNegativePurchase() {
        assertThrows(
            IllegalArgumentException.class,
            () -> RewardPoints.calculate(-1L, true)
        );
    }
}
~~~

Các giá trị `expected` lấy từ bảng quy tắc nghiệp vụ. Nếu dùng cùng công thức của hàm cần kiểm thử để sinh `expected`, kiểm thử có thể lặp lại chính lỗi của mã nguồn. Ngay cả khi bộ test cũ luôn xanh, thêm các trường hợp **9.999, 10.000, 19.999, 20.000** giúp bảo vệ những chỗ dễ bị thay đổi ngoài ý muốn.

Với mã mới sau refactor, bộ kiểm thử này phải được chạy lại. Mỗi trường hợp thất bại là dấu hiệu cần kiểm tra **đặc tả**, **test** và **bản thay đổi** để xác định nguyên nhân.

### Bổ sung thuộc tính tổng quát

Ngoài các ví dụ cố định, ta có thể kiểm tra những **bất biến** đúng theo chính sách:

- Với số tiền hợp lệ, điểm không âm.
- Với cùng hạng khách, tăng số tiền không làm giảm điểm.
- Điểm Premium luôn bằng **hai lần** điểm của khách thường khi cùng số tiền.
- Trong mỗi khoảng từ `10_000 * n` đến `10_000 * (n + 1) - 1` (n không âm và không vượt miền số), điểm không thay đổi.

Kiểm thử dựa trên thuộc tính (property-based testing) có thể sinh nhiều giá trị để tìm trường hợp ít được nghĩ đến. Tuy nhiên, các thuộc tính phải được nghiệp vụ chấp nhận; không được tự đặt một bất biến chỉ vì nó dễ viết.

## 5. Characterization tests: khi mã cũ chưa có đặc tả rõ

Một hệ thống lâu năm đôi khi có hành vi được khách hàng phụ thuộc nhưng tài liệu không đầy đủ. Trước khi thay cấu trúc, có thể viết **kiểm thử đặc trưng (characterization tests)** nhằm ghi nhận *mã hiện tại đang làm gì* trên các đầu vào đại diện.

Quy trình:

1. Xác định các luồng quan trọng và điểm tương tác với người dùng, dữ liệu hoặc hệ thống khác.
2. Tạo bộ đầu vào điển hình, giá trị biên và tình huống lỗi.
3. Ghi nhận đầu ra, sự kiện, thay đổi dữ liệu hoặc ngoại lệ thực tế của bản cũ.
4. Đối chiếu với yêu cầu hiện có và trao đổi với người phụ trách nghiệp vụ: hành vi nào **đúng cần giữ**, hành vi nào **là lỗi cần sửa**, hành vi nào còn chưa rõ.
5. Chuyển các hành vi đã xác nhận thành kiểm thử hồi quy có tên và kết quả mong đợi dễ hiểu.

Ví dụ, nếu hệ thống cũ trả 3 điểm cho khách Premium mua 19.999 VND, một characterization test có thể ghi lại con số 3 để phát hiện mọi thay đổi so với bản cũ. Nhưng nếu chính sách đã xác nhận “mỗi **khối đủ** 10.000 VND được 2 điểm”, kết quả 3 là **bug**. Khi sửa bug, cần cập nhật kiểm thử theo hành vi đúng là 2 và nêu rõ đây là thay đổi có chủ đích.

**Khác biệt quan trọng:** characterization test ghi nhận **hiện trạng**; acceptance test kiểm tra **yêu cầu đã xác nhận**. Có lúc chúng trùng nhau, có lúc không. Không được lấy hành vi bất kỳ của bản cũ làm chuẩn đúng đắn tuyệt đối.

## 6. Khi có tác dụng phụ, “cùng giá trị trả về” vẫn chưa đủ

Xét thao tác đánh dấu đơn hàng đã thanh toán. Phiên bản cũ, theo một hợp đồng giả định, phải:

- Chỉ cho phép chuyển từ `PENDING` sang `PAID`.
- Lưu chuyển trạng thái bền vững.
- Phát **một** sự kiện `OrderPaid` cho lần chuyển đổi thành công.
- Nếu nhận lại cùng yêu cầu sau khi đã thanh toán, không tạo thêm giao dịch hoặc sự kiện trùng.

Một đoạn xử lý sau refactor có thể vẫn trả về `true` nhưng gửi thông báo hai lần, hoặc gửi thông báo trước khi ghi dữ liệu thành công. Điều đó **thay đổi hành vi quan sát được** dù kiểu và giá trị trả về không đổi.

Ví dụ minh họa một sai lệch:

~~~java
// Rủi ro: phát sự kiện trước khi chắc chắn lưu trạng thái thành công.
eventPublisher.publish(new OrderPaid(orderId));
repository.markPaid(orderId);
return true;
~~~

Nếu `markPaid` lỗi, bên nhận đã thấy `OrderPaid` dù đơn hàng chưa chuyển trạng thái. Chỉ đảo thứ tự lời gọi:

~~~java
repository.markPaid(orderId);
eventPublisher.publish(new OrderPaid(orderId));
return true;
~~~

cũng **chưa tự đảm bảo nhất quán**: nếu lưu thành công rồi phát sự kiện lỗi, sự kiện có thể bị mất. Với yêu cầu phát sự kiện tin cậy theo trạng thái đã commit, thiết kế như **transactional outbox** kết hợp cơ chế phát lại/idempotency có thể phù hợp hơn. Tuy nhiên, cần đánh giá cơ chế lưu trữ và hợp đồng giao dịch cụ thể; không thể kết luận đúng chỉ từ ba dòng mã.

Các phép kiểm tra quan trọng ở đây gồm:

| Tình huống | Cần quan sát |
| --- | --- |
| Thanh toán lần đầu thành công | Trạng thái `PAID` được lưu; sự kiện hợp lệ được ghi nhận đúng một lần theo chính sách |
| Gửi lại cùng yêu cầu | Không tạo hiệu ứng nghiệp vụ trùng |
| Lưu dữ liệu thất bại | Không công bố kết quả thanh toán thành công sai sự thật |
| Phát sự kiện gặp lỗi tạm thời | Có cơ chế khôi phục theo cam kết, không làm sai trạng thái |
| Hai yêu cầu cạnh tranh | Không tạo hai lần chuyển trạng thái/ghi nhận tiền |

Khi refactor mã có I/O, các test cần kiểm tra không chỉ dữ liệu trả về mà cả **trạng thái lưu trữ, số lần gọi, thứ tự có ý nghĩa, và hành vi khi một bước thất bại**.

## 7. Hành vi của API, dữ liệu và ngoại lệ

Thay đổi cách triển khai có thể làm thay đổi hợp đồng công khai dù người sửa chỉ định “dọn mã”:

| Thay đổi | Rủi ro hành vi | Cách bảo vệ |
| --- | --- | --- |
| Thay thư viện JSON | Đổi tên trường, thứ tự xử lý null hoặc định dạng ngày | Contract test với payload đại diện và schema được công bố |
| Thay truy vấn SQL | Mất thứ tự kết quả vì không có `ORDER BY` | Xác định thứ tự có phải hợp đồng; nếu có, truy vấn và test phải quy định rõ |
| Chuyển từ tuần tự sang song song | Thay thứ tự hoặc gây race condition | Test với dữ liệu nhiều phần tử; kiểm tra tác dụng phụ và luồng đồng thời |
| Gộp các nhánh xử lý lỗi | Trả khác mã lỗi hoặc khác loại ngoại lệ | Test dữ liệu không hợp lệ và ánh xạ lỗi API |
| Đổi cấu trúc cache | Dữ liệu cũ xuất hiện lâu hơn hoặc không được làm mới đúng lúc | Kiểm tra freshness, invalidation và retry |
| Tối ưu phép tính số | Khác làm tròn hoặc tràn số | Kiểm tra giới hạn kiểu, giá trị biên và đơn vị |

Không phải mọi chi tiết đều bắt buộc giữ. Ví dụ, thứ tự khóa trong JSON object thường không phải điều ứng dụng khách nên phụ thuộc, nhưng **nếu** hợp đồng của một giao thức hoặc cách ký dữ liệu yêu cầu thứ tự/canonicalization cụ thể, thay đổi ấy lại quan trọng. Cần dựa vào **hợp đồng thực tế** để xác định điều phải bảo toàn.

Tương tự, thông điệp của một ngoại lệ nội bộ có thể không phải hợp đồng công khai, trong khi **mã HTTP**, **loại lỗi trả cho khách**, **cấu trúc lỗi** hoặc **khả năng retry** có thể là phần bắt buộc của giao diện.

## 8. Kiểm tra tương đương trước và sau

Khi hành vi được xác định rõ, nên có hai nhóm bằng chứng bổ trợ nhau:

**Kiểm thử theo đặc tả:** so sánh kết quả của bản mới với **kết quả mong đợi từ quy tắc**, bao gồm trường hợp bình thường, biên, lỗi và tác dụng phụ.

**Kiểm thử so sánh (differential testing):** chạy cả bản cũ và bản mới với cùng dữ liệu, sau đó so sánh các quan sát liên quan. Kỹ thuật này đặc biệt hữu ích khi đổi thuật toán có nhiều nhánh hoặc chuyển đổi công cụ, vì nó phát hiện khác biệt mà nhóm chưa lường trước.

Sơ đồ quy trình:

~~~text
            Tập đầu vào đại diện
                  |
          +-------+-------+
          |               |
     Bản triển khai cũ   Bản triển khai mới
          |               |
    Kết quả / dấu vết  Kết quả / dấu vết
          |               |
          +-------+-------+
                  |
        So sánh phần hành vi đã cam kết
                  |
        Khác biệt? Xác minh với đặc tả
~~~

Điều kiện để so sánh có ý nghĩa:

- Hai bản phải dùng dữ liệu và cấu hình **tương đương**; thời gian, số ngẫu nhiên và trạng thái bên ngoài cần được kiểm soát khi chúng ảnh hưởng đến kết quả.
- Khi cần so sánh tác dụng phụ, dùng môi trường thử nghiệm hoặc fake/spy, **không gửi hai lần thao tác thật** đến hệ thống thanh toán hay người dùng.
- Chỉ so sánh những thuộc tính cần bảo vệ; ví dụ thời gian chạy chính xác từng mili giây không phải thứ nên buộc bằng nhau nếu chưa có hợp đồng tương ứng.
- Nếu bản cũ sai so với đặc tả, khác biệt ở bản mới có thể là **sửa lỗi đúng đắn**. Phải phân loại có chủ đích, không làm cho test cũ xanh bằng cách khôi phục bug.

Với chức năng RewardPoints, differential test có thể sinh nhiều giá trị `purchaseVnd` hợp lệ và kiểm tra bản cũ/bản mới cho cùng điểm. Bộ kiểm thử theo đặc tả vẫn cần để phát hiện trường hợp **cả hai cùng sai**.

## 9. Quy trình refactor giữ hành vi hợp lệ

Một quy trình gọn nhưng có căn cứ:

1. **Xác định phạm vi:** đang đổi cấu trúc, tối ưu hiệu năng, thay dependency hay thay yêu cầu? Ghi rõ hành vi nào được giữ và điều gì thay đổi có chủ đích.
2. **Làm rõ hợp đồng:** dùng yêu cầu sản phẩm, tài liệu API, bảng quy tắc, mẫu dữ liệu và tiêu chí chấp nhận. Với phần chưa rõ, xác nhận trước khi coi là bất biến.
3. **Tạo baseline:** chạy kiểm thử hiện có, bổ sung test giá trị biên, lỗi, trạng thái và tác dụng phụ. Nếu mã cũ khó hiểu, dùng characterization tests để phát hiện hành vi đang có.
4. **Chia thay đổi thành bước nhỏ:** đổi tên, trích xuất phương thức, di chuyển logic và thay thuật toán theo từng đợt dễ xem xét. Chạy test sau mỗi bước có ý nghĩa.
5. **Đối chiếu cả hành vi và môi trường:** chạy unit test, integration/contract test liên quan, thử dữ liệu thật đã khử nhạy cảm hoặc dữ liệu mô phỏng đại diện. Khi đổi hiệu năng, đo trong điều kiện tải thích hợp.
6. **Review các khác biệt:** tách lỗi do refactor, thay đổi yêu cầu được phê duyệt và hành vi cũ vốn sai. Cập nhật test, tài liệu và cách triển khai tương ứng.
7. **Triển khai có khả năng theo dõi:** với thay đổi rủi ro cao, quan sát tỷ lệ lỗi, kết quả nghiệp vụ, số lần gọi ngoài và cảnh báo; có kế hoạch khôi phục nếu phát hiện hồi quy.

Giữ cho mỗi thay đổi đủ nhỏ để người review dễ hiểu **trước đó mã làm gì, sau đó mã làm gì và bằng chứng nào cho thấy hành vi hợp lệ vẫn được giữ**.

## 10. Các lỗi tư duy thường gặp

| Ngộ nhận | Vì sao chưa đủ | Cách kiểm chứng |
| --- | --- | --- |
| “Chỉ đổi cấu trúc nên chắc chắn không có lỗi” | Refactor vẫn có thể đổi toán tử, thứ tự thực hiện, exception hoặc tác dụng phụ | Chạy test hành vi và kiểm tra diff |
| “100% coverage nên an toàn” | Coverage không chứng minh tình huống hoặc kết quả mong đợi đầy đủ | Bổ sung test theo quy tắc và giá trị biên |
| “Đầu ra hai bản giống nhau là đủ” | Cả hai có thể cùng sai; tác dụng phụ có thể khác | Dùng acceptance test và quan sát trạng thái/I/O |
| “Thay đổi nhỏ không cần chạy lại test” | Một toán tử hoặc thứ tự phép toán có thể làm sai ngưỡng | Kiểm thử hồi quy tương ứng với vùng thay đổi |
| “Mã cũ là chuẩn tuyệt đối” | Bug cũ cũng là hành vi hiện có | Xác nhận với nghiệp vụ trước khi quyết định giữ |
| “Đổi tên/sắp xếp thông tin không ảnh hưởng khách hàng” | API/JSON/schema và kết quả có thứ tự có thể là hợp đồng | Kiểm thử hợp đồng với bên tiêu thụ |

## 11. Bài tập tự kiểm tra

Một hệ thống tính điểm có chính sách trong phần 2. Lập trình viên muốn tối ưu bằng cách thay:

~~~java
long blocks = purchaseVnd / 10_000L;
return premium ? blocks * 2 : blocks;
~~~

thành:

~~~java
return premium
    ? purchaseVnd / 5_000L
    : purchaseVnd / 10_000L;
~~~

**Câu hỏi A.** Hai cách viết có luôn tương đương trên miền đầu vào không âm không?

**Câu hỏi B.** Chọn một giá trị cụ thể để chứng minh nhận định.

**Câu hỏi C.** Nếu muốn thay bảng cộng điểm bằng một cấu hình theo hạng khách, cần bảo vệ những quy tắc và tình huống kiểm thử nào trước khi thay?

### Gợi ý trả lời

**A.** Không. Ở hạng Premium, phép chia cho `5_000` thay đổi quy tắc bỏ phần lẻ so với “đếm khối đủ 10.000 rồi nhân 2”.

**B.** Với `purchaseVnd = 9_999`, cách cũ cho `(9_999 / 10_000) * 2 = 0`, cách mới cho `9_999 / 5_000 = 1`. Cả hai đều dùng số nguyên, nhưng **không giữ cùng hành vi**. Với `purchaseVnd = 19_999`, cách cũ cho 2, cách mới cho 3.

**C.** Cần xác nhận ngưỡng và hệ số từng hạng, cách làm tròn từng khối, xử lý tổng âm, giới hạn kiểu số, không phát sinh tác dụng phụ và hành vi mặc định với hạng không được hỗ trợ. Test nên bao gồm giá trị sát các ngưỡng, từng hạng, số lớn hợp lệ, dữ liệu không hợp lệ và các tích hợp cung cấp đúng số tiền.

## Ghi nhớ

**Giữ hành vi hợp lệ khi thay đổi cách triển khai** là giữ nguyên những kết quả, trạng thái và tác dụng phụ **đã được cam kết**, đồng thời cho phép thay đổi cấu trúc bên trong để mã dễ hiểu và dễ bảo trì hơn. Muốn làm được điều này, cần có **đặc tả đúng**, **kiểm thử hồi quy ở các trường hợp có ý nghĩa**, **quan sát các tác dụng phụ**, và **đối chiếu mọi khác biệt với yêu cầu**. Bản cũ là nguồn dữ liệu tham khảo quan trọng, nhưng yêu cầu được xác nhận mới là thước đo cuối cùng cho tính đúng đắn.
