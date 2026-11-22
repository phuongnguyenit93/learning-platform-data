# Lựa chọn cơ chế SASL từ nhà cung cấp và chính sách hiện hành

## 1. Cơ chế có sẵn chưa chắc là cơ chế được phép dùng

SASL tách API chung khỏi các cơ chế xác thực. Nhà cung cấp (provider) cung cấp phần triển khai; ứng dụng quyết định cơ chế nào phù hợp với chính sách, đối tác và thông tin xác thực đang có.

Hãy phân biệt bốn câu hỏi:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Cơ chế có tên trong chuẩn hay registry không? | Đặc tả và tên cơ chế chính thức |
| Môi trường Java cục bộ có triển khai không? | Provider/factory đã đăng ký, đúng phía client hoặc server |
| Đối tác có chấp nhận không? | Khả năng cơ chế do giao thức công bố và cấu hình máy chủ |
| Tổ chức có cho phép dùng trong kết nối này không? | Chính sách cơ chế, bảo vệ đường truyền, danh tính và chất lượng bảo vệ |

Không lấy toàn bộ danh sách provider công bố rồi gửi thông tin xác thực bằng cơ chế đầu tiên dùng được. Danh sách khả năng không phải danh sách được đánh giá an toàn cho mọi mục đích. [Java SASL Programming Guide](https://docs.oracle.com/en/java/javase/25/security/java-sasl-api-programming-and-deployment-guide1.html).

Bài này dùng API vẫn áp dụng trên JDK hiện đại. Mục tiêu là chọn đúng cơ chế và cách triển khai, không khôi phục các cơ chế đã bị chính sách hiện tại loại bỏ.

## 2. Viết yêu cầu trước khi chọn tên cơ chế

Một chính sách hữu ích phải trả lời được các câu hỏi cụ thể:

- Người dùng hoặc dịch vụ đang có loại thông tin xác thực nào: vé Kerberos, mật khẩu, chứng chỉ máy khách hay access token?
- Đối tác và giao thức thực sự hỗ trợ cơ chế nào?
- Có yêu cầu ràng buộc xác thực với kênh TLS (channel binding) không?
- Cần bảo vệ dữ liệu sau xác thực bằng TLS, lớp bảo vệ SASL hay cả hai?
- Có cho phép danh tính ẩn danh hoặc hoạt động thay danh tính khác không?
- Khi không có cơ chế đáp ứng, phải từ chối hay có ngoại lệ đã được phê duyệt?

Ví dụ một hồ sơ cho hệ thống doanh nghiệp đã có Kerberos có thể ưu tiên GSSAPI. Một dịch vụ dùng thông tin xác thực dựa trên token có thể chọn cơ chế OAuth phù hợp với giao thức. Đây là sự phù hợp với hạ tầng, không phải thứ hạng tuyệt đối giữa mọi cơ chế.

Ghi chính sách thành danh sách được phép có thứ tự ưu tiên, gắn với loại kết nối và phiên bản chính sách. Không để thứ tự từ máy chủ hay provider vô tình trở thành quyết định bảo mật của ứng dụng.

## 3. Các nhóm cơ chế hiện đại có điều kiện triển khai khác nhau

| Cơ chế hoặc nhóm | Điều kiện cần đánh giá |
| --- | --- |
| `SCRAM-SHA-256` | Hai đầu có triển khai, quản lý thông tin xác thực và tham số phù hợp, kiểm tra bằng chứng cuối đúng đặc tả |
| `SCRAM-SHA-256-PLUS` | Có đủ hỗ trợ channel binding của cơ chế, thư viện và lớp TLS; không chỉ đổi tên từ cơ chế không PLUS |
| `GSSAPI` | Có ngữ cảnh Kerberos/thông tin xác thực phù hợp, tên dịch vụ/host và hạ tầng được cấu hình đúng |
| `OAUTHBEARER` | Giao thức/provider hỗ trợ và có access token phù hợp; máy chủ kiểm tra token theo chính sách |
| `EXTERNAL` | Danh tính đã được thiết lập ngoài SASL, chẳng hạn từ chứng chỉ máy khách được kiểm tra; máy chủ ánh xạ và chấp nhận danh tính đó |

Đây là các hướng lựa chọn theo ngữ cảnh, không phải danh sách tất cả cơ chế hoặc khuyến nghị bật đồng loạt. `SCRAM-SHA-256` và biến thể PLUS được định nghĩa trong [RFC 7677](https://www.rfc-editor.org/rfc/rfc7677.html). `OAUTHBEARER` được định nghĩa trong [RFC 7628](https://www.rfc-editor.org/rfc/rfc7628.html). `EXTERNAL` được mô tả trong [RFC 4422](https://www.rfc-editor.org/rfc/rfc4422.html#appendix-A).

Với TLS 1.3, channel binding phải phù hợp chuẩn và thư viện đang dùng; RFC 9266 định nghĩa `tls-exporter` và cập nhật các cơ chế liên quan. Không lấy một chuỗi nhận diện chứng chỉ hoặc byte tự chọn rồi gọi đó là channel binding. [RFC 9266](https://www.rfc-editor.org/rfc/rfc9266.html).

Một cơ chế chuẩn không nhất thiết có sẵn trong JDK cài trên máy. Thư viện giao thức có thể có triển khai riêng, dùng SPI của Java hoặc không dùng SPI ấy. Trước khi thêm dependency, xác định đường tích hợp thực sự thay vì giả định `Sasl.createSaslClient()` sẽ tự tìm mọi thư viện có trên classpath.

## 4. Khám phá provider và factory đúng vai trò

Java có hai hướng khám phá:

```java
Enumeration<SaslClientFactory> clientFactories = Sasl.getSaslClientFactories();
Enumeration<SaslServerFactory> serverFactories = Sasl.getSaslServerFactories();
```

Đây là đoạn minh họa cần import các kiểu từ `javax.security.sasl` và `java.util`. Factory phía client và server có thể hỗ trợ tập khác nhau. Có client cho một cơ chế không chứng minh cùng máy có server cho cơ chế ấy.

Mỗi factory có `getMechanismNames(properties)` để liệt kê tên phù hợp các thuộc tính chính sách lựa chọn. Kết quả này phục vụ khám phá khả năng; nó không thử thông tin xác thực, không kết nối máy chủ và không chứng minh đáp ứng mọi yêu cầu thương lượng. Các thuộc tính không phải thuộc tính chính sách lựa chọn có thể bị bỏ qua trong phép liệt kê này. [API SaslClientFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/SaslClientFactory.html).

Các provider có thể cùng triển khai một tên cơ chế. Vì vậy, chỉ in tên cơ chế chưa đủ để biết phần triển khai nào đã được chọn. Khi điều tra môi trường, ghi phiên bản JDK, provider đã đăng ký, mô-đun/runtime đóng gói và chính sách bảo mật. Môi trường Java được thu gọn hoặc thêm provider có thể khác bản JDK đầy đủ trên máy phát triển. [JDK Providers Documentation](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html).

Không sao chép một danh sách cơ chế từ tài liệu của phiên bản JDK khác rồi coi là kết quả kiểm tra máy đang chạy.

## 5. Thuộc tính chính sách là bộ lọc, không phải giấy chứng nhận bảo mật

Các hằng `Sasl.POLICY_*` diễn đạt thuộc tính yêu cầu của cơ chế. Ví dụ:

| Thuộc tính | Điều kiện yêu cầu khi đặt `"true"` |
| --- | --- |
| `Sasl.POLICY_NOANONYMOUS` | Không chọn cơ chế cho phép xác thực ẩn danh |
| `Sasl.POLICY_NOPLAINTEXT` | Không chọn cơ chế dễ bị tấn công nghe lén đơn giản theo thuộc tính cơ chế |
| `Sasl.POLICY_NODICTIONARY` | Yêu cầu không dễ bị tấn công từ điển thụ động theo mô tả API |
| `Sasl.POLICY_NOACTIVE` | Yêu cầu không dễ bị tấn công chủ động thuộc phạm vi mô tả API |

Giá trị chuẩn của các thuộc tính này là chuỗi `"true"`/`"false"`, chẳng hạn trong `Map<String, String>`, không tự thay bằng Boolean rồi trông chờ mọi provider hiểu giống nhau.

Một thuộc tính riêng lẻ không thay cho danh sách cơ chế được phép. Cũng không bật mọi cờ lên rồi cho rằng sẽ có một cơ chế đáp ứng tất cả: nếu yêu cầu không tương thích khả năng môi trường, kết quả hợp lý là không chọn được cơ chế. [API Sasl](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

`POLICY_NOPLAINTEXT` đánh giá đặc tính cơ chế; nó không tự xây dựng TLS hay kiểm tra chứng chỉ. Provider cũng không tự suy ra mọi bảo vệ của giao thức ngoài chỉ từ tên host. Nếu ứng dụng cần TLS đã xác thực trước khi phát bí mật, điều kiện ấy phải được kiểm tra tại lớp quản lý kết nối.

### Chất lượng bảo vệ là yêu cầu khác

`Sasl.QOP` có các giá trị `auth`, `auth-int`, `auth-conf`, lần lượt biểu diễn chỉ xác thực, thêm bảo vệ toàn vẹn và thêm bảo vệ bí mật. Đây là yêu cầu thương lượng mà cơ chế phải hỗ trợ, không phải tính năng mọi cơ chế có thể tạo ra chỉ vì thuộc tính đã được đặt.

`Sasl.SERVER_AUTH` cũng không thay cho kiểm tra danh tính TLS. Thuộc tính không áp dụng với một cơ chế có thể bị bỏ qua; cần hiểu hợp đồng của provider, kiểm tra kết quả và lớp bảo vệ ngoài. Không suy luận rằng một `Map` có nhiều cờ bảo mật đồng nghĩa mọi cờ đều có hiệu lực đối với mọi cơ chế.

## 6. Chọn giao của chính sách, khả năng đối tác và khả năng cục bộ

Một thuật toán lựa chọn định hướng:

```text
Bắt đầu từ danh sách được phê duyệt, theo thứ tự ưu tiên của ứng dụng
  -> giữ tên mà đối tác công bố cho giao thức/kết nối hiện tại
  -> giữ tên mà phía cục bộ có triển khai theo chính sách lựa chọn
  -> kiểm tra điều kiện hạ tầng, TLS, channel binding và loại thông tin xác thực
  -> chọn một ứng viên
  -> yêu cầu tạo đối tượng với đúng ứng viên ấy
  -> thực hiện trao đổi và kiểm chứng kết quả
Không có ứng viên đáp ứng -> từ chối với lỗi có thể chẩn đoán
```

Danh sách cơ chế do máy chủ công bố cũng cần đến từ ngữ cảnh đáng tin cậy theo giao thức. Nếu kẻ tấn công có thể sửa danh sách, việc chọn cơ chế yếu hơn có thể trở thành một cuộc hạ cấp. Khi giao thức nâng cấp bảo vệ bằng TLS, làm mới thông tin khả năng theo quy tắc của giao thức thay vì dùng mù quáng thông tin trước đó. [RFC 4422, mục 6.1.2](https://www.rfc-editor.org/rfc/rfc4422.html#section-6.1.2).

Thứ tự provider và thứ tự cơ chế là hai khái niệm khác nhau. `Sasl.createSaslClient()` dùng framework provider để tìm factory tạo được client; không dùng thứ tự một tập tên ngẫu nhiên như cam kết ưu tiên bảo mật. Nếu ứng dụng cần cưỡng chế một lựa chọn, hãy chọn tên trước rồi truyền mảng chỉ chứa tên đó. [API Sasl.createSaslClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html#createSaslClient(java.lang.String[],java.lang.String,java.lang.String,java.lang.String,java.util.Map,javax.security.auth.callback.CallbackHandler)).

## 7. Chương trình Java 17+: tìm ứng viên mà không gửi bí mật

Ví dụ sau liệt kê khả năng client cục bộ với hai thuộc tính chính sách, rồi lấy giao với danh sách được phép và danh sách máy chủ giả lập. Hồ sơ ví dụ ưu tiên môi trường đã có Kerberos; đó không phải thứ hạng chung giữa GSSAPI và SCRAM.

Chương trình không mở mạng, không đăng nhập và không tạo đối tượng cơ chế có thông tin xác thực. Vì vậy, tên được tìm thấy chỉ là ứng viên.

Lưu thành `SaslSelectionDemo.java`:

```java
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.security.sasl.Sasl;
import javax.security.sasl.SaslClientFactory;

public class SaslSelectionDemo {
    public static void main(String[] args) {
        Map<String, String> properties = Map.of(
                Sasl.POLICY_NOANONYMOUS, "true",
                Sasl.POLICY_NOPLAINTEXT, "true");
        Set<String> local = new HashSet<>();
        Enumeration<SaslClientFactory> factories = Sasl.getSaslClientFactories();
        while (factories.hasMoreElements()) {
            local.addAll(Arrays.asList(
                    factories.nextElement().getMechanismNames(properties)));
        }

        // Dữ liệu giả lập cho bài học, không đọc từ máy chủ thật.
        Set<String> advertised = Set.of("GSSAPI", "SCRAM-SHA-256");
        // Hồ sơ giả định một môi trường doanh nghiệp ưu tiên Kerberos.
        List<String> approvedPreference = List.of("GSSAPI", "SCRAM-SHA-256");
        String candidate = approvedPreference.stream()
                .filter(advertised::contains)
                .filter(local::contains)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException(
                        "No approved locally available candidate"));

        System.out.println("candidate=" + candidate);
        System.out.println("approved=" + approvedPreference.contains(candidate));
        System.out.println("advertised=" + advertised.contains(candidate));
        System.out.println("locallyListed=" + local.contains(candidate));
        System.out.println("authenticationPerformed=false");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 SaslSelectionDemo.java
java SaslSelectionDemo
```

Stdout quan sát trên bản JDK 21 có factory GSSAPI phù hợp:

```text
candidate=GSSAPI
approved=true
advertised=true
locallyListed=true
authenticationPerformed=false
```

Kết quả có thể khác khi provider, mô-đun hoặc thuộc tính bảo mật của runtime khác. Nếu không có ứng viên, ví dụ ném lỗi; không mở rộng sang cơ chế ngoài hồ sơ. Việc thấy GSSAPI không chứng minh máy đang có vé Kerberos hợp lệ, kết nối được tới hạ tầng hay tên dịch vụ máy chủ đã đúng.

## 8. Tạo đối tượng bằng đúng ứng viên và xử lý thất bại

Trong lớp tích hợp đã có kết nối và nguồn thông tin xác thực, có thể thực hiện bước tạo như sau:

```java
SaslClient client = Sasl.createSaslClient(
        new String[] {candidate}, authorizationId,
        protocol, serverName, properties, callbackHandler);
if (client == null) {
    throw new SaslException("Selected mechanism unavailable under current policy");
}
```

Đây là đoạn minh họa, không phải chương trình độc lập. `candidate` đã qua chính sách; các tham số còn lại phải được lớp tích hợp cung cấp. `protocol` là tên dịch vụ/giao thức theo hợp đồng cơ chế, không phải chuỗi tùy tiện. `serverName` phải là máy chủ mục tiêu phù hợp; với cơ chế gắn danh tính dịch vụ như GSSAPI, chọn sai tên có thể làm xác thực sai đích hoặc thất bại.

`callbackHandler` cung cấp thông tin mà cơ chế yêu cầu, chẳng hạn danh tính, mật khẩu hoặc realm. Không đưa cùng một bí mật vào mọi callback bất kể loại; callback không được hỗ trợ phải được xử lý rõ ràng. Máy chủ cần chính sách ánh xạ và cho phép hoạt động dưới danh tính được yêu cầu, không chỉ kiểm tra một tên người dùng có tồn tại.

Có hai kết quả lỗi cần phân biệt:

- Trả `null`: framework không tìm được factory tạo đối tượng với các tham số hiện tại.
- Ném `SaslException`: xảy ra lỗi trong quá trình tạo.

Trong cả hai trường hợp, không gửi tiếp dữ liệu nghiệp vụ như thể xác thực đã hoàn tất. Nếu đã chọn một cơ chế mà nó thất bại vì thông tin xác thực hoặc chính sách, không tự thử cơ chế khác với cùng bí mật trừ khi thiết kế giao thức và chính sách cho phép rõ ràng. Việc liệt kê nhiều ứng viên ban đầu không phải quyền hạ cấp sau một lỗi xác thực.

## 9. Thuộc tính bảo mật runtime và quản trị provider

Trong triển khai tham chiếu JDK được tài liệu hóa, cơ chế có trong security property `jdk.sasl.disabledMechanisms` bị bỏ qua khi tạo đối tượng SASL. Có thể đọc thuộc tính bảo mật bằng `Security.getProperty("jdk.sasl.disabledMechanisms")`; không nhầm với system property đọc bằng `System.getProperty()`. [API Sasl](https://docs.oracle.com/en/java/javase/25/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

Danh sách khám phá chỉ là dữ kiện ban đầu. Bước tạo mới là nơi framework/provider tiếp tục áp dụng hạn chế, nên ví dụ tìm ứng viên ở trên vẫn phải xử lý trường hợp không tạo được. Không xóa hạn chế runtime chỉ để ví dụ hoặc đối tác cũ chạy được.

Khi cần cơ chế chưa có, đánh giá provider/thư viện theo phiên bản, nguồn phát hành, cách cập nhật và hợp đồng tích hợp. Một provider có thể chạy mã xử lý thông tin xác thực trong tiến trình; việc cài đặt là một thay đổi hạ tầng có tác động rộng hơn việc thêm một tên cơ chế vào danh sách.

Không ép một tên provider cụ thể nếu không có yêu cầu triển khai rõ ràng. Cùng tên cơ chế nhưng provider khác nhau có thể khác cách cấp thông tin xác thực, channel binding và thuộc tính mở rộng. Giữ lựa chọn ấy có thể quan sát và kiểm thử thay vì phụ thuộc vô tình vào thứ tự môi trường.

## 10. Kiểm chứng sau lựa chọn

Tạo được `SaslClient` hoặc `SaslServer` mới chỉ bắt đầu cuộc trao đổi. Cần hoàn tất challenge–response, xử lý dữ liệu cuối và kết quả giao thức. Cờ hoàn tất cục bộ của client không tự chứng minh máy chủ đã chấp nhận kết nối.

Sau thành công, kiểm tra các thuộc tính thương lượng áp dụng với cơ chế. Nếu chính sách bắt buộc một lớp bảo vệ nhưng kết quả không đáp ứng, không cho chuyển tiếp sang trạng thái sử dụng nghiệp vụ. Chỉ gọi `wrap()`/`unwrap()` SASL khi cơ chế đã thương lượng lớp bảo vệ tương ứng; TLS ngoài có vòng đời và kiểm tra danh tính riêng.

Một ma trận kiểm thử phù hợp gồm:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Hai đầu có cơ chế được phê duyệt, điều kiện hạ tầng đúng | Chọn đúng ứng viên và xác thực thành công |
| Máy chủ chỉ công bố cơ chế ngoài danh sách | Từ chối trước khi gửi bí mật xác thực |
| Không có provider hoặc phía server/client tương ứng | Lỗi cấu hình rõ ràng, không tự đổi chính sách |
| Runtime cấm ứng viên đã được liệt kê | Không tạo/không sử dụng cơ chế bị cấm |
| Thông tin xác thực sai hoặc danh tính dịch vụ sai | Xác thực thất bại, không hạ cấp tự động |
| Chính sách bắt buộc channel binding nhưng không thực hiện được | Từ chối, không đổi sang biến thể không ràng buộc kênh |
| Đã cập nhật JDK/provider hoặc đổi cấu hình TLS | Chạy lại kiểm thử lựa chọn và kết quả thực tế |

Khi ghi nhật ký, ưu tiên tên cơ chế, phiên bản chính sách, thông tin runtime/provider, giai đoạn thất bại và loại lỗi. Không ghi mật khẩu, vé, access token hoặc toàn bộ token challenge–response.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Cơ chế có tên trong chuẩn nên chắc có sẵn ở JDK | Phải kiểm tra provider và cách tích hợp hiện tại |
| Provider liệt kê được nên được phép dùng | Cần chính sách, khả năng đối tác và điều kiện hạ tầng |
| Đặt `QOP=auth-conf` là mọi cơ chế sẽ mã hóa | Chỉ cơ chế hỗ trợ mới thương lượng được; phải kiểm tra kết quả |
| Bật `POLICY_NOPLAINTEXT` là đã có TLS | Bộ lọc cơ chế không tạo hoặc xác minh kênh TLS |
| Đổi tên sang biến thể PLUS là có channel binding | Phải có dữ liệu ràng buộc kênh đúng chuẩn và hỗ trợ hai đầu |
| Không tạo được thì bỏ cờ chính sách cho chạy | Giữ yêu cầu và sửa môi trường/đối tác theo quy trình |
| Danh sách máy chủ đứng đầu là lựa chọn ưu tiên của client | Ưu tiên do chính sách ứng dụng quyết định |

Bài tập: máy chủ công bố SCRAM-SHA-256-PLUS nhưng provider cục bộ chỉ có SCRAM-SHA-256. Nếu chính sách bắt buộc channel binding, kết quả là chưa có lựa chọn đáp ứng. Không tự đổi sang tên không PLUS, không tự tạo dữ liệu ràng buộc và không suy luận rằng TLS bên ngoài đã thay thế yêu cầu ấy.
