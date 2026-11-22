# Mốc Java 17 cho sealed class và sealed interface

Java 17 đánh dấu thời điểm **sealed classes và sealed interfaces trở thành tính năng chính thức của ngôn ngữ Java**. Chúng cho phép tác giả API kiểm soát những kiểu nào được kế thừa hoặc triển khai trực tiếp một kiểu cha. Điều này hữu ích khi API muốn công bố một tập hợp biến thể có chủ đích, nhưng vẫn cần cho phép một số nhánh mở rộng.

Sealed types liên quan trực tiếp đến tiến hóa API: chúng làm rõ phần nào của hệ phân cấp là do thư viện kiểm soát, phần nào được phép mở rộng, và những thay đổi nào cần được xem xét khi phát hành phiên bản mới.

## 1. Mốc lịch sử và cú pháp ổn định

Sealed classes được thử nghiệm dưới dạng preview trong JDK 15, tiếp tục ở JDK 16, rồi được hoàn thiện trong JDK 17 theo JEP 409. Từ Java 17, có thể dùng `sealed`, `permits` và `non-sealed` như cú pháp chính thức mà không bật preview features.

Ví dụ khai báo một interface chỉ cho phép hai kiểu trực tiếp:

~~~java
sealed interface ApiResult permits ApiSuccess, ApiFailure {
}
~~~

`ApiSuccess` và `ApiFailure` phải là các kiểu con trực tiếp của `ApiResult`. Mỗi kiểu con trực tiếp phải xác định rõ nhánh của nó sẽ đóng lại, tiếp tục được kiểm soát hay mở ra cho các kiểu khác.

~~~java
record ApiSuccess(String value) implements ApiResult {
}

record ApiFailure(int code, String message) implements ApiResult {
}
~~~

Hai record này là final ngầm định theo quy tắc của Java, vì vậy đáp ứng yêu cầu của sealed interface. Chúng không cần ghi thêm từ khóa `final`.

## 2. Ba lựa chọn cho kiểu con trực tiếp

Một class hoặc interface được liệt kê trong `permits` phải khai báo cách nhánh của nó tiếp tục tồn tại:

| Khai báo | Ý nghĩa trong hệ phân cấp |
|---|---|
| `final` | Đóng nhánh tại class này; không cho class khác kế thừa nó. |
| `sealed` | Tiếp tục giới hạn kiểu con trực tiếp bằng một danh sách `permits` riêng. |
| `non-sealed` | Mở nhánh này để các kiểu khác có thể kế thừa hoặc triển khai nó mà không cần được liệt kê trong `permits` của sealed type gốc. |

Record luôn là `final` ngầm định. Một enum không có hằng nào khai báo thân lớp riêng là `final` ngầm định; enum có ít nhất một hằng với thân lớp riêng là `sealed` ngầm định. Interface không thể khai báo `final`; nếu interface là kiểu con trực tiếp của sealed type thì nó phải là `sealed` hoặc `non-sealed`.

Ví dụ về một tầng được kiểm soát:

~~~java
sealed interface ApiResult permits ApiSuccess, ApiFailure, ApiDeferred {
}

sealed class ApiFailure implements ApiResult
        permits NotFoundFailure, ValidationFailure {
}

final class NotFoundFailure extends ApiFailure {
}

final class ValidationFailure extends ApiFailure {
}
~~~

Đây là đoạn minh họa quan hệ kiểu, không phải chương trình hoàn chỉnh. `ApiFailure` có danh sách `permits` riêng vì nó là một sealed class. Hai kiểu con của nó đóng nhánh bằng `final`.

Một nhánh mở có thể được khai báo như sau:

~~~java
non-sealed interface ApiDeferred extends ApiResult {
    String retryAfter();
}

final class RetryLater implements ApiDeferred {
    @Override
    public String retryAfter() {
        return "30 seconds";
    }
}
~~~

`ApiDeferred` vẫn phải xuất hiện trong danh sách `permits` của `ApiResult`, vì nó là kiểu con trực tiếp. Nhưng `RetryLater` chỉ triển khai `ApiDeferred`; nó không cần xuất hiện trong danh sách của `ApiResult`, vì quan hệ đó là gián tiếp.

## 3. Quy tắc về package, module và danh sách permits

Java áp dụng một số ràng buộc để sealed hierarchy được kiểm soát:

- Các kiểu được nêu trong `permits` phải thực sự là kiểu con trực tiếp của sealed class hoặc sealed interface đó.
- Trong named module, sealed type và các kiểu con trực tiếp được cho phép phải thuộc cùng module.
- Trong unnamed module, sealed type và các kiểu con trực tiếp được cho phép phải thuộc cùng package.
- Mỗi kiểu con trực tiếp phải là `final`, `sealed` hoặc `non-sealed`, trừ các kiểu như record vốn final ngầm định.
- Nếu bỏ mệnh đề `permits`, Java suy ra các kiểu con được cho phép từ những khai báo phù hợp trong cùng compilation unit.

Những giới hạn này có ý nghĩa với API công khai. Một sealed interface trong thư viện không thể được triển khai tùy ý bởi một class ở module bên ngoài. Nếu cần hỗ trợ phần mở rộng của bên thứ ba, API có thể cung cấp một nhánh `non-sealed` làm điểm mở rộng, hoặc chọn một interface không sealed ngay từ đầu.

## 4. Ví dụ hoàn chỉnh chạy trên Java 17

Lưu chương trình sau thành file `SealedApiDemo.java`. Ví dụ thể hiện một API kết quả có hai biến thể được đóng và một nhánh trì hoãn có thể mở rộng. Chương trình dùng pattern matching với `instanceof`, đã là tính năng chính thức trước Java 17; không dùng preview switch patterns.

~~~java
public class SealedApiDemo {
    public static void main(String[] args) {
        ApiResult[] results = {
            new ApiSuccess("created"),
            new ApiFailure(404, "Not found"),
            new RetryLater("30 seconds")
        };

        for (ApiResult result : results) {
            if (result instanceof ApiSuccess success) {
                System.out.println("SUCCESS: " + success.value());
            } else if (result instanceof ApiFailure failure) {
                System.out.println(
                        "ERROR " + failure.code() + ": " + failure.message());
            } else if (result instanceof ApiDeferred deferred) {
                System.out.println("DEFERRED: retry after " + deferred.retryAfter());
            }
        }
    }
}

sealed interface ApiResult
        permits ApiSuccess, ApiFailure, ApiDeferred {
}

record ApiSuccess(String value) implements ApiResult {
}

record ApiFailure(int code, String message) implements ApiResult {
}

non-sealed interface ApiDeferred extends ApiResult {
    String retryAfter();
}

final class RetryLater implements ApiDeferred {
    private final String delay;

    RetryLater(String delay) {
        this.delay = delay;
    }

    @Override
    public String retryAfter() {
        return delay;
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 SealedApiDemo.java
java SealedApiDemo
~~~

Stdout chính xác:

~~~text
SUCCESS: created
ERROR 404: Not found
DEFERRED: retry after 30 seconds
~~~

Các kiểu phụ trợ không khai báo `public` nên có thể cùng nằm trong file với lớp `public` `SealedApiDemo`. Nếu chuyển ví dụ sang thư viện thật, cần thiết kế package/module và mức truy cập phù hợp với hợp đồng API.

## 5. Sealed types giúp định hình tiến hóa API ra sao?

Giả sử phiên bản đầu của thư viện công bố:

~~~java
public sealed interface ApiResult
        permits ApiSuccess, ApiFailure {
}
~~~

Hợp đồng cho biết mọi kiểu triển khai trực tiếp đều thuộc danh sách được kiểm soát. Người dùng API có thể dựa vào tập hợp biến thể đã công bố khi viết xử lý nghiệp vụ và kiểm thử.

Nếu phiên bản sau cần bổ sung kết quả trì hoãn, thư viện có thể mở rộng danh sách một cách tường minh:

~~~java
public sealed interface ApiResult
        permits ApiSuccess, ApiFailure, ApiDeferred {
}
~~~

Sau đó thư viện khai báo `ApiDeferred` là `non-sealed` nếu muốn cho phép các kiểu khác tiếp tục triển khai nhánh này. Nếu nhánh mới cũng cần được kiểm soát chặt chẽ, có thể dùng một interface hoặc class `sealed` với danh sách `permits` riêng.

Việc thay đổi danh sách cho phép là một thay đổi hợp đồng API cần được xem xét khi phát hành. Trước khi công bố phiên bản mới, hãy biên dịch lại các module phụ thuộc và kiểm tra các trường hợp xử lý mọi biến thể. Mức độ ảnh hưởng phụ thuộc vào cách client sử dụng API, phiên bản Java và cách mã client được biên dịch.

Sealed type tạo ra sự cân bằng giữa tính ổn định và khả năng mở rộng:

- **Tập biến thể đóng:** phù hợp với các kết quả, trạng thái hoặc kiểu dữ liệu mà thư viện muốn kiểm soát.
- **Nhánh mở có chủ đích:** phù hợp khi cần một điểm mở rộng dành cho các implementation khác.
- **Interface mở:** phù hợp khi mục tiêu chính là cho phép client bên ngoài tự triển khai nhiều kiểu mà thư viện không thể liệt kê trước.

Không nên seal một interface công khai chỉ vì muốn dùng cú pháp mới. Hãy chọn nó khi giới hạn kiểu con trực tiếp là một phần có chủ đích của thiết kế API.

## 6. Tác động tới switch và xử lý đầy đủ các nhánh

Sealed hierarchy cung cấp thông tin về các kiểu con trực tiếp mà trình biên dịch có thể dùng để kiểm tra tính đầy đủ trong những cấu trúc ngôn ngữ hỗ trợ việc đó. Điều này đặc biệt hữu ích với pattern matching for `switch` trong Java hiện đại.

Cần phân biệt mốc ngôn ngữ: pattern matching for `switch` vẫn là preview trong Java 17 và chỉ trở thành tính năng chính thức trong Java 21. Vì vậy, ví dụ chạy bằng `--release 17` ở trên sử dụng `instanceof` thay vì pattern switch.

Khi một thư viện thêm biến thể mới, client dùng switch expression exhaustive có thể cần cập nhật các nhánh khi biên dịch lại. Ngay cả khi client hiện tại dùng `if/else`, logic cũng có thể cần được xem xét để không bỏ qua một biến thể mới. Sealed giúp trình biên dịch phát hiện một số trường hợp thiếu nhánh, nhưng không tự bảo đảm mọi logic nghiệp vụ đã xử lý đúng.

Với nhánh `non-sealed`, cần đặc biệt cẩn thận: có thể tồn tại nhiều kiểu con gián tiếp hơn danh sách ở sealed type gốc. Mã xử lý nên xem xét abstraction mở đó như một nhóm, thay vì giả định rằng chỉ có một implementation cụ thể.

## 7. Lựa chọn sealed, non-sealed hay interface mở

Dùng `sealed` khi tập biến thể trực tiếp là một phần của mô hình nghiệp vụ và thư viện cần kiểm soát các kiểu được phép xuất hiện. Ví dụ gồm kết quả phân tích cú pháp, trạng thái giao dịch hoặc loại sự kiện nội bộ.

Dùng `non-sealed` cho một nhánh khi thư viện muốn kiểm soát loại khái niệm ở tầng trên, nhưng vẫn muốn cho phép ứng dụng mở rộng phía dưới. Ví dụ, `ApiResult` có thể giới hạn các nhóm kết quả, trong khi `ApiDeferred` cho phép từng ứng dụng tạo các loại kết quả trì hoãn riêng.

Dùng interface mở khi client cần quyền triển khai trực tiếp mà không cần được thư viện cho phép trước. Đây thường là lựa chọn phù hợp cho SPI hoặc plugin API được thiết kế để mở rộng qua module độc lập.

Hãy đánh giá ranh giới module, mức truy cập, vòng đời API và khả năng xử lý các biến thể mới. Những quyết định đó quan trọng hơn việc chỉ thêm từ khóa `sealed`.

## 8. Lỗi thường gặp khi áp dụng vào API

**Quên modifier ở kiểu con trực tiếp.** Một class thông thường kế thừa sealed class mà không khai báo `final`, `sealed` hoặc `non-sealed` sẽ không biên dịch. Hãy xác định rõ nhánh cần đóng hay mở.

**Đưa kiểu con gián tiếp vào `permits`.** Mệnh đề chỉ liệt kê kiểu con trực tiếp. Một kiểu ở sâu hơn phải được kết nối thông qua nhánh trung gian.

**Dùng `sealed` cho plugin API vốn cần mở rộng tự do.** Client bên ngoài module/package không thể tùy ý triển khai trực tiếp sealed interface. Hãy cân nhắc interface mở hoặc một nhánh `non-sealed` công khai.

**Nghĩ rằng Java 17 đã có pattern switch chính thức.** Java 17 có sealed types chính thức, nhưng pattern matching for `switch` ở phiên bản này vẫn là preview. Không bật preview khi mục tiêu là mã nguồn Java 17 thông thường.

**Thêm biến thể mà không kiểm tra client.** Khi danh sách `permits` thay đổi, hãy rà soát code xử lý kết quả, kiểm thử tích hợp và quy trình biên dịch các module phụ thuộc.

**Dùng `non-sealed` nhưng giả định cây kiểu đã đóng.** `non-sealed` cố ý mở nhánh đó. Mọi logic dựa trên danh sách implementation cố định cần tính đến các kiểu con có thể được thêm về sau.

**Nhầm giới hạn kiểu với xác thực dữ liệu.** Sealed types kiểm soát quan hệ kế thừa/triển khai trong hệ phân cấp. Chúng không thay thế kiểm tra đầu vào, phân quyền, validation hoặc các quy tắc nghiệp vụ.

## 9. Checklist trước khi công bố API

- Xác định tập kiểu con trực tiếp có thực sự cần được kiểm soát hay không.
- Khai báo rõ danh sách `permits`, hoặc để Java suy ra khi các kiểu được cho phép nằm trong cùng compilation unit.
- Chọn `final`, `sealed` hoặc `non-sealed` cho từng kiểu con trực tiếp theo chính sách mở rộng.
- Kiểm tra các quy tắc cùng module/package.
- Nếu muốn cho phép client mở rộng, cung cấp nhánh `non-sealed` thích hợp hoặc giữ interface mở.
- Khi thay đổi danh sách `permits`, kiểm tra mã client, các nhánh xử lý và kiểm thử tương thích trước khi phát hành.
- Biên dịch ví dụ và thư viện với phiên bản Java mục tiêu. Với Java 17, dùng `javac --release 17` để xác nhận cú pháp ổn định.
- Ghi rõ trong tài liệu API liệu tập biến thể là đóng hay có điểm mở rộng được hỗ trợ.

Sealed classes và sealed interfaces trong Java 17 cung cấp công cụ để công bố ranh giới mở rộng rõ ràng. Chúng phù hợp nhất khi chính sách về các kiểu con trực tiếp là một phần quan trọng của hợp đồng API và được duy trì có chủ đích qua các phiên bản thư viện.
