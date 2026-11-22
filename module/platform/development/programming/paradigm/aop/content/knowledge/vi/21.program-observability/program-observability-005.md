# Che dữ liệu nhạy cảm và giới hạn kích thước tham số trong Aspect (AOP)

## 1. Mục tiêu

Khi sử dụng **Aspect-Oriented Programming (AOP)** để quan sát chương trình, một advice có thể nhìn thấy phương thức được gọi, danh sách đối số, kết quả trả về, ngoại lệ và thời gian thực thi. Khả năng chặn tại nhiều điểm gọi rất hữu ích để ghi log, trace và đo hiệu năng, nhưng cũng tạo ra một đường rò rỉ thông tin tập trung: chỉ một interceptor ghi tất cả tham số có thể khiến mật khẩu, mã truy cập, dữ liệu cá nhân hoặc payload lớn xuất hiện ở hệ thống log.

Bài này hướng dẫn thiết kế **chính sách quan sát an toàn ở lớp AOP**: phân loại tham số, che hoặc bỏ qua dữ liệu nhạy cảm, chỉ cho phép xuất các trường đã duyệt, giới hạn độ lớn trước khi dựng bản ghi, rồi kiểm tra cả dữ liệu lẫn đường đi của bản ghi quan sát.

Kết quả mong đợi:

- Biết **cần che gì, che ở đâu, ở thời điểm nào** trong chu trình around/before/after advice.
- Phân biệt ***redact*** (thay bằng ký hiệu), ***omit*** (không xuất), ***truncate*** (cắt có giới hạn) và ***aggregate*** (chỉ xuất thông tin tổng hợp).
- Tính giới hạn theo **số tham số**, **số byte UTF-8 mỗi giá trị**, **tổng byte mỗi sự kiện**, độ sâu của cấu trúc và số phần tử.
- Tránh gọi `toString()`, serializer, formatter hoặc mã có tác dụng phụ trên đối tượng tùy ý chỉ để tạo log.
- Xử lý injection vào log, lỗi telemetry, ngoại lệ nghiệp vụ, và nguy cơ vô tình lộ dữ liệu từ các kênh quan sát khác.

Trọng tâm là **AOP tổng quát**, áp dụng cho interception theo proxy, weaving hoặc interceptor tương đương. Chi tiết điểm chặn thay đổi theo kỹ thuật hiện thực, nhưng nguyên tắc bảo vệ dữ liệu và giới hạn tài nguyên vẫn giữ nguyên.

## 2. Vì sao AOP quan sát dễ làm lộ dữ liệu?

Một lời gọi tưởng như bình thường:

```java
paymentService.charge(cardNumber, securityCode, amount, customerProfile);
```

Nếu một advice ghi `Arrays.toString(args)` hoặc biến toàn bộ đối số thành JSON, nó có thể đưa cả số thẻ, mã bảo mật và thông tin khách hàng vào log. Log thường được sao chép qua nhiều chặng: console, file, collector, queue, hệ thống lưu trữ, dashboard và bản xuất hỗ trợ sự cố. Mỗi chặng có chính sách truy cập, thời gian lưu và hệ thống sao lưu riêng.

Rủi ro không giới hạn ở mật khẩu. Cần rà soát theo ngữ cảnh nghiệp vụ:

| Loại dữ liệu | Ví dụ | Cách xử lý mặc định |
|---|---|---|
| Bí mật xác thực | Mật khẩu, khóa API, access/refresh token, cookie phiên | **Không ghi giá trị**; redact hoặc omit |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ, hồ sơ khách hàng | Omit hoặc ghi dạng tối thiểu đã được duyệt |
| Dữ liệu tài chính/y tế hoặc hồ sơ riêng tư | Số tài khoản, bệnh án, định danh | Không đưa vào log tổng quát |
| Nội dung người dùng | Tin nhắn, văn bản nhập, biểu mẫu, URL chứa query bí mật | Mặc định ẩn; chỉ xuất trường đã xét duyệt |
| Dữ liệu kích thước lớn | File, byte array, ảnh, JSON sâu, collection dài | Metadata tổng hợp và giới hạn số lượng/kích thước |
| Thông tin vận hành ít nhạy cảm | Tên operation cố định, cờ trạng thái đã duyệt, mã lỗi nội bộ | Có thể allowlist và giới hạn chặt |

Không thể xác định nhạy cảm chỉ bằng kiểu dữ liệu: cùng một `String` có thể là trạng thái `"APPROVED"` hoặc một token. Tên biến như `password` cũng không đủ: tên tham số có thể vắng trong bytecode, bị đổi hoặc nằm sâu trong một DTO. Một tập regex tìm `password|token|secret` có thể hỗ trợ phát hiện bổ sung, nhưng không đủ làm cơ chế bảo vệ chính.

**Nguyên tắc ưu tiên:** *không xuất dữ liệu chưa được phê duyệt*. Redaction theo tên trường là một lớp bổ sung, còn **allowlist** theo hợp đồng quan sát giúp chặn cả những trường mới chưa được đặt tên trong blacklist.

## 3. Điểm chặn AOP và luồng dữ liệu an toàn

Trong AOP, một **join point** là vị trí thực thi mà hệ thống có thể quan sát/chặn theo mô hình của công cụ; một **pointcut** chọn tập join point; **advice** là hành vi bổ sung chạy trước, sau hoặc bao quanh điểm đó.

Một cách đặt trách nhiệm rõ ràng:

```text
Lời gọi nghiệp vụ
    |
    v
Around advice
    |-- Xác định phương thức / hợp đồng quan sát
    |-- Phân loại từng tham số (metadata, annotation, allowlist)
    |-- Redact / omit trước khi chuyển thành chuỗi
    |-- Giới hạn chiều dài, số phần tử và tổng bản ghi
    |-- Escape ký tự điều khiển, chuẩn bị event an toàn
    |-- Gửi event đến sink quan sát
    |
    +--> proceed / gọi phương thức gốc
    |       |
    |       +--> trả kết quả hoặc ném ngoại lệ
    |
    +-- Ghi trạng thái / thời lượng an toàn
    +-- Trả nguyên kết quả hoặc ném lại ngoại lệ gốc
```

Điểm quan trọng là **lọc trước khi chuyển đổi hoặc serialize**, không phải ghi nguyên dữ liệu rồi mới tìm cách xóa ở collector. Nếu hệ thống đã từng in bí mật ở console hay buffer trung gian, xóa ở bước sau không thể thu hồi mọi bản sao.

Một interceptor phù hợp nên tách ít nhất ba trách nhiệm:

1. **Classification policy:** trường/đối số nào được phép quan sát? Phạm vi và trạng thái dữ liệu có thay đổi theo môi trường hoặc use case không?
2. **Safe value renderer:** cách biểu diễn giá trị đã được phép, với escape và định mức tài nguyên.
3. **Event writer:** xuất bản ghi có kích thước cố định, tránh ghi trùng, quản lý lỗi của hệ thống telemetry.

Bộ phân loại nên có chính sách mặc định `HIDDEN` khi không biết kiểu, tên, annotation hoặc cấu trúc. Nếu áp dụng nhiều quy tắc, quy tắc **nhạy cảm/deny** phải thắng quy tắc cho phép.

## 4. Bốn cách xử lý và khi nào dùng

### 4.1. Omit: không xuất giá trị

Đối với token, payload tự do, tập tin hoặc đối tượng chưa phân loại, có thể chỉ xuất tên thao tác và trạng thái. Ví dụ:

```text
operation=payment.authorize outcome=success duration_ms=18
```

Nếu cần biết một tham số có được cung cấp hay không, dùng cờ boolean đã được duyệt như `hasAttachment=true`; đôi khi cả sự tồn tại, chiều dài hoặc tần suất của dữ liệu cũng nhạy cảm, vì vậy không tự động ghi metadata.

### 4.2. Redact: thay giá trị bằng ký hiệu an toàn

Ví dụ: `arg0=[REDACTED]`. Ký hiệu này xác nhận trường đã được che, nhưng không để lộ chuỗi gốc. Tránh giữ bốn số cuối, prefix/suffix của token, domain email hoặc biểu thức khớp nếu chưa có yêu cầu rõ và kiểm tra rủi ro liên kết dữ liệu.

Với đối tượng lồng nhau, redaction ở **trường gốc** thường an toàn hơn việc serialize toàn bộ rồi thay chuỗi con. JSON được dựng trước khi che có thể đã chứa bí mật trong bộ nhớ hoặc sự kiện trung gian.

### 4.3. Truncate: giới hạn giá trị được phép ghi

Truncate chỉ có ý nghĩa với **dữ liệu đã được phân loại là có thể quan sát**. Một token bị cắt còn 20 byte vẫn có thể lộ token; **truncation không thay thế redaction**.

Một giới hạn rõ ràng gồm: tối đa bao nhiêu byte, tính sau khi escape hay trước khi escape, ký hiệu cắt có được tính vào ngân sách không, và có cắt giữa ký tự Unicode hay không. Trong Java:

- `String.length()` đếm **UTF-16 code unit**, không đồng nghĩa số ký tự Unicode theo code point, càng không đồng nghĩa số byte UTF-8.
- Một emoji thường chiếm **hai UTF-16 code unit và bốn byte UTF-8**.
- Escape ký tự xuống dòng `\n` thành hai ký tự hiển thị `\\n` khiến bản ghi lớn hơn dữ liệu đầu vào.
- Phải giữ chỗ cho ký hiệu cắt như `…` (ba byte UTF-8), nếu ký hiệu này nằm trong hạn mức.

Nếu giới hạn áp cho payload sau mã hóa hoặc hệ thống lưu trữ, cần đo **byte của biểu diễn cuối cùng**. Nếu hệ thống dùng JSON, dấu nháy, backslash, tên trường và metadata cũng tiêu tốn byte.

### 4.4. Aggregate: ghi thông tin tổng hợp

Với `byte[]`, collection hoặc DTO lớn, thường chỉ cần loại dữ liệu, mã thao tác, số item theo một khoảng đã cho phép, hoặc trạng thái kiểm tra. Ví dụ `attachment_present=true` hoặc `batch_size_bucket=100-999`. Không nên gọi `collection.toString()` hay duyệt toàn bộ cấu trúc để lấy một đoạn đầu nếu có thể truy xuất thông tin tổng hợp an toàn.

Hash không tự động làm dữ liệu ẩn danh: giá trị có miền nhỏ, email hoặc mã khách hàng có thể bị đoán bằng tấn công từ điển; hash ổn định còn cho phép liên kết hoạt động giữa nhiều request. Chỉ dùng hash/HMAC định danh nếu có mục đích đã duyệt, quản lý khóa và chính sách thời hạn rõ ràng.

## 5. Thiết lập ngân sách quan sát

Giới hạn kích thước cần đo tại **nhiều cấp**, vì chỉ cắt từng chuỗi chưa đủ:

| Cấp | Biện pháp | Trường hợp cần tránh |
|---|---|---|
| Lựa chọn join point | Chỉ instrument những phương thức cần thiết | Ghi mọi getter, vòng lặp, helper nóng |
| Số tham số | Chỉ xử lý N vị trí đầu hoặc các vị trí được chọn | Phương thức có hàng chục trường |
| Kiểu dữ liệu | Chỉ nhận loại scalar đã duyệt | Serializer đi vào đối tượng lớn |
| Chuỗi | Giới hạn byte của bản hiển thị sau escape | Chuỗi nhiều byte Unicode hoặc ký tự điều khiển |
| Collection/array | Giới hạn số phần tử; mặc định không đi sâu | Iterator vô hạn, collection rất lớn |
| Độ sâu lồng nhau | Ngưỡng tối đa (thường chọn không duyệt) | Cấu trúc vòng tròn, đệ quy vô hạn |
| Toàn event | Giới hạn byte tính cả nhãn/dấu phân cách | Nhiều chuỗi nhỏ cộng lại quá lớn |
| Toàn hệ thống | Sampling, rate limit, quota, backpressure | Bão log/trace, tắc collector |

Các con số dưới đây **chỉ là ví dụ thiết kế**, không phải chuẩn chung: tối đa 4 đối số, 24 byte UTF-8 mỗi chuỗi đã escape, 192 byte cho một thông điệp. Chọn hạn mức thực tế theo nhu cầu truy vết, chi phí lưu trữ, tài liệu pháp lý và tải vận hành.

Điều kiện an toàn tài nguyên là giới hạn **trước khi** thực hiện thao tác tốn tài nguyên. Viết `serialize(object)` rồi mới `substring(0, 100)` có thể đã tốn nhiều CPU/RAM và quét dữ liệu nhạy cảm. Với chuỗi đầu vào rất lớn, formatter nên xử lý theo từng code point và dừng khi hết ngân sách, thay vì tạo một bản sao đã escape của toàn chuỗi.

## 6. Ví dụ Java 17 chạy được: interceptor với chính sách ẩn mặc định

Ví dụ dùng **JDK dynamic proxy** để biểu diễn around interceptor tại lời gọi đi qua interface `Operation`. Đây là một cơ chế AOP theo proxy cho phạm vi cụ thể:

- `@Sensitive` đánh dấu tham số phải che, ưu tiên cao nhất.
- `@Visible` cho phép hiển thị **chỉ khi đối số thực sự là String**. Giá trị được escape và giới hạn 24 byte UTF-8.
- Tham số khác được giữ ở trạng thái `[HIDDEN]`, không bị gọi `toString()`.
- Chỉ xét tối đa 4 đối số; kết quả cuối cùng bị giới hạn 192 byte. Mã đi qua code point nên không chia đôi cặp surrogate hợp lệ.
- Interceptor gọi phương thức gốc và ném lại nguyên nhân gốc nếu `Method.invoke` gói lỗi bằng `InvocationTargetException`.

Lưu chương trình dưới tên **SafeAspectDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;

public class SafeAspectDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Sensitive {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Visible {}

    public interface Operation {
        String execute(@Sensitive String password,
                       @Visible String action,
                       @Visible String message,
                       Object body);
    }

    static String limit(String text, int maxBytes, boolean escape) {
        StringBuilder out = new StringBuilder();
        int used = 0;
        for (int offset = 0; offset < text.length();) {
            int cp = text.codePointAt(offset);
            int next = offset + Character.charCount(cp);
            String piece = new String(Character.toChars(cp));
            if (escape) {
                if (cp == '\n') piece = "\\n";
                else if (cp == '\r') piece = "\\r";
                else if (cp == '\t') piece = "\\t";
                else if (cp == '\\') piece = "\\\\";
                else if (cp == '"') piece = "\\\"";
                else if (Character.isISOControl(cp) || cp == 0x2028 || cp == 0x2029) {
                    piece = String.format("\\u%04X", cp);
                }
            }
            int needed = piece.getBytes(StandardCharsets.UTF_8).length;
            int marker = next < text.length() ? 3 : 0;
            if (used + needed + marker > maxBytes) {
                out.append('…');
                return out.toString();
            }
            out.append(piece);
            used += needed;
            offset = next;
        }
        return out.toString();
    }

    static String audit(Method method, Object[] arguments) {
        Object[] args = arguments == null ? new Object[0] : arguments;
        Parameter[] params = method.getParameters();
        StringBuilder line = new StringBuilder("call ")
                .append(limit(method.getName(), 32, false)).append('(');
        int shown = Math.min(args.length, 4);
        for (int i = 0; i < shown; i++) {
            if (i > 0) line.append(", ");
            line.append("arg").append(i).append('=');
            if (params[i].isAnnotationPresent(Sensitive.class)) {
                line.append("[REDACTED]");
            } else if (params[i].isAnnotationPresent(Visible.class)
                    && args[i] instanceof String text) {
                line.append('"').append(limit(text, 24, true)).append('"');
            } else {
                line.append("[HIDDEN]");
            }
        }
        if (args.length > shown) line.append(", ... omitted=").append(args.length - shown);
        line.append(')');
        return limit(line.toString(), 192, false);
    }

    public static void main(String[] ignored) {
        Operation implementation = (password, action, message, body) -> "SUCCESS";
        Operation proxied = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] {Operation.class},
                (proxy, method, args) -> {
                    System.out.println(audit(method, args));
                    try {
                        return method.invoke(implementation, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });

        System.out.println(proxied.execute(
                "pass-123", "CREATE", "hello\nabcdefghijklmnopqrstuvw", new Object()));
    }
}
```

Biên dịch và chạy với Java 17 hoặc phiên bản tương thích mới hơn:

```bash
javac --release 17 -encoding UTF-8 SafeAspectDemo.java
java SafeAspectDemo
```

**Kết quả đã kiểm tra:**

```text
call execute(arg0=[REDACTED], arg1="CREATE", arg2="hello\nabcdefghijklmn…", arg3=[HIDDEN])
SUCCESS
```

Giải thích kết quả:

1. `arg0` mang `@Sensitive` nên không xuất `pass-123`.
2. `arg1` được phép quan sát và có kích thước nhỏ; giá trị `CREATE` xuất hiện.
3. `arg2` chứa xuống dòng: formatter đổi xuống dòng thật thành hai ký tự `\\n`, cắt trong ngân sách 24 byte **bao gồm** ký hiệu `…`.
4. `arg3` là một `Object` không được cho phép và không bị chuyển thành chuỗi.
5. Hàm nghiệp vụ vẫn trả `SUCCESS`; interceptor quan sát không thay đổi dữ liệu mà phương thức đích nhận.

**Phạm vi ví dụ:** `@Visible` là một cam kết do người viết mã đưa ra, không phải kiểm định tự động rằng dữ liệu không nhạy cảm. Việc vô tình gắn annotation cho tham số chứa bí mật vẫn có thể làm lộ nội dung. Cơ chế proxy chỉ chặn lời gọi đi **qua proxy** và phương thức thuộc interface; nó không tự chặn mọi lời gọi nội bộ. Ví dụ không trình bày collector production, đo latency hay lifecycle bất đồng bộ. Một hệ thống thực cần chính sách được quản lý tập trung và kiểm tra thường xuyên.

Mã `limit(..., escape=false)` ở cấp event giả định các đoạn giá trị được đưa vào đã qua safe renderer. Vì vậy **không** được lấy chuỗi tùy ý từ exception, object hoặc request ghép thẳng vào event rồi chỉ áp dụng hàm cắt tổng này. Trong chương trình demo, nguồn dữ liệu động của user phải đi qua `limit(..., escape=true)` trước khi đưa vào event. Bản triển khai production nên dựng event theo trường có kiểu rõ ràng, và chỉ serialize một lần bằng formatter an toàn của đích lưu trữ.

## 7. Khi tham số là DTO, Map, List, array hoặc object lồng nhau

Một lỗi phổ biến là đặt `@Sensitive` trên vài trường rồi vẫn gọi serializer để dựng toàn bộ object. DTO có thể chứa field mới, getter tính toán, tham chiếu vòng, lazily-loaded value hoặc tham chiếu đến credential. Ngay cả annotation cũng có thể khác nhau giữa field, getter, constructor parameter và interface; đừng giả định một annotation sẽ tự đi theo mọi cách truy cập.

Chính sách hợp lý:

- **Mặc định omit object nguyên khối.** Nếu cần chi tiết, khai báo danh sách đường dẫn trường được cho phép, ví dụ `command.kind` hoặc `request.region`, và đọc bằng accessor đã kiểm tra.
- **Không duyệt graph tùy ý.** Giới hạn độ sâu, số phần tử, thời gian, tổng byte và tham chiếu đã ghé thăm; tránh tuần hoàn.
- **Không tự gọi getter vì đang quan sát.** Getter có thể đọc I/O, tải dữ liệu, ném lỗi, mutate state hoặc gây thêm join point được instrument.
- **Không chuyển binary thành Base64 để log.** Mã hóa Base64 vừa tăng kích thước vừa giữ nguyên dữ liệu.
- **Không để serializer đa hình quyết định lớp cần khởi tạo/đọc.** Chỉ xử lý những kiểu đã cho phép, tránh việc đi sâu vào đối tượng ngoại lai.
- **Xử lý dữ liệu null và thiếu:** quyết định có được log trạng thái `missing`/`null` hay không. Trong một số use case, bản thân sự tồn tại của trường cũng tiết lộ dữ liệu.

Ví dụ một payload có `userId`, `status`, `accessToken` và `metadata`: chỉ nên xuất `operation`, một trạng thái nằm trong tập giá trị cố định đã duyệt và có thể là thời gian xử lý. Không nên sao chép cả object rồi che mỗi trường `accessToken` vì các trường còn lại có thể cũng nhận bí mật trong tương lai.

Nếu thật sự cần recursive renderer, cần có ngân sách tường minh và được chứng minh trên dữ liệu độc hại: `maxDepth`, `maxNodes`, `maxCollectionItems`, `maxTotalBytes`, phát hiện vòng tham chiếu, timeout/budget CPU và fail-closed khi gặp kiểu chưa được hỗ trợ. Việc duyệt đến hạn rồi mới cắt string cuối là quá muộn.

## 8. Chính sách theo phương thức, tham số và kết quả trả về

Tầng AOP nên mô tả rõ nơi nào cho phép xuất dữ liệu. Các khả năng thường gặp:

**Allowlist theo phương thức và vị trí.** Dùng bộ metadata liên kết join point với các vị trí đối số đã được duyệt; an toàn hơn lựa chọn toàn cục dựa trên tên biến. Trong Java, `Method.getParameters()` có thể thấy các annotation runtime của tham số. Tuy nhiên `Parameter.getName()` không bảo đảm chứa tên nguồn nếu không biên dịch với `-parameters`; dùng chỉ số hoặc metadata ổn định nếu cần chính xác.

**Annotation.** Có thể gắn đánh dấu nhạy cảm/có thể quan sát vào tham số hoặc property. Annotation chỉ hiệu lực ở nơi công cụ đọc nó: annotation trên interface không nhất thiết tồn tại trên implementation và ngược lại. Nếu thiếu metadata hoặc có xung đột chính sách, chọn `HIDDEN`.

**Kiểu và schema.** Một enum trạng thái đã duyệt dễ quan sát hơn raw String; một ID có cardinality rất cao có thể làm metric tăng chi phí hoặc cho phép liên kết người dùng. Không phải loại dữ liệu có thể log được cũng phù hợp để đặt thành nhãn metric.

**Giá trị trả về.** Cần áp dụng chính sách **riêng** cho return value. Tránh advice sau phương thức kiểu `logger.info("result={}", result)`: giá trị có thể là token, DTO hoặc payload lớn, và `toString()` có thể kích hoạt hành vi ngoài ý muốn. Thường chỉ xuất `outcome=success`, số lượng đã xét duyệt hoặc loại lỗi.

**Ngoại lệ.** `Throwable.getMessage()` có thể chứa query SQL, URL, thông tin người dùng hoặc tham số. Stack trace có thể chứa tên file, đường dẫn, input và dữ liệu ngữ cảnh trong suppressed exceptions. Giới hạn ghi theo loại lỗi đã phân loại, mã lỗi chuẩn hóa và chính sách stack trace riêng; không in nguyên toàn bộ đối tượng exception theo mặc định.

## 9. Escape dữ liệu để chống giả mạo log

Bỏ bí mật thôi chưa đủ. Một giá trị được phép xuất vẫn có thể chứa ký tự làm hỏng cấu trúc sự kiện:

```text
hello
2026-10-20 ERROR login failed
```

Nếu in nguyên giá trị hai dòng, người đọc hoặc parser có thể hiểu dòng thứ hai như một sự kiện hệ thống khác (**log injection**). Hãy escape các ký tự điều khiển, dấu phân tách và ký tự đặc biệt của định dạng đích. Với JSON, ưu tiên serializer JSON được cấu hình an toàn cho những trường **đã được phân loại**; không tự nối dấu nháy và dấu phẩy với dữ liệu gốc.

Một pipeline đáng tin:

```text
original argument
    -> classify (deny/allow)
    -> extract only allowed scalar
    -> normalize/escape for target format
    -> enforce field byte budget
    -> build structured event with bounded fields
    -> enforce entire event budget
    -> publish through controlled sink
```

Nếu giới hạn áp cho JSON hay một giao thức cụ thể, tính byte **sau khi serialization cuối cùng** hoặc dùng writer có quota trong lúc encode. Không giả định ký tự hiển thị bằng một byte. Tránh cắt mù vào giữa sequence escape hoặc giữa hai byte trong UTF-8; có thể cắt ở ranh giới code point/field rồi thêm một marker hợp lệ.

## 10. Advice phải giữ nguyên hành vi nghiệp vụ

Logging là hoạt động phụ trợ. Interceptor quan sát cần hạn chế thay đổi tính đúng đắn:

- **Không thay đổi args gốc để redact.** Tạo biểu diễn an toàn *riêng cho telemetry*; nếu thay chuỗi mật khẩu gốc thành `[REDACTED]` rồi gọi `proceed`, hành vi nghiệp vụ đã bị phá.
- **Không gọi phương thức đích hai lần.** Trong around advice, kiểm soát chính xác một lần gọi trong đường thành công thông thường; đừng retry chỉ vì log thất bại.
- **Không để lỗi ghi log che ngoại lệ gốc.** Cần chính sách cách ly lỗi exporter/sanitizer với ứng dụng. Nếu chính sách yêu cầu telemetry có tính bắt buộc, thay đổi luồng nghiệp vụ phải được thiết kế và công bố rõ.
- **Không gọi `toString()` trên tham số lạ.** `toString()` là mã người dùng, có thể tốn kém, có tác dụng phụ hoặc vô tình in field nhạy cảm.
- **Không lưu reference đến args trong queue telemetry.** Một asynchronous appender nhận trực tiếp object sẽ serialize sau thời điểm advice, có thể nhìn thấy giá trị đã thay đổi hoặc giữ một object graph lớn trong bộ nhớ. Đẩy **snapshot đã lọc và giới hạn** vào queue.
- **Không giả định mọi lời gọi đều đồng bộ.** Với future, callback hoặc stream, kết quả được quan sát có thể chỉ là handle; advice đo "thành công" khi trả handle không nhất thiết nghĩa là công việc đã hoàn tất.

Nếu bản thân sink bị quá tải, áp dụng chính sách giảm tải có dự báo (sampling, drop counters, bounded queue). Đừng giữ một request đang chờ vô thời hạn chỉ vì đẩy log vào hàng đợi đầy.

## 11. Thất bại thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cải thiện |
|---|---|---|
| Log chứa thông tin xác thực | Chặn toàn bộ tham số bằng formatter tổng quát | Fail-closed; chỉ render allowlist, redact bí mật |
| Giữ lại prefix token sau khi cắt | Dùng truncation như biện pháp bảo mật | Omit hoặc redact hoàn toàn |
| Bộ nhớ tăng khi có payload lớn | Serialize hết rồi mới `substring` | Dừng ngay khi hết budget trong renderer |
| Dòng log bị tách, giả mạo level | Không escape CR, LF và dấu phân cách | Escape có xét format đích trước khi ghi |
| Cắt hỏng emoji/ký tự Unicode | Dùng chỉ số UTF-16/byte thô tùy ý | Cắt theo code point hoặc encoder có giới hạn |
| Log lộ nội dung lỗi | In nguyên `exception.getMessage()`/stack trace | Phân loại mã lỗi, rà soát thông điệp và stack |
| Sau khi thêm field mới xuất hiện dữ liệu riêng tư | Blacklist theo tên trường | Deny-by-default và review khi thay schema |
| Mất dữ liệu nghiệp vụ | Redact trực tiếp đối số đưa vào `proceed` | Chỉ tạo bản telemetry đã làm sạch |
| Lỗi log làm request thất bại | Recorder ném ngoại lệ trong advice | Cách ly lỗi quan sát theo chính sách |
| Tốn CPU trên đường gọi nóng | Instrument quá nhiều điểm + reflection/regex mỗi lần | Cache chính sách phương thức, giảm cardinality/sampling |
| Log chứa toàn bộ object khi sink xử lý muộn | Đưa reference sống vào queue | Chụp giá trị an toàn, có kích thước hữu hạn trước enqueue |

## 12. Kiểm thử: xem đầu ra quan sát là bề mặt có thể bị tấn công

Ngoài kiểm thử chức năng, cần kiểm tra dữ liệu được gửi đến **đúng sink mà ứng dụng dùng**, bao gồm log thành công, lỗi, log của retry, trace attribute và event bất đồng bộ. Có thể dùng sink giả để thu thập sự kiện và assert nội dung:

1. **Canary bí mật:** truyền mật khẩu/token giả dễ nhận diện; assert **không** xuất hiện trong bất kỳ event, log lỗi, exception render hoặc hàng đợi telemetry nào.
2. **Trường mới:** thêm một thuộc tính nhạy cảm vào DTO; assert renderer mặc định vẫn giữ `[HIDDEN]`.
3. **Chuỗi cực lớn:** cung cấp chuỗi dài hàng triệu ký tự vào tham số đã allowlist; đo rằng output không vượt byte quota và không tạo bản sao khổng lồ.
4. **Unicode:** kiểm thử ASCII, tiếng Việt, emoji surrogate pair, ký tự kết hợp và chuỗi chỉ chứa dấu điều khiển; kiểm tra tính hợp lệ của output UTF-8.
5. **Log injection:** chứa `\r`, `\n`, `\t`, quote, backslash và ký tự xuống dòng Unicode; sự kiện vẫn có cấu trúc hợp lệ.
6. **Object độc hại:** tạo object có `toString()` ném lỗi hoặc tăng bộ đếm; assert interceptor không gọi nó khi kiểu chưa được duyệt.
7. **Collection vòng và rất lớn:** renderer không rơi vào đệ quy vô hạn hoặc duyệt không giới hạn.
8. **Lỗi nghiệp vụ:** phương thức ném exception; advice không che nguyên nhân, không thêm giá trị nhạy cảm vào failure event.
9. **Lỗi quan sát:** sink ném lỗi hoặc queue đầy; luồng nghiệp vụ tuân theo chính sách đã công bố.
10. **Ngân sách tổng:** nhiều tham số vừa dưới quota riêng vẫn không làm event vượt giới hạn chung.

Kiểm tra **đầu ra byte thực tế**, không chỉ độ dài `String.length()`. Nếu sink dùng JSON hoặc escape bổ sung, test event sau serialization. Với log có cấu trúc, bảo đảm tên trường và metadata cố định không phá quota; với metrics, bảo đảm số lượng giá trị nhãn không tăng vô hạn.

## 13. Vận hành và quản trị chính sách

Một chính sách AOP tốt không kết thúc ở formatter. Cần giữ cùng quy tắc qua môi trường và version triển khai:

- **Điểm instrument:** ghi rõ tập pointcut và kiểu join point được bảo vệ. Proxy-based interception có thể bỏ qua lời gọi nội bộ không đi qua proxy; weaving có phạm vi khác, nên phải audit phạm vi thật.
- **Quyền bật debug:** chế độ debug không được tự động vô hiệu hóa redaction. Cấp quyền tạm thời để xem một số trường vẫn cần kiểm soát chặt và dấu vết kiểm toán.
- **Bản đồ dữ liệu:** mỗi trường xuất log có owner, mục đích, mức độ nhạy cảm và thời gian giữ. Thay schema hoặc annotation phải qua kiểm tra tương ứng.
- **Bảo vệ hạ tầng lưu trữ:** phân quyền, mã hóa, thời gian lưu, xóa dữ liệu, quota và kiểm soát việc tải log xuống là các lớp bắt buộc dù formatter đã an toàn.
- **Đánh giá định kỳ:** dùng dữ liệu thử/canary và kiểm tra sample thực tế đã được phép; tìm đường ghi trực tiếp nằm ngoài interceptor (logger thủ công, library, framework, profiler, dump).
- **Quan sát chính cơ chế bảo vệ:** đếm số giá trị bị ẩn/cắt, số event bị bỏ hoặc lỗi exporter bằng metric tổng hợp, tránh đưa dữ liệu gốc vào metric.

Một số trường hợp cần điều tra sâu. Hãy thiết kế kênh thu thập chuyên biệt có cấp quyền, phạm vi và thời hạn rõ ràng; đừng mở rộng log AOP phổ thông thành kho sao chép mọi input.

## 14. Checklist trước khi dùng advice trong sản phẩm

- [ ] Có allowlist theo use case; khi thiếu metadata thì ẩn.
- [ ] Bí mật và dữ liệu riêng tư được omit/redact **trước** khi serialize.
- [ ] Renderer không gọi `toString()` hoặc duyệt đối tượng lạ.
- [ ] Có ngân sách theo tham số, tổng event, phần tử, độ sâu và tốc độ phát.
- [ ] Giới hạn theo byte của định dạng đích; không cắt hỏng Unicode/escape.
- [ ] Không để ký tự điều khiển tạo log giả hoặc phá JSON.
- [ ] Kết quả trả về, ngoại lệ và các đường bất đồng bộ dùng chính sách riêng.
- [ ] Advice giữ nguyên args, return và exception của nghiệp vụ.
- [ ] Test có canary bí mật, payload lớn, chuỗi độc hại, scope interception và lỗi sink.
- [ ] Sink và log store có quyền truy cập, lưu giữ và quota phù hợp.

**Điểm cốt lõi:** AOP giúp đưa quan sát vào một vị trí tập trung, nên lỗi ở vị trí đó cũng ảnh hưởng đồng loạt nhiều chức năng. Hãy coi dữ liệu của join point là **không đáng tin và có thể nhạy cảm**; chỉ phát các trường được duyệt, che bí mật trước khi chuyển đổi, đặt giới hạn byte/tài nguyên cho từng bước, và không làm thay đổi hành vi nghiệp vụ.
