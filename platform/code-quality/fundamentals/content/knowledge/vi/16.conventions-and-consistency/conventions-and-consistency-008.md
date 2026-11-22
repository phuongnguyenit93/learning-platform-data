# Ngoại lệ có lý do thay vì áp dụng máy móc

Một dự án Java quy định tên phương thức phải nói rõ ý nghĩa nghiệp vụ, mã phải tuân theo formatter và không nên sao chép logic. Những quy ước ấy giúp các thành viên đọc, sửa và review mã dễ dàng hơn. Nhưng đôi khi việc tuân thủ máy móc lại gây hại: đổi tên một phương thức công khai có thể làm hỏng client cũ; ép mọi phương thức chỉ có một lệnh return có thể khiến điều kiện bị lồng sâu; hoặc gom hai đoạn mã nhìn giống nhau nhưng có quy tắc nghiệp vụ khác nhau vào một hàm chung có thể làm hai chức năng phụ thuộc nhau không cần thiết.

Trong chương **Quy ước và nhất quán** của module **CODE_QUALITY_FUNDAMENTALS**, cần hiểu rằng chất lượng mã không phải số lượng quy tắc hình thức được làm đúng. Mục tiêu là giữ mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một ngoại lệ có căn cứ là quyết định **chủ động, có phạm vi, có thể giải thích và kiểm chứng**, chứ không phải cách hợp thức hóa sở thích cá nhân hoặc bỏ qua kiểm tra chất lượng.

> Mặc định tuân thủ quy ước chung. Chỉ đi khác khi có lý do kỹ thuật hoặc nghiệp vụ rõ ràng, lợi ích lớn hơn chi phí làm mất nhất quán, và phạm vi ngoại lệ được kiểm soát.

## 1. Tại sao cần quy ước trước khi nói đến ngoại lệ?

**Quy ước** (*convention*) là cách làm được một nhóm hoặc hệ sinh thái thống nhất để giảm số quyết định nhỏ lặp lại. Ví dụ trong dự án Java:

- Tên lớp dùng **UpperCamelCase**, tên phương thức và biến dùng **lowerCamelCase**.
- Định dạng mã theo một formatter thống nhất.
- Thư mục, package và tên tệp thể hiện cấu trúc dự án.
- API trả về kết quả và báo lỗi theo hợp đồng nhất quán.
- Những tác vụ I/O có quy tắc quản lý tài nguyên rõ ràng.
- Mỗi module có quy tắc ghi log, kiểm thử và tài liệu được công bố.

Khi nhiều thành phần áp dụng cùng cách diễn đạt, người đọc ít phải đoán:

| Khi có quy ước nhất quán | Khi mỗi nơi làm một kiểu |
| --- | --- |
| Có thể đoán chức năng từ tên và cấu trúc | Phải đọc sâu từng phương thức mới biết cách sử dụng |
| Code review tập trung vào logic và rủi ro | Review mất nhiều thời gian tranh luận định dạng |
| Công cụ formatter, linter dễ tự động hóa | Nhiều thay đổi không liên quan xuất hiện trong diff |
| Thành viên mới tiếp cận module nhanh hơn | Cần ghi nhớ nhiều ngoại lệ không được giải thích |
| Khi sửa API, kỳ vọng của bên gọi rõ hơn | Mỗi API có quy tắc lỗi và dữ liệu riêng khó đoán |

**Giá trị của quy ước nằm ở khả năng giảm gánh nặng nhận thức**, không phải ở việc biến mỗi quy tắc thành mục tiêu độc lập. Ngoại lệ tùy tiện làm mất lợi ích đó; ngoại lệ có lý do giúp tránh việc quy ước cản trở mục đích ban đầu.

## 2. Phân biệt quy ước, khuyến nghị và ràng buộc bắt buộc

Không phải mọi “quy tắc” đều có thể được miễn trừ theo cùng cách.

| Loại yêu cầu | Ví dụ | Cách xử lý khi muốn đi khác |
| --- | --- | --- |
| **Quy ước trình bày** | Xuống dòng, cách đặt tên biến cục bộ | Có thể cân nhắc ngoại lệ nhỏ nếu diễn đạt rõ hơn |
| **Khuyến nghị thiết kế** | Tránh phương thức dài, ưu tiên ít phụ thuộc, hạn chế lặp | So sánh đánh đổi theo bối cảnh |
| **Hợp đồng API** | Tham số, ngoại lệ, tên trường JSON, hành vi retry | Phải bảo toàn tương thích hoặc quản lý thay đổi hợp đồng |
| **Bất biến nghiệp vụ** | Không cho số lượng âm; không thu tiền hai lần cho một yêu cầu | Không được bỏ chỉ vì “làm code ngắn hơn” |
| **Yêu cầu an toàn/bảo mật** | Kiểm soát quyền truy cập, bind giá trị SQL, bảo vệ bí mật | Chỉ thay bằng cơ chế bảo vệ được chấp thuận, không vô hiệu hóa tùy tiện |
| **Yêu cầu nền tảng/hệ thống** | Giới hạn bộ nhớ, giao thức bên ngoài, phiên bản Java hỗ trợ | Cần đáp ứng hợp đồng của môi trường hoặc thay đổi phạm vi hỗ trợ |

Ví dụ, nhóm quy định “không đặt nhiều return trong một phương thức” có thể cân nhắc ngoại lệ khi **guard clause** rõ hơn. Nhưng không thể viện lý do “muốn linh hoạt” để bỏ kiểm tra phân quyền hay chấp nhận dữ liệu sai trạng thái nghiệp vụ.

Nếu một quy định là điều kiện bắt buộc của tổ chức, pháp lý hoặc hợp đồng giao tiếp, việc thay đổi cần đi theo **quy trình phê duyệt tương ứng**. Một bình luận trong mã không biến hành vi sai hợp đồng thành hợp lệ.

## 3. Thế nào là ngoại lệ có lý do?

Một ngoại lệ tốt cần trả lời được bảy câu hỏi:

1. **Quy ước mặc định là gì?** Người review có thể chỉ ra quy tắc đang được cân nhắc không?
2. **Bối cảnh cụ thể nào khiến quy tắc không phù hợp?** Có ràng buộc nghiệp vụ, tương thích, nền tảng hoặc bằng chứng đo đạc không?
3. **Điều gì xảy ra nếu cứ áp dụng quy ước?** Có làm giảm khả năng hiểu, tạo lỗi hoặc tăng chi phí thay đổi không?
4. **Đã cân nhắc giải pháp nào khác?** Có thể vẫn giữ quy ước bằng cách thiết kế lại đơn giản hơn không?
5. **Ngoại lệ được giới hạn ở đâu?** Một biểu thức, một phương thức, một adapter hay cả module?
6. **Làm sao kiểm chứng ngoại lệ không gây hại?** Có kiểm thử, số đo hoặc hành vi tương thích cụ thể không?
7. **Ai và khi nào xem lại quyết định?** Ngoại lệ tồn tại lâu dài do hợp đồng, hay chỉ tạm thời trong quá trình chuyển đổi?

Một mô tả như “viết vậy vì nhanh hơn” chưa đủ nếu không có bằng chứng về chỗ thực sự cần tối ưu. Tương tự, “team thích cách này” là lý do **thống nhất quy ước mới**, không phải lý do để mỗi tệp tự dùng một kiểu.

### 3.1. So sánh ngoại lệ tùy tiện và ngoại lệ có căn cứ

| Tiêu chí | Ngoại lệ tùy tiện | Ngoại lệ có căn cứ |
| --- | --- | --- |
| Lý do | “Tôi quen viết như vậy” | “Đổi tên sẽ phá client công khai đang sử dụng” |
| Phạm vi | Bỏ quy tắc cho cả module | Giữ một adapter cũ, API mới theo quy ước |
| Bằng chứng | Không có | Kiểm thử tương thích, usage hoặc benchmark liên quan |
| Rủi ro | Không được ghi nhận | Được nêu và có biện pháp giảm thiểu |
| Người review | Không biết tại sao khác | Hiểu được bối cảnh và phương án thay thế |
| Thời gian | Để mặc vô hạn | Có mốc xem lại hoặc lý do duy trì lâu dài |

**Ngoại lệ không đồng nghĩa là lỗi**, và cũng không phải “quy ước mới” cho toàn bộ dự án. Nó là một quyết định có phạm vi cụ thể, trong khi quy tắc mặc định vẫn có hiệu lực ở những nơi khác.

## 4. Ví dụ Java: guard clause thay vì ép một điểm return

Giả sử một quy ước cũ khuyến khích mỗi phương thức chỉ có một lệnh return. Mục đích ban đầu có thể là giúp dễ theo dõi đường thoát và dọn dẹp. Nhưng với một phương thức kiểm tra nhiều điều kiện độc lập, áp dụng máy móc có thể gây lồng nhánh:

~~~java
public String labelFor(User user) {
    String result;
    if (user == null) {
        result = "UNKNOWN";
    } else {
        if (!user.active()) {
            result = "INACTIVE";
        } else {
            if (user.vip()) {
                result = "VIP";
            } else {
                result = "STANDARD";
            }
        }
    }
    return result;
}
~~~

Nếu hợp đồng là: không có người dùng thì UNKNOWN; người dùng không hoạt động là INACTIVE; còn lại phân theo VIP, một cách viết dễ theo dõi hơn:

~~~java
public String labelFor(User user) {
    if (user == null) {
        return "UNKNOWN";
    }
    if (!user.active()) {
        return "INACTIVE";
    }
    if (user.vip()) {
        return "VIP";
    }
    return "STANDARD";
}
~~~

Trong hai ví dụ, **User** là kiểu miền nghiệp vụ minh họa có các phương thức truy vấn trạng thái. Giả định **active()** và **vip()** là phép đọc ổn định, không có tác dụng phụ.

**Lý do ngoại lệ:** cho phép nhiều return để diễn đạt các trường hợp loại trừ ngay tại đầu phương thức, giảm độ sâu lồng nhánh và giúp người đọc thấy thứ tự ưu tiên của các điều kiện.

**Phạm vi:** chỉ cách tổ chức luồng điều khiển trong phương thức, không thay đổi hợp đồng trả về hoặc xử lý lỗi. Một nhóm có thể quyết định cập nhật quy ước cho phép guard clause nói chung nếu phương án này thường xuyên hữu ích; khi đó không còn cần ghi ngoại lệ cho mỗi lần dùng.

**Điều phải giữ:** không bỏ qua cleanup hoặc làm sai khác tác dụng phụ. Với tài nguyên đóng bằng **try-with-resources**, return trong thân try vẫn thực hiện đóng. Nếu mã dựa vào lời gọi thủ công ở cuối phương thức, cần thiết kế lại vòng đời tài nguyên trước khi thêm return sớm.

### 4.1. Ngoại lệ không có nghĩa mọi return đều tốt

Một phương thức có mười nhánh return được phân tán xen kẽ với cập nhật trạng thái có thể vẫn rất khó hiểu. Nếu logic quyết định phức tạp, nên cân nhắc tách quy tắc có tên rõ nghĩa, trả về kiểu kết quả phù hợp hoặc đơn giản hóa máy trạng thái.

Mục tiêu là **giảm việc suy luận**, không phải thay “chỉ một return” bằng “càng nhiều return càng hay”.

## 5. Ví dụ Java: dùng var hay kiểu tường minh?

Nhiều nhóm quy định ưu tiên khai báo kiểu tường minh để người đọc nhìn thấy kiểu dữ liệu. Từ Java 10, **var** cho biến cục bộ giúp giảm lặp:

~~~java
var items = new ArrayList<OrderLine>();
~~~

Ở đây, kiểu kết quả hiển thị ngay phía phải và thường dễ suy ra. Viết lại với tên kiểu đầy đủ cũng hợp lệ nhưng có thể lặp thông tin:

~~~java
ArrayList<OrderLine> items = new ArrayList<OrderLine>();
~~~

Trong một ngữ cảnh khác, **var** có thể giấu một kiểu quan trọng:

~~~java
var result = repository.findById(userId);
~~~

Nếu hợp đồng của **repository** không được biết, người đọc chưa chắc nhận ra **result** là **Optional<User>**, **User** hay một kiểu kết quả khác. Có thể ưu tiên:

~~~java
Optional<User> user = repository.findById(userId);
~~~

Với tài nguyên JDBC, kiểu tường minh cũng có thể nhấn mạnh trách nhiệm:

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Sử dụng lượt mượn Connection; close được gọi khi thoát khối.
}
~~~

**var không làm Java mất kiểm tra kiểu tĩnh**: compiler suy ra kiểu từ biểu thức khởi tạo. Sự đánh đổi ở đây là **khả năng đọc của con người**, không phải var “kém an toàn” về mặt kiểu. Cả hai dạng đều có thể tốt tùy mức độ dễ đoán của kiểu và quy ước dự án.

### Ngoại lệ hợp lý

Một dự án mặc định yêu cầu kiểu tường minh có thể cho phép **var khi kiểu hiển nhiên từ constructor hoặc factory có tên rõ**, nhưng vẫn giữ kiểu tường minh khi tính chất của kết quả là hợp đồng quan trọng. Nên mô tả thành tiêu chí chung, thay vì để mỗi tác giả tự quyết không có nguyên tắc.

## 6. Ví dụ Java: không gom mọi đoạn mã giống nhau vào một hàm

Quy ước **DRY (Don't Repeat Yourself)** thường bị hiểu sai thành “hễ thấy hai đoạn có ký tự giống nhau thì phải trích xuất một phương thức chung”.

Giả sử hai luồng có cùng phép tính ban đầu:

~~~java
long reserveForRetail(long requestedVnd) {
    return Math.addExact(requestedVnd, 30_000L);
}

long estimateForWholesale(long requestedVnd) {
    return Math.addExact(requestedVnd, 30_000L);
}
~~~

Hiện tại hai phép tính giống nhau. Nhưng giả sử **retail** cộng phí giao hàng cố định còn **wholesale** cộng một khoản dự phòng logistics được thương lượng riêng. Nếu hai quy tắc có **lý do thay đổi độc lập**, gom vào:

~~~java
long addThirtyThousand(long amountVnd) {
    return Math.addExact(amountVnd, 30_000L);
}
~~~

có thể chỉ tạo một trừu tượng mang tên kỹ thuật mà **không mô tả quy tắc nghiệp vụ**. Khi một chính sách đổi, dễ có người sửa hàm chung và vô tình thay đổi chính sách còn lại.

Trong trường hợp đó, **chấp nhận trùng vài dòng có chủ đích** đôi khi dễ hiểu và an toàn hơn trừu tượng hóa sớm. Nếu sau này có một khái niệm chung thực sự, hãy đặt tên và gom nó dựa trên **cùng một quy tắc**, không chỉ dựa trên cùng hình thức mã.

Ngược lại, nếu hai nơi thực sự phải tính **cùng một loại thuế theo cùng chính sách duy nhất**, để công thức rải rác mới là rủi ro. Khi đó có thể trích xuất một hàm có tên nghiệp vụ và kiểm thử chung.

| Tình huống | Nên làm |
| --- | --- |
| Hai đoạn giống cú pháp nhưng là hai chính sách độc lập | Có thể giữ riêng và giải thích lý do |
| Hai nơi cùng triển khai một quy tắc phải nhất quán | Gom ở nơi sở hữu quy tắc |
| Một thay đổi ở A không được ảnh hưởng B | Tránh phụ thuộc chung không cần thiết |
| Một thay đổi của chính sách bắt buộc áp dụng cho A và B | Ưu tiên nguồn sự thật duy nhất |

Vấn đề không phải “cho phép sao chép vô hạn”, mà là **tránh nhầm lẫn giữa trùng cú pháp và trùng tri thức nghiệp vụ**.

## 7. Ngoại lệ vì tương thích ngược của API

Tên API công khai hoặc tên trường dữ liệu đã phát hành có thể không còn khớp quy ước đặt tên mới. Đổi ngay tên cũ có thể gây lỗi cho client, plugin, dữ liệu lưu trữ hoặc mã nguồn các dự án phụ thuộc.

Ví dụ một thư viện Java đã phát hành phương thức **getShipFee** nhưng nhóm thống nhất tên mới phải nói rõ đơn vị **VND**:

~~~java
public final class ShippingApi {
    public long shippingFeeVnd(long subtotalVnd) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
        return subtotalVnd >= 500_000L ? 0L : 30_000L;
    }

    /**
     * Preserved for existing callers.
     * Prefer shippingFeeVnd for new code.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public long getShipFee(long subtotalVnd) {
        return shippingFeeVnd(subtotalVnd);
    }
}
~~~

Ở đây tên **getShipFee** không theo quy ước mới, nhưng giữ lại là **ngoại lệ có lý do**:

- **Lý do:** bảo vệ client đang gọi tên cũ.
- **Phạm vi:** một phương thức chuyển tiếp, không lặp lại toàn bộ logic tính phí.
- **Kiểm chứng:** cả phương thức cũ và mới trả cùng kết quả theo hợp đồng hiện hành.
- **Hướng phát triển:** code mới dùng **shippingFeeVnd**; phương thức cũ có Javadoc và đánh dấu deprecated.
- **Giới hạn:** ví dụ giả định hai API có cùng ngữ nghĩa. Nếu phiên bản mới thay đổi cả cách tính phí, **không được** tự động chuyển tiếp làm thay đổi hành vi API cũ mà chưa có kế hoạch tương thích.

Annotation **@Deprecated** là tín hiệu khuyến nghị chuyển đổi, không tự xóa hoặc chặn người gọi. Nếu thật sự có kế hoạch loại bỏ, cần tuân thủ chính sách phiên bản, lịch di trú và thông báo tới các bên phụ thuộc.

### 7.1. Tương thích không chỉ là tên phương thức

Các quyết định có thể ảnh hưởng tới người sử dụng:

- Thứ tự và kiểu tham số, kiểu giá trị trả về.
- Loại lỗi, thời điểm lỗi và ý nghĩa của null hoặc Optional.
- JSON field name, mã HTTP và trạng thái nghiệp vụ.
- Định dạng sự kiện, tên cột DB, thứ tự xử lý thông điệp.
- Ngữ nghĩa timeout, retry và hủy.

Vì vậy, trước khi “chuẩn hóa” một API công khai, cần phân biệt **đổi cách trình bày trong mã** với **thay đổi hợp đồng**. Một tên cũ có thể được bao trong adapter tại ranh giới, trong khi code nội bộ dùng quy ước mới.

## 8. Ngoại lệ vì hiệu năng: chỉ khi có số liệu và giới hạn

Quy ước thường khuyến khích biểu thức dễ đọc, ít tối ưu hóa sớm. Nhưng ở đường xử lý nóng (*hot path*) được gọi hàng triệu lần, một tối ưu hóa nhỏ có thể có giá trị. Điều kiện là phải có **bằng chứng từ workload thực tế hoặc benchmark phù hợp**, không chỉ cảm giác “vòng lặp nhanh hơn Stream”.

Ví dụ, nếu hệ thống lặp lại việc kiểm tra mã sản phẩm bằng cùng một regex:

~~~java
public boolean isValidSku(String sku) {
    return sku != null
            && sku.matches("[A-Z][A-Z0-9-]{0,19}");
}
~~~

Trong Java, **String.matches** sử dụng cơ chế xử lý biểu thức regex cho mỗi lần gọi. Nếu kiểm tra này thực sự là điểm nóng đo được, có thể giữ **Pattern** đã biên dịch:

~~~java
import java.util.regex.Pattern;

public final class SkuValidator {
    private static final Pattern SKU =
            Pattern.compile("[A-Z][A-Z0-9-]{0,19}");

    private SkuValidator() {}

    public static boolean isValid(String sku) {
        return sku != null && SKU.matcher(sku).matches();
    }
}
~~~

**Pattern** là đối tượng có thể dùng chung giữa nhiều thread theo hợp đồng Java; mỗi lần gọi tạo **Matcher** riêng. Ví dụ này không chuyển một **Matcher mutable** thành trường static dùng chung.

Ngoại lệ hợp lý khi:

1. Có số đo cho thấy thao tác tạo/biên dịch mẫu là chi phí đáng kể.
2. Thay đổi không làm khác quy tắc validation.
3. Cấu trúc tối ưu vẫn dễ hiểu và có kiểm thử biên.
4. Benchmark đo đúng mức tải và môi trường mục tiêu.
5. Tối ưu không tạo vấn đề về bộ nhớ, đồng thời hoặc cache invalidation.

Một đo đạc nên ghi rõ **dữ liệu đầu vào, warmup, runtime, phương pháp đo và tiêu chí so sánh**. Với microbenchmark Java, dùng công cụ thích hợp như JMH khi cần, bởi JIT, GC và cách đo ngây thơ dễ làm kết quả gây hiểu nhầm. Không được tuyên bố có cải thiện hiệu năng cụ thể nếu chưa có kết quả kiểm chứng thực tế.

**Quan trọng:** nếu chỉ đang viết tài liệu giáo dục hoặc một chức năng chạy vài lần mỗi ngày, tối ưu hóa phức tạp không chắc đáng đánh đổi tính rõ ràng.

## 9. Ngoại lệ không được che giấu rủi ro

Có những trường hợp một người thấy quy ước “quá phiền” nên muốn bỏ đi:

~~~java
// Không nên viện lý do mã ngắn hơn để nối dữ liệu vào SQL.
String sql = "SELECT id FROM users WHERE name = '" + userInput + "'";
~~~

Nếu yêu cầu là tìm theo tên, cơ chế phù hợp vẫn là **PreparedStatement** với bind parameter. Không thể nói “đây chỉ là ngoại lệ cho một phương thức” để bỏ một biện pháp bảo mật bắt buộc.

Tương tự:

- Không bỏ **kiểm tra quyền truy cập** chỉ vì API nội bộ “ít người dùng”.
- Không nuốt ngoại lệ vận hành để mọi phương thức “trả kết quả giống nhau”.
- Không bỏ **try-with-resources** khi tài nguyên cần được đóng, rồi gọi đó là “đơn giản hóa”.
- Không dùng **suppress warning** để che lỗi kiểu hoặc lỗi null mà chưa hiểu nguyên nhân.
- Không thay đổi **định dạng wire protocol** mà không xét client đang sử dụng.

**Ngoại lệ trong quy ước thiết kế** khác với **ngoại lệ Java (Exception)**. Bài này dùng từ “ngoại lệ” chủ yếu theo nghĩa **đi khác quy ước mặc định có lý do**, không phải khuyến khích bắt hoặc ném Exception tùy ý.

## 10. Suppression và cấu hình công cụ: phạm vi càng hẹp càng tốt

Formatter và linter có ích vì tự động áp dụng quy ước, giúp review tập trung vào nội dung. Đôi khi một cảnh báo không phù hợp với một trường hợp đã được xem xét.

Ví dụ một adapter bắt buộc phải gọi API cũ đã bị đánh dấu deprecated để giữ tương thích:

~~~java
final class LegacyClientAdapter {
    private final LegacyService service;

    LegacyClientAdapter(LegacyService service) {
        this.service = service;
    }

    @SuppressWarnings("deprecation")
    String loadLegacyValue(long id) {
        // Chỉ bridge này dùng API cũ trong thời gian client di trú.
        return service.oldLookup(id);
    }
}
~~~

Đây là mã **minh họa** với **LegacyService** giả định có phương thức **oldLookup** đã deprecated. Việc dùng **@SuppressWarnings** phụ thuộc loại cảnh báo mà compiler hoặc công cụ hỗ trợ; annotation Java không được hiểu là tắt mọi cảnh báo của mọi linter.

Nếu suppression thật sự cần:

- Đặt ở **phạm vi nhỏ nhất** mà công cụ cho phép.
- Nêu **lý do cụ thể**, ví dụ ràng buộc tương thích với client cũ.
- Có **kiểm thử** hoặc bằng chứng rằng hành vi được bảo vệ.
- Theo dõi **điều kiện gỡ bỏ** hoặc lý do tiếp tục tồn tại.
- Không gộp nhiều cảnh báo không liên quan thành một ngoại lệ toàn module.

Đừng cấu hình tắt hẳn một loại cảnh báo trên toàn dự án chỉ vì một trường hợp chưa thuận tiện để sửa. Nếu linter tạo quá nhiều cảnh báo sai trên diện rộng, hãy xem xét **quy ước hoặc cấu hình công cụ** bằng quyết định chung thay vì mở ngoại lệ cá nhân không kiểm soát.

### 10.1. Bình luận tốt giải thích “vì sao”

Bình luận ít giá trị:

~~~java
// Dùng tên cũ vì cần dùng tên cũ.
~~~

Bình luận hữu ích hơn:

~~~java
// Giữ tên getShipFee trong API public để các client phiên bản 1.x
// tiếp tục gọi được; luồng code mới dùng shippingFeeVnd.
~~~

Bình luận trên mô tả **ràng buộc tương thích**, không chỉ lặp lại cú pháp. Khi chính sách tương thích thay đổi, bình luận và tài liệu di trú cũng phải được cập nhật.

## 11. Ghi lại quyết định ngoại lệ theo mức độ ảnh hưởng

Không phải mọi quyết định nhỏ đều cần một tài liệu kiến trúc dài. Nhưng một ngoại lệ ảnh hưởng nhiều module hoặc tồn tại lâu nên có hồ sơ ngắn để người sau không phải đoán.

| Trường | Câu hỏi cần ghi |
| --- | --- |
| **Quy ước mặc định** | Quy tắc hiện tại là gì? |
| **Ngoại lệ** | Điều gì khác so với mặc định, nằm ở tệp/lớp/API nào? |
| **Lý do** | Ràng buộc thực tế nào làm cách mặc định kém phù hợp? |
| **Các phương án** | Đã cân nhắc giữ nguyên quy ước và các cách khác chưa? |
| **Bằng chứng** | Test tương thích, benchmark, sự cố hoặc hợp đồng cụ thể nào? |
| **Rủi ro/đánh đổi** | Mất tính nhất quán, tăng phụ thuộc, chi phí duy trì gì? |
| **Biện pháp** | Test, adapter, tài liệu, cảnh báo hoặc giới hạn phạm vi nào? |
| **Xem lại** | Khi nào hoặc khi điều kiện nào thay đổi cần bỏ ngoại lệ? |

Ví dụ một quyết định ngắn:

~~~text
Quy ước: Public API mới dùng tên thể hiện đơn vị của số tiền.
Ngoại lệ: Tiếp tục cung cấp getShipFee(long) ở lớp ShippingApi.
Lý do: Client cũ đang phụ thuộc vào chữ ký phương thức công khai.
Phạm vi: Một phương thức bridge có @Deprecated.
Phương án khác: Đổi tên trực tiếp (gây breaking change),
                phát hành API song song (đã chọn cách bridge).
Bằng chứng cần giữ: Test kết quả cũ/mới tương đương ở giá trị biên.
Rủi ro: Hai tên API cùng tồn tại, có thể làm người mới nhầm.
Giảm thiểu: Javadoc hướng sang shippingFeeVnd.
Xem lại: Khi chấm dứt hỗ trợ client cũ theo chính sách phiên bản.
~~~

Với ngoại lệ chỉ về cách xuống dòng trong một biểu thức khó format, code review và một chú thích ngắn có thể đủ. Mức ghi chép nên **tỷ lệ với rủi ro và phạm vi ảnh hưởng**.

## 12. Kiểm thử để bảo vệ ngoại lệ khỏi hồi quy

Ngoại lệ có lý do cần được kiểm chứng như mọi quyết định thiết kế khác. Ví dụ với API bridge ở phần 7, kiểm thử JUnit 5 có thể bảo đảm hai tên luôn giữ cùng ngữ nghĩa trong thời gian hỗ trợ.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingApiCompatibilityTest {
    private final ShippingApi api = new ShippingApi();

    @Test
    void oldAndNewNamesAgreeBelowThreshold() {
        assertEquals(api.shippingFeeVnd(499_999L),
                api.getShipFee(499_999L));
    }

    @Test
    void oldAndNewNamesAgreeAtThreshold() {
        assertEquals(api.shippingFeeVnd(500_000L),
                api.getShipFee(500_000L));
    }

    @Test
    void oldAndNewNamesRejectNegativeValues() {
        assertThrows(IllegalArgumentException.class,
                () -> api.shippingFeeVnd(-1L));
        assertThrows(IllegalArgumentException.class,
                () -> api.getShipFee(-1L));
    }
}
~~~

JUnit 5 là thư viện kiểm thử ngoài JDK; cần dependency tương ứng. **@Deprecated** có thể phát sinh cảnh báo khi dùng API cũ trong kiểm thử, nhưng không làm kiểm thử sai. Chỉ dùng suppression cho một cảnh báo có lý do khi cấu hình kiểm thử thực sự yêu cầu.

Các ca trên có giá trị vì minh họa **khả năng tương thích giữa hai đường gọi**, đặc biệt ở giá trị biên. Nếu API cũ từng có hành vi riêng, oracle cần dựa trên **hợp đồng phiên bản cũ**, không tự động coi kết quả API mới là kết quả đúng.

### 12.1. Các loại bằng chứng khác

| Loại ngoại lệ | Bằng chứng phù hợp |
| --- | --- |
| Nhiều return để giảm lồng nhánh | Kiểm thử các nhánh và ngoại lệ, review điều khiển luồng |
| Giữ tên API cũ | Contract test, test client tương thích, kế hoạch deprecation |
| Tối ưu đường xử lý nóng | Benchmark/workload có phương pháp, test kết quả và đồng thời |
| Cho phép trùng hai quy tắc độc lập | Test riêng cho từng quy tắc, tài liệu về lý do thay đổi độc lập |
| Sử dụng API cũ trong adapter | Test hành vi adapter, giới hạn phạm vi sử dụng |
| Bỏ qua một cảnh báo công cụ | Bằng chứng cảnh báo không áp dụng và guardrail bù trừ |

**Đừng coi một test xanh là bằng chứng cho mọi đánh đổi.** Kiểm thử hành vi có thể cho biết kết quả không đổi, nhưng không chứng minh rằng code dễ đọc hơn. Benchmark đo hiệu năng có thể không chứng minh tính đúng nghiệp vụ. Cần chọn bằng chứng tương ứng với lý do ngoại lệ.

## 13. Quy trình review khi một thay đổi đi khác quy ước

Một cách thảo luận hiệu quả trong pull request:

1. **Xác nhận quy ước mặc định:** Tránh tranh luận khi các bên chưa thống nhất đang áp dụng quy tắc nào.
2. **Yêu cầu lý do thuộc bối cảnh:** Tương thích, tính rõ ràng, hiệu năng, bảo mật hay giới hạn nền tảng?
3. **Kiểm tra giải pháp mặc định:** Có thể tuân thủ quy ước mà vẫn đáp ứng mục tiêu không?
4. **So sánh các phương án:** Đánh giá tính đúng, dễ hiểu, khả năng thay đổi, chi phí và rủi ro.
5. **Thu hẹp phạm vi:** Dùng adapter, helper, comment hoặc suppression tại vị trí nhỏ nhất.
6. **Xác minh hợp đồng:** Test giá trị biên, lỗi, tác dụng phụ, client cũ và hiệu năng khi liên quan.
7. **Ghi lại quyết định:** Mô tả ngắn trong PR, code comment hoặc tài liệu thiết kế nếu có ảnh hưởng lâu dài.
8. **Xem lại định kỳ:** Khi điều kiện ban đầu hết hiệu lực, loại bỏ ngoại lệ để giảm chi phí duy trì.

Trong review, câu hỏi **“quy ước này bảo vệ thuộc tính chất lượng nào?”** thường hữu ích hơn **“tệp này có theo quy ước không?”**. Khi cả nhóm hiểu mục đích, việc giữ mặc định hoặc chấp nhận ngoại lệ trở nên có căn cứ hơn.

### 13.1. Nếu ngoại lệ xuất hiện thường xuyên

Nếu rất nhiều phương thức cần “ngoại lệ” cho cùng một quy tắc, có thể chính **quy ước đang không còn phù hợp**. Ví dụ, nếu guard clause liên tục cho kết quả dễ hiểu hơn và không tạo rủi ro, nhóm có thể điều chỉnh quy ước chính thức.

Thay đổi quy ước chung cần:

- Có mục tiêu và ví dụ minh họa.
- Xác định ranh giới áp dụng cho mã mới và mã cũ.
- Cập nhật formatter/linter hoặc checklist liên quan.
- Tránh thay đổi hàng loạt chỉ để “làm đẹp”, gây nhiễu các diff nghiệp vụ.
- Thống nhất cách xử lý module legacy trong quá trình chuyển đổi.

**Nhiều ngoại lệ cùng loại có thể là tín hiệu cần sửa quy tắc chung**, không phải lý do tắt hết kiểm tra.

## 14. Các hiểu nhầm thường gặp

**“Có quy ước thì không được có ngoại lệ.”** Quy ước là công cụ giảm phức tạp. Ngoại lệ có lý do và được giới hạn có thể giúp giữ mục đích đó trong một hoàn cảnh đặc biệt.

**“Có lý do cá nhân là đủ.”** Sở thích hoặc thói quen không chứng minh rằng lợi ích lớn hơn chi phí mất nhất quán. Cần lý do gắn với hành vi hoặc ràng buộc thực tế.

**“Mã chạy đúng thì có thể bỏ formatter, quy ước tên và tài liệu.”** Tính đúng chỉ là một chiều chất lượng. Cách diễn đạt nhất quán giúp người sau hiểu, review và sửa an toàn.

**“Đổi tên cho đồng bộ luôn là refactor an toàn.”** Đổi một API public, tên trường JSON hoặc giao thức sự kiện có thể làm hỏng bên gọi, dù mã nội bộ vẫn biên dịch.

**“Không được lặp bất kỳ dòng mã nào.”** Hai đoạn trùng cú pháp chưa chắc thể hiện cùng một quy tắc. Cần xem **lý do thay đổi**, không chỉ số dòng lặp.

**“Tối ưu hiệu năng luôn là lý do hợp lệ để phá quy ước.”** Phải có bằng chứng về điểm nghẽn và xác nhận không làm sai hợp đồng hoặc tăng rủi ro quá mức.

**“Chỉ cần @SuppressWarnings là vấn đề biến mất.”** Suppression che một cảnh báo của công cụ, không sửa lỗi tiềm ẩn. Cần hiểu nguyên nhân và giới hạn phạm vi.

**“Ngoại lệ được chấp nhận một lần là đúng mãi.”** Khi client đã di trú, hạn chế nền tảng thay đổi hoặc benchmark không còn đúng, ngoại lệ nên được xem xét lại.

## 15. Tình huống luyện tập

Một nhóm xây dựng dịch vụ đơn hàng Java có các quy ước:

~~~text
A. Tên public method mới phải có ý nghĩa nghiệp vụ rõ ràng.
B. Ưu tiên một lệnh return trong mỗi phương thức.
C. Không được lặp logic.
D. Mỗi biến cục bộ khai báo kiểu tường minh.
E. Cảnh báo compiler và linter phải được xử lý.
F. API không được thay đổi hành vi ngoài hợp đồng đã phát hành.
~~~

Nhóm đang xem xét bốn pull request:

1. **PR-1:** đổi một phương thức public cũ tên **getShipFee** thành **shippingFeeVnd**, xóa ngay tên cũ để “chuẩn quy ước”; nhiều client ngoài module còn sử dụng phương thức cũ.
2. **PR-2:** thay ba mức lồng if bằng các guard clause có return sớm, giữ nguyên kết quả, lỗi và cleanup.
3. **PR-3:** gom hai phép tính trông giống nhau của **retail** và **wholesale** vào một helper chung, trong khi mỗi chính sách có người phụ trách và lịch thay đổi riêng.
4. **PR-4:** dùng **@SuppressWarnings** trên cả class vì một lời gọi API deprecated ở một adapter.

Hãy phân tích theo các câu hỏi:

1. PR nào đang **áp dụng quy ước một cách máy móc** và có nguy cơ gây tác dụng ngược?
2. Ngoại lệ nào nên được cho phép tại phạm vi nhỏ hơn? Vì sao?
3. Trường hợp nào cần **kiểm thử tương thích**, trường hợp nào cần **kiểm thử nhánh hoặc test nghiệp vụ độc lập**?
4. PR-4 nên giới hạn suppression ở đâu, và cần ghi lại lý do gì?
5. Khi nào việc chấp nhận ngoại lệ nên dẫn tới **cập nhật quy ước chung**?
6. Đề xuất một mẫu ghi quyết định ngắn cho trường hợp giữ API cũ.

**Gợi ý đối chiếu:** PR-1 không nên xóa ngay tên API đang được client dùng; có thể cung cấp tên mới đồng thời giữ adapter cũ có deprecation và test tương thích. PR-2 có thể là ngoại lệ hợp lý đối với quy tắc một return khi các nhánh rõ hơn và không ảnh hưởng cleanup; nếu nhiều trường hợp tương tự, nên xem lại quy ước. PR-3 cần xem xét hai phép tính có **cùng tri thức nghiệp vụ** hay chỉ tình cờ có cùng giá trị; gom máy móc có thể gây phụ thuộc không cần thiết. PR-4 nên thu suppression tới một phương thức hoặc vị trí nhỏ nhất được công cụ hỗ trợ, kèm giải thích ràng buộc tương thích và điều kiện loại bỏ.

## 16. Ghi nhớ

- **Quy ước** tạo sự nhất quán để giảm công sức đọc và thay đổi mã; nó không phải mục tiêu độc lập với chất lượng phần mềm.
- Một **ngoại lệ có lý do** cần có bối cảnh cụ thể, so sánh đánh đổi, phạm vi hẹp, bằng chứng phù hợp và điều kiện xem lại.
- Có thể linh hoạt ở **cách trình bày hoặc cấu trúc thiết kế** khi điều đó làm mã rõ và an toàn hơn; không dùng ngoại lệ để bỏ **bất biến nghiệp vụ, kiểm soát bảo mật hoặc hợp đồng công khai**.
- **Tương thích API, quy tắc nghiệp vụ độc lập và hiệu năng đã đo** là những lý do có thể hợp lệ; sở thích cá nhân và tối ưu chưa có số liệu thường không đủ.
- Khi một ngoại lệ lặp lại ở nhiều nơi, hãy cân nhắc **cải tiến quy ước chung** thay vì tạo hàng loạt miễn trừ khó duy trì.
