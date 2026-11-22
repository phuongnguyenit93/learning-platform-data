# Tiến hóa API Java: interface con, adapter và deprecation

## 1. Vì sao cần một lộ trình chuyển đổi?

API công khai thường được nhiều ứng dụng, thư viện và nhóm phát triển sử dụng. Sau khi phát hành, thay đổi chữ ký phương thức hoặc thêm phương thức bắt buộc vào interface có thể khiến mã nguồn người dùng không biên dịch được, hoặc khiến chương trình đã biên dịch gặp lỗi khi chạy. Vì vậy, tiến hóa API cần có các bước chuyển tiếp và quy tắc tương thích rõ ràng.

Ba kỹ thuật thường được kết hợp:

- **Interface con:** tạo một hợp đồng mới mở rộng hợp đồng cũ, để khả năng mới có kiểu riêng mà không bắt buộc mọi implementation cũ thay đổi ngay.
- **Adapter:** bọc implementation cũ hoặc mới và chuyển đổi lời gọi giữa hai hợp đồng khi phép chuyển đổi có thể được xác định rõ.
- **Deprecation:** đánh dấu API cũ là không còn được khuyến nghị, chỉ ra phương án thay thế và cho người dùng thời gian di chuyển trước khi cân nhắc loại bỏ.

Mỗi kỹ thuật giải quyết một phần khác nhau. Interface con thể hiện quan hệ kiểu; adapter chuyển tiếp hoặc chuyển đổi hành vi; deprecation thông báo vòng đời API. Chúng không tự động bảo đảm mọi thay đổi đều tương thích. Trước khi phát hành, cần xác định mục tiêu là tương thích mã nguồn, tương thích binary, tương thích hành vi hay cả ba.

## 2. Mục tiêu tương thích khi di chuyển

Trước khi tạo cầu nối, xác định client cũ cần **biên dịch lại được** với API mới (source), **dùng bytecode cũ** với thư viện mới (binary), hay **giữ nguyên hành vi đã cam kết** (behavioral). Interface con giúp tránh sửa hợp đồng cũ; adapter giúp chuyển lời gọi giữa hai hợp đồng; deprecation báo cách và thời điểm chuyển đổi. Một adapter có thể giải quyết lỗi kiểu nhưng vẫn làm mất dữ liệu hoặc thay đổi ngoại lệ, nên kiểm thử cả ba mục tiêu.

## 3. Lộ trình tiến hóa API

1. **Khảo sát hợp đồng hiện tại.** Liệt kê kiểu và phương thức công khai, các implementation bên ngoài, client đang dùng API và hành vi được mong đợi.
2. **Thiết kế hợp đồng mới.** Xác định khả năng bổ sung, phần đổi nghĩa và phần không thể chuyển đổi tự động. Giữ chữ ký đã phát hành nếu có thể.
3. **Thêm API mới.** Tạo interface con hoặc kiểu mới cho khả năng mới; giữ API cũ hoạt động trong giai đoạn chuyển tiếp.
4. **Cung cấp adapter.** Chuyển tiếp các thao tác tương đương và xử lý rõ những trường hợp không thể ánh xạ.
5. **Đánh dấu deprecation.** Nêu lý do, API thay thế, khác biệt hành vi và thời điểm dự kiến loại bỏ nếu đã có kế hoạch.
6. **Kiểm thử và theo dõi.** Kiểm tra client cũ/mới, implementation cũ/mới, adapter và các trường hợp không hỗ trợ.
7. **Loại bỏ theo chính sách phát hành.** Chỉ bỏ API cũ sau thời gian chuyển tiếp phù hợp với cam kết tương thích và mức độ phụ thuộc của người dùng.

Với thư viện có người dùng bên ngoài, thường nên để API cũ và mới cùng tồn tại trong ít nhất một giai đoạn deprecation. Lộ trình cụ thể phụ thuộc vào chính sách phiên bản và mức độ ảnh hưởng của thay đổi.

## 4. Dùng interface con để mở rộng hợp đồng

Giả sử API cũ chỉ nhận tên, còn API mới cần thêm locale để tạo lời chào theo ngôn ngữ. Ta có thể tạo interface mới kế thừa interface cũ, bổ sung phương thức mới và cung cấp default method cho chữ ký cũ:

~~~java
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}

record GreetingRequest(String name, String locale) {
}

interface GreetingService extends LegacyGreeting {
    String greet(GreetingRequest request);

    @Override
    default String greet(String name) {
        return greet(new GreetingRequest(name, "en"));
    }
}
~~~

`GreetingService` là interface con của `LegacyGreeting`, vì vậy đối tượng triển khai GreetingService cũng có thể được dùng ở nơi yêu cầu LegacyGreeting. Default method chuyển lời gọi cũ `greet(String)` sang phương thức mới với locale mặc định là `en`.

Tuy nhiên, implementation cũ chỉ triển khai LegacyGreeting **không tự động trở thành** GreetingService. Quan hệ kế thừa không biến một đối tượng đã tồn tại thành instance của interface con. Adapter có thể làm cầu nối cho trường hợp này.

Default method phải có ngữ nghĩa hợp lý. Trong ví dụ, locale `en` là quyết định có chủ đích. Nếu không có giá trị mặc định phù hợp, hãy yêu cầu client gọi API mới hoặc trả lỗi rõ ràng thay vì tự đặt một giá trị tùy tiện.

## 5. Dùng adapter để bọc implementation cũ

Adapter triển khai interface mới nhưng nhận một đối tượng interface cũ ở constructor. Khi client gọi phương thức mới, adapter chuyển yêu cầu sang thao tác cũ nếu có thể:

~~~java
final class LegacyGreetingAdapter implements GreetingService {
    private final LegacyGreeting legacy;

    LegacyGreetingAdapter(LegacyGreeting legacy) {
        this.legacy = legacy;
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!"en".equals(request.locale())) {
            throw new IllegalArgumentException(
                    "Legacy API supports only en");
        }
        return legacy.greet(request.name());
    }
}
~~~

Adapter này chỉ hỗ trợ locale `en`, vì API cũ không nhận thông tin locale. Với locale khác, nó ném lỗi rõ ràng thay vì giả vờ đã hỗ trợ bản địa hóa. Nếu API cũ biểu diễn đủ dữ liệu, adapter có thể chuyển đổi tự động; nếu không, tài liệu phải nêu rõ giới hạn.

Có hai chiều chuyển tiếp thường gặp:

- **Cũ sang mới:** bọc implementation cũ để client đang cần interface mới có thể sử dụng nó.
- **Mới sang cũ:** cung cấp cách nhìn tương thích cho client cũ khi implementation nội bộ đã chuyển sang API mới. Default method trên interface con có thể đủ cho chiều này; nếu hai mô hình khác nhau nhiều, có thể cần adapter riêng.

Không phải lúc nào cũng cần hai adapter. Chỉ tạo cầu nối cần thiết và tránh nhân đôi logic nếu default method hoặc một facade đã đáp ứng hợp đồng.

## 6. Ví dụ Java 17 hoàn chỉnh

Chương trình sau minh họa cả hai chiều. ModernGreetingService triển khai hợp đồng mới nhưng vẫn được client cũ dùng qua LegacyGreeting. Ngược lại, LegacyGreetingAdapter bọc implementation cũ để client mới gọi qua GreetingService.

~~~java
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}

record GreetingRequest(String name, String locale) {
}

interface GreetingService extends LegacyGreeting {
    String greet(GreetingRequest request);

    @Override
    default String greet(String name) {
        return greet(new GreetingRequest(name, "en"));
    }
}

final class SimpleLegacyGreeting implements LegacyGreeting {
    @Override
    public String greet(String name) {
        return "Legacy hello, " + name;
    }
}

final class LegacyGreetingAdapter implements GreetingService {
    private final LegacyGreeting legacy;

    LegacyGreetingAdapter(LegacyGreeting legacy) {
        this.legacy = legacy;
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!"en".equals(request.locale())) {
            throw new IllegalArgumentException(
                    "Legacy API supports only en");
        }
        return legacy.greet(request.name());
    }
}

final class ModernGreetingService implements GreetingService {
    @Override
    public String greet(GreetingRequest request) {
        return switch (request.locale()) {
            case "en" -> "Hello, " + request.name();
            case "vi" -> "Xin chào, " + request.name();
            default -> throw new IllegalArgumentException(
                    "Unsupported locale: " + request.locale());
        };
    }
}

public class Main {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) {
        GreetingService modern = new ModernGreetingService();

        // Client cũ vẫn dùng implementation mới qua kiểu cũ.
        LegacyGreeting oldView = modern;
        System.out.println("Old client -> " + oldView.greet("Linh"));

        // Client mới dùng implementation cũ qua adapter.
        GreetingService adapted =
                new LegacyGreetingAdapter(new SimpleLegacyGreeting());
        System.out.println("New client -> "
                + adapted.greet(new GreetingRequest("An", "en")));

        // Default method chuyển lời gọi cũ sang API mới.
        System.out.println("Default bridge -> " + adapted.greet("Mai"));

        try {
            adapted.greet(new GreetingRequest("An", "vi"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Unsupported feature -> " + ex.getMessage());
        }
    }
}
~~~

Lưu toàn bộ chương trình vào `Main.java`, rồi biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Kết quả stdout chính xác:

~~~text
Old client -> Hello, Linh
New client -> Legacy hello, An
Default bridge -> Legacy hello, Mai
Unsupported feature -> Legacy API supports only en
~~~

Dòng đầu cho thấy implementation mới vẫn được dùng qua kiểu cũ nhờ default method. Dòng thứ hai cho thấy adapter bọc implementation cũ để đáp ứng API mới. Dòng thứ ba minh họa bridge mặc định; dòng cuối thể hiện adapter từ chối yêu cầu mà API cũ không thể biểu diễn.

Switch expression trong ví dụ là cú pháp chuẩn từ Java 14, nên không cần bật preview trên Java 17. Các kiểu không khai báo public có thể cùng nằm trong tệp với public class Main.

## 7. Deprecation có chủ đích

Dùng `@Deprecated` để báo rằng API không còn được khuyến nghị. Từ Java 9, annotation hỗ trợ hai thuộc tính quan trọng:

- `since`: phiên bản bắt đầu deprecate API, ví dụ `since = "2.0"`.
- `forRemoval`: cho biết API có dự kiến bị loại bỏ hay chưa. `false` phù hợp khi mới khuyến cáo chuyển đổi; `true` biểu thị ý định loại bỏ rõ ràng hơn.

Annotation không tự di chuyển người dùng, không tự tạo adapter và cũng không xóa phương thức. Hãy bổ sung JavaDoc bằng `@deprecated` để nêu lý do và API thay thế. Ví dụ minh họa riêng sau đây dùng lại tên kiểu trong chương trình chính, nên không cần dán đoạn này vào cùng tệp `Main.java`:

~~~java
/**
 * @deprecated Use {@link GreetingService} instead.
 *     This legacy API does not support locale selection.
 */
@Deprecated(since = "2.0", forRemoval = false)
interface LegacyGreeting {
    String greet(String name);
}
~~~

Giữ hướng dẫn nhất quán giữa annotation, JavaDoc, tài liệu phát hành và ví dụ. Chỉ đặt `forRemoval = true` khi có ý định loại bỏ thực tế và lộ trình phù hợp với chính sách tương thích của thư viện.

## 8. Công bố và duy trì giai đoạn chuyển tiếp

Khi giới thiệu API mới, tiếp tục phát hành các chữ ký cũ theo thời hạn tương thích đã cam kết; công bố adapter, JavaDoc deprecation và hướng dẫn thay thế cùng một phiên bản. Theo dõi nơi còn dùng API cũ, thử chạy bytecode client từ bản trước và đo những trường hợp adapter không biểu diễn được. Chỉ chuyển `forRemoval` sang `true` khi kế hoạch loại bỏ đã rõ, và tránh xóa API cũ ngay sau khi phát hành kiểu mới.

## 9. Những giới hạn cần xử lý trong adapter

Một adapter tốt thực hiện phép ánh xạ có thể giải thích và công bố phần không tương thích. Cần chú ý:

- **Mất thông tin:** API cũ không có trường dữ liệu mới. Quy định giá trị mặc định, từ chối yêu cầu hoặc yêu cầu một chính sách chuyển đổi rõ ràng.
- **Khác biệt lỗi:** API mới có thể dùng kiểu kết quả hoặc exception khác. Adapter phải chuyển đổi có chủ đích và giữ nguyên nguyên nhân cần thiết.
- **Khác biệt vòng đời:** API mới có thể yêu cầu đóng tài nguyên, hủy tác vụ hoặc quản lý trạng thái mà API cũ không hỗ trợ.
- **Vòng gọi đệ quy:** nếu default method gọi API mới nhưng adapter lại gọi ngược phương thức cũ, hãy chắc chắn có điểm triển khai thực sự kết thúc lời gọi. Hai bridge gọi qua lại có thể gây đệ quy vô hạn.
- **Trạng thái và luồng:** nếu API mới bổ sung thread-safety, tính bất biến hoặc đồng bộ, adapter chỉ nên cam kết điều mà nó thực sự bảo đảm.

Ghi giới hạn trong JavaDoc và kiểm thử các trường hợp không thể ánh xạ. Adapter minh bạch có thể từ chối thao tác không được hỗ trợ; âm thầm trả về giá trị giả thường gây lỗi khó phát hiện hơn.

## 10. Kiểm thử lộ trình di chuyển

1. **Implementation cũ:** xác nhận class chỉ triển khai interface cũ vẫn hoạt động với phiên bản thư viện được hỗ trợ.
2. **Implementation mới:** xác nhận lớp mới triển khai interface con và hoạt động qua cả kiểu mới lẫn kiểu cũ.
3. **Adapter:** kiểm tra dữ liệu, kết quả, exception và các trường hợp không được hỗ trợ.
4. **Client cũ và mới:** biên dịch client cũ với API cũ và kiểm tra nó trong môi trường nâng cấp được hỗ trợ; biên dịch client mới với API mới.
5. **Kiểm thử tương thích:** nếu cam kết binary compatibility, dùng công cụ kiểm tra API/binary hoặc bộ kiểm thử tương thích.
6. **Tài liệu:** kiểm tra hướng dẫn migration, ví dụ, JavaDoc deprecation và thông báo phát hành.

Chỉ chạy test sau khi biên dịch lại toàn bộ mã nguồn không đủ để chứng minh binary compatibility. Khi thư viện có cam kết này, giữ artifact đã biên dịch từ phiên bản trước trong bộ kiểm thử.

## 11. Chọn kỹ thuật theo tình huống

| Tình huống | Hướng xử lý |
|---|---|
| Muốn bổ sung khả năng nhưng giữ kiểu cũ làm hợp đồng cơ sở | Tạo interface con và đặt phương thức mới ở đó. |
| Client cũ cần dùng implementation mới | Cho kiểu mới tương thích với kiểu cũ qua interface con và default method có ngữ nghĩa hợp lệ. |
| Client mới cần dùng implementation chỉ triển khai API cũ | Viết adapter từ interface cũ sang interface mới. |
| Có hành vi mặc định đúng cho mọi implementation cũ | Cân nhắc default method sau khi kiểm tra xung đột và ngữ nghĩa. |
| Hai API khác nhau đáng kể về dữ liệu hoặc hành vi | Thiết kế phép chuyển đổi tường minh; có thể cần API mới độc lập. |
| API cũ đã có lựa chọn thay thế ổn định | Đánh dấu deprecated, hướng dẫn migration và lên kế hoạch loại bỏ theo chính sách phiên bản. |

Không có một mẫu duy nhất cho mọi thay đổi. Quyết định dựa trên số lượng implementation bên ngoài, mức tương thích đã cam kết, khác biệt ngữ nghĩa và chi phí hỗ trợ hai hợp đồng trong giai đoạn chuyển tiếp.

## 12. Lỗi thường gặp

- **Thêm phương thức abstract trực tiếp vào interface công khai mà không đánh giá tác động.** Implementation bên ngoài có thể không biên dịch hoặc không đáp ứng lời gọi mới.
- **Cho rằng interface con tự biến implementation cũ thành implementation mới.** Cần adapter hoặc thay đổi rõ ràng ở class triển khai.
- **Dùng default method với giá trị tùy tiện.** Chỉ dùng khi mặc định đúng và được tài liệu hóa.
- **Đánh dấu deprecated nhưng không nêu phương án thay thế.** Người dùng cần biết kiểu/phương thức nào nên dùng và khác biệt gì.
- **Bật `forRemoval = true` khi chưa có lộ trình.** Annotation phải phản ánh ý định phát hành thực tế.
- **Bỏ qua dữ liệu bị mất trong adapter.** Không âm thầm bỏ locale, trạng thái, lỗi hoặc dữ liệu mà API mới cần.
- **Chỉ kiểm thử sau khi biên dịch lại toàn bộ dự án.** Cách đó không chứng minh binary cũ còn tương thích.
- **Xóa API cũ ngay khi tạo API mới.** Giữ giai đoạn chuyển tiếp phù hợp với cam kết của thư viện.

## 13. Ghi nhớ

Tiến hóa API an toàn cần hợp đồng mới rõ ràng, cầu nối có hành vi xác định và thông báo deprecation đủ sớm. Interface con mở rộng khả năng mà vẫn giữ kiểu cũ làm hợp đồng cơ sở; adapter giúp dùng implementation cũ trong API mới hoặc ngược lại; `@Deprecated` báo cho người dùng biết đường di chuyển. Hãy phân biệt source, binary và behavioral compatibility, kiểm tra giới hạn ánh xạ, thử nghiệm với implementation/client cũ và chỉ loại bỏ API sau giai đoạn chuyển tiếp theo chính sách phiên bản.