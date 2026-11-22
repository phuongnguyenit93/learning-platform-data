# Giới hạn thu thập tham số chứa dữ liệu nhạy cảm trong advice AOP

**Advice** trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**) có thể quan sát các lời gọi và lần thực thi phương thức, đồng thời nhận thông tin về chữ ký, đối tượng đích, đối tượng đang thực thi, các tham số, kết quả và ngoại lệ tùy cơ chế hỗ trợ. Khả năng nhận dữ liệu này giúp ghi log, audit, tracing và đo lường; nhưng cũng làm một advice ghi log quá rộng trở thành **đường rò rỉ dữ liệu nhạy cảm**.

Một lời gọi nghiệp vụ có thể mang mật khẩu, access token, khóa API, số tài khoản, thông tin sức khỏe, định danh cá nhân, địa chỉ giao hàng hoặc payload tự do do người dùng nhập. Nếu advice mặc định in toàn bộ `args`, serialise object hoặc gọi `toString()`, dữ liệu ấy có thể bị nhân bản vào hệ thống log, công cụ tracing, bộ thu thập metrics, queue, bản sao lưu hoặc trang xử lý sự cố.

**Nguyên tắc trọng tâm:** giới hạn **ngay tại lúc thu thập**; mặc định **không ghi giá trị tham số**, chỉ lấy những thuộc tính thực sự cần thiết và đã được phân loại là an toàn. Che giấu sau khi dữ liệu thô đã bị gửi đi không phải là biện pháp tương đương.

Bài học này áp dụng cho **AOP nói chung**: phân biệt loại join point, cách expose/binding ngữ cảnh, chính sách tối thiểu hóa dữ liệu, chiến lược biến đổi, giới hạn lưu trữ và cách kiểm thử. Cú pháp pointcut/khả năng đọc tham số phụ thuộc nền tảng AOP; ví dụ Java 17 ở dưới chỉ mô phỏng một lời gọi được chặn qua dynamic proxy để làm rõ các nguyên tắc.

## 1. Đặt đúng ranh giới: pointcut, binding và collection

Trong AOP:

- **Join point:** vị trí/sự kiện chương trình mà cơ chế AOP có thể can thiệp, ví dụ method call hoặc method execution khi được hỗ trợ.
- **Pointcut:** quy tắc chọn join point cần can thiệp, chẳng hạn phương thức thuộc một thành phần hoặc một chữ ký cụ thể.
- **Advice:** xử lý được chạy ở điểm đã chọn, ví dụ trước khi gọi hoặc sau khi kết thúc.
- **Context binding/exposure:** cách đưa thông tin của lần thực thi vào advice; có thể gồm `args`, `target`, `this`, signature, result hay exception tùy loại join point.
- **Weaving:** cách kết hợp advice với code nghiệp vụ bằng khả năng của nền tảng: proxy, biến đổi bytecode hoặc kỹ thuật khác.

Có ba quyết định **khác nhau** cần thực hiện:

1. **Có được chọn join point này không?** Đây là quyết định phạm vi cấu trúc và điều kiện pointcut.
2. **Advice có thể nhận thông tin gì?** Đây là khả năng binding của mô hình AOP.
3. **Thông tin nào được phép thu thập, giữ hoặc phát tán?** Đây là chính sách an toàn dữ liệu.

Cơ chế AOP **có thể** cung cấp toàn bộ mảng `Object[] args`, nhưng điều đó không có nghĩa advice **nên** copy toàn bộ mảng vào một event log. Tính năng kỹ thuật và quyền sử dụng dữ liệu là hai việc tách biệt.

Ví dụ mảnh code minh họa:

~~~java
checkout.placeOrder(accessToken, shippingAddress, channel, totalCents);
~~~

Nếu chỉ cần biết kênh thanh toán và tình trạng thành công, advice có thể phát ra:

~~~text
event=order.place channel=WEB outcome=SUCCESS
~~~

Không có lý do tự động nào để lưu token, địa chỉ, giá trị tổng tiền hoặc toàn bộ `checkout.toString()` chỉ vì những giá trị đó sẵn có tại join point.

## 2. Vì sao thu thập tham số tự động lại nguy hiểm?

Một mảng args có thể mang dữ liệu từ nhiều vùng tin cậy:

| Nhóm dữ liệu | Ví dụ | Rủi ro nếu advice ghi nguyên giá trị |
| --- | --- | --- |
| Bí mật xác thực | Mật khẩu, OTP, API key, refresh token, bearer token | Người có quyền đọc log có thể dùng lại bí mật để truy cập |
| Định danh phiên | Cookie phiên, session identifier, token reset | Chiếm phiên, liên kết hành vi trái phép |
| Dữ liệu định danh | Số giấy tờ, địa chỉ, điện thoại, email, tên khách hàng | Xâm phạm riêng tư hoặc liên kết danh tính |
| Tài chính | Số tài khoản, thông tin thẻ, số dư, nội dung giao dịch | Rò rỉ dữ liệu tài chính, vi phạm chính sách |
| Dữ liệu đặc biệt nhạy cảm | Hồ sơ sức khỏe, nội dung cá nhân, thông tin trẻ em | Hậu quả riêng tư và pháp lý cao |
| Bí mật hệ thống | Chuỗi kết nối có mật khẩu, private key, khóa mã hóa | Mở rộng bề mặt tấn công hạ tầng |
| Payload tự do | Search text, ghi chú, nội dung form, tệp tải lên | Chứa bất kỳ dữ liệu nhạy cảm nào, khó lọc bằng tên |
| Kết quả và lỗi | Response body, exception message, stack trace | Có thể chứa lại đầu vào, query, token hoặc địa chỉ nội bộ |

Một đối tượng có vẻ vô hại như `OrderRequest` có thể chứa những field bí mật lồng sâu. Gọi `String.valueOf(request)` hoặc serialise toàn bộ object là hành vi **mở rộng phạm vi thu thập**, kể cả khi tên phương thức nghe không liên quan dữ liệu nhạy cảm.

Dữ liệu có thể bị nhân bản qua nhiều tầng:

~~~text
Invocation arguments
        |
        v
 Advice giữ/copy giá trị thô
        |
        +--> Log formatter / console
        +--> Trace span attribute / baggage
        +--> Event queue / metrics label
        +--> Error reporter / crash dump
        +--> Tập trung log / backup / kho phân tích
        |
        v
Nhiều nơi lưu, nhiều quyền truy cập, nhiều vòng đời
~~~

Vì vậy, việc định dạng log chỉ là **một điểm bảo vệ**. Cần nghĩ về luồng dữ liệu từ lúc advice đọc args cho đến lúc event bị xóa hoặc được chia sẻ cho hệ thống khác.

## 3. Phân loại dữ liệu trước khi thiết kế advice

Không nên chờ đến lúc viết dòng log mới đoán tham số có nhạy cảm hay không. Mỗi thao tác được chọn nên có một **hợp đồng ghi nhận dữ liệu (observability data contract)**:

- **Mục đích:** cần chẩn đoán lỗi, audit hay đo độ trễ?
- **Loại sự kiện:** thao tác nào, mức độ quan trọng, trạng thái hoàn thành?
- **Trường được phép:** sự kiện, kênh dạng enum, mã lỗi đã chuẩn hóa, thời lượng hoặc ID tương quan phi nhạy cảm.
- **Trường cấm:** thông tin xác thực, payload riêng tư, dữ liệu thô không cần thiết.
- **Biến đổi được phép:** bỏ, phân loại, làm tròn, tổng hợp, mask/tokenize theo chính sách.
- **Đích gửi:** log, trace, metrics, cảnh báo, audit store.
- **Quyền truy cập và vòng đời:** ai được đọc, giữ bao lâu, khi nào xóa?
- **Kiểm thử:** làm sao chứng minh chuỗi canary nhạy cảm không đi vào bất kỳ đầu ra nào?

### 3.1 Không đánh giá bằng kiểu dữ liệu đơn giản

Một `String` có thể là kênh `"WEB"` hoặc bearer token. Một `int` có thể là số lượng hàng hoặc mã PIN. Một enum có thể mô tả trạng thái thông thường, nhưng cũng có thể là phân loại bệnh. **Không có kiểu Java nào tự chứng minh dữ liệu an toàn để log.**

Cách làm thích hợp là phân loại **theo ý nghĩa nghiệp vụ và đích thu thập**, không chỉ dựa vào `String`, `int` hay tên tham số.

### 3.2 Chính sách mặc định loại trừ (default-deny)

Một quy tắc an toàn có thể là:

~~~text
if field is approved, required, and already safe:
    collect minimal representation
else:
    do not collect field value
~~~

Trường chưa được phân loại **không được tự động cho qua**. Khi thêm một tham số mới, hệ thống log vẫn an toàn theo mặc định. Đây là khác biệt cơ bản giữa **allowlist** và **denylist theo tên trường**.

Denylist có thể bỏ sót tên `pwd`, `credential`, `authorization`, `secretValue` hoặc field lồng sâu dưới một tên khác. Allowlist ngược lại buộc chủ sở hữu hệ thống chủ động tuyên bố điều gì được phép đi vào kênh quan sát.

## 4. Tránh những lối tắt dễ làm lộ dữ liệu

### 4.1 In nguyên mảng args

~~~java
System.out.println(java.util.Arrays.toString(args));
~~~

Đây là **mảnh mã cần tránh đối với dữ liệu không được phân loại**. Nó gọi cách biểu diễn chuỗi của các phần tử; có thể để lộ nhiều trường hoặc chuỗi chứa dữ liệu nhạy cảm. Với mảng lồng nhau, các API biểu diễn sâu còn tăng độ rộng thu thập.

### 4.2 Gọi `toString()` của toàn bộ target hoặc request

~~~java
logger("request=" + request);
~~~

Đây là **mảnh minh họa**, không phải chương trình độc lập. Một `toString()` do mã nghiệp vụ viết có thể in tất cả field, truy cập object lồng nhau, chạy logic không mong muốn hoặc ném ngoại lệ. Advice không nên dựa vào `toString()` của đối tượng tùy ý để quyết định những trường nào được lưu.

### 4.3 Dựa hoàn toàn vào regex để che bí mật

Ví dụ thay số thẻ bằng `****` sau khi đã tạo chuỗi log có thể bỏ sót định dạng lạ, dữ liệu phân mảnh hoặc secret xuất hiện ở vị trí không lường trước. Regex phù hợp cho **lớp phòng vệ bổ sung**, không thay việc bỏ trường ngay khi thu thập.

### 4.4 Cho rằng chỉ log DEBUG mới nguy hiểm

Tham số có thể lọt vào event ngay khi tạo dữ liệu, trước khi filter theo mức log, hoặc vào hệ thống tracing và báo lỗi tự động. Log có thể bật ở production khi điều tra sự cố. Cần bảo vệ **bất kể mức log**, không chỉ dựa vào cấu hình tắt DEBUG.

### 4.5 Ghi thông báo ngoại lệ nguyên văn

~~~java
System.out.println(error.getMessage());
~~~

Đây là **mảnh mã rủi ro nếu error message có thể chứa đầu vào**. Ngoại lệ từ HTTP, SQL, validation hoặc ứng dụng có thể nhúng token, địa chỉ, email hoặc payload. Nếu cần trạng thái lỗi, nên chọn **mã lỗi và loại đã chuẩn hóa**, hạn chế ghi chi tiết chưa lọc.

## 5. Phạm vi pointcut càng rộng, bề mặt lộ càng lớn

Một pointcut chọn mọi method execution trong cả ứng dụng có thể bắt cả:

- Phương thức đăng nhập chứa password/OTP.
- Phương thức gửi thanh toán chứa dữ liệu thẻ.
- Phương thức đọc hồ sơ có dữ liệu đặc biệt nhạy cảm.
- Phương thức xử lý token và khóa hệ thống.
- Phương thức chỉ dùng nội bộ hoặc mã sinh mà trước đó người viết không để ý.

Vì vậy, một chính sách quan sát tốt thường giới hạn cấu trúc theo **đúng nhóm nghiệp vụ cần quan sát**, sau đó áp dụng **allowlist dữ liệu** ở cấp tham số/trường.

~~~text
selected = structuralScope AND allowedJoinPointKind

event = {
    operation: approvedOperationName,
    outcome: approvedStatus,
    durationBucket: approvedBucket
}

raw args -> excluded by default
~~~

Các biểu thức trên là **giả mã ngữ nghĩa**, không phải cú pháp pointcut phổ quát. Kể cả khi pointcut đủ hẹp, một phương thức thuộc đúng nhóm vẫn có thể nhận secret; phạm vi hẹp không thay thế phân loại field.

### 5.1 Call và execution có thể expose ngữ cảnh khác nhau

Tại **method call join point**, advice có thể quan sát args từ chỗ phát sinh lời gọi, đối tượng đích và đối tượng phía caller nếu mô hình hỗ trợ. Tại **method execution join point**, advice quan sát lần chạy thân phương thức và các tham số của phần thực thi đó.

Không phải cơ chế AOP nào cũng expose cả hai loại điểm. Với proxy qua interface, advice chỉ thấy lời gọi **đi qua proxy**; lời gọi trực tiếp hay self-invocation trên target có thể bỏ qua. **Giới hạn phạm vi thu thập** và **giới hạn phạm vi weaving** phải được kiểm chứng riêng: một phép đo không đầy đủ không được trình bày như đã bao phủ mọi đường vào.

### 5.2 Target và this cũng có thể chứa secret

Không chỉ args: đối tượng `target` hoặc `this` có thể giữ thông tin cấu hình, trạng thái xác thực, cache dữ liệu người dùng và tham chiếu tới object có vòng đời dài. Ghi `target.toString()`, dump toàn bộ field qua reflection hoặc đưa object trực tiếp vào event queue cũng có nguy cơ rò dữ liệu.

Nếu chỉ cần biết loại thao tác, dùng **tên sự kiện đã cố định** thay vì trích xuất object. Nếu cần loại target, cân nhắc ánh xạ vào một **nhóm danh mục được duyệt** thay vì in tên lớp đầy đủ, vì tên lớp và đường dẫn nội bộ cũng có thể là thông tin hạ tầng không cần công bố.

## 6. Kỹ thuật thu thập an toàn

### 6.1 Thu thập metadata và trạng thái đã chuẩn hóa

Những trường thường dễ kiểm soát hơn nội dung dữ liệu thô:

| Nhu cầu | Trường có thể xem xét | Điều không nên lấy mặc định |
| --- | --- | --- |
| Đếm lời gọi | Mã sự kiện cố định, success/error | Nguyên mảng tham số |
| Đo độ trễ | Tên thao tác được duyệt, duration | Response body hoặc credential |
| Điều tra validation | Mã quy tắc vi phạm, trường phân loại | Giá trị đầu vào bị từ chối |
| Audit truy cập | Loại thao tác, kết quả allow/deny, chủ thể đã xác thực theo chính sách | Token hoặc payload xác thực |
| Theo dõi lỗi | Mã lỗi an toàn, nhóm lỗi, request correlation | Exception message chưa lọc |
| Đo phân bố | Histogram thời gian hoặc lượng dữ liệu được nhóm | Giá trị cá nhân làm label duy nhất |

Khi một event không cần định danh đối tượng, **bỏ hẳn ID** thường an toàn hơn việc tạo ID thay thế. Nếu thực sự cần correlation, dùng định danh ngẫu nhiên không suy ra thông tin cá nhân và có vòng đời/không gian sử dụng phù hợp.

### 6.2 Redaction, masking, hashing và tokenization khác nhau

- **Omission:** bỏ hoàn toàn trường. Đây thường là mặc định tốt nhất cho secret.
- **Redaction:** thay giá trị bằng nhãn cố định như `<REDACTED>`. Cho biết tham số có mặt nhưng không giữ nội dung.
- **Masking:** giữ một phần ký tự. Chỉ hợp lệ khi chính sách cho phép; vài ký tự cuối vẫn có thể đủ để liên kết hoặc suy đoán dữ liệu.
- **Aggregation/bucketing:** thay số cụ thể bằng nhóm có ý nghĩa như `SMALL`, `MEDIUM`, `LARGE`, khi ranh giới được duyệt.
- **Hashing:** tạo dấu vết một chiều; **hash không salt/không key đối với giá trị dễ đoán vẫn có thể bị dò từ điển**. Kể cả HMAC, giá trị đầu ra có thể là định danh liên kết lâu dài, nên vẫn cần giới hạn quyền và vòng đời.
- **Tokenization:** ánh xạ dữ liệu sang mã giả thay thế, có thể cho phép tra cứu ngược qua kho ánh xạ được bảo vệ; kho ấy trở thành thành phần nhạy cảm riêng.
- **Encryption:** bảo vệ nội dung khi lưu/truyền nếu quản lý khóa đúng, nhưng **không xóa bỏ trách nhiệm** tối thiểu hóa thu thập hoặc điều chỉnh quyền đọc giải mã.

Không được nói “đã hash nên không còn dữ liệu nhạy cảm” cho mọi trường hợp; tính liên kết qua nhiều event hoặc nguy cơ dò giá trị vẫn có thể tồn tại.

### 6.3 Không log dữ liệu đầu vào dù có lỗi

Ở nhánh validation fail, log có thể ghi `validation_rule=AMOUNT_NEGATIVE` thay vì `badAmount=-123456789`. Ở nhánh authentication fail, ghi mã lỗi `AUTH_FAILED`, không in credential hay token được cung cấp.

Nếu yêu cầu audit cần giữ nhiều thông tin hơn log chẩn đoán thông thường, hãy thiết kế **kênh audit riêng**, dữ liệu được phê duyệt, phân quyền nghiêm ngặt và vòng đời phù hợp. Không nên cho phép một advice log thông thường thu thập vô hạn chỉ vì cùng hệ thống có nhu cầu kiểm toán.

## 7. Java 17: ví dụ chạy độc lập với allowlist và annotation

Ví dụ sau **không sử dụng ngôn ngữ pointcut của một bộ AOP cụ thể**. Nó dùng dynamic proxy Java để minh họa cách advice có thể nhận `Method` và `args` nhưng **chỉ tạo bản tóm tắt an toàn** cho log.

Hợp đồng:

- `@Sensitive`: tham số chứa thông tin phải che, chỉ log nhãn `<REDACTED>`.
- `@SafeToLog`: gợi ý một tham số **đã được duyệt** cho mục đích minh họa; code **chỉ cho phép** giá trị thuộc enum `Channel`, không tự log mọi object mang annotation.
- Không có annotation: `<OMITTED>` theo mặc định.
- Không log `Method.toString()`, `target.toString()`, toàn bộ `args` hoặc exception message.
- Với nhánh lỗi, log **category** đã chuẩn hóa, vẫn ném tiếp ngoại lệ nghiệp vụ gốc.
- Mã là ví dụ **đơn luồng**, không thực hiện thanh toán thật và không xác thực người dùng.

Tạo file `SafeAdviceLoggingDemo.java`:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.StringJoiner;

public class SafeAdviceLoggingDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Sensitive {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface SafeToLog {}

    enum Channel {
        WEB, MOBILE
    }

    interface Checkout {
        String placeOrder(
                @Sensitive String sessionToken,
                @Sensitive String shippingAddress,
                @SafeToLog Channel channel,
                int totalCents);
    }

    static final class CheckoutImpl implements Checkout {
        @Override
        public String placeOrder(
                String sessionToken,
                String shippingAddress,
                Channel channel,
                int totalCents) {
            if (totalCents < 0) {
                throw new IllegalArgumentException("invalid amount");
            }
            System.out.println("BUSINESS processed");
            return "ACCEPTED";
        }
    }

    static String safeArguments(Method method, Object[] values) {
        Annotation[][] parameterTags =
                method.getParameterAnnotations();
        StringJoiner result = new StringJoiner(",");

        for (int i = 0; i < parameterTags.length; i++) {
            boolean sensitive = false;
            boolean safe = false;

            for (Annotation tag : parameterTags[i]) {
                if (tag.annotationType() == Sensitive.class) {
                    sensitive = true;
                }
                if (tag.annotationType() == SafeToLog.class) {
                    safe = true;
                }
            }

            String rendered = "<OMITTED>";
            if (sensitive) {
                rendered = "<REDACTED>";
            } else if (safe && i < values.length
                    && values[i] instanceof Channel channel) {
                // name() có tập giá trị hữu hạn được duyệt.
                rendered = channel.name();
            }

            result.add("p" + i + "=" + rendered);
        }
        return result.toString();
    }

    static Object invokeTarget(
            Object target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Checkout instrument(Checkout target) {
        return (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[] { Checkout.class },
                (proxy, method, args) -> {
                    Object[] values =
                            args == null ? new Object[0] : args;

                    if (method.getDeclaringClass() == Object.class) {
                        return invokeTarget(target, method, values);
                    }

                    System.out.println("ADVICE event=order.place args="
                            + safeArguments(method, values));

                    try {
                        Object result =
                                invokeTarget(target, method, values);
                        System.out.println("ADVICE status=SUCCESS");
                        return result;
                    } catch (Throwable error) {
                        String category =
                                error instanceof IllegalArgumentException
                                ? "VALIDATION" : "OTHER";
                        System.out.println(
                                "ADVICE status=ERROR category=" + category);
                        throw error;
                    }
                });
    }

    public static void main(String[] args) {
        Checkout checkout = instrument(new CheckoutImpl());

        System.out.println("CALLER " + checkout.placeOrder(
                "demo-token", "demo-address", Channel.WEB, 1200));

        try {
            checkout.placeOrder(
                    "demo-token-2", "demo-address-2",
                    Channel.MOBILE, -1);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER validation error");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac SafeAdviceLoggingDemo.java
java SafeAdviceLoggingDemo
~~~

Stdout chính xác:

~~~text
ADVICE event=order.place args=p0=<REDACTED>,p1=<REDACTED>,p2=WEB,p3=<OMITTED>
BUSINESS processed
ADVICE status=SUCCESS
CALLER ACCEPTED
ADVICE event=order.place args=p0=<REDACTED>,p1=<REDACTED>,p2=MOBILE,p3=<OMITTED>
ADVICE status=ERROR category=VALIDATION
CALLER validation error
~~~

### 7.1 Vì sao đây là ví dụ thu thập tối thiểu?

**Thứ nhất**, `sessionToken` và `shippingAddress` ở vị trí 0 và 1 không được chuyển thành chuỗi. Advice chỉ xuất ra nhãn cố định `<REDACTED>`; không cắt chuỗi đầu vào, không in độ dài và không tính hash.

**Thứ hai**, `channel` là enum với một tập giá trị đã biết; code chỉ dùng `name()` khi annotation cho phép **và** giá trị thực tế thuộc enum đó. Một tham số `String` được gắn cùng annotation sẽ không tự được in nhờ điều kiện kiểm tra kiểu hạn chế.

**Thứ ba**, `totalCents` không có annotation `@SafeToLog`, nên log chỉ cho biết `p3=<OMITTED>`; nó không suy rằng mọi số nguyên đều an toàn. Tùy hệ thống, giá trị tiền có thể là dữ liệu kinh doanh nhạy cảm.

**Thứ tư**, advice ghi `SUCCESS` hoặc `ERROR category=VALIDATION` thay vì in kết quả, error message và stack trace. Lỗi nghiệp vụ được truyền ra như cũ; việc ẩn thông tin trên log **không có nghĩa thay đổi ngoại lệ nhận bởi bên gọi**.

**Thứ năm**, annotation được đọc từ `Method` của interface `Checkout` mà dynamic proxy cung cấp. Trong ví dụ, annotation được khai báo **trực tiếp ở tham số của interface**. Parameter annotation trên interface không thể mặc định coi là có mặt trên mọi `Method` của lớp triển khai nếu đọc reflection tại một điểm khác. Vì vậy cơ chế AOP thật cần xác định chính xác **chữ ký nào được đọc để phân loại**.

### 7.2 Những giới hạn không được bỏ qua

- Dynamic proxy chỉ can thiệp những lời gọi **thông qua proxy**. Nếu gọi trực tiếp `new CheckoutImpl().placeOrder(...)`, advice demo không chạy. Điều này làm phạm vi đo khác, **không chứng minh các đường khác an toàn để log**.
- Các giá trị `"demo-token"`, `"demo-address"` là **dữ liệu giả** trong mã minh họa, không phải secret thật.
- Nếu một developer bỏ annotation hoặc thêm tham số mới, chính sách **mặc định bỏ giá trị**; đó là hành vi mong muốn.
- Annotation là **tín hiệu phân loại**, không tự kiểm định pháp lý hay bảo đảm một field có thật sự an toàn. Quy trình review và kiểm thử vẫn cần thiết.
- Ví dụ không có logger bất đồng bộ, metric backend, audit store hoặc chính sách retention. Những phần đó cần triển khai theo môi trường thật.
- Hệ thống có thể có thêm đường log từ thư viện HTTP, ORM, exception handler, request filter hoặc các công cụ profiling độc lập với advice. Bảo đảm riêng tại advice **không bảo đảm toàn ứng dụng không bao giờ lưu secret**.

## 8. Nhận dữ liệu theo loại advice mà không làm lộ bí mật

### 8.1 Before advice

Before advice thường thấy args trước khi gọi nghiệp vụ. Nó phù hợp để ghi **tên sự kiện an toàn**, số lượng tham số nếu cần, correlation ID hoặc thời điểm bắt đầu. Nhưng **chưa có kết quả**; không được ghi `success=true` tại điểm này chỉ vì phương thức đã được gọi.

Một điểm rủi ro là in **mọi tham số đầu vào** trước cả khi biết phương thức có được phép chạy hay không. Người dùng độc hại có thể cố đưa dữ liệu nhạy cảm hoặc chuỗi gây log injection vào các đối số.

### 8.2 After returning advice

Loại này có thể nhận **giá trị trả về** ngoài args. Kết quả còn nhạy cảm hơn đầu vào: thông tin hồ sơ, access token mới cấp, dữ liệu tài chính hoặc nội dung tìm kiếm. Nếu mục tiêu chỉ là đếm thành công, lưu `outcome=SUCCESS` thay vì serialize response.

Đừng giả định kết quả trả về là “an toàn vì là output đã được duyệt”. Nó có thể thuộc một phạm vi phân quyền cao hơn log store.

### 8.3 After throwing advice

Ngoại lệ có thể chứa input trong message, suppressed exceptions, cause chain và stack trace. Một điểm ghi lỗi chung nên phân loại theo **mã lỗi đã duyệt**; chỉ truyền message và trace vào nơi có mức bảo vệ tương xứng khi có cơ sở cần thiết và chính sách rõ.

Nếu advice chỉ bắt lỗi để log, nó thường cần **bảo toàn ngoại lệ gốc**; đừng đổi đường thất bại thành thành công chỉ vì muốn giấu lỗi khỏi log.

### 8.4 Around advice

Around advice có thể đọc args, gọi tiếp, đổi tham số, đổi kết quả hoặc short-circuit nếu mô hình hỗ trợ. Nó cần tránh:

- Copy toàn bộ args và giữ trong closure/queue lâu hơn yêu cầu.
- Ghi raw args trước khi gọi tiếp và raw result sau khi trả về.
- Gọi `toString()` hoặc serializer toàn diện trong `finally`.
- Trả về nội dung đã bị mask **cho bên gọi** chỉ vì muốn mask log, làm sai hợp đồng nghiệp vụ.
- Gọi lại `proceed` nhiều lần gây lặp side effect chỉ để thu thập thêm dữ liệu.

**Che dữ liệu khi phát event quan sát** phải tách khỏi **dữ liệu nghiệp vụ được chuyển tiếp**. Không tự sửa token/địa chỉ mà nghiệp vụ cần dùng chỉ nhằm làm log an toàn.

## 9. Dữ liệu cấu trúc: mục tiêu tốt hơn nội dung tự do

Một event có cấu trúc hữu ích có thể gồm:

~~~text
event_name: order.place
component: checkout
outcome: VALIDATION_ERROR
channel: MOBILE
duration_bucket: UNDER_50_MS
trace_id: an approved random correlation identifier
~~~

Các giá trị trên là ví dụ của **event schema được thiết kế trước**, không phải dữ liệu thật của một người dùng. Dữ liệu cấu trúc có ích vì:

- Mỗi field có mô tả, loại, ranh giới và chính sách rõ.
- Có thể giới hạn các trường vào tập enum hoặc khoảng giá trị được duyệt.
- Dễ kiểm thử sự vắng mặt của field nhạy cảm.
- Dễ áp dụng thời hạn giữ và quyền truy cập riêng cho mỗi loại sự kiện.
- Giảm nhu cầu gắn payload tự do vào một chuỗi lớn khó kiểm soát.

Ngay cả trace ID hoặc mã đối tượng nghiệp vụ cũng có thể **giúp liên kết hoạt động của một cá nhân**. Chúng cần được xem xét theo mục đích và phạm vi; “không phải password” không đồng nghĩa “không nhạy cảm”.

### 9.1 Cardinality cao cũng là rủi ro

Đưa email, user ID, số tài khoản, request body hoặc token vào **metric labels** tạo ra rất nhiều chuỗi giá trị khác nhau, gây quá tải lưu trữ và làm lộ dữ liệu trong hệ thống metrics. Để phân tích tỷ lệ lỗi hoặc latency, thường dùng nhãn **bounded** như tên thao tác, trạng thái và nhóm nguyên nhân, không dùng định danh cá nhân làm label.

### 9.2 Chống log injection

Nếu thật sự phải ghi một chuỗi do bên ngoài cung cấp, cần chặn hoặc escape đúng theo format sink: xuống dòng, carriage return, dấu phân cách, control characters và cấu trúc có thể phá định dạng log. Ưu tiên sử dụng API structured logging có escaping đúng, giới hạn kích thước và schema đã duyệt.

Sanitization định dạng **không** thay phân loại độ nhạy. Một token đã escape an toàn khỏi log injection vẫn là một token bị lộ nếu ghi nguyên giá trị.

## 10. Giới hạn về vòng đời và nơi lưu

### 10.1 Ngay trong bộ nhớ advice

Đừng giữ tham chiếu toàn bộ `args`, `target`, `this` hoặc response vào một queue lâu dài khi chỉ cần ba trường an toàn. Nếu log bất đồng bộ, hãy tạo **sự kiện nhỏ, bất biến và đã lọc**, thay vì chuyển toàn bộ object rồi định dạng ở consumer.

Sao chép mảng bằng `args.clone()` là **sao chép nông**: các object bên trong vẫn được chia sẻ. Nếu nội dung mutable thay đổi, event ghi sau có thể phản ánh thời điểm khác và làm lộ dữ liệu không lường trước.

### 10.2 Khi truyền đi

Kênh log/trace/audit cần bảo vệ tính bí mật và toàn vẹn khi truyền, cấu hình endpoint đúng, dùng credentials theo nguyên tắc ít quyền. Đảm bảo các hệ thống thu thập thứ ba được phê duyệt trước khi gửi dữ liệu; một SDK telemetry không phải nơi mặc định được phép nhận mọi payload.

### 10.3 Khi lưu trữ và truy cập

- Phân quyền theo vai trò, hạn chế người có thể truy vấn log.
- Có retention và cơ chế xóa phù hợp chính sách và quy định áp dụng.
- Xem xét dữ liệu trong bản sao lưu, kho thứ cấp, export và môi trường thử nghiệm.
- Bảo vệ quyền xem, chia sẻ, tải xuống, tìm kiếm và đối chiếu sự kiện.
- Kiểm tra nhà cung cấp log/trace có phù hợp với phân loại dữ liệu thực tế.
- Ghi nhận và kiểm toán việc truy cập log nhạy cảm nếu cần.

Việc **mã hóa lúc lưu** là biện pháp quan trọng, nhưng không cho phép thu thập tùy ý. Dữ liệu nhạy cảm không cần thiết vẫn nên bị loại **trước** khi đến kho lưu trữ.

## 11. Kiểm thử để chứng minh không rò qua advice

Một bài kiểm thử tốt phải dùng **giá trị canary giả** có thể tìm kiếm dễ dàng, ví dụ chuỗi như `CANARY_DO_NOT_RECORD_123` đặt vào tham số được phân loại sensitive. Sau đó chạy đủ các đường và kiểm tra không có chuỗi canary trong bất kỳ event/trace/metric được hệ thống thử nghiệm thu thập.

Nên kiểm tra:

1. **Success:** lời gọi thành công không in token, thông tin cá nhân, request body hoặc response nhạy cảm.
2. **Validation failure:** input sai không được đưa nguyên vào exception log.
3. **Backend failure:** lỗi từ thư viện/thân phương thức không làm advice vô tình in thông báo chứa dữ liệu nhạy cảm.
4. **Tham số mới:** nếu thêm field chưa được phân loại, mặc định bị bỏ.
5. **Object lồng nhau:** `CustomerRequest` chứa secret không bị serialize nguyên object.
6. **`null`, array, collection, varargs, generic:** cách duyệt không làm mất an toàn khi loại dữ liệu thay đổi.
7. **Overload:** các chữ ký cùng tên không dùng nhầm metadata annotation hoặc chỉ số tham số.
8. **Interface/override/proxy:** code đọc annotation tại `Method` đúng như thiết kế; phương thức triển khai không tự được giả định kế thừa parameter annotation.
9. **After returning / throwing / finally:** không lộ kết quả và message lỗi khi advice ở nhiều giai đoạn.
10. **Multiple advice:** lớp ngoài và trong không tạo thêm bản sao raw args do một bên lọc còn bên kia log toàn bộ.
11. **Dynamic sampling / debug level:** bật mức chi tiết cao vẫn không được xuất secret.
12. **Async logging:** queue/event cuối cùng đã chứa dữ liệu an toàn, không có object nhạy cảm được giữ chờ format.
13. **Metrics/tracing:** label/attribute và baggage không chứa payload.
14. **Sink:** cả console, file, collector, exporter, error reporter, backup được kiểm tra ở phạm vi có thể quan sát.
15. **Performance:** phân loại và tạo event đủ nhanh; advice không gây reentrancy, deadlock hoặc tăng contention quá mức.

**Kiểm tra bằng điều kiện phủ định:** `assert(!capturedOutput.contains(canary))` cho mọi đích quan sát được trong test. Đồng thời kiểm tra **những event được phép vẫn tồn tại** để tránh tình trạng “an toàn” bằng cách vô hiệu hóa toàn bộ audit bắt buộc.

Không đưa secret thật vào test. Canaries giả có cấu trúc nhận diện riêng giúp phát hiện rò dữ liệu mà không làm phát sinh một vụ rò thật.

## 12. Tình huống thiết kế: cùng một phương thức, ba nhu cầu khác nhau

Giả sử nghiệp vụ `registerAccount(email, password, consent)` và ba nhóm muốn dùng cùng join point.

**Nhóm vận hành** cần biết tỷ lệ thành công và latency. Event phù hợp có thể là `event=account.register`, `outcome=SUCCESS/ERROR`, `duration_ms`. Không cần email hay password.

**Nhóm bảo mật** cần phát hiện các lần đăng ký đáng ngờ. Nó có thể cần trạng thái xác thực, mã nguyên nhân và dấu hiệu gian lận đã chuẩn hóa; nếu cần định danh để điều tra, phải dùng phương pháp được phê duyệt và kho audit có kiểm soát, không tự phát tán email/password vào log ứng dụng.

**Nhóm sản phẩm** cần phân tích lựa chọn consent. Có thể cần các giá trị boolean/enum được duyệt và tổng hợp, nhưng cần xem mục đích thu thập, thông báo, quyền riêng tư và giới hạn lưu giữ. Không được suy rằng “đã có args nên dùng toàn bộ args cho analytics”.

**Kết luận tình huống:** một join point có thể phục vụ nhiều mục tiêu, nhưng **mỗi mục tiêu cần schema thu thập riêng**. Gộp các nhu cầu thành một “log everything” sẽ làm tăng rủi ro mà không nhất thiết cải thiện khả năng phân tích.

## 13. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| Log toàn bộ `args` | Rò token, PII, payload lồng nhau | Mặc định omit; allowlist các field tối thiểu |
| Log mọi `target.toString()` | Rò trạng thái object và thông tin nội bộ | Ghi tên thao tác/nhóm target đã được duyệt |
| Cho rằng String không nhạy cảm nếu tên là `message` | Tên trường không bảo đảm ý nghĩa | Phân loại theo hợp đồng nghiệp vụ |
| Dùng blacklist tên `password` duy nhất | Bỏ sót tên khác và trường nested | Default-deny và review schema |
| Dùng hash đơn giản của email/token | Có thể bị dò và liên kết lâu dài | Omit hoặc dùng cơ chế bảo vệ được phê duyệt |
| Mask bằng regex sau khi đã gửi log | Bản thô có thể đã tới nhiều sink | Biến đổi trước khi phát event |
| Ghi exception message trong catch | Message có thể chứa input nhạy cảm | Mã lỗi an toàn, kiểm tra riêng exception detail |
| In kết quả từ after advice | Response có thể chứa dữ liệu nhạy cảm | Log status hoặc số liệu đã tổng hợp |
| Tin rằng DEBUG tắt nên không có rủi ro | Có exporter/queue/sink khác | Áp dụng giới hạn ở nguồn thu thập |
| Bỏ audit bắt buộc để tránh log | Mất dấu vết an ninh | Schema audit tối thiểu có kiểm soát |
| Sử dụng mọi ID làm metrics label | Cardinality cao và rò định danh | Nhóm trạng thái/tên thao tác hữu hạn |
| Bắt lớp proxy rồi coi đã bao phủ mọi đường gọi | Direct/self-call có thể bỏ qua proxy | Xác minh phạm vi weaving và mọi điểm bắt buộc |
| Lưu args cho async formatter | Giữ tham chiếu nhạy cảm, dữ liệu đổi | Tạo event đã lọc và bất biến ngay tại advice |
| Dùng annotation mà không kiểm thử | Metadata có thể nằm ở chữ ký khác | Xác nhận nguồn Method và chính sách mặc định |

## 14. Checklist trước khi đưa một advice thu thập dữ liệu vào vận hành

- [ ] Xác định **mục đích hợp lệ** của từng trường trong event.
- [ ] Chọn đúng **join point/pointcut**, không dùng phạm vi rộng chỉ vì dễ viết.
- [ ] Biết `args`, `this`, `target`, `result`, `exception` thực chất là dữ liệu nào ở loại điểm đang xét.
- [ ] Có bảng phân loại và **default-deny** cho tham số chưa được duyệt.
- [ ] Không in secret/token/password và payload nhạy cảm, kể cả trong nhánh lỗi.
- [ ] Không gọi `toString()` hoặc serializer trên object tùy ý.
- [ ] Nếu dùng annotation, xác minh metadata đúng interface/method/parameter và inheritance/override.
- [ ] Chỉ phát event **nhỏ, có schema, đã lọc**; không chuyển raw args tới queue.
- [ ] Các field động được giới hạn kích thước, escape an toàn, không tạo metrics label cardinality vô hạn.
- [ ] Correlation ID hoặc định danh thay thế tuân thủ chính sách quyền riêng tư.
- [ ] Sinks và bên thứ ba được phân quyền, mã hóa và áp dụng retention.
- [ ] Kiểm thử canary qua success/failure/debug/async và nhiều advice cùng can thiệp.
- [ ] Chức năng audit bắt buộc vẫn hoạt động với **dữ liệu tối thiểu đã được duyệt**.
- [ ] Advice không làm biến đổi kết quả, ngoại lệ hoặc tác dụng phụ nghiệp vụ chỉ để thay đổi log.
- [ ] Đánh giá định kỳ khi thêm tham số hoặc mở rộng schema.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một advice có thể truy cập `Object[] args`. Có nên mặc định ghi `Arrays.deepToString(args)` để dễ debug?

**Đáp:** không. Điều đó có thể serialize dữ liệu nhạy cảm hoặc object lồng nhau. Cần allowlist các trường đã phân loại an toàn, thường chỉ giữ tên thao tác và trạng thái.

**Câu 2.** Nếu thay số tài khoản bằng SHA-256 không có key rồi ghi vào log, dữ liệu có chắc đã vô danh?

**Đáp:** không. Dữ liệu có không gian giá trị hạn chế có thể bị dò từ điển; hash còn có thể làm liên kết nhiều sự kiện. Cần ưu tiên omission, hoặc cơ chế pseudonymization/hashing được phê duyệt với quản lý khóa và vòng đời phù hợp.

**Câu 3.** Nếu advice after returning nhận object response, có thể coi nó an toàn vì là dữ liệu do server tạo không?

**Đáp:** không. Response có thể chứa thông tin riêng tư, token hoặc bí mật thương mại. Chỉ ghi metadata/kết quả tổng quát được duyệt.

**Câu 4.** Nếu tên phương thức là `getCustomer`, ta nên log `customerId` để đo latency theo từng khách không?

**Đáp:** thông thường không dùng ID khách hàng làm label metrics; cardinality cao và làm lộ mối liên kết. Dùng tên thao tác, trạng thái và duration histogram; nếu phải có correlation trong kênh riêng, cần thiết kế có kiểm soát.

**Câu 5.** Một param có `@SafeToLog`; vậy có thể gọi `String.valueOf(value)` dù nó là object bất kỳ không?

**Đáp:** không. Annotation không thay thế xác minh loại và ý nghĩa giá trị. Ví dụ Java giới hạn việc xuất dữ liệu vào enum `Channel`; object tùy ý vẫn bị omit.

**Câu 6.** Nếu proxy advice đã không ghi token, có nghĩa không còn rủi ro rò token trong toàn ứng dụng không?

**Đáp:** không. HTTP logging, exception formatter, tracing exporter, ORM, profiler hoặc lời gọi không đi qua proxy vẫn có thể thu thập. Cần kiểm soát theo **toàn luồng dữ liệu**.

**Câu 7.** Một audit bắt buộc cần biết ai thực hiện thao tác. Có nên tắt toàn bộ audit để không lưu PII?

**Đáp:** không. Cần phân biệt nhật ký nghiệp vụ thường và audit được kiểm soát; audit nên dùng chỉ danh tính đã xác thực và các trường tối thiểu theo chính sách, có phân quyền và retention rõ.

## 16. Tài liệu tham khảo

- [OWASP Logging Cheat Sheet – Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): phân loại những nhóm dữ liệu thường không nên ghi nguyên vào log, bảo vệ đường truyền/kho lưu và tránh log injection.
- [OWASP Secure Logging Benchmark](https://owasp.github.io/www-project-secure-logging-benchmark/): các rủi ro thực tế khi dữ liệu xác thực và dữ liệu cá nhân đi vào log.
- [Java SE 17 – Executable.getParameterAnnotations()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getParameterAnnotations()): đọc annotation của từng tham số theo thứ tự khai báo.
- [Java SE 17 – Dynamic Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): lớp proxy và cơ chế chuyển lời gọi qua InvocationHandler.

**Ghi nhớ:** Một advice nhận được tham số không có nghĩa nó được phép **thu thập toàn bộ tham số**. Hãy chọn đúng join point, hiểu ngữ cảnh, mặc định không lưu dữ liệu thô, chỉ tạo event tối thiểu đã phân loại và kiểm thử nhiều đường ghi để tránh rò rỉ. Quan sát tốt là quan sát **đủ để vận hành đúng**, không phải thu thập càng nhiều càng tốt.
